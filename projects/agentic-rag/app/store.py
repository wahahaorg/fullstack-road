from __future__ import annotations

import asyncio
from uuid import uuid4

from app.domain import ChunkDraft, SearchHit, StoredChunk
from app.embeddings import Embedder, tokenize


class InMemoryVectorStore:
    def __init__(self, embedder: Embedder) -> None:
        self.embedder = embedder
        self._chunks: list[StoredChunk] = []
        self._lock = asyncio.Lock()

    async def add_document(
        self,
        filename: str,
        chunks: list[ChunkDraft],
        *,
        knowledge_base_id: str,
        document_status: str = "published",
        document_id: str | None = None,
    ) -> tuple[str, int]:
        document_id = document_id or str(uuid4())
        vectors = await self.embedder.embed([chunk.content for chunk in chunks])
        stored = [
            StoredChunk(
                id=f"{document_id}:chunk-{index}",
                document_id=document_id,
                knowledge_base_id=knowledge_base_id,
                document_status=document_status,
                filename=filename,
                heading=chunk.heading,
                content=chunk.content,
                embedding=tuple(vector),
            )
            for index, (chunk, vector) in enumerate(
                zip(chunks, vectors, strict=True), start=1
            )
        ]
        async with self._lock:
            self._chunks.extend(stored)
        return document_id, len(stored)

    async def search(
        self,
        query: str,
        top_k: int,
        *,
        allowed_knowledge_base_ids: frozenset[str],
        allowed_document_statuses: frozenset[str],
    ) -> list[SearchHit]:
        query_vector = (await self.embedder.embed([query]))[0]
        async with self._lock:
            chunks = [
                chunk
                for chunk in self._chunks
                if chunk.knowledge_base_id in allowed_knowledge_base_ids
                and chunk.document_status in allowed_document_statuses
            ]
        hits = [
            SearchHit(
                chunk=chunk,
                score=sum(
                    left * right
                    for left, right in zip(query_vector, chunk.embedding, strict=True)
                ),
            )
            for chunk in chunks
        ]
        hits.sort(key=lambda hit: hit.score, reverse=True)
        return hits[:top_k]

    async def keyword_search(
        self,
        query: str,
        top_k: int,
        *,
        allowed_knowledge_base_ids: frozenset[str],
        allowed_document_statuses: frozenset[str],
    ) -> list[SearchHit]:
        query_terms = set(tokenize(query))
        if not query_terms:
            return []
        async with self._lock:
            chunks = [
                chunk
                for chunk in self._chunks
                if chunk.knowledge_base_id in allowed_knowledge_base_ids
                and chunk.document_status in allowed_document_statuses
            ]
        hits = [
            SearchHit(
                chunk=chunk,
                score=len(query_terms.intersection(tokenize(chunk.content)))
                / len(query_terms),
            )
            for chunk in chunks
        ]
        hits = [hit for hit in hits if hit.score > 0]
        hits.sort(key=lambda hit: hit.score, reverse=True)
        return hits[:top_k]

    async def count_chunks(self) -> int:
        async with self._lock:
            return len(self._chunks)

    async def clear(self) -> None:
        async with self._lock:
            self._chunks = []

    async def update_document_status(self, document_id: str, status: str) -> None:
        async with self._lock:
            self._chunks = [
                chunk
                if chunk.document_id != document_id
                else StoredChunk(
                    id=chunk.id,
                    document_id=chunk.document_id,
                    knowledge_base_id=chunk.knowledge_base_id,
                    document_status=status,
                    filename=chunk.filename,
                    heading=chunk.heading,
                    content=chunk.content,
                    embedding=chunk.embedding,
                )
                for chunk in self._chunks
            ]

    async def discard_document(self, document_id: str) -> None:
        async with self._lock:
            self._chunks = [
                chunk for chunk in self._chunks if chunk.document_id != document_id
            ]
