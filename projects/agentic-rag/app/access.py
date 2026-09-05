from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.domain import KnowledgeBase, SearchScope, User


@dataclass(frozen=True, slots=True)
class FixtureDocument:
    id: str
    title: str
    filename: str
    knowledge_base_id: str
    status: str
    version: int


class AccessDirectory:
    def __init__(
        self,
        users: dict[str, User],
        knowledge_bases: dict[str, KnowledgeBase],
        grants: dict[str, frozenset[str]],
        documents: tuple[FixtureDocument, ...],
    ) -> None:
        self._users = users
        self._knowledge_bases = knowledge_bases
        self._grants = grants
        self.documents = documents

    @classmethod
    def from_fixture(cls) -> AccessDirectory:
        path = Path(__file__).resolve().parents[1] / "fixtures" / "scenario.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        users = {
            item["id"]: User(
                id=item["id"],
                name=item["name"],
                team_ids=frozenset(item["teams"]),
                global_roles=frozenset(item["roles"]),
            )
            for item in raw["users"]
        }
        knowledge_bases = {
            item["id"]: KnowledgeBase(
                id=item["id"],
                name=item["name"],
                visibility=item["visibility"],
                owner_team_id=item.get("team_id"),
            )
            for item in raw["knowledge_bases"]
        }
        # Resource grants intentionally live outside JWT claims. They model
        # exceptional write access in this teaching fixture.
        grants = {
            "user-finance-alice": frozenset({"kb-company"}),
            "user-admin-carol": frozenset(knowledge_bases),
        }
        documents = tuple(
            FixtureDocument(
                id=item["id"],
                title=item["title"],
                filename=item["filename"],
                knowledge_base_id=item["knowledge_base_id"],
                status=item["status"],
                version=item["version"],
            )
            for item in raw["documents"]
        )
        return cls(users, knowledge_bases, grants, documents)

    def get_user(self, user_id: str) -> User | None:
        return self._users.get(user_id)

    def readable_knowledge_bases(self, user: User) -> list[KnowledgeBase]:
        return [
            knowledge_base
            for knowledge_base in self._knowledge_bases.values()
            if self.can_read(user, knowledge_base)
        ]

    def normal_search_scope(self, user: User) -> SearchScope:
        return SearchScope(
            knowledge_base_ids=frozenset(
                knowledge_base.id
                for knowledge_base in self.readable_knowledge_bases(user)
            ),
            document_statuses=frozenset({"published"}),
        )

    def can_read(self, user: User, knowledge_base: KnowledgeBase) -> bool:
        if knowledge_base.visibility == "company":
            return True
        if (
            knowledge_base.visibility == "team"
            and knowledge_base.owner_team_id in user.team_ids
        ):
            return True
        return knowledge_base.id in self._grants.get(user.id, frozenset())

    def can_write(self, user: User, knowledge_base_id: str) -> bool:
        return knowledge_base_id in self._grants.get(user.id, frozenset())

    def get_knowledge_base(self, knowledge_base_id: str) -> KnowledgeBase | None:
        return self._knowledge_bases.get(knowledge_base_id)
