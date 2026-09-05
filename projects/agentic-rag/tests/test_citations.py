from __future__ import annotations

from app.citations import validate_claims
from app.context import Evidence
from app.domain import AnswerClaim, SearchHit, StoredChunk


def test_claim_validator_rejects_a_number_missing_from_its_source() -> None:
    evidence = [
        Evidence(
            source_id="S1",
            hit=SearchHit(
                chunk=StoredChunk(
                    id="chunk-1",
                    document_id="document-1",
                    knowledge_base_id="kb-company",
                    document_status="published",
                    filename="policy.md",
                    heading="住宿标准",
                    content="上海住宿每晚 650 元。",
                    embedding=(1.0,),
                ),
                score=1.0,
            ),
        )
    ]

    valid, reason = validate_claims(
        (AnswerClaim(text="上海住宿每晚 850 元。", source_ids=("S1",)),), evidence
    )

    assert valid is False
    assert reason == "unsupported_number"


def test_claim_validator_rejects_source_ids_not_in_this_request() -> None:
    valid, reason = validate_claims(
        (AnswerClaim(text="任何结论", source_ids=("S9",)),), []
    )

    assert valid is False
    assert reason == "unknown_source"
