from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
from fastapi import HTTPException, status
from jwt import InvalidTokenError

from app.config import Settings


class TokenService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def issue(self, user_id: str) -> str:
        now = datetime.now(UTC)
        return jwt.encode(
            {
                "sub": user_id,
                "iss": self._settings.jwt_issuer,
                "aud": self._settings.jwt_audience,
                "iat": now,
                "exp": now + timedelta(minutes=self._settings.jwt_exp_minutes),
            },
            self._settings.jwt_secret,
            algorithm="HS256",
        )

    def decode_subject(self, token: str) -> str:
        try:
            payload = jwt.decode(
                token,
                self._settings.jwt_secret,
                algorithms=["HS256"],
                issuer=self._settings.jwt_issuer,
                audience=self._settings.jwt_audience,
                options={"require": ["sub", "exp", "iat"]},
            )
        except InvalidTokenError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid access token",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
        return str(payload["sub"])
