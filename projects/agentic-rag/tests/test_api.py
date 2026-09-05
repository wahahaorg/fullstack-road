from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRAVEL_POLICY = (
    PROJECT_ROOT / "fixtures" / "documents" / "travel-policy-v2.md"
).read_bytes()


def make_client() -> TestClient:
    app = create_app(Settings(provider="demo", top_k=3))
    return TestClient(app)


def test_health_starts_empty() -> None:
    with make_client() as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "provider": "demo",
        "indexed_chunks": 0,
    }


def test_chat_refuses_before_document_upload() -> None:
    with make_client() as client:
        response = client.post("/api/chat", json={"question": "上海住宿上限是多少？"})
    assert response.status_code == 200
    assert response.json()["refused"] is True
    assert response.json()["sources"] == []


def test_chat_rejects_blank_question() -> None:
    with make_client() as client:
        response = client.post("/api/chat", json={"question": "   "})
    assert response.status_code == 422


def test_upload_then_answer_with_source() -> None:
    with make_client() as client:
        upload = client.post(
            "/api/documents",
            files={"file": ("travel-policy-v2.md", TRAVEL_POLICY, "text/markdown")},
        )
        answer = client.post("/api/chat", json={"question": "上海住宿每晚最多多少钱？"})

    assert upload.status_code == 201
    assert upload.json()["chunk_count"] > 0
    assert answer.status_code == 200
    body = answer.json()
    assert body["refused"] is False
    assert "650" in body["answer"]
    assert "城市类别 | 示例 | 每人每晚上限" not in body["answer"]
    assert body["answer"].count("\n- ") == 1
    assert body["provider"] == "demo"
    assert body["sources"]
    assert body["sources"][0]["filename"] == "travel-policy-v2.md"


def test_rejects_unsupported_file_type() -> None:
    with make_client() as client:
        response = client.post(
            "/api/documents",
            files={"file": ("policy.pdf", b"fake-pdf", "application/pdf")},
        )
    assert response.status_code == 415


def test_rejects_empty_document() -> None:
    with make_client() as client:
        response = client.post(
            "/api/documents",
            files={"file": ("empty.md", b"\n\n", "text/markdown")},
        )
    assert response.status_code == 422
