from __future__ import annotations

from app.domain import User


def can_publish(user: User) -> bool:
    return "knowledge_admin" in user.global_roles
