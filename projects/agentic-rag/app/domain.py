from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ChunkDraft:
    heading: str | None
    content: str


@dataclass(frozen=True, slots=True)
class StoredChunk:
    id: str
    document_id: str
    filename: str
    heading: str | None
    content: str
    embedding: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class SearchHit:
    chunk: StoredChunk
    score: float


@dataclass(frozen=True, slots=True)
class AnswerResult:
    answer: str
    cited_chunk_ids: tuple[str, ...]
