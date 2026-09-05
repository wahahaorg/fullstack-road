from __future__ import annotations

import asyncio
from uuid import uuid4

from app.domain import ChunkDraft, SearchHit, StoredChunk
from app.embeddings import Embedder


class InMemoryVectorStore:
    def __init__(self, embedder: Embedder) -> None:
        self.embedder = embedder
        self._chunks: list[StoredChunk] = []
        self._lock = asyncio.Lock()

    async def add_document(
        self, filename: str, chunks: list[ChunkDraft]
    ) -> tuple[str, int]:
        document_id = str(uuid4())
        vectors = await self.embedder.embed([chunk.content for chunk in chunks])
        stored = [
            StoredChunk(
                id=f"{document_id}:chunk-{index}",
                document_id=document_id,
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

    async def search(self, query: str, top_k: int) -> list[SearchHit]:
        query_vector = (await self.embedder.embed([query]))[0]
        async with self._lock:
            chunks = list(self._chunks)
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

    async def count_chunks(self) -> int:
        async with self._lock:
            return len(self._chunks)
