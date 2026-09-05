from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True, slots=True)
class ConversationMemory:
    conversation_id: str
    actor_id: str
    summary: str
    updated_at: datetime


class ConversationMemoryStore:
    """Bounded per-process memory; durable checkpoints arrive with run persistence."""

    def __init__(self) -> None:
        self._items: dict[str, ConversationMemory] = {}

    def get(self, conversation_id: str, actor_id: str) -> ConversationMemory | None:
        item = self._items.get(conversation_id)
        return item if item and item.actor_id == actor_id else None

    def save(
        self, conversation_id: str, actor_id: str, summary: str
    ) -> ConversationMemory:
        item = ConversationMemory(
            conversation_id=conversation_id,
            actor_id=actor_id,
            summary=summary[:500],
            updated_at=datetime.now(UTC),
        )
        self._items[conversation_id] = item
        return item
