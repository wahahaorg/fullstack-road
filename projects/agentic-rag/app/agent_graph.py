from __future__ import annotations

from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from app.domain import SearchHit, SearchScope
from app.rag import RagContainer
from app.schemas import ChatResponse


class AgentState(TypedDict, total=False):
    question: str
    actor_id: str
    scope: SearchScope
    pending_queries: list[str]
    queried: list[str]
    hits: list[SearchHit]
    rounds: int
    max_rounds: int
    exit_reason: str
    node_trace: list[str]


class AgenticRagGraph:
    """A bounded, read-only LangGraph orchestration over existing RAG services."""

    def __init__(self, rag: RagContainer) -> None:
        self._rag = rag
        graph = StateGraph(AgentState)
        graph.add_node("plan", self._plan)
        graph.add_node("retrieve", self._retrieve)
        graph.add_node("assess", self._assess)
        graph.add_node("rewrite", self._rewrite)
        graph.add_node("synthesize", self._synthesize)
        graph.add_node("partial", self._partial)
        graph.add_edge(START, "plan")
        graph.add_edge("plan", "retrieve")
        graph.add_conditional_edges("retrieve", self._after_retrieve)
        graph.add_conditional_edges("assess", self._after_assess)
        graph.add_edge("rewrite", "retrieve")
        graph.add_edge("synthesize", END)
        graph.add_edge("partial", END)
        self._graph = graph.compile()

    async def run(self, question: str, actor_id: str) -> ChatResponse:
        actor = self._rag.directory.get_user(actor_id)
        if actor is None:
            raise ValueError("unknown user")
        await self._rag.refresh_search_index()
        state = await self._graph.ainvoke(
            {
                "question": question,
                "actor_id": actor_id,
                "scope": self._rag.directory.normal_search_scope(actor),
                "pending_queries": [],
                "queried": [],
                "hits": [],
                "rounds": 0,
                "max_rounds": 3,
                "node_trace": [],
            },
            {"recursion_limit": 12},
        )
        response = await self._rag.answer_from_hits(
            question,
            state.get("hits", []),
            profile="hybrid-v1",
            rerank_applied=True,
        )
        partial = state.get("exit_reason") != "evidence_sufficient"
        return response.model_copy(
            update={
                "route": "agentic_rag",
                "intent": "multi_fact",
                "route_reason": state.get("exit_reason"),
                "route_degraded": False,
                "partial": partial and not response.refused,
                "missing_information": (
                    ["未能在当前检索预算内补足全部证据"] if partial else []
                ),
                "agent_trace": state.get("node_trace", []),
            }
        )

    def _plan(self, state: AgentState) -> AgentState:
        question = state["question"]
        if "住宿" in question and ("报销" in question or "材料" in question):
            queries = ["差旅 住宿 标准 城市 上限", "出差 报销 提交期限 材料"]
        else:
            queries = [question]
        return {
            "pending_queries": queries,
            "node_trace": [*state["node_trace"], "plan"],
        }

    async def _retrieve(self, state: AgentState) -> AgentState:
        query = state["pending_queries"][0]
        pending = state["pending_queries"][1:]
        hits, _ = await self._rag.retriever.retrieve(query, state["scope"])
        by_id = {hit.chunk.id: hit for hit in state["hits"]}
        by_id.update({hit.chunk.id: hit for hit in hits})
        return {
            "pending_queries": pending,
            "queried": [*state["queried"], query],
            "hits": list(by_id.values()),
            "rounds": state["rounds"] + 1,
            "node_trace": [*state["node_trace"], "retrieve"],
        }

    @staticmethod
    def _after_retrieve(state: AgentState) -> Literal["retrieve", "assess"]:
        return "retrieve" if state["pending_queries"] else "assess"

    def _assess(self, state: AgentState) -> AgentState:
        return {"node_trace": [*state["node_trace"], "assess"]}

    @staticmethod
    def _after_assess(
        state: AgentState,
    ) -> Literal["synthesize", "rewrite", "partial"]:
        if state["hits"]:
            return "synthesize"
        if state["rounds"] >= state["max_rounds"]:
            return "partial"
        return "rewrite"

    def _rewrite(self, state: AgentState) -> AgentState:
        rewritten = f"{state['question']} 制度规定 第 {state['rounds'] + 1} 次检索"
        return {
            "pending_queries": [rewritten],
            "node_trace": [*state["node_trace"], "rewrite"],
        }

    @staticmethod
    def _synthesize(state: AgentState) -> AgentState:
        return {
            "exit_reason": "evidence_sufficient",
            "node_trace": [*state["node_trace"], "synthesize"],
        }

    @staticmethod
    def _partial(state: AgentState) -> AgentState:
        return {
            "exit_reason": "retrieval_budget_exhausted",
            "node_trace": [*state["node_trace"], "partial"],
        }


async def run_agentic_rag(
    rag: RagContainer, question: str, actor_id: str
) -> ChatResponse:
    return await AgenticRagGraph(rag).run(question, actor_id)
