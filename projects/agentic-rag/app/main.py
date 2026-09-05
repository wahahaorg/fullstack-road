from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, Request, UploadFile, status

from app.config import Settings
from app.rag import RagContainer, build_container
from app.schemas import ChatRequest, ChatResponse, HealthResponse, UploadResponse

ALLOWED_SUFFIXES = {".md", ".txt"}


def create_app(settings: Settings | None = None) -> FastAPI:
    container = build_container(settings or Settings.from_env())
    app = FastAPI(
        title="Enterprise Agentic RAG",
        version="0.1.0",
        description="第 2 章：最小可运行 RAG 闭环",
    )
    app.state.rag = container

    @app.get("/health", response_model=HealthResponse)
    async def health(request: Request) -> HealthResponse:
        rag = get_rag(request)
        return HealthResponse(
            status="ok",
            provider=rag.provider_name,
            indexed_chunks=await rag.store.count_chunks(),
        )

    @app.post(
        "/api/documents",
        response_model=UploadResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def upload_document(
        request: Request,
        file: Annotated[UploadFile, File(description="Markdown or text document")],
    ) -> UploadResponse:
        rag = get_rag(request)
        filename = file.filename or "unnamed"
        suffix = Path(filename).suffix.lower()
        if suffix not in ALLOWED_SUFFIXES:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="当前章节只支持 .md 和 .txt 文件",
            )
        raw = await file.read(rag.settings.max_upload_bytes + 1)
        if len(raw) > rag.settings.max_upload_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="文件超过当前章节的上传大小限制",
            )
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="文件必须使用 UTF-8 编码",
            ) from exc
        try:
            return await rag.upload(filename=filename, text=text)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            ) from exc

    @app.post("/api/chat", response_model=ChatResponse)
    async def chat(request: Request, payload: ChatRequest) -> ChatResponse:
        rag = get_rag(request)
        return await rag.ask(
            question=payload.question,
            top_k=payload.top_k,
        )

    return app


def get_rag(request: Request) -> RagContainer:
    return request.app.state.rag


app = create_app()
