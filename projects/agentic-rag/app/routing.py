from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Route = Literal[
    "direct", "fixed_rag", "agentic_rag", "summary", "version_tool", "refuse"
]


@dataclass(frozen=True, slots=True)
class RouteDecision:
    route: Route
    intent: str
    reason: str
    degraded: bool = False


def classify_route(question: str, *, is_knowledge_admin: bool) -> RouteDecision:
    normalized = question.strip().lower()
    if "忽略" in normalized and "权限" in normalized:
        return RouteDecision("refuse", "policy_bypass", "permission_bypass")
    if any(greeting in normalized for greeting in ("你好", "您好", "你能做什么")):
        return RouteDecision("direct", "greeting", "no_retrieval_needed")
    if any(marker in normalized for marker in ("v1", "v2", "旧版本", "历史版本")):
        if is_knowledge_admin:
            return RouteDecision("version_tool", "version_compare", "historical_access")
        return RouteDecision("refuse", "version_compare", "historical_access_denied")
    if "总结" in normalized or "摘要" in normalized:
        return RouteDecision("summary", "summary", "summary_requested")
    if any(marker in normalized for marker in ("相差", "相比", "分别", "以及", "还要")):
        return RouteDecision("agentic_rag", "multi_fact", "multiple_evidence_needed")
    return RouteDecision("fixed_rag", "simple_fact", "single_retrieval_expected")
