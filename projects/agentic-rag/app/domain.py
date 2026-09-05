from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class ChunkDraft:
    heading: str | None
    content: str


@dataclass(frozen=True, slots=True)
class StoredChunk:
    id: str
    document_id: str
    knowledge_base_id: str
    document_status: str
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
    claims: tuple[AnswerClaim, ...] = ()
    missing_information: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AnswerClaim:
    text: str
    source_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class User:
    id: str
    name: str
    team_ids: frozenset[str]
    global_roles: frozenset[str]


@dataclass(frozen=True, slots=True)
class KnowledgeBase:
    id: str
    name: str
    visibility: Literal["company", "team", "private"]
    owner_team_id: str | None


@dataclass(frozen=True, slots=True)
class SearchScope:
    knowledge_base_ids: frozenset[str]
    document_statuses: frozenset[str]
