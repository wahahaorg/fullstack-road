from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCENARIO_PATH = ROOT / "fixtures" / "scenario.json"
DATASET_PATH = ROOT / "evals" / "dataset.jsonl"
DOCUMENT_DIR = ROOT / "fixtures" / "documents"

REQUIRED_CATEGORIES = {
    "simple_rag",
    "multi_hop",
    "comparison",
    "no_answer",
    "permission",
    "lifecycle",
    "security",
    "direct",
    "version_compare",
}
VALID_ROUTES = {"direct", "fixed_rag", "agentic_rag", "version_tool", "refuse"}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line:
            continue
        try:
            cases.append(json.loads(line))
        except json.JSONDecodeError as exc:
            message = f"评测集第 {line_number} 行不是有效 JSON: {exc}"
            raise AssertionError(message) from exc
    return cases


def can_search_normally(
    user: dict[str, Any],
    document: dict[str, Any],
    knowledge_base: dict[str, Any],
) -> bool:
    if document["status"] != "published":
        return False
    if knowledge_base["visibility"] == "company":
        return True
    if knowledge_base["visibility"] == "team":
        return knowledge_base.get("team_id") in user["teams"]
    return False


def validate() -> None:
    scenario = load_json(SCENARIO_PATH)
    cases = load_jsonl(DATASET_PATH)

    users = {item["id"]: item for item in scenario["users"]}
    teams = {item["id"]: item for item in scenario["teams"]}
    knowledge_bases = {item["id"]: item for item in scenario["knowledge_bases"]}
    documents = {item["id"]: item for item in scenario["documents"]}

    assert len(users) == len(scenario["users"]), "用户 ID 不能重复"
    assert len(teams) == len(scenario["teams"]), "团队 ID 不能重复"
    assert len(knowledge_bases) == len(scenario["knowledge_bases"]), (
        "知识库 ID 不能重复"
    )
    assert len(documents) == len(scenario["documents"]), "文档 ID 不能重复"

    for user in users.values():
        unknown_teams = set(user["teams"]) - teams.keys()
        assert not unknown_teams, f"用户 {user['id']} 引用了未知团队: {unknown_teams}"

    for knowledge_base in knowledge_bases.values():
        team_id = knowledge_base.get("team_id")
        assert not team_id or team_id in teams, (
            f"知识库 {knowledge_base['id']} 引用了未知团队: {team_id}"
        )

    for document in documents.values():
        assert document["knowledge_base_id"] in knowledge_bases, (
            f"文档 {document['id']} 引用了未知知识库"
        )
        document_path = DOCUMENT_DIR / document["filename"]
        assert document_path.is_file(), f"缺少样例文档: {document_path}"

    case_ids = [case["id"] for case in cases]
    assert len(case_ids) == len(set(case_ids)), "评测样例 ID 不能重复"

    categories = {case["category"] for case in cases}
    missing_categories = REQUIRED_CATEGORIES - categories
    assert not missing_categories, f"评测集缺少场景: {sorted(missing_categories)}"

    referenced_documents: set[str] = set()
    for case in cases:
        assert case["actor_id"] in users, f"样例 {case['id']} 使用了未知用户"
        assert case["expected_route"] in VALID_ROUTES, (
            f"样例 {case['id']} 的路由无效: {case['expected_route']}"
        )

        expected_sources = set(case["expected_source_ids"])
        forbidden_sources = set(case["forbidden_source_ids"])
        all_sources = expected_sources | forbidden_sources
        unknown_documents = all_sources - documents.keys()
        assert not unknown_documents, (
            f"样例 {case['id']} 引用了未知文档: {sorted(unknown_documents)}"
        )
        assert not expected_sources & forbidden_sources, (
            f"样例 {case['id']} 同时期待并禁止同一来源"
        )
        referenced_documents.update(all_sources)

        if case.get("access_mode", "normal_search") != "normal_search":
            continue

        user = users[case["actor_id"]]
        for document_id in expected_sources:
            document = documents[document_id]
            knowledge_base = knowledge_bases[document["knowledge_base_id"]]
            assert can_search_normally(user, document, knowledge_base), (
                f"样例 {case['id']} 将无权或未发布文档设为普通检索来源: {document_id}"
            )

    unreferenced_documents = documents.keys() - referenced_documents
    assert not unreferenced_documents, (
        f"存在未被任何验收样例覆盖的文档: {sorted(unreferenced_documents)}"
    )

    print(
        "fixtures valid: "
        f"users={len(users)}, teams={len(teams)}, "
        f"documents={len(documents)}, eval_cases={len(cases)}"
    )


if __name__ == "__main__":
    validate()
