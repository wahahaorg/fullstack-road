from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def _headers(client: TestClient, user_id: str) -> dict[str, str]:
    response = client.post("/api/auth/dev-token", json={"user_id": user_id})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_agentic_route_runs_a_bounded_multi_retrieval_graph() -> None:
    app = create_app(
        Settings(
            provider="demo",
            seed_fixtures=True,
            database_url="sqlite+aiosqlite:///:memory:",
        )
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/chat",
            json={
                "question": (
                    "我去上海出差，住宿上限是多少，回来后报销要在多久内提交，还要准备哪些材料？"
                )
            },
            headers=_headers(client, "user-finance-alice"),
        )

    body = response.json()
    assert response.status_code == 200
    assert body["route"] == "agentic_rag"
    assert body["route_degraded"] is False
    assert body["agent_trace"] == [
        "plan",
        "retrieve",
        "retrieve",
        "assess",
        "synthesize",
    ]


def test_agent_graph_preserves_the_callers_search_scope() -> None:
    app = create_app(
        Settings(
            provider="demo",
            seed_fixtures=True,
            database_url="sqlite+aiosqlite:///:memory:",
        )
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/chat",
            json={"question": "研发值班和报销材料分别是什么？"},
            headers=_headers(client, "user-finance-alice"),
        )

    assert response.status_code == 200
    source_ids = [source["document_id"] for source in response.json()["sources"]]
    assert "doc-oncall-v1" not in source_ids
