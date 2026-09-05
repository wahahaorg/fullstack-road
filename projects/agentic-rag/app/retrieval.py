from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from app.domain import SearchHit, SearchScope
from app.embeddings import tokenize
from app.store import InMemoryVectorStore


@dataclass(frozen=True, slots=True)
class RetrievalProfile:
    name: str
    vector_top_k: int
    keyword_top_k: int
    fused_top_k: int
    rerank_top_k: int
    context_top_k: int
    rrf_k: int = 60


PROFILES = {
    "vector-only": RetrievalProfile("vector-only", 10, 0, 10, 0, 5),
    "hybrid-v1": RetrievalProfile("hybrid-v1", 20, 20, 20, 10, 5),
}


@dataclass(frozen=True, slots=True)
class RankedChunk:
    hit: SearchHit
    vector_rank: int | None
    keyword_rank: int | None
    rrf_score: float


@dataclass(frozen=True, slots=True)
class RetrievalTrace:
    profile: str
    vector: tuple[RankedChunk, ...]
    keyword: tuple[RankedChunk, ...]
    rrf: tuple[RankedChunk, ...]
    rerank: tuple[RankedChunk, ...]
    rerank_applied: bool


class HybridRetriever:
    def __init__(self, store: InMemoryVectorStore) -> None:
        self._store = store

    async def retrieve(
        self, query: str, scope: SearchScope, profile_name: str = "hybrid-v1"
    ) -> tuple[list[SearchHit], RetrievalTrace]:
        profile = PROFILES.get(profile_name)
        if profile is None:
            raise ValueError(f"unknown retrieval profile: {profile_name}")
        vector_hits = await self._store.search(
            query,
            profile.vector_top_k,
            allowed_knowledge_base_ids=scope.knowledge_base_ids,
            allowed_document_statuses=scope.document_statuses,
        )
        keyword_hits = (
            await self._store.keyword_search(
                query,
                profile.keyword_top_k,
                allowed_knowledge_base_ids=scope.knowledge_base_ids,
                allowed_document_statuses=scope.document_statuses,
            )
            if profile.keyword_top_k
            else []
        )
        fused = self._fuse(vector_hits, keyword_hits, profile.rrf_k)
        fused = fused[: profile.fused_top_k]
        reranked = self._rerank(query, fused)[: profile.rerank_top_k]
        final = reranked if profile.rerank_top_k else fused[: profile.context_top_k]
        trace = RetrievalTrace(
            profile=profile.name,
            vector=tuple(self._with_rank(vector_hits, "vector")),
            keyword=tuple(self._with_rank(keyword_hits, "keyword")),
            rrf=tuple(fused),
            rerank=tuple(reranked),
            rerank_applied=bool(profile.rerank_top_k),
        )
        return [entry.hit for entry in final[: profile.context_top_k]], trace

    @staticmethod
    def _with_rank(hits: list[SearchHit], kind: str) -> list[RankedChunk]:
        return [
            RankedChunk(
                hit=hit,
                vector_rank=rank if kind == "vector" else None,
                keyword_rank=rank if kind == "keyword" else None,
                rrf_score=0.0,
            )
            for rank, hit in enumerate(hits, start=1)
        ]

    @staticmethod
    def _fuse(
        vector_hits: list[SearchHit], keyword_hits: list[SearchHit], rrf_k: int
    ) -> list[RankedChunk]:
        scores: dict[str, float] = defaultdict(float)
        hits: dict[str, SearchHit] = {}
        vector_ranks: dict[str, int] = {}
        keyword_ranks: dict[str, int] = {}
        for rank, hit in enumerate(vector_hits, start=1):
            scores[hit.chunk.id] += 1 / (rrf_k + rank)
            hits[hit.chunk.id] = hit
            vector_ranks[hit.chunk.id] = rank
        for rank, hit in enumerate(keyword_hits, start=1):
            scores[hit.chunk.id] += 1 / (rrf_k + rank)
            hits[hit.chunk.id] = hit
            keyword_ranks[hit.chunk.id] = rank
        return sorted(
            (
                RankedChunk(
                    hit=hits[chunk_id],
                    vector_rank=vector_ranks.get(chunk_id),
                    keyword_rank=keyword_ranks.get(chunk_id),
                    rrf_score=score,
                )
                for chunk_id, score in scores.items()
            ),
            key=lambda item: item.rrf_score,
            reverse=True,
        )

    @staticmethod
    def _rerank(query: str, candidates: list[RankedChunk]) -> list[RankedChunk]:
        query_terms = set(tokenize(query))
        return sorted(
            candidates,
            key=lambda item: (
                len(query_terms.intersection(tokenize(item.hit.chunk.content))),
                item.rrf_score,
            ),
            reverse=True,
        )
