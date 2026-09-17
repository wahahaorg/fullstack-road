---
title: LLM 与 Prompt 基础：从一次调用到可上线的模型接口
description: 面向 Python AI Agent 学习路线的第一块底座，解释模型调用、Prompt 结构、结构化输出、上下文、超时、重试、评测和进入 Agent 前的工程边界。
---

# LLM 与 Prompt 基础：从一次调用到可上线的模型接口

这篇是 [Python AI Agent 路线融合指南](./python-ai-agent-path) 的第一块底座。它回答一个容易被跳过、但上线时一定会回来补的问题：在做 Agent、RAG、Tool Calling 之前，一次普通 LLM 调用到底应该怎样被设计、约束、测试和观测。

先给结论：Prompt 不是神秘咒语，它是一个“给模型的接口契约”。你要把输入、角色、任务、输出格式、边界、失败策略写清楚；然后像测普通接口一样，持续用样例、Bad-case、日志和评测去验证它。

## 能力阶梯：先别急着上 Agent

很多 AI 应用可以分成四级：

| 级别 | 流程控制 | 适合场景 | 什么时候升级 |
|---|---|---|---|
| 单次调用 | 代码发一次请求 | 分类、摘要、改写、翻译、字段抽取 | 单次输出不稳定或需要固定流水线 |
| Prompt Chain | 代码按固定步骤调用多次 | 清洗、抽取、摘要、审核 | 步骤因输入不同而变化 |
| RAG | 代码先检索，再让模型回答 | 企业知识问答、政策查询 | 一次检索不够，需要多轮查证 |
| Agent | 模型参与决定下一步 | 查单、查政策、建工单、人工确认 | 需求确实有动态路径 |

这和 [Agent 工程总览](./agent-intro) 里的判断一致：只有“下一步做什么”需要模型在运行时决定，才需要 Agent。否则，固定 Chain 或 RAG 更容易测试，也更便宜。

## 一次 LLM 调用包含什么

一次模型调用至少有六个要素：

| 要素 | 工程含义 | 常见错误 |
|---|---|---|
| System 指令 | 定义角色、边界、输出规则 | 把业务数据塞进 System，导致难以复用 |
| User 输入 | 用户本次任务和上下文 | 不做长度控制，超出上下文窗口 |
| 模型参数 | 模型名、温度、top_p、max_tokens | 用高 temperature 做结构化抽取 |
| 输出协议 | JSON、Markdown、自然语言、函数参数 | 没有 schema，后端解析靠正则 |
| 超时与重试 | 网络和模型服务都可能慢或失败 | 默认超时过长，重试放大流量 |
| 观测字段 | trace_id、token、延迟、错误类型 | 出错后只剩“模型又胡说了” |

最小封装不要只返回字符串，至少返回内容、耗时、token、模型名和错误类型。后面做评测、成本控制和线上排查都靠这些字段。

## Prompt 的基本结构

一个可维护的 Prompt 通常分四段：

```text
角色与目标：
你是企业知识库问答助手。你的目标是基于给定资料回答用户问题。

输入说明：
资料在 <context> 中，用户问题在 <question> 中。资料可能不足或互相冲突。

规则：
1. 只能使用资料中的事实。
2. 资料不足时回答“无法根据现有资料判断”。
3. 不要编造政策、金额、日期、人名。
4. 输出必须是 JSON。

输出格式：
{
  "answer": "给用户看的回答",
  "citations": ["引用编号"],
  "confidence": "high | medium | low"
}
```

这四段分别负责“你是谁”“你看什么”“你不能做什么”“我要怎么解析你”。写 Prompt 时最容易漏的是第三段：边界和拒答规则。上线后大部分事故也发生在这里。

## Prompt 不是越长越好

长 Prompt 有三个代价：

- 成本更高：每次请求都要付输入 token。
- 延迟更高：模型要读更多上下文。
- 冲突更多：规则越多，互相打架的概率越高。

更好的写法是把 Prompt 拆成稳定规则和动态上下文。稳定规则放模板，动态上下文由代码拼装，并且限制长度：

```python
def build_prompt(question: str, chunks: list[Chunk]) -> list[dict]:
    context = "\n\n".join(
        f"[{i}] {chunk.title}\n{chunk.text[:1200]}"
        for i, chunk in enumerate(chunks[:5], start=1)
    )
    return [
        {"role": "system", "content": SYSTEM_RULES},
        {"role": "user", "content": f"<context>\n{context}\n</context>\n\n<question>{question}</question>"},
    ]
```

注意这里的截断不是随手切一刀，而是先限制 chunk 数，再限制单块长度。更完整的检索上下文控制见 [RAG 检索与重排](./rag-retrieval) 与 [RAG 引用与拒答](./rag-citation)。

## 结构化输出：能用 Schema 就别靠正则

只要输出要进入后端逻辑，就尽量让它结构化。比如工单分类：

```python
from pydantic import BaseModel, Field


class TicketLabel(BaseModel):
    category: str = Field(description="billing | bug | account | other")
    urgency: str = Field(description="low | medium | high")
    reason: str = Field(description="一句话说明判断依据")
```

模型输出后用 Pydantic 校验。如果校验失败，不要继续执行业务逻辑：

```python
try:
    label = TicketLabel.model_validate_json(raw_output)
except ValueError:
    # 记录原始输出和 trace_id，返回可恢复错误，必要时重试一次
    raise ModelOutputInvalid("模型输出格式不合法")
```

结构化输出的关键不是“看起来整齐”，而是让后端可以明确拒绝不合格结果。模型不是数据库，不能因为它给了字段名就默认可信。

## 温度、随机性和可复现

参数不用玄学化，先记住几条实践线：

| 任务 | temperature 建议 | 原因 |
|---|---|---|
| 分类、抽取、路由 | 0 到 0.2 | 需要稳定、可复现 |
| 问答、摘要 | 0.1 到 0.5 | 允许措辞变化，但事实要稳 |
| 创意写作 | 0.7 以上 | 多样性更重要 |
| 代码生成、SQL 生成 | 0 到 0.3 | 语法和约束优先 |

低温不代表一定正确，高温不代表一定聪明。温度只影响采样随机性，事实正确性主要依赖输入证据、任务拆分、输出约束和评测。

## 超时、重试与降级

模型调用是远程依赖，必须像调用支付、地图或短信服务一样设计失败路径。

```python
async def call_llm_with_boundary(payload: dict) -> ModelResult:
    try:
        return await llm_client.chat(payload, timeout=20)
    except TimeoutError as exc:
        raise ModelTimeout("模型调用超时") from exc
    except RateLimitError as exc:
        raise ModelBusy("模型限流") from exc
    except Exception as exc:
        raise ModelUnavailable("模型服务不可用") from exc
```

重试要克制：

- 只对网络抖动、限流、临时 5xx 重试。
- 不对 schema 校验失败无限重试，最多带格式错误提示重试一次。
- 写操作前的模型判断不能自动重试后直接执行，要保留人工确认或幂等保护。
- 设置整体超时，不要让每一层各自重试导致请求放大。

在 [Agent 生产可靠性](./agent-reliability) 里，这些会进一步扩展成预算、熔断、队列和降级策略。

## 幻觉不是一个问题，而是四类问题

“模型幻觉”这个词太宽了，排查时要拆开：

| 类型 | 表现 | 主要解法 |
|---|---|---|
| 证据不足还硬答 | 没资料也编政策 | 明确拒答规则、RAG 引用、答案必须绑定证据 |
| 输出格式乱 | JSON 少字段、多注释 | Schema 校验、错误反馈后重试一次 |
| 指令冲突 | 同时要求简短和详细 | 减少 Prompt 冲突，按优先级组织规则 |
| 工具参数乱 | 调不存在的工具或传错参数 | 工具白名单、参数校验、权限检查 |

不同类型要用不同工具解决。不要把所有问题都交给“再加一句 Prompt”。Prompt 能改善行为，但工程边界靠代码兜住。

## 从 Prompt 到评测

只要这个 Prompt 会长期使用，就要建立最小评测集。哪怕只有 20 条，也比完全凭感觉强。

评测集至少包含：

- 正常样例：用户最常见问题。
- 边界样例：信息不足、问题含糊、多个意图。
- 攻击样例：让模型忽略规则、泄露系统提示、编造来源。
- 业务 Bad-case：权限不够、证据冲突、外部工具超时。

每条样例记录：

| 字段 | 说明 |
|---|---|
| input | 用户输入 |
| context | 检索资料或业务上下文 |
| expected_behavior | 不是固定答案，而是必须满足的行为 |
| reject_when | 什么时候必须拒答 |
| tags | 分类、拒答、注入、权限、格式 |

评测不一定一开始就全自动。早期可以人工检查，但要固定样例和判据。后续再进入 [Agent 与 RAG 评测方法](./agent-eval) 和 [Agentic RAG 项目评测闭环](./agentic-rag-project-evaluation)。

## 什么时候进入 Agent

完成这篇后，不要立刻追框架。先用下面的问题判断：

- 这个需求是否只需要一次模型调用？
- 流程是否固定，能不能写成 Prompt Chain？
- 是否需要外部知识，如果需要，一次 RAG 是否足够？
- 模型输出是否会触发写操作或外部副作用？
- 失败时用户应该看到什么，系统应该记录什么？

只有当“路径会根据中间结果变化”时，再进入 [Agent 范式与框架选型](./agent-patterns)、[LangGraph 状态机](./agent-langgraph) 和 [Tool Calling 与 MCP](./agent-tool-calling)。

## 最小练习

建议你做一个“工单摘要与分类”小练习：

1. 输入一段用户投诉文本。
2. 输出 `category`、`urgency`、`summary`、`need_human` 四个字段。
3. 用 10 条样例测试正常、模糊、辱骂、信息不足、恶意提示注入。
4. 对 schema 失败、超时、限流分别设计返回。
5. 记录 trace_id、模型名、延迟、输入/输出 token 和错误类型。

做完这个练习，你就拥有了一个能迁移到 Agent、RAG、Text2SQL 的模型调用基线。

## 和外部路线的关系

[`umlink/python-ai-agent`](https://github.com/umlink/python-ai-agent) 把 Prompt 工程、大模型原理、Agent 范式、框架、RAG、MCP、评测、安全和部署放进八阶段学习路线。本站在这里先抽出最基础的一层：把一次 LLM 调用做成可约束、可观测、可评测的工程接口。正文为本站原创组织，不复制外部项目正文。
