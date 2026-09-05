from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def _headers(client: TestClient, user_id: str) -> dict[str, str]:
    token = client.post("/api/auth/dev-token", json={"user_id": user_id}).json()
    return {"Authorization": f"Bearer {token['access_token']}"}


def test_stream_endpoint_emits_ordered_events_and_terminal_state() -> None:
    app = create_app(
        Settings(
            provider="demo",
            seed_fixtures=True,
            database_url="sqlite+aiosqlite:///:memory:",
        )
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/chat/stream",
            json={"question": "上海住宿上限是多少？"},
            headers=_headers(client, "user-finance-alice"),
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = []
    for block in response.text.strip().split("\n\n"):
        data = next(
            line[6:] for line in block.splitlines() if line.startswith("data: ")
        )
        events.append(json.loads(data))
    assert [item["id"] for item in events] == list(range(1, len(events) + 1))
    assert events[0]["type"] == "run.started"
    assert events[-1]["type"] == "run.completed"
    assert any(item["type"] == "citation" for item in events)
