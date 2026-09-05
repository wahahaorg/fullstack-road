from __future__ import annotations

import re

from app.domain import ChunkDraft

HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def split_markdown(text: str, max_chars: int = 600) -> list[ChunkDraft]:
    """Split Markdown by heading and paragraph while keeping heading context."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    chunks: list[ChunkDraft] = []
    current_heading: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        nonlocal buffer
        body = "\n".join(buffer).strip()
        buffer = []
        if not body:
            return
        prefix = f"{current_heading}\n" if current_heading else ""
        for part in _split_oversized(prefix + body, max_chars=max_chars):
            chunks.append(ChunkDraft(heading=current_heading, content=part.strip()))

    for line in lines:
        heading_match = HEADING_PATTERN.match(line)
        if heading_match:
            flush()
            current_heading = heading_match.group(2).strip()
            continue
        if not line.strip() and buffer:
            flush()
            continue
        if line.strip():
            buffer.append(line.rstrip())
    flush()
    return chunks


def _split_oversized(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]

    parts: list[str] = []
    start = 0
    overlap = min(80, max_chars // 5)
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            boundary = max(
                text.rfind("。", start, end),
                text.rfind("\n", start, end),
            )
            if boundary > start + max_chars // 2:
                end = boundary + 1
        parts.append(text[start:end])
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return parts
