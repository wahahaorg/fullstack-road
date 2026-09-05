from __future__ import annotations

import re

from app.context import Evidence
from app.domain import AnswerClaim


def validate_claims(
    claims: tuple[AnswerClaim, ...], evidence: list[Evidence]
) -> tuple[bool, str | None]:
    evidence_by_id = {item.source_id: item for item in evidence}
    for claim in claims:
        if not claim.source_ids:
            return False, "claim_without_source"
        sources = [evidence_by_id.get(source_id) for source_id in claim.source_ids]
        if any(source is None for source in sources):
            return False, "unknown_source"
        source_text = "\n".join(
            source.hit.chunk.content for source in sources if source
        )
        if set(_numbers(claim.text)) - set(_numbers(source_text)):
            return False, "unsupported_number"
    return True, None


def _numbers(text: str) -> list[str]:
    return re.findall(r"\d+(?:\.\d+)?", text)
