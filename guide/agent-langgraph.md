---
title: LangGraph 状态机与 Checkpoint
description: 用状态图表达带分支、回环、中断与恢复的 Agent 流程，讲清 State 设计、Reducer、条件边、子图、Checkpointer 持久化与断点恢复。
---

# LangGraph 状态机与 Checkpoint

> Chain 只能一路向前。真实业务里到处是"校验没过要退回重试""信息不全要先追问""这一步失败了明天从断点接着跑"。这篇讲怎么用状态图把这些流程表达出来，以及为什么 State 设计做错会拖垮整个 Agent。

## 为什么 Chain 不够用

Chain（`prompt | llm | parser`）本质是函数组合，数据单向流动。如果你写过前端，它相当于 `Promise.then` 链——写起来很顺，但一旦需要"回到第二步再来一次"就没有语法能表达。真实需求几乎立刻会撞上四堵墙：

| 需求 | Chain 的困境 | 状态图的做法 |
|---|---|---|
| 按意图走不同流程 | 只能在一个函数里塞 `if`，链的结构消失了 | 条件边路由到不同节点 |
| 生成结果不合格要重新检索 | 单向流动，无法回退 | 加一条从校验节点回到检索节点的边 |
| 信息不全要先追问用户 | 只能抛异常中断，再从头跑一遍 | 中断在某个节点，下次从该节点继续 |
| 服务重启后接着跑 | 中间结果都在内存里，全丢 | Checkpointer 把每步状态落库 |

```mermaid
flowchart LR
    G0([START]) --> G1[理解]
    G1 -->|需要澄清| G5[追问]
    G1 -->|信息完整| G2[检索]
    G2 --> G3[生成]
    G3 --> G4{校验}
    G4 -->|不通过且未超次| G2
    G4 -->|通过| G6([END])
    G5 --> G6
```

对照一下 Chain 只能表达 `理解 → 检索 → 生成 → 输出` 这一条直线。LangGraph 提供的是上面这张图：**节点是你的函数，边是流转规则，State 是在节点之间传递的那个字典**。它不负责让模型变聪明，只负责把流程表达清楚、把状态存下来。如果你写过 Redux：State 相当于 store，节点是业务函数，节点返回值相当于 action 的 payload，而 LangGraph 的 Reducer 就是真正的 reducer——决定新返回值怎么合并进旧状态。

---

## 核心概念对照表

| 概念 | 是什么 | 类比 | 关键细节 |
|---|---|---|---|
| `StateGraph` | 图的构建器，绑定 State 类型 | Redux store 的 schema | `StateGraph(State)`，最后必须 `.compile()` |
| Node（节点） | 一个普通函数：`(state) -> dict` | 业务处理函数 | 只返回**要更新的字段**，不是整个 State |
| Edge（普通边） | A 跑完就跑 B | 固定的下一步 | `add_edge("a", "b")` |
| Conditional Edge | 由路由函数决定下一步 | `switch` / 路由表 | `add_conditional_edges(源, 路由函数, 映射表)` |
| `START` / `END` | 入口与出口的虚拟节点 | 程序的 main 与 return | `add_edge(START, "first")` |
| Reducer | 定义某个字段"新值怎么合并旧值" | Redux reducer | `Annotated[list, add]`，不写就是整体覆盖 |
| Checkpointer | 每步之后把 State 快照持久化 | 数据库里的会话表 | 决定能不能续聊、能不能断点恢复 |
| `thread_id` | 一条会话/一次任务的标识 | 会话 ID | 有 Checkpointer 时必传 |

最小骨架（`from langgraph.graph import StateGraph, START, END`，其余 import 见下一节）：

```python
class State(TypedDict):
    messages: Annotated[list, add_messages]   # 有 reducer：追加；不写 reducer 就是覆盖
    question: str

def understand(state: State) -> dict:
    return {"question": state["messages"][-1].content}   # 只返回需要更新的键

builder = StateGraph(State)
builder.add_node("understand", understand)   # 注册节点，名字后面路由要用
builder.add_edge(START, "understand")        # 入口
builder.add_edge("understand", END)          # 出口
graph = builder.compile()                    # 编译后才能 invoke / stream
graph.invoke({"messages": [{"role": "user", "content": "你好"}]})
```

---

## State 设计：整个 Agent 最该认真做的事

State 决定了节点之间能传什么、Checkpoint 存多大、并行时会不会冲突、多轮会话能不能续。**State 设计错了，后面所有问题都是它的症状。**

### TypedDict + Annotated Reducer

不带 Reducer 的字段是"覆盖"语义，带 Reducer 的字段是"合并"语义。

```python
import operator
from typing import Annotated, Literal
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages

class RetrievedDoc(TypedDict):
    doc_id: str; title: str; snippet: str; score: float   # snippet 只放片段不放全文

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]      # 追加 + 按 id 去重 + 格式归一
    intent: Literal["查订单", "退换货", "开发票", "闲聊"] | None   # 每轮重算，覆盖即可
    docs: Annotated[list[RetrievedDoc], operator.add]   # 并行检索都写它，需要合并语义
    retry_count: int                              # 计数器显式维护，别靠 recursion_limit
    answer: str
    verdict: Literal["pass", "need_retrieve", "reject"] | None
```

| Reducer | 行为 | 适用字段 |
|---|---|---|
| 不写（默认） | 新值整体覆盖旧值 | 意图、当前问题、最终答案、计数器 |
| `operator.add` | 列表拼接（`old + new`） | 检索结果、工具调用记录、日志 |
| `add_messages` | 追加 + 按消息 id 去重 + 支持 `RemoveMessage` 删除 | 会话历史 |
| 自定义函数 | 你说了算 | 需要去重、限长、按分数排序合并的场景 |

自定义 Reducer 的典型用途是**给字段自带上限**，这是防止 State 膨胀最省事的一招：

```python
def merge_docs(old: list[RetrievedDoc], new: list[RetrievedDoc]) -> list[RetrievedDoc]:
    """按 doc_id 去重、按分数降序、最多留 12 条。上限写在这里，任何节点都绕不过去"""
    merged = {d["doc_id"]: d for d in (old or [])}
    for d in new or []:
        if d["doc_id"] not in merged or d["score"] > merged[d["doc_id"]]["score"]:
            merged[d["doc_id"]] = d      # 多路检索命中同一文档时保留高分那条
    return sorted(merged.values(), key=lambda d: d["score"], reverse=True)[:12]
# 用法：docs: Annotated[list[RetrievedDoc], merge_docs]
```

### 什么该进 State，什么不该

判断标准只有一条：**它是否需要跨节点传递、并且值得被持久化。**

| 该进 State | 不该进 State | 替代方案 |
|---|---|---|
| 会话历史（裁剪后） | 上传文档的全文 | 存对象存储/数据库，State 只放 `doc_id` |
| 结构化意图与槽位 | 数据库 Session、Redis 连接、HTTP Client | 放依赖注入容器或模块级单例 |
| 检索片段摘要 + 引用信息、重试次数 | 检索/工具返回的原始大 JSON | 只挑模型真正要看的字段 |
| 用户 id、租户 id、权限范围 | 明文密钥、access token | 从请求上下文取，别落进 Checkpoint |

**踩坑：** Checkpointer 要序列化整个 State。放进 `AsyncSession` 或 `httpx.AsyncClient`，`MemorySaver` 下"看起来能跑"，一换 `PostgresSaver` 立刻序列化失败。State 里只放 JSON 能表达的东西。

### State 膨胀会怎么炸

不是"多占一点内存"这么温和，它有四个连锁后果：

- **Token 成本爆炸**：膨胀字段只要进提示词，每轮都要重发。30KB 全文跑 6 轮就是 180KB 输入。
- **Checkpoint 写放大**：在**每个节点之后**写一次快照，State 1MB × 10 个节点 ≈ 单次会话写 10MB。
- **续聊变慢**：每次 `invoke` 都要先反序列化最新 checkpoint；**超上下文**时报错发生在生成节点，根因却在几步之前。

三条防线建议全上：入口截断超大输入、Reducer 里写死条数上限、专门的裁剪节点删历史。裁剪节点的关键是用 `RemoveMessage`——它会真正把消息从历史和 Checkpoint 里移除，而不只是不发送：

```python
from langchain_core.messages import RemoveMessage

def trim_history(state: AgentState) -> dict:
    """保留最近 12 条消息；无需更新时返回空字典，比返回 None 更明确"""
    messages = state["messages"]
    return {} if len(messages) <= 12 else \
           {"messages": [RemoveMessage(id=m.id) for m in messages[:-12]]}
```

**生产推荐：** 给 State 定体积预算（序列化后 ≤ 64KB），在测试里加断言 `len(json.dumps(state)) < 65536`。

---

## 节点：纯函数、只返回增量、幂等

节点签名极简：`(state) -> dict`。但有三条纪律，违反任何一条都会在生产上咬人。

**纪律一：只返回要更新的字段。** 返回整个 State 会覆盖别的节点刚写的东西，也让 Checkpoint 体积翻倍。

**纪律二：不要原地修改传入的 state。** 原地改会完全绕过 Reducer，在并行和恢复时行为不可预测。

```python
# 反面：复制整个 state 再改 = 全字段覆盖；原地 append = 绕过 reducer
def bad_node(state: AgentState) -> dict:
    new = dict(state)
    new["answer"] = "..."
    state["docs"].append({"doc_id": "d1"})
    return new

# 正面：只声明这个节点负责的字段，列表字段交给 reducer 合并
def good_node(state: AgentState) -> dict:
    return {"answer": "...", "docs": [{"doc_id": "d1", "title": "t",
                                       "snippet": "s", "score": 0.9}]}
```

**纪律三：节点必须幂等。** 有 Checkpointer 时节点可能被重放（恢复、重试、人工介入后继续）。"写数据库""发消息""扣库存"这类副作用要么带幂等键，要么挪到专门的写入节点里配合确认流程。幂等键构造见 [工具幂等设计](./agent-tool-calling#幂等设计)，事务边界见 [并发、事务与一致性](./concurrency-transaction)。

节点一律用 `async def`、用 `ainvoke` / `astream` 驱动，因为检索和模型调用都是 IO 密集型：

```python
async def retrieve(state: AgentState) -> dict:
    """并发发起向量检索与关键词检索，结果交给 reducer 去重合并"""
    vec_docs, kw_docs = await asyncio.gather(
        vector_search(state["question"], top_k=8),
        keyword_search(state["question"], top_k=8))
    return {"docs": vec_docs + kw_docs}
```

节点粒度按"可观测边界"切：你希望在监控里单独看到耗时和失败率的那一步就是一个节点。太细会让图难读，太粗会让排查时只能看到"某个大节点慢了 8 秒"。经验值是一个节点对应一次外部调用。

---

## 条件边：分流、重试、澄清

`add_conditional_edges` 的三个参数是：**从哪个节点出发、用哪个函数决定去向、去向名到节点名的映射**。路由函数读 State，返回一个字符串（或字符串列表，表示并行走多条）。

```python
def route_by_intent(state: AgentState) -> str:
    """路由函数只做判断：不做业务、不改 State、不调模型"""
    intent = state["intent"]
    if intent in ("查订单", "退换货"):
        return "order_flow"
    return "kb_flow"           # 兜底分支必须有，否则遇到 None 会 KeyError

builder.add_conditional_edges(
    "understand",              # 从哪个节点出发
    route_by_intent,           # 路由函数
    {"order_flow": "order_subgraph", "kb_flow": "retrieve"},   # 返回值 → 目标节点名
)

# 形态二：校验失败回退重试（回环），用计数器兜底
def route_after_verify(state: AgentState) -> str:
    if state["verdict"] == "pass":
        return "done"
    if state["retry_count"] >= 2:        # 业务语义的上限，和 recursion_limit 是两回事
        return "fallback"                # 退回"保守答案 / 转人工"
    return "retry"

builder.add_conditional_edges("verify", route_after_verify,
                              {"done": END, "retry": "retrieve", "fallback": "handoff"})

# 形态三：并行扇出——返回列表，多个分支同时执行，结果靠 reducer 合并
builder.add_conditional_edges("understand", lambda s: ["retrieve_kb", "retrieve_faq"],
                              ["retrieve_kb", "retrieve_faq"])
```

**踩坑：** 并行分支写同一个**没有 Reducer** 的字段时会报 `InvalidUpdateError: At key 'xxx': Can receive only one value per step`，本质是并发写冲突，解决办法是给该字段加 Reducer 或让分支写不同字段。另外路由函数里不要调模型：它不产生 State 更新、链路里看不到，而且路由需要确定性——要用模型判断就单独做一个节点，把结果写进 State，路由函数只读这个字段。

---

## 循环与终止：别让图跑飞

有回环就有跑飞的风险。三重手段要同时用，它们拦的是不同类型的问题。

| 手段 | 拦什么 | 触发后表现 | 定位 |
|---|---|---|---|
| `recursion_limit` | 图结构性死循环（配置错、路由写错） | 抛 `GraphRecursionError` | 最后一道保险，不是业务语义 |
| 业务计数器（`retry_count`） | 正常重试次数用尽 | 走 fallback 分支，用户拿到保守回答 | 主要手段，可控可解释 |
| 整体墙钟超时 | 单步不慢但累积很慢 | 取消任务，返回"处理超时" | 保护用户体验和资源 |

```python
from langgraph.errors import GraphRecursionError

CONFIG = {"configurable": {"thread_id": "sess-1001"}, "recursion_limit": 25}  # 默认也是 25

async def run_agent(question: str) -> dict:
    payload = {"messages": [{"role": "user", "content": question}]}
    try:   # 墙钟超时用 asyncio 控制，和 recursion_limit 各管一件事
        return await asyncio.wait_for(graph.ainvoke(payload, CONFIG), timeout=55)
    except GraphRecursionError:               # 路由有 bug，要告警而不是静默兜底
        logger.error("recursion limit hit")
        return {"answer": "系统处理异常，已转人工。"}
    except asyncio.TimeoutError:
        return {"answer": "处理超时，请稍后重试或转人工。"}
```

计数器要**在被重试的节点里自增**（`return {"retry_count": state["retry_count"] + 1}`），别放在路由函数里改状态。

::: warning recursion_limit 不是"最多循环几次"
它统计的是整张图执行的**超步（superstep）**数量，一次并行扇出的多个节点算一个超步，所以它和"重试 2 次"之间没有直观换算关系。把它当成防止无限循环的熔断，业务上"最多重试几次"永远用 State 里的计数器表达。
:::

---

## 子图：主图管流程，子图管领域

当业务超过三四条分支，单张图会迅速变成谁都不敢改的意大利面。拆分原则很清晰：**主图只维护跨领域必须共享的东西**（会话历史、意图、用户与权限上下文、最终答案），**子图各自维护只有自己关心的中间证据**（订单子图存物流轨迹，知识库子图存检索片段，工单子图存表单草稿）。

```mermaid
flowchart TB
    U[理解意图 · 鉴权] --> R{意图路由}
    R -->|订单类| OG["订单子图<br/>取订单→查物流→判可退"]
    R -->|知识类| KG["知识库子图<br/>检索→生成→校验"]
    R -->|工单类| TG["工单子图<br/>填表→确认→提交"]
    OG --> M[汇总与合规校验]
    KG --> M
    TG --> M
    M --> E([END])
```

### 写法一：State 有共享键，直接把编译后的图当节点用

```python
class KBSubState(TypedDict):         # question/answer 与主图同名 → 自动映射
    question: str
    answer: str
    evidence: Annotated[list[RetrievedDoc], merge_docs]   # 只属子图，不污染主图

kb_subgraph = kb_builder.compile()   # 子图不要单独传 checkpointer，继承父图的即可
parent.add_node("kb", kb_subgraph)   # 编译后的图可以直接当节点用
```

主图的 `question` 自动传进子图，子图写回的 `answer` 自动合并回主图，`evidence` 留在子图——这就是我们要的隔离。

### 写法二：State 结构不同，用函数显式做映射

生产上更推荐这种，因为父子契约显式，改子图不会意外影响主图。

```python
async def call_order_flow(state: AgentState) -> dict:
    """显式映射：父 State → 子 State → 父 State，中间证据留在子图里不外泄"""
    sub_out = await order_subgraph.ainvoke({
        "order_id": state.get("slots", {}).get("order_id", ""),
        "user_id": state["user_id"],       # 权限上下文必须父图下传，不能让子图自己猜
        "question": state["question"],
    })
    # 只把结论和引用带回主图，物流原始轨迹等中间数据丢弃
    return {"answer": sub_out["conclusion"], "docs": sub_out.get("citations", [])}

parent.add_node("order", call_order_flow)
```

| 对比项 | 直接当节点 | 函数映射 |
|---|---|---|
| 父子耦合 | 靠同名键隐式耦合 | 契约显式，改动可控 |
| 状态隔离 | 共享键自动同步 | 完全由你决定带回什么 |
| 流式与 Checkpoint | 天然贯通，可 `stream(subgraphs=True)` | 子图事件默认不外传，需自己转发 |
| 适用场景 | 主子结构相近的小拆分 | 领域边界清晰、多人分工维护 |

**生产推荐：** 主图 State 字段数控制在 10 个以内，超过说明领域没拆干净。多 Agent（角色分工、互相调用）与人工审批的组织方式见 [多 Agent 协作与人工介入](./agent-multi-agent)。

---

## Checkpointer：多轮续聊与断点恢复

Checkpointer 在**每个节点执行完之后**把 State 快照写下来，于是你免费得到三件事：多轮会话、断点恢复、时间旅行调试。如果你写过后端：它就是把"会话表 + 任务状态表"这套你本来要手写的东西标准化了，而 `thread_id` 是这张表的业务主键。

### MemorySaver vs PostgresSaver

| 维度 | `MemorySaver` | `PostgresSaver` / `AsyncPostgresSaver` |
|---|---|---|
| 存储位置 | 进程内存，重启即丢 | PostgreSQL 表，重启保留 |
| 多实例部署 | 各实例不共享，续聊会串味 | 共享，任意实例都能续上 |
| 需要建表 | 否 | 首次需要 `setup()` 建表 |
| 适用 | 单测、本地开发、脚本 | 生产 |

生产上用异步版本，并且**在应用启动时编译一次、全程复用**（放进 FastAPI 的 `lifespan`）：

```python
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

DB_URI = "postgresql://user:pwd@127.0.0.1:5432/agent?sslmode=disable"

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncPostgresSaver.from_conn_string(DB_URI) as checkpointer:
        await checkpointer.setup()          # 幂等：首次创建 checkpoints 等表
        app.state.graph = builder.compile(checkpointer=checkpointer)   # 全局编译一次
        yield                               # 应用运行期间持有同一个连接池
```

**踩坑：** 每个请求都 `builder.compile()` 一次不会报错，但会反复建连接池，QPS 一上来就耗尽数据库连接。lifespan 与依赖注入见 [FastAPI 进阶](./fastapi-advanced)。

### thread_id：一条会话的身份

`thread_id` 决定"这次执行接在谁的历史后面"。有 Checkpointer 却不传它会直接报错。

```python
config = {"configurable": {"thread_id": "conv-8f21", "user_id": 1001}}
await graph.ainvoke({"messages": [{"role": "user", "content": "订单 A1001 到哪了"}]}, config)
# 第二轮只传新消息，历史由 Checkpointer 自动装载
await graph.ainvoke({"messages": [{"role": "user", "content": "那能退吗"}]}, config)
```

| 场景 | thread_id 怎么取 |
|---|---|
| 聊天会话 | 会话 id（前端创建或后端返回给前端保存） |
| 一次批处理任务 | 任务 id，天然支持失败后断点续跑 |
| 同一用户多个独立话题 | 一话题一个 thread_id，避免上下文串味 |
| 压测 / 评测 | 每条样本一个随机 thread_id，互不干扰 |

::: warning 别把 user_id 当 thread_id
用户会同时问不同的事。用 user_id 当 thread_id 意味着所有话题挤在一条历史里，既涨 token 又互相干扰。`configurable` 里可以同时放 `thread_id` 和 `user_id`，节点通过 `RunnableConfig` 读取后者做权限控制。
:::

### 读状态、改状态、断点恢复

```python
snapshot = await graph.aget_state(config)   # 读当前状态
print(snapshot.values["retry_count"], snapshot.next)   # next 为空元组表示已结束

async for st in graph.aget_state_history(config):      # 时间旅行：逐步快照
    print(st.config["configurable"]["checkpoint_id"], st.next)

await graph.aupdate_state(config, {"intent": "退换货"}, as_node="understand")  # 人工修正
await graph.ainvoke(None, config)           # 输入传 None = 从上次中断处继续
```

**断点恢复的真实用法**：某节点因为下游接口 500 抛异常，这次 `invoke` 失败了。Checkpointer 已经把失败节点**之前**的状态存好，你用同一个 `thread_id` 再 `ainvoke(None, config)`，它就从失败的那个节点重新开始——前面的检索和模型调用都不重跑。这对"每步都要花几秒和几分钱"的 Agent 是实打实的省钱。但要注意 Checkpoint 表会无限增长，上线时就要定清理策略：按 `thread_id` 保留最近 N 个 checkpoint，或按更新时间删除 30 天前的会话（`checkpointer.adelete_thread(thread_id)` 删整条）。

---

## interrupt：把人塞进流程里

Checkpointer 存在的另一个收益是"能停下来等人"。写入类操作、金额相关操作、对外发消息，都应该在执行前停一下。

```python
from langgraph.types import interrupt, Command

def confirm_refund(state: AgentState) -> dict:
    """interrupt 抛出中断并保存现场，恢复后它的返回值就是外部传入的 resume 值"""
    decision = interrupt({"action": "refund", "order_id": state["slots"]["order_id"],
                          "amount": state["slots"]["amount"]})
    if decision != "approved":
        return {"verdict": "reject", "answer": "已取消退款申请。"}
    return {"verdict": "pass"}

result = await graph.ainvoke({"messages": [...]}, config)   # 跑到该节点就停住
print(result["__interrupt__"][0].value)                     # 推给前端做确认弹窗
await graph.ainvoke(Command(resume="approved"), config)     # 人工同意后从中断处继续
```

编译时用 `interrupt_before=["do_refund", "create_ticket"]` 可声明静态断点，适合"所有写入节点前一律审批"这类统一策略。

**踩坑：** `interrupt` 依赖 Checkpointer，没有它会报错——现场存不下来自然无法恢复。另外恢复时**当前节点从头重跑**，所以 `interrupt` 之前不要写有副作用的代码。审批流的完整设计（谁审、超时、留痕、多级审批）见 [多 Agent 协作与人工介入](./agent-multi-agent)。

---

## 流式输出的三种 stream_mode

`stream_mode` 决定你从图里拿到什么粒度的事件，选错会让前端很难做：

| 模式 | 每次产出 | 典型用途 | 数据量 |
|---|---|---|---|
| `values` | 每个超步后的**完整 State** | 调试、需要整体快照 | 大（State 越大越夸张） |
| `updates` | 每个节点返回的**增量字典** | 给前端推进度（"正在检索…"） | 小 |
| `messages` | LLM 逐 token 输出 + 元数据 | 打字机效果 | 中，但事件频繁 |
| `custom` | 节点内 `get_stream_writer()` 写的数据 | 自定义进度、引用逐条推送 | 可控 |

```python
# 生产常用组合：进度用 updates，正文用 messages（传列表时产出 (mode, chunk) 元组）
async for mode, chunk in graph.astream(payload, config,
                                       stream_mode=["updates", "messages"]):
    if mode == "updates":
        yield sse_event("progress", {"node": next(iter(chunk))})   # 哪个节点刚跑完
    else:
        token, meta = chunk
        if token.content and meta.get("langgraph_node") == "generate":
            yield sse_event("token", {"text": token.content})      # 只推正文节点的 token
```

SSE 协议细节、断连重连、取消与背压见 [Agent 流式输出](./agent-streaming)。

---

## 完整示例：理解 → 检索 → 生成 → 校验（失败回检索，最多 2 次）

场景是某企业知识库问答：理解问题并改写检索式 → 检索证据 → 生成带引用的答案 → 校验答案是否真有证据支撑；不合格就带着"缺什么"回到改写，最多两次。

```python
import asyncio
from typing import Annotated, Literal
from typing_extensions import TypedDict
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages

llm = ChatOpenAI(model="qwen-plus", temperature=0, timeout=20, max_retries=0)

class KBState(TypedDict):                    # Doc 与 merge_docs 沿用前面小节的定义
    messages: Annotated[list, add_messages]
    query: str                                   # 改写后的检索式
    missing: str                                 # 校验节点指出"还缺什么信息"
    docs: Annotated[list[Doc], merge_docs]       # 自带去重与条数上限
    answer: str
    verdict: Literal["pass", "need_retrieve"] | None
    retry_count: int

class Verification(BaseModel):               # 结构化校验结论，供路由函数直接消费
    grounded: bool = Field(description="答案中每个结论是否都能在给定资料里找到依据")
    missing: str = Field(default="", description="若不成立，说明还需要检索什么信息")

async def understand(state: KBState) -> dict:
    """改写检索式；重试时把 missing 一起喂进去，让检索式换个角度"""
    hint = f"上一轮缺少的信息：{state['missing']}" if state.get("missing") else ""
    rewritten = await llm.ainvoke(
        f"把用户问题改写成检索关键词，只输出关键词。{hint}\n"
        f"问题：{state['messages'][-1].content}")
    return {"query": rewritten.content}

async def retrieve(state: KBState) -> dict:
    """真实项目这里是混合检索 + 重排；权限和有效期过滤必须在这一层做掉"""
    hits = await hybrid_search(state["query"], top_k=5)        # 返回 list[Doc]
    return {"docs": hits, "retry_count": state["retry_count"] + 1}

def _context(docs: list[Doc]) -> str:
    return "\n\n".join(f"[{i}] {d['title']}：{d['snippet']}" for i, d in enumerate(docs, 1))

async def generate(state: KBState) -> dict:
    """带编号的证据进提示词，要求答案标注引用，方便下一步校验"""
    answer = await llm.ainvoke(
        f"只依据资料回答，每个结论后标注 [编号]；资料不足就直说。\n\n"
        f"资料：\n{_context(state['docs'])}\n\n问题：{state['messages'][-1].content}")
    return {"answer": answer.content}

async def verify(state: KBState) -> dict:
    """判断答案是否有证据支撑，这是抑制幻觉最划算的一道工序"""
    result = await llm.with_structured_output(Verification).ainvoke(
        f"资料：\n{_context(state['docs'])}\n\n待校验答案：\n{state['answer']}\n\n"
        f"判断答案中的每个结论是否都能在资料中找到依据。")
    return {"verdict": "pass" if result.grounded else "need_retrieve",
            "missing": result.missing}

async def finalize(state: KBState) -> dict:
    return {"messages": [{"role": "assistant", "content": state["answer"]}]}

async def fallback(state: KBState) -> dict:
    """重试用尽：给保守回答并引导转人工，绝不硬编一个没证据的答案"""
    return {"messages": [{"role": "assistant", "content": "现有资料不足以确认，建议人工核实。"}]}

def route_after_verify(state: KBState) -> str:
    if state["verdict"] == "pass":
        return "ok"
    if state["retry_count"] >= 2:      # 已经检索两次还不达标，停止回环
        return "give_up"
    return "again"

builder = StateGraph(KBState)
for name, fn in [("understand", understand), ("retrieve", retrieve), ("generate", generate),
                 ("verify", verify), ("finalize", finalize), ("fallback", fallback)]:
    builder.add_node(name, fn)
for a, b in [(START, "understand"), ("understand", "retrieve"),
             ("retrieve", "generate"), ("generate", "verify"),
             ("finalize", END), ("fallback", END)]:
    builder.add_edge(a, b)
builder.add_conditional_edges("verify", route_after_verify, {
    "ok": "finalize",
    "again": "understand",        # 回环：带着 missing 重新改写检索式再检索
    "give_up": "fallback",
})
graph = builder.compile(checkpointer=MemorySaver())   # 生产换成 AsyncPostgresSaver

async def main():
    config = {"configurable": {"thread_id": "demo-1"}, "recursion_limit": 20}
    state = await graph.ainvoke(
        {"messages": [{"role": "user", "content": "试用期离职需要提前几天通知？"}],
         "retry_count": 0, "docs": [], "missing": "", "verdict": None},   # 初始化要给全
        config)
    print(state["messages"][-1].content, state["retry_count"], state["verdict"])

asyncio.run(main())
```

::: details 为什么回环回到 understand 而不是直接回 retrieve
回到 `understand` 才有机会**换检索式**。直接回 `retrieve` 用同样的 query 再查一遍，结果几乎一定相同，重试就是纯浪费。通用原则：**重试必须改变输入，否则不要重试。**另外初始输入要把带 Reducer 的字段和计数器初始化好，`retry_count` 缺失时 `state["retry_count"] + 1` 会 `KeyError`；更稳的做法是加一个入口节点统一初始化 State。
:::

---

## 调试与可观测

Agent 出问题时最贵的成本是"不知道哪一步坏了"。三样东西必须在上线前就有。

### 节点耗时与失败率

用一个装饰器统一埋点（`import time, functools, logging` 略），比在每个节点里写日志靠谱：

```python
def observe(name: str):
    """给节点加耗时打点；结构化字段方便在日志平台按节点聚合"""
    def deco(fn):
        @functools.wraps(fn)
        async def wrapper(state, *args, **kw):
            t0 = time.perf_counter()
            try:
                return await fn(state, *args, **kw)
            finally:
                logger.info("node done", extra={
                    "node": name, "retry": state.get("retry_count"),
                    "cost_ms": round((time.perf_counter() - t0) * 1000, 1)})
        return wrapper
    return deco

builder.add_node("retrieve", observe("retrieve")(retrieve))
```

**生产推荐：** 至少记这几个维度——`thread_id`、节点名、耗时、是否重试、本轮 token 消耗、检索命中数。有了它们，"P95 延迟被哪个节点拖的"才有答案。

### State 快照与图结构

```python
# 时间旅行：把每一步快照打出来对照，比读日志文字快得多
async for st in graph.aget_state_history(config):
    print(st.next, {k: v for k, v in st.values.items() if k != "messages"})

print(graph.get_graph().draw_mermaid())   # 导出图结构，贴进 PR 一眼看出回环写错没
```

把某个历史 `checkpoint_id` 塞进 config 还能从那一步分叉重跑，用来验证"如果检索结果不同，答案会不会对"。

### 常见报错对照

| 报错 | 原因 | 处理 |
|---|---|---|
| `Checkpointer requires ... thread_id` | 编译时传了 checkpointer，调用时没给 thread_id | 在 `configurable` 里补上 |
| `InvalidUpdateError: Can receive only one value per step` | 并行分支写同一个无 Reducer 的字段 | 加 Reducer，或让分支写不同字段 |
| `GraphRecursionError` | 回环没有出口，或路由条件写反 | 检查路由；确认计数器真的在自增 |
| 路由 `KeyError` | 路由函数返回了映射表里没有的键 | 映射表加兜底分支 |
| 换 PostgresSaver 后序列化失败 | State 里放了连接、客户端等对象 | State 只放可 JSON 序列化的数据 |

效果层面的回归（改了提示词之后答得更好还是更差）不靠人眼看，要有评测集，见 [Agent 效果评测](./agent-eval)。

---

## 面试高频问题

### 1. 为什么用状态图而不是 Chain？

- Chain 是函数组合，数据单向流动，无法表达回退、中断、恢复。
- 四类真实需求逼你换：意图分流、校验失败重试、信息不全先追问、失败后断点续跑。
- 状态图三要素：节点是函数、边是流转规则、State 是节点间传递并被持久化的数据。
- 附加收益：节点是天然的可观测边界，能单独看耗时和失败率。但别过度设计——流程真的是线性的，Chain 更省事。

### 2. State 该怎么设计？膨胀了会怎样？

- 进 State 的标准：需要跨节点传递，且值得被持久化。
- 不该进：文档全文、数据库 Session / HTTP Client 等不可序列化对象、日志缓冲、密钥。大对象用 `doc_id` 引用代替。
- 膨胀的四个后果：输入 token 每轮重发、每个节点写一次快照造成写放大、续聊反序列化变慢、最终撞上下文上限。
- 三条防线：入口截断超大输入、Reducer 里写死条数上限、裁剪节点用 `RemoveMessage` 删历史。
- 定体积预算（序列化后 ≤ 64KB）并在测试里加断言，能拦住绝大多数问题。

### 3. Reducer 是什么？不写会怎样？

- Reducer 定义"节点返回的新值如何与旧值合并"，不写就是整体覆盖。
- `operator.add` 列表拼接；`add_messages` 追加 + 按 id 去重 + 支持 `RemoveMessage` 删除；自定义 Reducer 可以自带去重、排序和条数上限。
- 并行分支写同一个无 Reducer 字段会报 `InvalidUpdateError`，本质是并发写冲突。
- 反例：节点里 `state["docs"].append(...)` 原地修改会完全绕过 Reducer。

### 4. Checkpointer 解决什么问题？thread_id 是什么？

- 每个节点后把 State 快照落库，于是免费得到多轮续聊、断点恢复、时间旅行调试。
- `thread_id` 是一条会话或一次任务的标识，决定这次执行接在谁的历史后面；有 Checkpointer 时必传，且别拿 user_id 当它。
- `MemorySaver` 只适合单测和本地；生产用 `AsyncPostgresSaver`，多实例才能共享会话。
- 断点恢复：失败后用同一 `thread_id` 调 `ainvoke(None, config)`，从失败节点继续，前面的检索和生成不重跑。
- 工程细节：图在启动时编译一次复用；Checkpoint 表必须有清理策略。

### 5. 怎么保证带回环的图不会跑飞？

- 三重手段各管一层：`recursion_limit` 熔断结构性死循环，State 里的业务计数器控制重试次数，`asyncio.wait_for` 控整体墙钟。
- `recursion_limit` 统计的是超步数，不等于"循环几次"，只当保险不当业务语义。
- 计数器在被重试的节点里自增，不要在路由函数里改状态。
- 重试必须**改变输入**（换检索式、补充缺失信息），否则结果不变，纯浪费钱；重试用尽走 fallback 给保守回答或转人工。

### 6. 什么时候拆子图？人工介入怎么落地？

- 分支超过三四条、或多人分工维护不同领域时拆子图。
- 主图只留跨领域共享字段（历史、意图、权限、最终结果），子图各管自己的中间证据；只把结论和引用带回主图。
- 两种接法：编译后的子图直接当节点（同名键自动映射，省事但隐式耦合）；函数显式映射父子 State（契约清晰，推荐）。子图不要单独传 Checkpointer。
- 人工介入用 `interrupt(payload)` 保存现场、`Command(resume=值)` 继续；统一策略可用编译期 `interrupt_before`。它强依赖 Checkpointer，且恢复时当前节点从头重跑，所以 `interrupt` 之前不能有副作用。
