from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class PublishProposal:
    id: str
    document_id: str
    actor_id: str
    expected_lock_version: int
    expires_at: datetime
    status: str = "pending"


class PublishProposalStore:
    """A bounded teaching-store for explicit human approval of document publishing."""

    def __init__(self) -> None:
        self._items: dict[str, PublishProposal] = {}

    def create(
        self, *, document_id: str, actor_id: str, expected_lock_version: int
    ) -> PublishProposal:
        proposal = PublishProposal(
            id=str(uuid4()),
            document_id=document_id,
            actor_id=actor_id,
            expected_lock_version=expected_lock_version,
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
        )
        self._items[proposal.id] = proposal
        return proposal

    def decide(
        self, proposal_id: str, actor_id: str, approved: bool
    ) -> PublishProposal | None:
        proposal = self._items.get(proposal_id)
        if (
            proposal is None
            or proposal.actor_id != actor_id
            or proposal.status != "pending"
            or proposal.expires_at <= datetime.now(UTC)
        ):
            return None
        decided = replace(proposal, status="approved" if approved else "rejected")
        self._items[proposal_id] = decided
        return decided
