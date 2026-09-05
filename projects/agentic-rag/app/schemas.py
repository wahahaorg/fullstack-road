from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class UploadResponse(BaseModel):
    document_id: str
    filename: str
    chunk_count: int
    status: str = "published"
    version: int = 1
    lock_version: int = 1


class IngestionTaskResponse(BaseModel):
    task_id: str
    document_id: str
    status: str
    stage: str | None
    completed: int
    total: int
    attempt: int
    error_code: str | None
    error_detail: str | None


class DevTokenRequest(BaseModel):
    user_id: str


class DevTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class KnowledgeBaseResponse(BaseModel):
    id: str
    name: str
    visibility: str


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    top_k: int | None = Field(default=None, ge=1, le=10)
    conversation_id: str | None = Field(default=None, min_length=1, max_length=100)

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
    document_version: int
    knowledge_base_id: str
    filename: str
    heading: str | None
    excerpt: str
    score: float


class ClaimResponse(BaseModel):
    text: str
    source_ids: list[str]


class ChatResponse(BaseModel):
    answer: str
    refused: bool
    provider: str
    refusal_reason: str | None = None
    claims: list[ClaimResponse] = Field(default_factory=list)
    sources: list[SourceResponse]
    retrieval_profile: str | None = None
    rerank_applied: bool = False
    route: str = "fixed_rag"
    intent: str = "simple_fact"
    route_reason: str | None = None
    route_degraded: bool = False
    partial: bool = False
    missing_information: list[str] = Field(default_factory=list)
    agent_trace: list[str] = Field(default_factory=list)


class RoutingDebugResponse(BaseModel):
    route: str
    intent: str
    reason: str
    degraded: bool


class DocumentVersionResponse(BaseModel):
    document_id: str
    version: int
    title: str
    filename: str
    status: str
    content: str


class ConversationMemoryResponse(BaseModel):
    conversation_id: str
    summary: str
    updated_at: str


class PublishDecisionRequest(BaseModel):
    approved: bool


class PublishProposalResponse(BaseModel):
    proposal_id: str
    document_id: str
    expected_lock_version: int
    status: str
    expires_at: str


class RetrievalDebugRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    profile: str = "hybrid-v1"


class RetrievalDebugStage(BaseModel):
    chunk_id: str
    rank: int
    score: float | None = None


class RetrievalDebugResponse(BaseModel):
    profile: str
    vector: list[RetrievalDebugStage]
    keyword: list[RetrievalDebugStage]
    rrf: list[RetrievalDebugStage]
    rerank: list[RetrievalDebugStage]
    rerank_applied: bool


class HealthResponse(BaseModel):
    status: str
    provider: str
    indexed_chunks: int


class ReadinessResponse(BaseModel):
    status: str
    provider: str
    database: str
