# Agentic RAG 项目升级任务：给 Agent 补上 LLM 驱动

> 目的：把 `projects/agentic-rag` 的 Agent 层从“确定性规则”升级为“LLM 驱动”，补齐求职面试最容易被追问的三块：LLM 规划、工具调用循环、token 级流式。
>
> 用法：**每个任务自己动手写**。让 AI 做三件事——出验收标准、答疑、review 完成后的代码；不要让 AI 直接生成完整实现。每完成一个任务，把取舍写回对应教程章节（第 10、11、12 章），并更新项目 README 的进度与“未实现”清单。

## 开始前

```bash
cd projects/agentic-rag
uv sync
uv run pytest -q        # 44 个测试全绿后再动手
```

先读懂四个文件（都不长）：`app/agent_graph.py`、`app/answering.py`、`app/streaming.py`、`app/schemas.py`。

对照阅读专题文章：

- [LangGraph 状态机](./guide/agent-langgraph.md)：State 设计、条件边、recursion_limit
- [Tool Calling 与 MCP](./guide/agent-tool-calling.md)：工具协议、参数描述、失败处理矩阵
- [Agent 流式输出](./guide/agent-streaming.md)：事件协议、流中失败降级

**一条铁律**：所有新能力都要同时提供 `demo` 确定性实现（或 fake）和 `openai_compatible` 实现；自动化测试只跑确定性路径。这是这个项目离线可测的根基，不要为了接真实 LLM 破坏它。

---

## 任务 A：LLM 查询规划（替换 `_plan` 关键词规则）

**背景**：`app/agent_graph.py` 的 `_plan` 用硬编码关键词拆分子查询（“住宿”+“报销”→ 两个查询）。目标是让 LLM 输出结构化查询计划，同时保留规则实现作为 demo 路径和回退。

### A1 定义 QueryPlan 模型

- 动手：在 `app/schemas.py` 加 `QueryPlan`：`sub_queries: list[str]`、`needs_agent: bool`、`rationale: str | None`。校验：子查询非空、去重、数量上限（建议 ≤3，注释写明为什么）。
- 验收：
  - [ ] 单测：合法 JSON 能解析为模型；非法输入（空列表、超限）有明确行为且测试覆盖。

### A2 Provider 注入 planner

- 动手：定义 `QueryPlanner` Protocol（`plan(question, history) -> QueryPlan`）；demo 实现即把现有 `_plan` 的关键词规则搬进去；在 `build_container` 按 `APP_PROVIDER` 装配。
- 验收：
  - [ ] `APP_PROVIDER=demo` 下 `uv run pytest` 全绿（现有行为不变）。
  - [ ] 新增测试用 `FakePlanner` 断言 `node_trace` 与检索次数随计划变化。

### A3 真实 LLM 规划 + 回退

- 动手：`OpenAICompatiblePlanner` 用结构化输出（`response_format` json schema 或 json_object + Pydantic 校验）调用模型；超时、解析失败、内容拒绝时回退到规则实现。
- 验收：
  - [ ] `openai_compatible` 下手工验证：fixture 的“上海住宿上限 + 报销时限”被拆成两个子查询。
  - [ ] 回退路径有测试（fake 一个抛错的 planner）。
  - [ ] `agent_trace` 记录 planner 来源（`llm` / `rule` / `fallback`），可在调试端点观察。

---

## 任务 B：工具调用循环（function calling）

**背景**：图里没有任何 LLM 工具调用；`tools.py` 的版本工具是独立 REST 端点，`app/main.py` 路由到它时还标着 `route_degraded=True`。目标是让模型通过 tool_call 决定调用工具。

### B1 工具清单与 Schema

- 动手：定义 `AgentTool`：`name`、`description`、参数 JSON Schema、执行函数、统一 `ToolResult`（含稳定错误码分支，不泄漏内部信息）；附审计字段（tool name、duration、args 摘要）。
- 验收：
  - [ ] Schema 手工通过一次 OpenAI `tools` 参数校验。
  - [ ] `ToolResult` 错误分支有测试；权限校验在执行函数内（版本工具仅限管理员，沿用现有 access 逻辑）。

### B2 图内工具循环

- 动手：新增 `decide` 节点（`openai_compatible` 下带 `tools` 调 LLM；demo 下用确定性选择器）与 `tool_node`（执行并回灌 ToolMessage）；循环终止复用检索预算与 `recursion_limit`。
- 验收：
  - [ ] demo/fake 测试断言“V2 相比 V1 提高了多少”会走版本工具且终态正确。
  - [ ] 预算耗尽走 `partial` / `missing_information`，不会无限循环。
  - [ ] 无权限用户调工具被拒绝，测试覆盖。

### B3 摘除降级标记

- 动手：`main.py` 版本工具路由改为真正消费工具结果，删除 `route_degraded=True`。
- 验收：
  - [ ] `grep -rn route_degraded app/` 只剩 schemas 默认值 `False`。
  - [ ] `test_agent_graph.py` 补上工具路径用例。

---

## 任务 C：token 级流式

**背景**：`answer.delta` 事件一次性吐整段答案。目标是真实增量流式，并处理流中引用校验失败。

### C1 流式回答器

- 动手：`OpenAICompatibleAnswerer` 增加 `stream_answer()`（`stream=True`，逐段 yield）；demo provider 按句子切分模拟增量，保持离线可测。
- 验收：
  - [ ] 单测：demo 模式下所有 delta 拼接 == 完整答案。

### C2 SSE 协议适配

- 动手：`streaming.py` 让 `answer.delta` 携带真实增量；事件语义变化时 bump `schema_version` 并在文档注明；心跳与断连逻辑不动。
- 验收：
  - [ ] `test_streaming.py` 扩展通过：事件 id 连续、有终态事件。
  - [ ] `curl -N` 实测 token 逐段到达。

### C3 流中失败与引用校验

- 动手：终态前校验 claims；失败发结构化 `error` 事件（不泄漏内部栈与提示词）；对“已发出去的内容怎么办”给出策略并在注释写明取舍。
- 验收：
  - [ ] 注入坏回答的测试：客户端收到 `error` 事件且内容不含内部信息。

---

## 全部完成后

1. 重跑 `uv run pytest -q`、`uv run evals/run.py`；真实 LLM 下评测基线会变，与 demo 基线分开记录，不要混用口径。
2. 更新教程第 10、11、12 章的“本章交付与边界”与项目 README 的“仍未实现”清单。
3. 简历与口述稿同步改写：Agent 层现在是 LLM 驱动 + 确定性回退，这是面试里最好讲的一层取舍。
