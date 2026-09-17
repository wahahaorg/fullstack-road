---
title: 企业知识库 Agentic RAG 实战（十二）：SSE 流式事件协议
description: 设计节点进度、检索、Token、引用、人工确认、错误与完成事件，支持心跳、序号、取消和有限断线恢复。
---

# 企业知识库 Agentic RAG 实战（十二）：SSE 流式事件协议

> Agentic RAG 可能经历规划、多轮检索和工具调用。如果前端只等一个最终 JSON，用户无法判断系统是在工作、等待确认还是已经卡住。本章用 SSE 暴露稳定业务事件，而不是把后端日志直接流给浏览器。

## 当前项目边界

配套项目已经提供 `POST /api/chat/stream`：它发送版本化 Envelope、递增 `id`、`run.started`、节点完成、`answer.delta`、经过普通回答校验后的 `citation` 和 `run.completed`/`run.failed`。当前 Demo 是请求内生成器，没有持久事件表、Last-Event-ID 重放、心跳、取消或 Token 级模型流；下面这些协议约束是接入生产事件总线时的实现清单。

通用设计见 [SSE 流式与阶段事件协议](./agent-streaming) 与 [FastAPI 进阶 · 流式响应](./fastapi-advanced#流式响应sse)。本篇是**项目落地协议**：事件名更细、终态更明确，并刻意把「断开连接」和「取消运行」拆开。

## 用户看到的是可理解的执行过程

提交复杂问题后，客户端收到：

```text
event: run.started
id: 1
data: {"run_id":"run-123","route":"agentic_rag","schema_version":"1"}

event: node.progress
id: 2
data: {"node":"plan","message":"已拆分为 2 个检索目标"}

event: retrieval.completed
id: 3
data: {"query":"上海 住宿上限","source_count":2}

event: answer.delta
id: 4
data: {"text":"上海住宿每人每晚上限为"}

event: citation
id: 5
data: {"source_id":"S1","document_id":"doc-travel-v2"}

event: run.completed
id: 6
data: {"finish_reason":"success"}
```

页面可以分别渲染进度、正文和来源，不需要解析“正在检索……”这种混在答案里的自然语言。

## 为什么选 SSE

当前交互主要是客户端发起一次请求，服务器持续单向推送状态和文本。SSE 基于 HTTP，浏览器原生支持事件流，经过反向代理也容易观测。WebSocket 更适合高频双向通信，但会增加连接状态和协议维护。

人工审批和取消通过普通 HTTP 接口提交，流只负责接收事件。这个组合让写操作继续使用明确的鉴权、幂等和状态码。

如果未来出现实时协同编辑或持续双向语音，再单独评估 WebSocket，不为尚未出现的需求提前更换传输层。选型细节与代理兼容性见 [agent-streaming](./agent-streaming)。

## 协议对照：概念篇 vs 本项目

[agent-streaming](./agent-streaming) / [fastapi-advanced](./fastapi-advanced#流式响应sse) 用一套**通用阶段协议**：`stage`、`token`、`citation`、`tool_call`、`interrupt`、`error`、`done`。本项目把它落到 Run 生命周期上，事件名带业务语义，方便前端按状态机分支，也方便审计按类型过滤。

| 概念篇事件 | 本项目事件 | 映射说明 |
|---|---|---|
| `stage`（`understanding` / `retrieving` / `tool_calling` / `generating` / `verifying`） | `run.started`、`node.started` / `node.progress` / `node.completed`、`retrieval.completed` | 概念篇用粗粒度阶段文案；本项目用节点与检索结果表达同一进度 |
| `token` | `answer.delta` | 都是增量正文；本项目禁止透传供应商原始 Chunk |
| `citation` | `citation` | 名称相同；本项目要求**校验通过后才发**，见第 8 章 |
| `tool_call` | `tool.started` / `tool.completed` | 拆成起止，便于计时与失败卡片 |
| `interrupt` | `run.waiting_for_human` | 人工审批 / 确认卡片 |
| （无直接对应） | `run.warning` | Rerank 降级等非致命问题，不终止 Run |
| `error` | `run.failed` | 失败即终态；概念篇常再跟 `done` |
| `done` | `run.completed` | 成功、部分回答、拒答、取消都走完成终态，靠 `finish_reason` 区分 |

两套名字可以并存：概念篇教「阶段事件」怎么设计；本篇钉死本仓库对外契约。前端适配器可以做一层映射（例如把 `answer.delta` 接到原来的 `token` handler），但**服务端只发本表右侧事件**，避免同一连接混用两套名字。

未知 `event` 前端忽略；协议版本走 Envelope 的 `schema_version`（概念篇的 `X-Stream-Protocol` 头可作为传输层补充，不替代业务 Envelope）。

## 事件 Envelope 保持一致

所有事件共享字段：

```python
class StreamEvent(BaseModel):
    id: int
    type: str
    run_id: str
    timestamp: datetime
    payload: dict[str, Any]
    schema_version: str = "1"
```

编码到 SSE 时：`id:` 行用单调整数，`event:` 行用 `type`，`data:` 行是整份 Envelope 的 JSON（或至少包含 `run_id` / `payload` / `schema_version`）。`data` 必须 JSON，禁止裸换行——模型输出里的换行会破坏 SSE 帧边界。

事件类型：

| 类型 | 用途 |
|---|---|
| `run.started` | 返回运行 ID、路线和能力信息 |
| `node.started/progress/completed` | 展示状态机进度 |
| `retrieval.completed` | 展示查询与有权限来源数量 |
| `tool.started/completed` | 展示工具名称和安全摘要 |
| `answer.delta` | 增量答案文本 |
| `citation` | 可点击来源元数据 |
| `run.waiting_for_human` | 展示审批卡片 |
| `run.warning` | 告知 Rerank 降级等非致命问题 |
| `run.failed` | 结构化错误终态 |
| `run.completed` | 成功、部分回答、拒答或取消终态 |

### `id` 单调：重复与乱序

每个 `run_id` 内事件 `id` 从 1 单调递增，只由事件总线分配，业务节点不得自造序号。

| 客户端收到 | 处理 |
|---|---|
| `id` 等于已处理最大值 | 丢弃（重放 / 重复投递） |
| `id` 小于已处理最大值 | 丢弃（乱序迟到） |
| `id` 等于最大值 + 1 | 正常应用 |
| `id` 大于最大值 + 1 | 记缺口；可请求补发持久事件，或等重连后按 `Last-Event-ID` 对齐 |

前端伪代码：

```ts
let lastId = 0
function onEvent(ev: StreamEvent) {
  if (ev.id <= lastId) return          // 重复或乱序
  if (ev.id > lastId + 1) markGap(ev)  // 可选：触发补发
  lastId = ev.id
  apply(ev)
}
```

终态事件（`run.completed` / `run.failed`）即使迟到也要能应用一次：若本地已终态，后到的同 Run 终态直接忽略，保证 UI 不会从「已完成」跳回「运行中」。

### `schema_version` 兼容规则

| 变更 | 是否升主版本 | 做法 |
|---|---|---|
| 新增可选字段（如 `payload.latency_ms`） | 否 | 旧客户端忽略未知字段 |
| 新增事件类型（如 `run.warning`） | 否 | 旧客户端忽略未知 `type` |
| 删除字段、改字段语义、改必填约束 | 是 | `schema_version` 升到 `"2"`；双发或按客户端能力协商 |
| 把 `answer.delta.text` 改成数组 | 是 | 破坏性变更，禁止静默改 |

服务端可以短暂同时理解 `1` 与 `2`，但单条连接内版本不得中途切换。前端以 `run.started` 里的版本锁定本轮解析器。

## 业务事件与模型 Token 分开

LangGraph 节点把领域事件写入异步队列：

```python
await events.publish(
    run_id,
    type="retrieval.completed",
    payload={"query": query.text, "source_count": len(evidence)},
)
```

模型流式输出转换为 `answer.delta`：

```python
async for chunk in answerer.stream(prompt):
    if text := chunk.text:
        await events.publish(run_id, "answer.delta", {"text": text})
```

不要把 Provider 的原始 Chunk 直接传给前端。供应商字段可能变化，还可能包含内部 Token 统计、推理内容或错误信息。适配器只抽取产品协议允许的内容。这对应概念篇里的 `token`，只是本项目命名强调「答案增量」而不是「模型 Token」。

## 引用延迟发送与前端状态机

模型生成 `[S1]` 时不能立刻把它当作有效引用。服务端完成[第 8 章](./agentic-rag-project-citations)的引用校验后才发送 `citation` 事件，并在最终 `run.completed` 中给出完整 Claims。

前端不要把「正文里出现了 `[S1]`」当成可以点击的来源。推荐 4 态：

| 状态 | 进入条件 | UI |
|---|---|---|
| `streaming` | 收到 `run.started` / 首个 `answer.delta` | 正文追加；引用角标灰色或隐藏 |
| `verifying` | 正文结束或进入校验节点（`node.progress` 指向 verify） | 角标显示「校验中」，不可点 |
| `cited` | 收到已校验的 `citation` | 角标可点，打开来源卡片 |
| `terminal` | `run.completed` / `run.failed` | 锁定正文；失败则撤掉未校验草稿或标拒答 |

```text
streaming --answer.delta--> streaming
streaming --verify node--> verifying
verifying --citation--> cited
cited|verifying|streaming --run.completed/failed--> terminal
```

规则：

1. 未进入 `cited` 前，不把引用按钮写入可分享/可落库答案。
2. 若最终校验失败：服务端发 `run.failed` 或 `run.completed` + 结构化拒答；客户端不得把未校验草稿保存成正式答案。
3. 严谨场景可先流式展示「生成中草稿」，最后用可选的 `answer.committed`（若接入）替换为校验后全文；当前 Demo 未发该事件时，以 `run.completed.payload` 中的最终答案为准。

## FastAPI 返回事件流

```python
@router.post("/api/chat/stream")
async def stream_chat(payload: ChatRequest, actor: CurrentUser):
    run = await run_service.create(payload, actor)

    async def generate():
        async for event in run_service.subscribe(run.id, actor):
            yield encode_sse(event)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Stream-Protocol": "agentic-rag/1",
        },
    )
```

`X-Stream-Protocol` 标明这是本项目落地协议，避免客户端按概念篇的 `stage`/`token` 去解析。服务端要点与响应头表见 [fastapi-advanced SSE](./fastapi-advanced#流式响应sse)。

## 反代缓冲排查

反向代理必须关闭响应缓冲，否则后端已经逐条发送，浏览器仍可能在结束时一次性收到。

| 手段 | 作用 |
|---|---|
| 响应头 `X-Accel-Buffering: no` | 按响应关闭 Nginx 缓冲，只影响这条流，推荐 |
| `proxy_buffering off;` | location 级关闭；别误关到普通 JSON 接口 |
| 该路径 `gzip off` | 压缩也会攒块，流式路径直接关 |
| `proxy_http_version 1.1` + 调大 `proxy_read_timeout` | HTTP/1.0 不支持流式 keep-alive；超时要大于最长 Agent 执行 |

典型现象与排查顺序：

1. **直连 uvicorn**：`curl -N http://127.0.0.1:8000/...` 能逐条看到事件 → 后端正常。
2. **经 Nginx 后一次性刷出** → 查该 location 是否缺 `X-Accel-Buffering` / `proxy_buffering off` / `gzip off`。
3. **固定延迟几秒一块** → 多半是压缩或 CDN 缓冲，对该路径关闭。
4. **约 60s 断开** → `proxy_read_timeout` 默认过短，同时确认心跳是否发出。

完整 Nginx 片段与 CDN 注意见 [agent-streaming 生产坑](./agent-streaming)。

## 心跳、序号与背压

模型或工具长时间没有输出时，每 15 秒发送 SSE 注释作为心跳：

```text
: heartbeat 2026-09-05T12:00:15Z
```

注释行不占用业务 `id`，客户端忽略即可。当前 Demo 未实现心跳；接入事件总线后与概念篇的 `with_heartbeat` 同一思路。

每个 Run 的事件 ID 单调递增。事件队列设置上限，如果浏览器消费速度过慢：

- 合并细碎 `answer.delta`。
- 丢弃可重复的低优先级进度（连续 `node.progress` 可保留最新一条）。
- 永远保留 waiting、failed 和 completed 终态。
- 超过硬限制后断开连接，但后台 Run 是否取消由产品策略决定——本项目默认**不断开就取消**。

不能让一个断网浏览器无限堆积内存，拖垮同进程的其他请求。

## 断线恢复分持久事件和瞬时事件

所有 Token 都写数据库成本很高，也没有必要。本项目区分：

- 持久事件：运行开始、节点完成、工具结果、人工等待、错误、最终答案。
- 瞬时事件：细粒度 Token、心跳、频繁进度。

客户端重连时携带 `Last-Event-ID`。服务端先补发该 ID 之后的持久事件，再订阅实时流。丢失的 Token 不逐字重放；如果答案已经提交，直接发送完整最终答案（或未来的 `answer.committed`）。

这样保证业务状态可恢复，同时避免把流式传输变成庞大的事件存储系统。当前 Demo 没有事件表，不能把请求内生成器描述成可重放流。

## 断开 ≠ 取消

浏览器关闭连接不一定表示用户要取消。移动网络切换、笔记本电脑休眠、页面刷新都会断线。若把 `request.is_disconnected()` 直接映射成取消，用户刷新后会发现 Run 被杀掉，只能重新提问并重复计费。

| 信号 | 含义 | 本项目默认 |
|---|---|---|
| TCP / SSE 断开 | 接收端暂时消失 | Run **继续**跑一段受限时间；客户端可重连取结果 |
| `POST .../cancel` | 用户明确停止 | 标记 `cancel_requested`，协作式停下 |
| 超时 / 租约到期 | 系统回收 | 按可靠性策略失败或取消 |

概念篇与 fastapi-advanced 示例里常见「断开即 `cancel_agent`」，那是为了立刻停计费的保守默认。本项目作为可重连的 Agentic RAG，把取消做成显式写操作；断开只停止**向该连接推送**，不停止图执行。多副本下取消标志仍应写 Redis，见 [agent-streaming](./agent-streaming)。

用户点击停止：

```http
POST /api/agent-runs/run-123/cancel
Authorization: Bearer <token>
Idempotency-Key: cancel-123
```

服务端把 Run 改成 `cancel_requested`。取消必须是**协作式**的，检查点放在：

1. **节点边界**：每个 LangGraph 节点入口读取消标志，不再调度下一节点。
2. **Token / 模型流边界**：`answer.delta` 循环每次迭代检查；不要等整段生成完。
3. **工具调用前后**：长工具可在可取消的 HTTP 客户端上绑定同一标志。

最终发送：

```text
event: run.completed
id: 17
data: {"finish_reason":"cancelled"}
```

不要用裸断开假装取消——前端收不到终态会一直转圈，且 `EventSource` 可能自动重连放大开销。

## 错误即事件

第一个字节发出后，HTTP 状态码已钉死为 200。模型超时、工具失败、权限拒绝、内容审核，都不能再改成 4xx/5xx。只能在同一条流里发结构化错误，并进入终态。详见 [fastapi-advanced · 错误是事件，不是 HTTP 500](./fastapi-advanced#错误是事件不是-http-500) 与 [agent-streaming 错误矩阵](./agent-streaming)。

```json
{
  "code": "model_timeout",
  "message": "回答生成超时，请稍后重试。",
  "retryable": true,
  "request_id": "req-123"
}
```

映射到本项目：

| 场景 | 流内动作 | 前端 |
|---|---|---|
| 模型超时 / 上游不可用 | `run.failed`（可带上表字段） | 保留已输出（若策略允许），提供重试 |
| 引用校验失败且不可交付 | `run.failed` 或 `run.completed` + 拒答 | 不落库未校验草稿 |
| 内容安全命中 | `run.failed`，`retryable: false` | 撤回已输出 |
| 用户取消 | `run.completed` + `finish_reason=cancelled` | 保留部分输出 |
| Rerank 降级 | `run.warning`，Run 继续 | 弱提示，不中断 |

硬约束：

1. **`run.failed` 本身就是终态**，其后不得再发 `answer.delta` / `citation`。
2. 成功路径必须有且仅有一次 `run.completed`；失败路径必须有且仅有一次 `run.failed`（或等价的完成+拒答），禁止「只断连不发终态」。
3. 堆栈、Prompt、对象存储路径和供应商原始响应只进受控日志与 Trace；权限失败不能返回内部文档标题。
4. 错误码稳定可枚举，前端按 `code` 分支，不解析 `message` 文案。

## 验证清单

```bash
curl -N http://127.0.0.1:8000/api/chat/stream \
  -H "Authorization: Bearer $ALICE_TOKEN" \
  -H 'content-type: application/json' \
  -d '{"question":"上海住宿上限和报销材料是什么？"}'
```

`-N` 关闭 curl 输出缓冲，才能看见逐条事件。

| 检查项 | 期望 |
|---|---|
| 事件 `id` | 同一 Run 内严格递增，无回退 |
| Envelope | 每条含 `run_id`、`schema_version`；`data` 为 JSON |
| 业务顺序 | `run.started` → 节点/检索 → `answer.delta` →（校验后）`citation` → 终态 |
| 引用 | 正文出现 `[S1]` 之后、校验完成之前，**没有**可点击 `citation` |
| 心跳（接入后） | 静默超过约 15s 出现 `: heartbeat ...` 注释行 |
| 终态唯一 | `run.completed` 或 `run.failed` 只出现一次，之后无业务事件 |
| 经反代 | 与直连一样逐条到达；否则按上一节排查缓冲 |
| 断线重连 | 生成中断开，带 `Last-Event-ID` 重连能拿到持久事件或最终答案（Demo 未实现则标为待接入） |
| 取消 | `POST /cancel` 后在节点或 Token 边界停下，收到 `finish_reason=cancelled`；仅关页面不应取消 |
| 超时错误 | 触发模型超时，流内收到稳定 `code`，连接正常收尾而非裸断 |

当前 Demo 只保证请求内生成器路径上的事件形状与引用延迟发送；清单中带「接入后」的项用于生产事件总线验收。

## 本章小结

Agent 的最小执行过程现在通过版本化 SSE 事件暴露，客户端可以解析序号、答案、引用和终态。本篇事件名是项目契约，与 [agent-streaming](./agent-streaming) / [fastapi-advanced](./fastapi-advanced#流式响应sse) 的 `stage`/`token`/`error`/`done` 通过对照表映射，而不是另起一套不说明的名字。断开默认继续、取消走独立 POST、错误只能是事件、引用校验前不上屏——这四条比「能流起来」更决定产品是否可信。

持久事件、心跳、有限重放和取消仍未接入当前 Demo，不能把请求内生成器描述成可断线恢复的生产流。

下一阶段将把系统推向可交付标准。继续阅读[第 13 章：权限安全与越权检索测试](./agentic-rag-project-security)，集中验证越权检索、Prompt Injection、工具滥用和原文泄漏，证明前面建立的安全边界确实有效。
