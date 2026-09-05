from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    provider: str = "demo"
    top_k: int = 3
    max_upload_bytes: int = 1024 * 1024
    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: str | None = None
    embedding_model: str | None = None
    chat_model: str | None = None
    jwt_secret: str = "agentic-rag-dev-only-secret-change-this-2026"
    jwt_issuer: str = "agentic-rag-local"
    jwt_audience: str = "agentic-rag-api"
    jwt_exp_minutes: int = 60
    enable_dev_tokens: bool = True
    seed_fixtures: bool = False
    database_url: str = "sqlite+aiosqlite:///./.data/agentic-rag.db"
    object_store: str = "filesystem"
    object_store_root: Path = Path(".data/objects")
    minio_endpoint: str | None = None
    minio_access_key: str | None = None
    minio_secret_key: str | None = None
    minio_bucket: str = "agentic-rag"

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            provider=os.getenv("APP_PROVIDER", "demo"),
            top_k=int(os.getenv("APP_TOP_K", "3")),
            max_upload_bytes=int(os.getenv("APP_MAX_UPLOAD_BYTES", str(1024 * 1024))),
            openai_base_url=os.getenv(
                "OPENAI_BASE_URL", "https://api.openai.com/v1"
            ).rstrip("/"),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            embedding_model=os.getenv("EMBEDDING_MODEL"),
            chat_model=os.getenv("CHAT_MODEL"),
            jwt_secret=os.getenv(
                "JWT_SECRET", "agentic-rag-dev-only-secret-change-this-2026"
            ),
            jwt_issuer=os.getenv("JWT_ISSUER", "agentic-rag-local"),
            jwt_audience=os.getenv("JWT_AUDIENCE", "agentic-rag-api"),
            jwt_exp_minutes=int(os.getenv("JWT_EXP_MINUTES", "60")),
            enable_dev_tokens=os.getenv("APP_ENABLE_DEV_TOKENS", "true").lower()
            in {"1", "true", "yes"},
            seed_fixtures=os.getenv("APP_SEED_FIXTURES", "false").lower()
            in {"1", "true", "yes"},
            database_url=os.getenv(
                "DATABASE_URL", "sqlite+aiosqlite:///./.data/agentic-rag.db"
            ),
            object_store=os.getenv("OBJECT_STORE", "filesystem"),
            object_store_root=Path(os.getenv("OBJECT_STORE_ROOT", ".data/objects")),
            minio_endpoint=os.getenv("MINIO_ENDPOINT"),
            minio_access_key=os.getenv("MINIO_ACCESS_KEY"),
            minio_secret_key=os.getenv("MINIO_SECRET_KEY"),
            minio_bucket=os.getenv("MINIO_BUCKET", "agentic-rag"),
        )

    def validate(self) -> None:
        if self.provider not in {"demo", "openai_compatible"}:
            raise ValueError("APP_PROVIDER must be 'demo' or 'openai_compatible'")
        if self.top_k < 1 or self.top_k > 20:
            raise ValueError("APP_TOP_K must be between 1 and 20")
        if self.max_upload_bytes < 1:
            raise ValueError("APP_MAX_UPLOAD_BYTES must be positive")
        if not self.jwt_secret:
            raise ValueError("JWT_SECRET must not be empty")
        if self.jwt_exp_minutes < 1:
            raise ValueError("JWT_EXP_MINUTES must be positive")
        if self.object_store not in {"filesystem", "minio"}:
            raise ValueError("OBJECT_STORE must be 'filesystem' or 'minio'")
        if self.object_store == "minio":
            missing = [
                name
                for name, value in {
                    "MINIO_ENDPOINT": self.minio_endpoint,
                    "MINIO_ACCESS_KEY": self.minio_access_key,
                    "MINIO_SECRET_KEY": self.minio_secret_key,
                }.items()
                if not value
            ]
            if missing:
                raise ValueError("Missing MinIO settings: " + ", ".join(missing))
        if self.provider == "openai_compatible":
            missing = [
                name
                for name, value in {
                    "OPENAI_API_KEY": self.openai_api_key,
                    "EMBEDDING_MODEL": self.embedding_model,
                    "CHAT_MODEL": self.chat_model,
                }.items()
                if not value
            ]
            if missing:
                raise ValueError(
                    "Missing settings for openai_compatible provider: "
                    + ", ".join(missing)
                )
