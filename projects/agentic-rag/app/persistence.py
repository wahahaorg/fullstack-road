from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, Integer, String, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.domain import ChunkDraft


class Base(DeclarativeBase):
    pass


class DocumentRow(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_family_id: Mapped[str] = mapped_column(String(36), index=True)
    knowledge_base_id: Mapped[str] = mapped_column(String(100), index=True)
    title: Mapped[str] = mapped_column(String(500))
    filename: Mapped[str] = mapped_column(String(500))
    object_key: Mapped[str] = mapped_column(String(1024), unique=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    version: Mapped[int] = mapped_column(Integer)
    lock_version: Mapped[int] = mapped_column(Integer, default=1)


class IngestionTaskRow(Base):
    __tablename__ = "ingestion_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_id: Mapped[str] = mapped_column(String(36), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    completed: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(String(500), nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OutboxEventRow(Base):
    __tablename__ = "outbox_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    aggregate_id: Mapped[str] = mapped_column(String(36), index=True)
    event_type: Mapped[str] = mapped_column(String(100))
    payload: Mapped[str] = mapped_column(String)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ChunkRow(Base):
    __tablename__ = "document_chunks"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    document_id: Mapped[str] = mapped_column(String(36), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    heading: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content: Mapped[str] = mapped_column(String)


@dataclass(frozen=True, slots=True)
class Document:
    id: str
    document_family_id: str
    knowledge_base_id: str
    title: str
    filename: str
    object_key: str
    status: str
    version: int
    lock_version: int

    @classmethod
    def from_row(cls, row: DocumentRow) -> Document:
        return cls(
            id=row.id,
            document_family_id=row.document_family_id,
            knowledge_base_id=row.knowledge_base_id,
            title=row.title,
            filename=row.filename,
            object_key=row.object_key,
            status=row.status,
            version=row.version,
            lock_version=row.lock_version,
        )


@dataclass(frozen=True, slots=True)
class IngestionTask:
    id: str
    document_id: str
    status: str
    stage: str | None
    completed: int
    total: int
    attempt: int
    error_code: str | None
    error_detail: str | None

    @classmethod
    def from_row(cls, row: IngestionTaskRow) -> IngestionTask:
        return cls(
            id=row.id,
            document_id=row.document_id,
            status=row.status,
            stage=row.stage,
            completed=row.completed,
            total=row.total,
            attempt=row.attempt,
            error_code=row.error_code,
            error_detail=row.error_detail,
        )


@dataclass(frozen=True, slots=True)
class IndexedDocument:
    document: Document
    chunks: list[ChunkDraft]


class DocumentRepository:
    def __init__(self, database_url: str) -> None:
        self._engine = create_async_engine(database_url)
        self._sessions = async_sessionmaker(self._engine, expire_on_commit=False)

    async def initialize(self) -> None:
        async with self._engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def get(self, document_id: str) -> Document | None:
        async with self._sessions() as session:
            row = await session.get(DocumentRow, document_id)
            return Document.from_row(row) if row else None

    async def create_draft(
        self,
        *,
        knowledge_base_id: str,
        title: str,
        filename: str,
        object_key: str,
        document_family_id: str | None = None,
        version: int = 1,
        document_id: str | None = None,
        status: str = "draft",
    ) -> Document:
        row = DocumentRow(
            id=document_id or str(uuid4()),
            document_family_id=document_family_id or str(uuid4()),
            knowledge_base_id=knowledge_base_id,
            title=title,
            filename=filename,
            object_key=object_key,
            status=status,
            version=version,
        )
        async with self._sessions.begin() as session:
            session.add(row)
        return Document.from_row(row)

    async def mark_review_pending(
        self, document_id: str, expected_lock_version: int
    ) -> Document | None:
        return await self._transition(
            document_id, "draft", "review_pending", expected_lock_version
        )

    async def publish(
        self, document_id: str, expected_lock_version: int
    ) -> tuple[Document, list[str]] | None:
        async with self._sessions.begin() as session:
            row = await session.get(DocumentRow, document_id)
            if (
                row is None
                or row.status != "review_pending"
                or row.lock_version != expected_lock_version
            ):
                return None
            archived = list(
                await session.scalars(
                    select(DocumentRow.id).where(
                        DocumentRow.document_family_id == row.document_family_id,
                        DocumentRow.id != row.id,
                        DocumentRow.status == "published",
                    )
                )
            )
            if archived:
                await session.execute(
                    update(DocumentRow)
                    .where(DocumentRow.id.in_(archived))
                    .values(
                        status="archived", lock_version=DocumentRow.lock_version + 1
                    )
                )
            row.status = "published"
            row.lock_version += 1
            document = Document.from_row(row)
        return document, archived

    async def create_ingestion_task(self, document_id: str) -> IngestionTask | None:
        now = datetime.now(UTC)
        async with self._sessions.begin() as session:
            document = await session.get(DocumentRow, document_id)
            if document is None or document.status != "draft":
                return None
            document.status = "processing"
            document.lock_version += 1
            task = IngestionTaskRow(
                id=str(uuid4()),
                document_id=document_id,
                status="queued",
                stage="download",
                created_at=now,
                updated_at=now,
            )
            session.add(task)
            session.add(
                OutboxEventRow(
                    id=str(uuid4()),
                    aggregate_id=task.id,
                    event_type="ingestion.requested",
                    payload='{"task_id": "' + task.id + '"}',
                )
            )
            await session.flush()
            return IngestionTask.from_row(task)

    async def pending_outbox(self) -> list[tuple[str, str, str]]:
        async with self._sessions() as session:
            rows = await session.scalars(
                select(OutboxEventRow).where(OutboxEventRow.published_at.is_(None))
            )
            return [(row.id, row.event_type, row.payload) for row in rows]

    async def mark_outbox_published(self, event_id: str) -> bool:
        async with self._sessions.begin() as session:
            row = await session.get(OutboxEventRow, event_id)
            if row is None or row.published_at is not None:
                return False
            row.published_at = datetime.now(UTC)
            return True

    async def replace_chunks(self, document_id: str, chunks: list[ChunkDraft]) -> None:
        async with self._sessions.begin() as session:
            await session.execute(
                ChunkRow.__table__.delete().where(ChunkRow.document_id == document_id)
            )
            session.add_all(
                ChunkRow(
                    id=f"{document_id}:chunk-{ordinal}",
                    document_id=document_id,
                    ordinal=ordinal,
                    heading=chunk.heading,
                    content=chunk.content,
                )
                for ordinal, chunk in enumerate(chunks, start=1)
            )

    async def discard_chunks(self, document_id: str) -> None:
        async with self._sessions.begin() as session:
            await session.execute(
                ChunkRow.__table__.delete().where(ChunkRow.document_id == document_id)
            )

    async def indexed_documents(self) -> list[IndexedDocument]:
        async with self._sessions() as session:
            rows = await session.execute(
                select(DocumentRow, ChunkRow)
                .join(ChunkRow, ChunkRow.document_id == DocumentRow.id)
                .order_by(DocumentRow.id, ChunkRow.ordinal)
            )
        grouped: dict[str, IndexedDocument] = {}
        for document_row, chunk_row in rows:
            document = grouped.setdefault(
                document_row.id,
                IndexedDocument(document=Document.from_row(document_row), chunks=[]),
            )
            document.chunks.append(
                ChunkDraft(heading=chunk_row.heading, content=chunk_row.content)
            )
        return list(grouped.values())

    async def get_ingestion_task(self, task_id: str) -> IngestionTask | None:
        async with self._sessions() as session:
            row = await session.get(IngestionTaskRow, task_id)
            return IngestionTask.from_row(row) if row else None

    async def claim_ingestion_task(
        self, task_id: str, worker_id: str
    ) -> IngestionTask | None:
        now = datetime.now(UTC)
        async with self._sessions.begin() as session:
            claimed = await session.execute(
                update(IngestionTaskRow)
                .where(
                    IngestionTaskRow.id == task_id,
                    IngestionTaskRow.status.in_({"queued", "retry_wait"}),
                )
                .values(
                    status="running",
                    stage="parse",
                    worker_id=worker_id,
                    attempt=IngestionTaskRow.attempt + 1,
                    updated_at=now,
                )
            )
            if claimed.rowcount != 1:
                return None
            row = await session.get(IngestionTaskRow, task_id)
            assert row is not None
            return IngestionTask.from_row(row)

    async def next_queued_ingestion_task(self) -> IngestionTask | None:
        async with self._sessions() as session:
            row = await session.scalar(
                select(IngestionTaskRow)
                .where(IngestionTaskRow.status.in_({"queued", "retry_wait"}))
                .order_by(IngestionTaskRow.created_at)
                .limit(1)
            )
            return IngestionTask.from_row(row) if row else None

    async def report_ingestion_progress(
        self, task_id: str, stage: str, completed: int, total: int
    ) -> None:
        async with self._sessions.begin() as session:
            row = await session.get(IngestionTaskRow, task_id)
            if row is None or row.status != "running":
                return
            row.stage = stage
            row.completed = completed
            row.total = total
            row.updated_at = datetime.now(UTC)

    async def complete_ingestion_task(self, task_id: str) -> IngestionTask | None:
        async with self._sessions.begin() as session:
            task = await session.get(IngestionTaskRow, task_id)
            if task is None or task.status != "running":
                return None
            document = await session.get(DocumentRow, task.document_id)
            if document is None or document.status != "processing":
                return None
            document.status = "review_pending"
            document.lock_version += 1
            task.status = "succeeded"
            task.stage = "finalizing"
            task.updated_at = datetime.now(UTC)
            return IngestionTask.from_row(task)

    async def fail_ingestion_task(
        self, task_id: str, error_code: str, error_detail: str
    ) -> IngestionTask | None:
        async with self._sessions.begin() as session:
            task = await session.get(IngestionTaskRow, task_id)
            if task is None or task.status != "running":
                return None
            document = await session.get(DocumentRow, task.document_id)
            if document is not None and document.status == "processing":
                document.status = "failed"
                document.lock_version += 1
            task.status = "failed"
            task.error_code = error_code
            task.error_detail = error_detail[:500]
            task.updated_at = datetime.now(UTC)
            return IngestionTask.from_row(task)

    async def request_ingestion_cancel(self, task_id: str) -> IngestionTask | None:
        async with self._sessions.begin() as session:
            task = await session.get(IngestionTaskRow, task_id)
            if task is None or task.status not in {"queued", "running", "retry_wait"}:
                return None
            task.status = "cancelled"
            task.stage = None
            task.updated_at = datetime.now(UTC)
            document = await session.get(DocumentRow, task.document_id)
            if document is not None and document.status == "processing":
                document.status = "draft"
                document.lock_version += 1
            return IngestionTask.from_row(task)

    async def retry_ingestion_task(self, task_id: str) -> IngestionTask | None:
        """Return a failed task to the queue without creating a second task record."""
        async with self._sessions.begin() as session:
            task = await session.get(IngestionTaskRow, task_id)
            if task is None or task.status != "failed":
                return None
            document = await session.get(DocumentRow, task.document_id)
            if document is None or document.status != "failed":
                return None
            document.status = "processing"
            document.lock_version += 1
            task.status = "queued"
            task.stage = "download"
            task.completed = 0
            task.total = 0
            task.error_code = None
            task.error_detail = None
            task.worker_id = None
            task.updated_at = datetime.now(UTC)
            return IngestionTask.from_row(task)

    async def _transition(
        self,
        document_id: str,
        current_status: str,
        next_status: str,
        expected_lock_version: int,
    ) -> Document | None:
        async with self._sessions.begin() as session:
            row = await session.get(DocumentRow, document_id)
            if (
                row is None
                or row.status != current_status
                or row.lock_version != expected_lock_version
            ):
                return None
            row.status = next_status
            row.lock_version += 1
            return Document.from_row(row)
