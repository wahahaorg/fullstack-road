from __future__ import annotations

import asyncio
from pathlib import Path

from app.config import Settings
from app.rag import build_container


def test_ingestion_task_and_outbox_share_a_transaction(tmp_path: Path) -> None:
    settings = Settings(
        provider="demo",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'db.sqlite'}",
        object_store_root=tmp_path / "objects",
    )
    container = build_container(settings)

    async def scenario() -> None:
        await container.documents.initialize()
        document = await container.create_draft(
            "policy.md", b"# Policy\n\n- five minutes", knowledge_base_id="kb-company"
        )
        task = await container.queue_ingestion(document.id)
        assert task is not None
        events = await container.documents.pending_outbox()
        assert len(events) == 1
        assert task.id in events[0][2]
        assert await container.documents.mark_outbox_published(events[0][0])
        assert await container.documents.pending_outbox() == []

    asyncio.run(scenario())
