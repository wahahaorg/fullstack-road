from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class UploadResponse(BaseModel):
    document_id: str
    filename: str
    chunk_count: int


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    top_k: int | None = Field(default=None, ge=1, le=10)

    @field_validator("question")
    @classmethod
    def question_must_have_content(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("question must not be blank")
        return stripped


class SourceResponse(BaseModel):
    id: str
    document_id: str
    filename: str
    heading: str | None
    content: str
    score: float


class ChatResponse(BaseModel):
    answer: str
    refused: bool
    provider: str
    sources: list[SourceResponse]


class HealthResponse(BaseModel):
    status: str
    provider: str
    indexed_chunks: int
