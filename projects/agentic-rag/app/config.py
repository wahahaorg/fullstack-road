from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    provider: str = "demo"
    top_k: int = 3
    max_upload_bytes: int = 1024 * 1024
    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: str | None = None
    embedding_model: str | None = None
    chat_model: str | None = None

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
        )

    def validate(self) -> None:
        if self.provider not in {"demo", "openai_compatible"}:
            raise ValueError("APP_PROVIDER must be 'demo' or 'openai_compatible'")
        if self.top_k < 1 or self.top_k > 20:
            raise ValueError("APP_TOP_K must be between 1 and 20")
        if self.max_upload_bytes < 1:
            raise ValueError("APP_MAX_UPLOAD_BYTES must be positive")
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
