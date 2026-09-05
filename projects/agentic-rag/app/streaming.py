from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.rag import RagContainer
from app.routing import classify_route


@dataclass(frozen=True, slots=True)
class StreamEvent:
    id: int
    type: str
    run_id: str
    payload: dict[str, Any]
    schema_version: str = "1"

    def encode(self) -> str:
        data = {
            "id": self.id,
            "type": self.type,
            "run_id": self.run_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "schema_version": self.schema_version,
            "payload": self.payload,
        }
        serialized = json.dumps(data, ensure_ascii=False)
        return f"id: {self.id}\nevent: {self.type}\ndata: {serialized}\n\n"


async def stream_chat(
    rag: RagContainer, question: str, actor_id: str, top_k: int | None = None
) -> AsyncIterator[str]:
    run_id = str(uuid4())
    sequence = 0

    def event(event_type: str, payload: dict[str, Any]) -> str:
        nonlocal sequence
        sequence += 1
        return StreamEvent(sequence, event_type, run_id, payload).encode()

    decision = classify_route(
        question,
        is_knowledge_admin=(
            (actor := rag.directory.get_user(actor_id)) is not None
            and "knowledge_admin" in actor.global_roles
        ),
    )
    yield event("run.started", {"route": decision.route})
    if decision.route == "refuse":
        yield event("run.failed", {"code": "request_refused", "message": "请求被拒绝"})
        return
    yield event("node.started", {"node": "retrieve"})
    response = await rag.ask(question, top_k, actor_id=actor_id)
    yield event(
        "node.completed", {"node": "retrieve", "source_count": len(response.sources)}
    )
    if response.refused:
        yield event(
            "run.failed",
            {
                "code": response.refusal_reason or "insufficient_evidence",
                "message": response.answer,
            },
        )
        return
    yield event("answer.delta", {"text": response.answer})
    for source in response.sources:
        yield event(
            "citation",
            {"source_id": source.id, "document_id": source.document_id},
        )
    yield event("run.completed", {"finish_reason": "success"})
