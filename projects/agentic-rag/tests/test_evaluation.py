from __future__ import annotations

from evals.run import run


def test_local_evaluation_produces_risk_metrics() -> None:
    report = run(__import__("pathlib").Path("evals/dataset.jsonl"))

    assert report["case_count"] == 11
    assert report["forbidden_source_leakage_rate"] == 0
    assert report["route_accuracy"] >= 0.8
    assert len(report["results"]) == 11
