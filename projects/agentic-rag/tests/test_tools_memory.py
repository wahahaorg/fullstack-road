from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.memory import ConversationMemoryStore

TRAVEL_POLICY = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "documents"
    / "travel-policy-v2.md"
).read_bytes()


def _headers(client: TestClient, user_id: str) -> dict[str, str]:
    response = client.post("/api/auth/dev-token", json={"user_id": user_id})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _client() -> TestClient:
    return TestClient(
        create_app(
            Settings(
                provider="demo",
                seed_fixtures=True,
                database_url="sqlite+aiosqlite:///:memory:",
            )
        )
    )


def test_memory_store_is_bound_to_one_actor_and_bounded() -> None:
    store = ConversationMemoryStore()
    saved = store.save("conversation-1", "alice", "x" * 600)

    assert saved.summary == "x" * 500
    assert store.get("conversation-1", "alice") == saved
    assert store.get("conversation-1", "bob") is None


def test_chat_saves_memory_only_for_the_conversation_owner() -> None:
    with _client() as client:
        alice = _headers(client, "user-finance-alice")
        bob = _headers(client, "user-engineering-bob")
        chat = client.post(
            "/api/chat",
            json={"question": "你好", "conversation_id": "alice-demo"},
            headers=alice,
        )
        own_memory = client.get("/api/conversations/alice-demo/memory", headers=alice)
        other_memory = client.get("/api/conversations/alice-demo/memory", headers=bob)

    assert chat.status_code == 200
    assert own_memory.status_code == 200
    assert own_memory.json()["summary"] == chat.json()["answer"]
    assert other_memory.status_code == 404


def test_version_read_tool_is_admin_only_and_uses_document_scope() -> None:
    with _client() as client:
        carol = _headers(client, "user-admin-carol")
        alice = _headers(client, "user-finance-alice")
        allowed = client.get(
            "/api/tools/document-versions/doc-travel-v1", headers=carol
        )
        denied = client.get("/api/tools/document-versions/doc-travel-v1", headers=alice)

    assert allowed.status_code == 200
    assert allowed.json()["version"] == 1
    assert "500" in allowed.json()["content"]
    assert denied.status_code == 404


def test_publish_requires_a_separate_human_decision_with_fresh_lock() -> None:
    with _client() as client:
        alice = _headers(client, "user-finance-alice")
        carol = _headers(client, "user-admin-carol")
        upload = client.post(
            "/api/documents",
            files={"file": ("policy.md", TRAVEL_POLICY, "text/markdown")},
            data={"knowledge_base_id": "kb-company"},
            headers=alice,
        )
        submitted = client.post(
            f"/api/documents/{upload.json()['document_id']}/submit", headers=alice
        )
        task = asyncio.run(
            client.app.state.rag.run_ingestion(
                submitted.json()["task_id"], "test-worker"
            )
        )
        assert task is not None and task.status == "succeeded"
        denied = client.post(
            f"/api/documents/{upload.json()['document_id']}/publish-proposals",
            headers=alice,
        )
        proposal = client.post(
            f"/api/documents/{upload.json()['document_id']}/publish-proposals",
            headers=carol,
        )
        published = client.post(
            f"/api/publish-proposals/{proposal.json()['proposal_id']}/decisions",
            json={"approved": True},
            headers=carol,
        )

    assert denied.status_code == 403
    assert proposal.status_code == 201
    assert proposal.json()["status"] == "pending"
    assert published.status_code == 200
    assert published.json()["status"] == "published"
