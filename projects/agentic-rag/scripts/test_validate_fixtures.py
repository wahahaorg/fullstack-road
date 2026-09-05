from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from validate_fixtures import can_search_normally  # noqa: E402


class SearchBoundaryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        scenario = json.loads(
            (PROJECT_ROOT / "fixtures" / "scenario.json").read_text(
                encoding="utf-8"
            )
        )
        cls.users = {item["id"]: item for item in scenario["users"]}
        cls.knowledge_bases = {
            item["id"]: item for item in scenario["knowledge_bases"]
        }
        cls.documents = {item["id"]: item for item in scenario["documents"]}

    def can_search(self, user_id: str, document_id: str) -> bool:
        document = self.documents[document_id]
        knowledge_base = self.knowledge_bases[document["knowledge_base_id"]]
        return can_search_normally(
            self.users[user_id], document, knowledge_base
        )

    def test_company_document_is_visible_to_employee(self) -> None:
        self.assertTrue(
            self.can_search("user-finance-alice", "doc-travel-v2")
        )

    def test_team_document_is_hidden_from_other_team(self) -> None:
        self.assertFalse(
            self.can_search("user-finance-alice", "doc-oncall-v1")
        )

    def test_team_document_is_visible_to_team_member(self) -> None:
        self.assertTrue(
            self.can_search("user-engineering-bob", "doc-oncall-v1")
        )

    def test_draft_and_archived_documents_are_not_normally_searchable(self) -> None:
        self.assertFalse(
            self.can_search("user-admin-carol", "doc-sales-price-v2-draft")
        )
        self.assertFalse(
            self.can_search("user-admin-carol", "doc-travel-v1")
        )


if __name__ == "__main__":
    unittest.main()

