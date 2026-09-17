---
title: Agent 框架生态与进阶能力：选型边界与全局图谱
description: LangChain、LangGraph、LlamaIndex、CrewAI、AutoGen 的适用边界，以及 ReAct、Plan-and-Execute、MCP、记忆、多智能体等进阶能力的全局图谱。
---

# Agent 框架生态与进阶能力：选型边界与全局图谱

这篇覆盖 [Python AI Agent 路线融合指南](./python-ai-agent-path) 的阶段二核心：主流框架的选型边界，以及 ReAct、Plan-and-Execute、MCP、记忆、多智能体等进阶能力的全局图谱。它对应外部 `python-ai-agent` 项目的阶段三（主流 Agent 开发框架）与阶段五（进阶技术）。

读这篇前建议先读 [LLM 与 Prompt 基础](./llm-prompt-foundations)：框架的一切 API 都在封装"一次 LLM 调用 + 一次工具调用"的组合，不清楚底层就看不懂框架在做什么。

## 选型的第一原则

先回答三个问题，再选框架：

1. **下一步由谁决定**：代码决定（工作流 / Prompt Chain），还是模型决定（Agent）？
2. **状态放哪里**：内存、checkpoint、数据库？失败后能否恢复？
3. **要不要多智能体**：单 Agent 能否解决？多智能体是复杂度倍增器，不是能力倍增器。

大多数"AI 功能"其实是 Prompt Chain 或固定工作流，真正需要模型自主决定路径的 Agent 是少数。这也是 [Agent 范式与框架选型](./agent-patterns) 反复强调的判断。

## 主流框架的适用边界

| 框架 | 定位 | 适合 | 不适合 |
|---|---|---|---|
| LangGraph | 状态图编排，Agent 开发事实标准 | 生产级 Agent：可恢复、可观测、可控流程 | 简单一次性调用（杀鸡用牛刀） |
| LangChain | 组件库：模型接入、工具、向量库适配 | 快速接模型、复用工具/检索组件 | 复杂控制流（用它底层组件 + LangGraph） |
| LlamaIndex | 数据感知型框架 | RAG 数据层：索引、检索、文档解析 | 复杂多 Agent 编排 |
| CrewAI | 多智能体快速开发 | 原型验证、角色分工明确的协作任务 | 生产系统（状态与恢复能力弱） |
| AutoGen | 微软多智能体框架 | 研究探索、对话式多 Agent 实验 | 生产工程化（迭代快，API 不稳定） |

本站主线的默认选择：**LangGraph 编排 + LangChain 组件 + LlamaIndex 做 RAG 数据层（可选）**。理由是 LangGraph 的 `StateGraph` 能显式表达节点、边和条件路由，配合 checkpointer 天然支持断点恢复，这对生产系统的可测试、可观测是刚需。详见 [LangGraph 状态图](./agent-langgraph)。

## 手搭一个最小 Agent：理解框架封装了什么

下面用 LangGraph 搭一个最小 ReAct 循环（思考 → 调工具 → 看结果 → 再思考 → 总结）。框架 API 会变，这个循环结构不会：

```python
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(model="gpt-4o-mini").bind_tools([get_weather, calculator])

def think(state: MessagesState):
    return {"messages": [llm.invoke(state["messages"])]}

def should_continue(state: MessagesState):
    last = state["messages"][-1]
    return "tools" if last.tool_calls else END

graph = (
    StateGraph(MessagesState)
    .add_node("think", think)
    .add_node("tools", ToolNode([get_weather, calculator]))
    .add_edge(START, "think")
    .add_conditional_edges("think", should_continue)
    .add_edge("tools", "think")  # ← 这条边构成循环
    .compile()
)
```

三个关键点对应了 [Tool Calling 与 MCP](./agent-tool-calling) 的核心：

- `bind_tools` 自动把函数签名转成 JSON Schema 给模型——工具的 docstring 决定模型何时调用它。
- `should_continue` 是"下一步由谁决定"的具体实现：读最后一条消息的 `tool_calls`，有就回工具，没有就结束。
- `tools → think` 这条边就是"循环"本身。没有循环，就只是单次工具调用的工作流。

不依赖框架手写同一循环的方式见 [Agent 工程总览](./agent-intro)；两者的对照能帮你看见框架省掉了什么、藏掉了什么。

## 进阶能力图谱

这些能力按"生产需要才加"的顺序排列，不要一次全上：

### Plan-and-Execute 与反思

ReAct 是"想一步做一步"，复杂任务可以先规划再执行（Plan-and-Execute），或执行后自我评估再修正（Reflexion）。代价是更多 LLM 调用、更长延迟。只有当任务确实需要多步规划且 ReAct 表现不稳时才引入。范式详解见 [Agent 范式与框架选型](./agent-patterns)。

### 上下文工程

Agent 越跑上下文越长，成本和错误率同步上升。工程手段：

- **压缩**：历史消息超过阈值时摘要压缩，保留关键决策和工具结果。
- **隔离**：子任务放进独立上下文（子 Agent 或独立调用），只回传结论。
- **检索**：长期知识不放上下文，放外部存储按需取。

详见 [Agent 上下文工程](./agent-context)。

### 记忆

| 类型 | 放什么 | 落地 |
|---|---|---|
| 短期记忆 | 当前会话消息 | 状态 + checkpointer |
| 长期记忆 | 跨会话的用户偏好、事实 | 向量库 / KV 存储，按需检索注入 |
| 程序性记忆 | 系统提示词、工具使用经验 | 版本化管理的 prompt 与规则文件 |

### MCP（Model Context Protocol）

MCP 解决的问题是**工具接入的标准化**：过去每个 Agent 自己定义工具协议，现在工具方实现一次 MCP server，所有支持 MCP 的 Agent 都能用。它改变的是工具生态的分发方式，不改变工具调用的本质——模型看到 schema、生成参数、宿主执行。见 [Tool Calling 与 MCP](./agent-tool-calling)。

### 多智能体

拆多 Agent 的合理理由：职责边界清晰（如"检索员 + 审核员"）、需要独立上下文隔离、需要并行。不合理理由：单 Agent 上下文太长（先做压缩）、想让系统"更智能"（多半更乱）。落地时先定三件事：分工边界、共享状态的所有权、任务仲裁规则。见 [多 Agent 系统](./agent-multi-agent)。

### 结构化输出与评测

进阶能力的收尾都是这两件事：模型输出进入系统边界前必须过结构化校验（Pydantic / JSON Schema + 失败重试）；每次加能力都跑评测集对比，没有评测的"提升"无法验证。见 [LLM 与 Prompt 基础](./llm-prompt-foundations) 的最小评测集与 [Agent 评测](./agent-eval)。

## 框架学习的底线

无论选哪个框架，学完要能回答：

- 下一步由代码决定还是模型决定？在哪里配置？
- 状态保存在哪里？进程重启后能恢复吗？
- 工具调用前后，权限、参数、副作用分别在哪校验？
- 框架挂了/不维护了，哪些逻辑能迁出来？

框架 API 变化很快，稳定的是这四问对应的能力层：循环、状态、工具、边界校验。

## 阶段自检

- 你能不看教程，手画出上面最小 Agent 的状态图吗？
- 给你一个新需求，你的第一个判断是工作流还是 Agent？依据是什么？
- CrewAI 和 LangGraph 你会分别用在什么场景，为什么？
- 你的 Agent 上下文超过 20 轮后，成本和正确率怎么控制？

## 下一步

- [RAG 入库链路](./rag-pipeline)：进入 [Python AI Agent 路线融合指南](./python-ai-agent-path) 的阶段三。
- [LangGraph 状态图](./agent-langgraph)：把本篇的最小循环扩展成生产状态图。
- [Agent 上下文工程](./agent-context)、[Agent 多 Agent 系统](./agent-multi-agent)：按需深入的进阶能力。

## 来源与授权说明

本篇吸收并改写自 [umlink/python-ai-agent](https://github.com/umlink/python-ai-agent) 阶段三（主流 Agent 开发框架）与阶段五（进阶技术）的主题结构，已取得作者授权。原项目采用 [MIT License](https://github.com/umlink/python-ai-agent/blob/main/LICENSE)。
