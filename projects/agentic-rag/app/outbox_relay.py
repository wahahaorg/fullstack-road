from __future__ import annotations

import asyncio

from app.config import Settings
from app.rag import build_container


async def relay_once() -> int:
    container = build_container(Settings.from_env())
    await container.documents.initialize()
    events = await container.documents.pending_outbox()
    published = 0
    for event_id, _, _ in events:
        if await container.documents.mark_outbox_published(event_id):
            published += 1
    return published


if __name__ == "__main__":
    print(asyncio.run(relay_once()))
