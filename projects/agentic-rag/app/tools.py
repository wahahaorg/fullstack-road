from __future__ import annotations

from dataclasses import dataclass

from app.domain import User
from app.parsing import parse_document
from app.rag import RagContainer


@dataclass(frozen=True, slots=True)
class DocumentVersion:
    document_id: str
    version: int
    title: str
    filename: str
    status: str
    content: str


async def read_document_version(
    rag: RagContainer, actor: User, document_id: str
) -> DocumentVersion | None:
    """Read one historical document version through a narrow admin-only tool."""
    if "knowledge_admin" not in actor.global_roles:
        return None
    document = await rag.documents.get(document_id)
    knowledge_base = (
        rag.directory.get_knowledge_base(document.knowledge_base_id)
        if document is not None
        else None
    )
    if knowledge_base is None or not rag.directory.can_read(actor, knowledge_base):
        return None
    raw = await rag.object_store.get(document.object_key)
    content = "\n".join(
        chunk.content for chunk in parse_document(document.filename, raw)
    )
    return DocumentVersion(
        document_id=document.id,
        version=document.version,
        title=document.title,
        filename=document.filename,
        status=document.status,
        content=content,
    )
