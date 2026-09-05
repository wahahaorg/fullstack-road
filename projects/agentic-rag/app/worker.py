from __future__ import annotations

import argparse
import asyncio

from app.config import Settings
from app.rag import build_container


async def run_once(task_id: str | None) -> int:
    container = build_container(Settings.from_env())
    await container.documents.initialize()
    task = (
        await container.documents.get_ingestion_task(task_id)
        if task_id
        else await container.documents.next_queued_ingestion_task()
    )
    if task is None:
        return 0
    result = await container.run_ingestion(task.id, worker_id="cli-worker")
    return 0 if result and result.status == "succeeded" else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one Agentic RAG ingestion task")
    parser.add_argument("task_id", nargs="?")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run_once(args.task_id)))


if __name__ == "__main__":
    main()
