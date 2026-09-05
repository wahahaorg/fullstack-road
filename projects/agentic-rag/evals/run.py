from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

ROOT = Path(__file__).resolve().parents[1]


def _headers(client: TestClient, user_id: str) -> dict[str, str]:
    response = client.post("/api/auth/dev-token", json={"user_id": user_id})
    response.raise_for_status()
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _load_cases(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def run(dataset_path: Path) -> dict[str, object]:
    dataset_path = dataset_path.resolve()
    cases = _load_cases(dataset_path)
    app = create_app(
        Settings(
            provider="demo",
            seed_fixtures=True,
            database_url="sqlite+aiosqlite:///:memory:",
        )
    )
    results: list[dict[str, object]] = []
    with TestClient(app) as client:
        for case in cases:
            response = client.post(
                "/api/chat",
                json={"question": case["question"]},
                headers=_headers(client, str(case["actor_id"])),
            )
            body = response.json()
            source_ids = {item["document_id"] for item in body.get("sources", [])}
            if case.get("access_mode") == "version_tool":
                source_ids = set()
                for document_id in case["expected_source_ids"]:
                    version = client.get(
                        f"/api/tools/document-versions/{document_id}",
                        headers=_headers(client, str(case["actor_id"])),
                    )
                    if version.status_code == 200:
                        source_ids.add(document_id)
            expected_sources = set(case["expected_source_ids"])
            forbidden_sources = set(case["forbidden_source_ids"])
            required_facts = [
                fact
                for fact in case["required_facts"]
                if fact not in body.get("answer", "")
            ]
            results.append(
                {
                    "id": case["id"],
                    "route_ok": body.get("route") == case["expected_route"],
                    "source_recall": (
                        len(expected_sources & source_ids) / len(expected_sources)
                        if expected_sources
                        else 1.0
                    ),
                    "forbidden_source_leak": bool(forbidden_sources & source_ids),
                    "refusal_ok": body.get("refused") == case["expect_refusal"],
                    "missing_facts": required_facts,
                    "status_code": response.status_code,
                }
            )
    total = len(results)
    return {
        "started_at": datetime.now(UTC).isoformat(),
        "environment": "local-demo",
        "dataset": str(dataset_path.relative_to(ROOT)),
        "dataset_hash": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
        "case_count": total,
        "route_accuracy": sum(item["route_ok"] for item in results) / total,
        "mean_source_recall": sum(item["source_recall"] for item in results) / total,
        "forbidden_source_leakage_rate": sum(
            item["forbidden_source_leak"] for item in results
        )
        / total,
        "refusal_accuracy": sum(item["refusal_ok"] for item in results) / total,
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the deterministic local RAG evaluation"
    )
    parser.add_argument(
        "--dataset", type=Path, default=ROOT / "evals" / "dataset.jsonl"
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run(args.dataset)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
