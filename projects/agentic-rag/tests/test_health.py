from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_live_and_ready_health_endpoints() -> None:
    with TestClient(
        create_app(
            Settings(provider="demo", database_url="sqlite+aiosqlite:///:memory:")
        )
    ) as client:
        live = client.get("/health/live")
        ready = client.get("/health/ready")

    assert live.status_code == 200
    assert live.json() == {"status": "ok"}
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"
