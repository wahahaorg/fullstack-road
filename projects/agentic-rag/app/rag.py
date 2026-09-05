from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from app.access import AccessDirectory
from app.answering import (
    Answerer,
    ExtractiveAnswerer,
    OpenAICompatibleAnswerer,
)
from app.auth import TokenService
from app.chunking import split_markdown
from app.citations import validate_claims
from app.config import Settings
from app.context import build_evidence
from app.domain import SearchHit
from app.embeddings import HashingEmbedder, OpenAICompatibleEmbedder
from app.ingestion import IngestionWorker
from app.memory import ConversationMemoryStore
from app.objects import FileObjectStore, MinioObjectStore, ObjectStore
from app.persistence import Document, DocumentRepository, IngestionTask
from app.proposals import PublishProposalStore
from app.retrieval import HybridRetriever, RetrievalTrace
from app.schemas import (
    ChatResponse,
    ClaimResponse,
    IngestionTaskResponse,
    SourceResponse,
    UploadResponse,
)
from app.store import InMemoryVectorStore


@dataclass(slots=True)
class RagContainer:
    settings: Settings
    store: InMemoryVectorStore
    answerer: Answerer
    provider_name: str
    directory: AccessDirectory
    token_service: TokenService
    documents: DocumentRepository
    object_store: ObjectStore
    retriever: HybridRetriever
    conversation_memory: ConversationMemoryStore
    publish_proposals: PublishProposalStore

    async def create_draft(
        self,
        filename: str,
        content: bytes,
        *,
        knowledge_base_id: str,
        document_family_id: str | None = None,
        version: int = 1,
    ) -> Document:
        document_id = str(uuid4())
        object_key = (
            f"knowledge-bases/{knowledge_base_id}/documents/{document_id}/{filename}"
        )
        await self.object_store.put(object_key, content)
        try:
            return await self.documents.create_draft(
                document_id=document_id,
                knowledge_base_id=knowledge_base_id,
                title=Path(filename).stem,
                filename=filename,
                object_key=object_key,
                document_family_id=document_family_id,
                version=version,
            )
        except Exception:
            await self.object_store.delete(object_key)
            raise

    async def queue_ingestion(self, document_id: str) -> IngestionTask | None:
        return await self.documents.create_ingestion_task(document_id)

    async def run_ingestion(
        self, task_id: str, worker_id: str = "local-worker"
    ) -> IngestionTask | None:
        return await IngestionWorker(
            worker_id=worker_id,
            documents=self.documents,
            object_store=self.object_store,
            store=self.store,
        ).run(task_id)

    async def publish(self, document: Document) -> tuple[Document, list[str]] | None:
        result = await self.documents.publish(document.id, document.lock_version)
        if result is None:
            return None
        published, archived_ids = result
        await self.store.update_document_status(published.id, "published")
        for archived_id in archived_ids:
            await self.store.update_document_status(archived_id, "archived")
        return result

    async def refresh_search_index(self) -> None:
        """Rebuild the small teaching index from durable chunks.

        Chapter 7 replaces this with a persistent vector index. Until then,
        rebuilding before a query keeps API and Worker processes consistent.
        """
        await self.store.clear()
        for indexed in await self.documents.indexed_documents():
            await self.store.add_document(
                indexed.document.filename,
                indexed.chunks,
                knowledge_base_id=indexed.document.knowledge_base_id,
                document_status=indexed.document.status,
                document_id=indexed.document.id,
            )

    @staticmethod
    def upload_response(document: Document) -> UploadResponse:
        return UploadResponse(
            document_id=document.id,
            filename=document.filename,
            chunk_count=0,
            status=document.status,
            version=document.version,
            lock_version=document.lock_version,
        )

    @staticmethod
    def task_response(task: IngestionTask) -> IngestionTaskResponse:
        return IngestionTaskResponse(
            task_id=task.id,
            document_id=task.document_id,
            status=task.status,
            stage=task.stage,
            completed=task.completed,
            total=task.total,
            attempt=task.attempt,
            error_code=task.error_code,
            error_detail=task.error_detail,
        )

    async def ask(
        self, question: str, top_k: int | None, *, actor_id: str
    ) -> ChatResponse:
        actor = self.directory.get_user(actor_id)
        if actor is None:
            raise ValueError("unknown user")
        if "忽略" in question and "权限" in question:
            return ChatResponse(
                answer="我不能执行绕过权限或读取无权资料的请求。",
                refused=True,
                provider=self.provider_name,
                refusal_reason="policy_bypass_request",
                sources=[],
                retrieval_profile="hybrid-v1",
            )
        await self.refresh_search_index()
        scope = self.directory.normal_search_scope(actor)
        hits, trace = await self.retriever.retrieve(question, scope)
        if top_k is not None:
            hits = hits[:top_k]
        return await self.answer_from_hits(
            question,
            hits,
            profile=trace.profile,
            rerank_applied=trace.rerank_applied,
        )

    async def answer_from_hits(
        self,
        question: str,
        hits: list[SearchHit],
        *,
        profile: str,
        rerank_applied: bool,
    ) -> ChatResponse:
        if not hits:
            return ChatResponse(
                answer="当前知识库还没有可检索内容，请先上传文档。",
                refused=True,
                provider=self.provider_name,
                refusal_reason="no_retrieval_result",
                sources=[],
                retrieval_profile=profile,
                rerank_applied=rerank_applied,
            )

        evidence = build_evidence(hits)
        if not evidence:
            return ChatResponse(
                answer="当前可访问的知识库没有足够证据回答该问题。",
                refused=True,
                provider=self.provider_name,
                refusal_reason="insufficient_evidence",
                sources=[],
                retrieval_profile=profile,
                rerank_applied=rerank_applied,
            )
        result = await self.answerer.answer(question, evidence)
        valid, reason = validate_claims(result.claims, evidence)
        if not result.claims or not valid:
            return ChatResponse(
                answer="当前可访问的知识库没有足够证据回答该问题。",
                refused=True,
                provider=self.provider_name,
                refusal_reason=reason or "insufficient_evidence",
                sources=[],
                retrieval_profile=profile,
                rerank_applied=rerank_applied,
            )
        cited_source_ids = {
            source_id for claim in result.claims for source_id in claim.source_ids
        }
        versions: dict[str, int] = {}
        for item in evidence:
            if item.source_id not in cited_source_ids:
                continue
            document = await self.documents.get(item.hit.chunk.document_id)
            if document is not None:
                versions[document.id] = document.version
        sources = [
            SourceResponse(
                id=item.source_id,
                document_id=item.hit.chunk.document_id,
                document_version=versions[item.hit.chunk.document_id],
                knowledge_base_id=item.hit.chunk.knowledge_base_id,
                filename=item.hit.chunk.filename,
                heading=item.hit.chunk.heading,
                excerpt=item.hit.chunk.content[:500],
                score=round(item.hit.score, 6),
            )
            for item in evidence
            if item.source_id in cited_source_ids
        ]
        return ChatResponse(
            answer=result.answer,
            refused=False,
            provider=self.provider_name,
            sources=sources,
            claims=[
                ClaimResponse(text=claim.text, source_ids=list(claim.source_ids))
                for claim in result.claims
            ],
            retrieval_profile=profile,
            rerank_applied=rerank_applied,
        )

    async def debug_retrieval(
        self, question: str, *, actor_id: str, profile: str
    ) -> RetrievalTrace:
        actor = self.directory.get_user(actor_id)
        if actor is None:
            raise ValueError("unknown user")
        await self.refresh_search_index()
        _, trace = await self.retriever.retrieve(
            question, self.directory.normal_search_scope(actor), profile
        )
        return trace


def build_container(settings: Settings) -> RagContainer:
    settings.validate()
    if settings.provider == "demo":
        embedder = HashingEmbedder()
        answerer: Answerer = ExtractiveAnswerer()
    else:
        assert settings.openai_api_key
        assert settings.embedding_model
        assert settings.chat_model
        embedder = OpenAICompatibleEmbedder(
            base_url=settings.openai_base_url,
            api_key=settings.openai_api_key,
            model=settings.embedding_model,
        )
        answerer = OpenAICompatibleAnswerer(
            base_url=settings.openai_base_url,
            api_key=settings.openai_api_key,
            model=settings.chat_model,
        )
    store = InMemoryVectorStore(embedder)
    object_store: ObjectStore
    if settings.object_store == "minio":
        assert settings.minio_endpoint
        assert settings.minio_access_key
        assert settings.minio_secret_key
        object_store = MinioObjectStore(
            settings.minio_endpoint,
            settings.minio_access_key,
            settings.minio_secret_key,
            settings.minio_bucket,
        )
    else:
        object_store = FileObjectStore(settings.object_store_root)
    return RagContainer(
        settings=settings,
        store=store,
        answerer=answerer,
        provider_name=settings.provider,
        directory=AccessDirectory.from_fixture(),
        token_service=TokenService(settings),
        documents=DocumentRepository(settings.database_url),
        object_store=object_store,
        retriever=HybridRetriever(store),
        conversation_memory=ConversationMemoryStore(),
        publish_proposals=PublishProposalStore(),
    )


async def seed_fixture_documents(container: RagContainer) -> None:
    fixture_root = Path(__file__).resolve().parents[1] / "fixtures" / "documents"
    for document in container.directory.documents:
        if await container.documents.get(document.id):
            continue
        raw = (fixture_root / document.filename).read_bytes()
        text = raw.decode("utf-8")
        chunks = split_markdown(text)
        family_id = document.filename.rsplit("-v", maxsplit=1)[0]
        object_key = f"fixtures/{document.id}/{document.filename}"
        await container.object_store.put(object_key, raw)
        await container.documents.create_draft(
            document_id=document.id,
            document_family_id=family_id,
            knowledge_base_id=document.knowledge_base_id,
            title=document.title,
            filename=document.filename,
            object_key=object_key,
            status=document.status,
            version=document.version,
        )
        await container.documents.replace_chunks(document.id, chunks)
