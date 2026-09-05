from __future__ import annotations

from dataclasses import dataclass

from app.answering import (
    Answerer,
    ExtractiveAnswerer,
    OpenAICompatibleAnswerer,
)
from app.chunking import split_markdown
from app.config import Settings
from app.embeddings import HashingEmbedder, OpenAICompatibleEmbedder
from app.schemas import ChatResponse, SourceResponse, UploadResponse
from app.store import InMemoryVectorStore


@dataclass(slots=True)
class RagContainer:
    settings: Settings
    store: InMemoryVectorStore
    answerer: Answerer
    provider_name: str

    async def upload(self, filename: str, text: str) -> UploadResponse:
        chunks = split_markdown(text)
        if not chunks:
            raise ValueError("文件中没有可索引的文本")
        document_id, chunk_count = await self.store.add_document(filename, chunks)
        return UploadResponse(
            document_id=document_id,
            filename=filename,
            chunk_count=chunk_count,
        )

    async def ask(self, question: str, top_k: int | None) -> ChatResponse:
        hits = await self.store.search(
            query=question,
            top_k=top_k or self.settings.top_k,
        )
        if not hits:
            return ChatResponse(
                answer="当前知识库还没有可检索内容，请先上传文档。",
                refused=True,
                provider=self.provider_name,
                sources=[],
            )

        result = await self.answerer.answer(question, hits)
        cited_ids = set(result.cited_chunk_ids)
        sources = [
            SourceResponse(
                id=hit.chunk.id,
                document_id=hit.chunk.document_id,
                filename=hit.chunk.filename,
                heading=hit.chunk.heading,
                content=hit.chunk.content,
                score=round(hit.score, 6),
            )
            for hit in hits
            if hit.chunk.id in cited_ids
        ]
        return ChatResponse(
            answer=result.answer,
            refused=not sources,
            provider=self.provider_name,
            sources=sources,
        )


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
    return RagContainer(
        settings=settings,
        store=InMemoryVectorStore(embedder),
        answerer=answerer,
        provider_name=settings.provider,
    )
