---
title: 企业知识库 Agentic RAG 实战（十二）：SSE 流式事件协议
description: 设计节点进度、检索、Token、引用、人工确认、错误与完成事件，支持心跳、序号、取消和有限断线恢复。
---

# 企业知识库 Agentic RAG 实战（十二）：SSE 流式事件协议

> Agentic RAG 可能经历规划、多轮检索和工具调用。如果前端只等一个最终 JSON，用户无法判断系统是在工作、等待确认还是已经卡住。本章用 SSE 暴露稳定业务事件，而不是把后端日志直接流给浏览器。

## 当前项目边界

配套项目已经提供 `POST /api/chat/stream`：它发送版本化 Envelope、递增 `id`、`run.started`、节点完成、`answer.delta`、经过普通回答校验后的 `citation` 和 `run.completed`/`run.failed`。当前 Demo 是请求内生成器，没有持久事件表、Last-Event-ID 重放、心跳、取消或 Token 级模型流；下面这些协议约束是接入生产事件总线时的实现清单。

## 用户看到的是可理解的执行过程

提交复杂问题后，客户端收到：

```text
event: run.started
id: 1
data: {"run_id":"run-123","route":"agentic_rag"}

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

如果未来出现实时协同编辑或持续双向语音，再单独评估 WebSocket，不为尚未出现的需求提前更换传输层。

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

事件类型分为：

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
| `run.completed` | 成功、部分回答或拒答终态 |

`schema_version` 用于前后端独立升级。新增可选字段可以保持版本，删除或改变字段语义才升级主版本。

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

不要把 Provider 的原始 Chunk 直接传给前端。供应商字段可能变化，还可能包含内部 Token 统计、推理内容或错误信息。适配器只抽取产品协议允许的内容。

## 引用在确认后再发送

模型生成 `[S1]` 时不能立刻把它当作有效引用。服务端完成第 8 章的引用校验后才发送 `citation` 事件，并在最终 `run.completed` 中给出完整 Claims。

前端可以先显示正文增量，但引用按钮在校验成功后出现。如果最终校验失败，服务端发送 `run.failed` 或结构化拒答，客户端不能把未校验草稿保存成正式答案。

对严谨场景也可以先流式展示“生成中草稿”，最后用 `answer.committed` 替换为校验后的完整文本。

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
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
```

反向代理必须关闭响应缓冲，否则后端已经逐条发送，浏览器仍可能在结束时一次性收到。压缩也要实测，有些代理会累积小块后再刷新。

## 心跳、序号与背压

模型或工具长时间没有输出时，每 15 秒发送 SSE 注释作为心跳：

```text
: heartbeat 2026-09-05T12:00:15Z
```

每个 Run 的事件 ID 单调递增。客户端丢弃小于等于已处理 ID 的重复事件。事件队列设置上限，如果浏览器消费速度过慢：

- 合并细碎 `answer.delta`。
- 丢弃可重复的低优先级进度。
- 永远保留 waiting、failed 和 completed 终态。
- 超过硬限制后断开连接，但后台 Run 是否取消由产品策略决定。

不能让一个断网浏览器无限堆积内存，拖垮同进程的其他请求。

## 断线恢复分持久事件和瞬时事件

所有 Token 都写数据库成本很高，也没有必要。本项目区分：

- 持久事件：运行开始、节点完成、工具结果、人工等待、错误、最终答案。
- 瞬时事件：细粒度 Token、心跳、频繁进度。

客户端重连时携带 `Last-Event-ID`。服务端先补发该 ID 之后的持久事件，再订阅实时流。丢失的 Token 不逐字重放；如果答案已经提交，直接发送完整 `answer.committed`。

这样保证业务状态可恢复，同时避免把流式传输变成庞大的事件存储系统。

## 取消需要单独请求

用户点击停止：

```http
POST /api/agent-runs/run-123/cancel
Authorization: Bearer <token>
Idempotency-Key: cancel-123
```

服务端把 Run 改成 `cancel_requested`，LangGraph 在节点和模型流边界检查取消标志，最终发送：

```text
event: run.completed
data: {"finish_reason":"cancelled"}
```

浏览器关闭连接不一定表示用户要取消。移动网络切换和页面刷新都会断线，因此默认让后台 Run 继续一段受限时间，客户端可重连获取结果。

## 错误事件不泄漏内部信息

```json
{
  "code": "model_timeout",
  "message": "回答生成超时，请稍后重试。",
  "retryable": true,
  "request_id": "req-123"
}
```

堆栈、Prompt、对象存储路径和供应商原始响应只进入受控日志与 Trace。权限失败不能返回内部文档标题。错误事件发送后必须跟随终态或直接作为终态，避免前端永远显示运行中。

## 用 curl 观察协议

```bash
curl -N http://127.0.0.1:8000/api/chat/stream \
  -H "Authorization: Bearer $ALICE_TOKEN" \
  -H 'content-type: application/json' \
  -d '{"question":"上海住宿上限和报销材料是什么？"}'
```

观察事件 ID 是否递增、心跳是否按时出现、完成事件是否只发送一次。随后在生成中断开连接并重连，确认最终答案能够恢复；执行取消，确认 Agent 停在安全边界；触发模型超时，确认收到稳定错误码。

## 本章小结

Agent 的最小执行过程现在通过版本化 SSE 事件暴露，客户端可以解析序号、答案、引用和终态。持久事件、心跳、有限重放和取消仍未接入当前 Demo，不能把请求内生成器描述成可断线恢复的生产流。

下一阶段将把系统推向可交付标准。继续阅读[第 13 章：权限安全与越权检索测试](./agentic-rag-project-security)，集中验证越权检索、Prompt Injection、工具滥用和原文泄漏，证明前面建立的安全边界确实有效。
