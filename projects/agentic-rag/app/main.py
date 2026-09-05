from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.agent_graph import run_agentic_rag
from app.config import Settings
from app.domain import User
from app.lifecycle import can_publish
from app.parsing import SUPPORTED_SUFFIXES
from app.rag import RagContainer, build_container, seed_fixture_documents
from app.routing import classify_route
from app.schemas import (
    ChatRequest,
    ChatResponse,
    ConversationMemoryResponse,
    DevTokenRequest,
    DevTokenResponse,
    DocumentVersionResponse,
    HealthResponse,
    IngestionTaskResponse,
    KnowledgeBaseResponse,
    PublishDecisionRequest,
    PublishProposalResponse,
    ReadinessResponse,
    RetrievalDebugRequest,
    RetrievalDebugResponse,
    RetrievalDebugStage,
    RoutingDebugResponse,
    UploadResponse,
)
from app.streaming import stream_chat
from app.tools import read_document_version

bearer = HTTPBearer(auto_error=False)


def get_rag(request: Request) -> RagContainer:
    return request.app.state.rag


def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> User:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing access token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    rag = get_rag(request)
    user_id = rag.token_service.decode_subject(credentials.credentials)
    user = rag.directory.get_user(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid access token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def create_app(settings: Settings | None = None) -> FastAPI:
    container = build_container(settings or Settings.from_env())

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await container.documents.initialize()
        if container.settings.seed_fixtures:
            await seed_fixture_documents(container)
        yield

    app = FastAPI(
        title="Enterprise Agentic RAG",
        version="0.16.0",
        description="第 16 章：可运行的企业 Agentic RAG 本地项目",
        lifespan=lifespan,
    )
    app.state.rag = container

    @app.get("/health", response_model=HealthResponse)
    async def health(request: Request) -> HealthResponse:
        rag = get_rag(request)
        await rag.refresh_search_index()
        return HealthResponse(
            status="ok",
            provider=rag.provider_name,
            indexed_chunks=await rag.store.count_chunks(),
        )

    @app.get("/health/live")
    async def health_live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready", response_model=ReadinessResponse)
    async def health_ready(request: Request) -> ReadinessResponse:
        rag = get_rag(request)
        try:
            await rag.documents.initialize()
            await rag.documents.get_ingestion_task("readiness-probe")
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="database unavailable",
            ) from exc
        return ReadinessResponse(
            status="ready", provider=rag.provider_name, database="ok"
        )

    @app.post(
        "/api/documents",
        response_model=UploadResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def upload_document(
        request: Request,
        file: Annotated[UploadFile, File(description="Markdown or text document")],
        knowledge_base_id: Annotated[str, Form()],
        current_user: Annotated[User, Depends(get_current_user)],
        document_family_id: Annotated[str | None, Form()] = None,
        version: Annotated[int, Form(ge=1)] = 1,
    ) -> UploadResponse:
        rag = get_rag(request)
        if rag.directory.get_knowledge_base(knowledge_base_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="not found"
            )
        if not rag.directory.can_write(current_user, knowledge_base_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="forbidden"
            )
        filename = file.filename or "unnamed"
        suffix = Path(filename).suffix.lower()
        if suffix not in SUPPORTED_SUFFIXES:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="仅支持 Markdown、文本、PDF、Word、PPT 和 Excel 文件",
            )
        raw = await file.read(rag.settings.max_upload_bytes + 1)
        if len(raw) > rag.settings.max_upload_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="文件超过当前章节的上传大小限制",
            )
        if not raw.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="文件中没有可索引的文本",
            )
        try:
            document = await rag.create_draft(
                filename=filename,
                content=raw,
                knowledge_base_id=knowledge_base_id,
                document_family_id=document_family_id,
                version=version,
            )
            return rag.upload_response(document)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            ) from exc

    @app.post("/api/chat", response_model=ChatResponse)
    async def chat(
        request: Request,
        payload: ChatRequest,
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> ChatResponse:
        rag = get_rag(request)
        decision = classify_route(
            payload.question,
            is_knowledge_admin="knowledge_admin" in current_user.global_roles,
        )
        if decision.route == "direct":
            response = ChatResponse(
                answer="我可以基于你有权限访问的企业文档回答问题，并给出来源。",
                refused=False,
                provider=rag.provider_name,
                sources=[],
                route=decision.route,
                intent=decision.intent,
                route_reason=decision.reason,
            )
        elif decision.route == "refuse":
            response = ChatResponse(
                answer="我不能执行该请求。",
                refused=True,
                provider=rag.provider_name,
                refusal_reason=decision.reason,
                sources=[],
                route=decision.route,
                intent=decision.intent,
                route_reason=decision.reason,
            )
        elif decision.route == "agentic_rag":
            response = await run_agentic_rag(
                rag,
                payload.question,
                current_user.id,
            )
        else:
            answer = await rag.ask(
                question=payload.question,
                top_k=payload.top_k,
                actor_id=current_user.id,
            )
            if decision.route in {"summary", "version_tool"}:
                response = answer.model_copy(
                    update={
                        "route": decision.route,
                        "intent": decision.intent,
                        "route_reason": (
                            f"{decision.reason}; use the dedicated "
                            "version tool endpoint"
                        ),
                        "route_degraded": True,
                    }
                )
            else:
                response = answer.model_copy(
                    update={
                        "route": decision.route,
                        "intent": decision.intent,
                        "route_reason": decision.reason,
                    }
                )
        if payload.conversation_id:
            rag.conversation_memory.save(
                payload.conversation_id, current_user.id, response.answer
            )
        return response

    @app.post("/api/chat/stream")
    async def chat_stream(
        request: Request,
        payload: ChatRequest,
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> StreamingResponse:
        rag = get_rag(request)
        return StreamingResponse(
            stream_chat(rag, payload.question, current_user.id, payload.top_k),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get(
        "/api/conversations/{conversation_id}/memory",
        response_model=ConversationMemoryResponse,
    )
    async def get_conversation_memory(
        request: Request,
        conversation_id: str,
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> ConversationMemoryResponse:
        memory = get_rag(request).conversation_memory.get(
            conversation_id, current_user.id
        )
        if memory is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="not found"
            )
        return ConversationMemoryResponse(
            conversation_id=memory.conversation_id,
            summary=memory.summary,
            updated_at=memory.updated_at.isoformat(),
        )

    @app.get(
        "/api/tools/document-versions/{document_id}",
        response_model=DocumentVersionResponse,
    )
    async def get_document_version(
        request: Request,
        document_id: str,
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> DocumentVersionResponse:
        version = await read_document_version(
            get_rag(request), current_user, document_id
        )
        if version is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="not found"
            )
        return DocumentVersionResponse(
            document_id=version.document_id,
            version=version.version,
            title=version.title,
            filename=version.filename,
            status=version.status,
            content=version.content,
        )

    @app.post("/api/routing/debug", response_model=RoutingDebugResponse)
    async def routing_debug(
        payload: ChatRequest,
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> RoutingDebugResponse:
        if "knowledge_admin" not in current_user.global_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="forbidden"
            )
        decision = classify_route(
            payload.question,
            is_knowledge_admin=True,
        )
        return RoutingDebugResponse(
            route=decision.route,
            intent=decision.intent,
            reason=decision.reason,
            degraded=decision.degraded,
        )

    @app.post("/api/retrieval/debug", response_model=RetrievalDebugResponse)
    async def retrieval_debug(
        request: Request,
        payload: RetrievalDebugRequest,
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> RetrievalDebugResponse:
        if "knowledge_admin" not in current_user.global_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="forbidden"
            )
        try:
            trace = await get_rag(request).debug_retrieval(
                payload.question, actor_id=current_user.id, profile=payload.profile
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
            ) from exc

        def stage(items: tuple, *, rrf: bool = False) -> list[RetrievalDebugStage]:
            return [
                RetrievalDebugStage(
                    chunk_id=item.hit.chunk.id,
                    rank=rank,
                    score=round(item.rrf_score if rrf else item.hit.score, 6),
                )
                for rank, item in enumerate(items, start=1)
            ]

        return RetrievalDebugResponse(
            profile=trace.profile,
            vector=stage(trace.vector),
            keyword=stage(trace.keyword),
            rrf=stage(trace.rrf, rrf=True),
            rerank=stage(trace.rerank, rrf=True),
            rerank_applied=trace.rerank_applied,
        )

    @app.post(
        "/api/documents/{document_id}/submit",
        response_model=IngestionTaskResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def submit_document(
        request: Request,
        document_id: str,
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> IngestionTaskResponse:
        rag = get_rag(request)
        document = await rag.documents.get(document_id)
        if document is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="not found"
            )
        if not rag.directory.can_write(current_user, document.knowledge_base_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="forbidden"
            )
        task = await rag.queue_ingestion(document.id)
        if task is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="conflict")
        return rag.task_response(task)

    @app.get("/api/documents/{document_id}", response_model=UploadResponse)
    async def get_document(
        request: Request,
        document_id: str,
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> UploadResponse:
        rag = get_rag(request)
        document = await rag.documents.get(document_id)
        knowledge_base = (
            rag.directory.get_knowledge_base(document.knowledge_base_id)
            if document is not None
            else None
        )
        if knowledge_base is None or not rag.directory.can_read(
            current_user, knowledge_base
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="not found"
            )
        return rag.upload_response(document)

    @app.get("/api/ingestion-tasks/{task_id}", response_model=IngestionTaskResponse)
    async def get_ingestion_task(
        request: Request,
        task_id: str,
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> IngestionTaskResponse:
        rag = get_rag(request)
        task = await rag.documents.get_ingestion_task(task_id)
        if task is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="not found"
            )
        document = await rag.documents.get(task.document_id)
        knowledge_base = (
            rag.directory.get_knowledge_base(document.knowledge_base_id)
            if document is not None
            else None
        )
        if knowledge_base is None or not rag.directory.can_read(
            current_user, knowledge_base
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="not found"
            )
        return rag.task_response(task)

    @app.delete("/api/ingestion-tasks/{task_id}", response_model=IngestionTaskResponse)
    async def cancel_ingestion_task(
        request: Request,
        task_id: str,
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> IngestionTaskResponse:
        rag = get_rag(request)
        task = await rag.documents.get_ingestion_task(task_id)
        if task is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="not found"
            )
        document = await rag.documents.get(task.document_id)
        if document is None or not rag.directory.can_write(
            current_user, document.knowledge_base_id
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="forbidden"
            )
        cancelled = await rag.documents.request_ingestion_cancel(task.id)
        if cancelled is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="conflict")
        return rag.task_response(cancelled)

    @app.post(
        "/api/ingestion-tasks/{task_id}/retry", response_model=IngestionTaskResponse
    )
    async def retry_ingestion_task(
        request: Request,
        task_id: str,
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> IngestionTaskResponse:
        rag = get_rag(request)
        task = await rag.documents.get_ingestion_task(task_id)
        if task is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="not found"
            )
        document = await rag.documents.get(task.document_id)
        if document is None or not rag.directory.can_write(
            current_user, document.knowledge_base_id
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="forbidden"
            )
        retried = await rag.documents.retry_ingestion_task(task.id)
        if retried is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="conflict")
        return rag.task_response(retried)

    @app.post("/api/documents/{document_id}/publish", response_model=UploadResponse)
    async def publish_document(
        request: Request,
        document_id: str,
        if_match: Annotated[int, Header(alias="If-Match")],
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> UploadResponse:
        rag = get_rag(request)
        document = await rag.documents.get(document_id)
        if document is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="not found"
            )
        if not can_publish(current_user) or not rag.directory.can_write(
            current_user, document.knowledge_base_id
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="forbidden"
            )
        if document.lock_version != if_match:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="conflict")
        result = await rag.publish(document)
        if result is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="conflict")
        published, _ = result
        return rag.upload_response(published)

    @app.post(
        "/api/documents/{document_id}/publish-proposals",
        response_model=PublishProposalResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_publish_proposal(
        request: Request,
        document_id: str,
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> PublishProposalResponse:
        rag = get_rag(request)
        document = await rag.documents.get(document_id)
        if document is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="not found"
            )
        if not can_publish(current_user) or not rag.directory.can_write(
            current_user, document.knowledge_base_id
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="forbidden"
            )
        proposal = rag.publish_proposals.create(
            document_id=document.id,
            actor_id=current_user.id,
            expected_lock_version=document.lock_version,
        )
        return PublishProposalResponse(
            proposal_id=proposal.id,
            document_id=proposal.document_id,
            expected_lock_version=proposal.expected_lock_version,
            status=proposal.status,
            expires_at=proposal.expires_at.isoformat(),
        )

    @app.post(
        "/api/publish-proposals/{proposal_id}/decisions",
        response_model=UploadResponse | PublishProposalResponse,
    )
    async def decide_publish_proposal(
        request: Request,
        proposal_id: str,
        payload: PublishDecisionRequest,
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> UploadResponse | PublishProposalResponse:
        rag = get_rag(request)
        proposal = rag.publish_proposals.decide(
            proposal_id, current_user.id, payload.approved
        )
        if proposal is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="conflict")
        if proposal.status != "approved":
            return PublishProposalResponse(
                proposal_id=proposal.id,
                document_id=proposal.document_id,
                expected_lock_version=proposal.expected_lock_version,
                status=proposal.status,
                expires_at=proposal.expires_at.isoformat(),
            )
        document = await rag.documents.get(proposal.document_id)
        if (
            document is None
            or not can_publish(current_user)
            or not rag.directory.can_write(current_user, document.knowledge_base_id)
            or document.lock_version != proposal.expected_lock_version
        ):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="conflict")
        result = await rag.publish(document)
        if result is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="conflict")
        published, _ = result
        return rag.upload_response(published)

    @app.post("/api/auth/dev-token", response_model=DevTokenResponse)
    async def dev_token(request: Request, payload: DevTokenRequest) -> DevTokenResponse:
        rag = get_rag(request)
        if not rag.settings.enable_dev_tokens:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="not found"
            )
        if rag.directory.get_user(payload.user_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="not found"
            )
        return DevTokenResponse(access_token=rag.token_service.issue(payload.user_id))

    @app.get("/api/knowledge-bases", response_model=list[KnowledgeBaseResponse])
    async def list_knowledge_bases(
        request: Request,
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> list[KnowledgeBaseResponse]:
        rag = get_rag(request)
        return [
            KnowledgeBaseResponse(
                id=knowledge_base.id,
                name=knowledge_base.name,
                visibility=knowledge_base.visibility,
            )
            for knowledge_base in rag.directory.readable_knowledge_bases(current_user)
        ]

    return app


app = create_app()
