from __future__ import annotations

from dataclasses import dataclass

from app.domain import SearchHit


@dataclass(frozen=True, slots=True)
class Evidence:
    source_id: str
    hit: SearchHit


def build_evidence(
    hits: list[SearchHit], *, char_budget: int = 4_000, max_per_document: int = 2
) -> list[Evidence]:
    """Select stable, bounded evidence before assigning prompt source IDs."""
    selected: list[Evidence] = []
    seen_content: set[str] = set()
    document_counts: dict[str, int] = {}
    used_chars = 0
    for hit in hits:
        chunk = hit.chunk
        if chunk.content in seen_content:
            continue
        count = document_counts.get(chunk.document_id, 0)
        if count >= max_per_document:
            continue
        if selected and used_chars + len(chunk.content) > char_budget:
            continue
        selected.append(Evidence(source_id=f"S{len(selected) + 1}", hit=hit))
        seen_content.add(chunk.content)
        document_counts[chunk.document_id] = count + 1
        used_chars += len(chunk.content)
    return selected
