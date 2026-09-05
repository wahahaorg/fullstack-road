from __future__ import annotations

from dataclasses import dataclass

from app.objects import ObjectStore
from app.parsing import parse_document
from app.persistence import DocumentRepository, IngestionTask
from app.store import InMemoryVectorStore


@dataclass(slots=True)
class IngestionWorker:
    worker_id: str
    documents: DocumentRepository
    object_store: ObjectStore
    store: InMemoryVectorStore

    async def run(self, task_id: str) -> IngestionTask | None:
        task = await self.documents.claim_ingestion_task(task_id, self.worker_id)
        if task is None:
            return None
        document = await self.documents.get(task.document_id)
        if document is None:
            return await self.documents.fail_ingestion_task(
                task.id, "document_not_found", "document record is unavailable"
            )
        try:
            await self.documents.report_ingestion_progress(task.id, "download", 0, 1)
            raw = await self.object_store.get(document.object_key)
        except Exception as exc:
            return await self.documents.fail_ingestion_task(
                task.id, "object_read_error", type(exc).__name__
            )
        try:
            await self.documents.report_ingestion_progress(task.id, "parse", 0, 1)
            chunks = parse_document(document.filename, raw)
        except Exception as exc:
            return await self.documents.fail_ingestion_task(
                task.id, "parse_error", type(exc).__name__
            )
        if not chunks:
            return await self.documents.fail_ingestion_task(
                task.id, "empty_document", "document contains no indexable text"
            )
        try:
            if await self._cancelled(task.id):
                return await self.documents.get_ingestion_task(task.id)
            await self.documents.report_ingestion_progress(
                task.id, "embedding", 0, len(chunks)
            )
            await self.documents.replace_chunks(document.id, chunks)
            # The API process uses an in-memory ranking cache in this chapter.
            # Persisted chunks remain the cross-process source of truth.
            await self.store.discard_document(document.id)
            await self.store.add_document(
                document.filename,
                chunks,
                knowledge_base_id=document.knowledge_base_id,
                document_status="processing",
                document_id=document.id,
            )
            await self.documents.report_ingestion_progress(
                task.id, "indexing", len(chunks), len(chunks)
            )
            if await self._cancelled(task.id):
                await self.documents.discard_chunks(document.id)
                await self.store.discard_document(document.id)
                return await self.documents.get_ingestion_task(task.id)
            completed = await self.documents.complete_ingestion_task(task.id)
            if completed is not None:
                await self.store.update_document_status(document.id, "review_pending")
            return completed
        except Exception as exc:
            return await self.documents.fail_ingestion_task(
                task.id, "internal_error", type(exc).__name__
            )

    async def _cancelled(self, task_id: str) -> bool:
        task = await self.documents.get_ingestion_task(task_id)
        return task is None or task.status == "cancelled"
