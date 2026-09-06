---
title: AI 应用前端：消费 Agent 事件流
description: 面向前端工程师的 AI 应用界面指南——用 fetch 消费 SSE、把后端事件协议转成 TS 判别联合、流式渲染与中断失败处理、引用与执行过程的可视化、会话状态与断线重连策略。
---

# AI 应用前端：消费 Agent 事件流

> 这一篇为前端工程师而写。多数 AI 教程止步于 `curl` 能看到流，而“把事件流变成可靠、可解释、可恢复的界面”恰是前端的主场：流解析、增量渲染、状态机、错误恢复、可访问性，全是你已有的技能。后端协议的原理见[Agent 流式输出](./agent-streaming)与[实战第 12 章](./agentic-rag-project-streaming)，本章讲浏览器侧怎么把它做成产品级的 UI。

## 为什么 AI 前端是不同的前端

传统界面是请求-响应：发出去，转圈，拿到完整结果，一次渲染。AI 界面是事件流，带来四个新问题：

| 传统界面 | AI 应用界面 |
|---|---|
| 一个响应一个状态 | 一条流十几个事件，UI 要表达“进行中”的中间态 |
| 失败 = 报错页 | 失败可能发生在第 7 个事件后，屏幕上已有部分内容 |
| 内容静态可缓存 | 内容逐 token 到达，渲染策略不当会闪烁、抖动 |
| 错误信息人写 | 错误是结构化事件（`refusal_reason`），要映射成用户能行动的提示 |

还有一条信任问题：AI 答案天生不可全信，**把检索了什么、引用了哪里展示出来**，是界面能做的最大可信度投资。这也是为什么“过程可视化”不是锦上添花。

## 事件契约先行：把后端协议变成 TS 类型

配套项目的 SSE 信封是版本化的（`schema_version: "1"`），每个事件带 `id`、`type`、`run_id`、`timestamp` 和 `payload`。前端的第一件事是把这个契约固化成类型——后端加事件类型时，TypeScript 会替你找出所有没处理的分支：

```typescript
interface StreamEnvelope<T extends EventType, P> {
  id: number;
  type: T;
  runId: string;
  timestamp: string;
  schemaVersion: "1";
  payload: P;
}

type StreamEvent =
  | StreamEnvelope<"run.started", { route: string }>
  | StreamEnvelope<"node.started", { node: string }>
  | StreamEnvelope<"node.completed", { node: string; source_count: number }>
  | StreamEnvelope<"answer.delta", { text: string }>
  | StreamEnvelope<"citation", { source_id: string; document_id: string }>
  | StreamEnvelope<"run.completed", { finish_reason: string }>
  | StreamEnvelope<"run.failed", { code: string; message: string }>;
```

判别联合（discriminated union）配合 `switch (event.type)` 的穷举检查，是事件协议前端的正确形态：**未知事件类型走 default 分支只记日志、不崩溃**——后端先于前端升级是常态，向前兼容要靠客户端的宽容。

## 用 fetch 而不是 EventSource

`EventSource` 只支持 GET、不能带 `Authorization` 头——这两条就足以否决它。用 `fetch` + `ReadableStream` 手写解析，核心是**按空行分帧、按行解析字段、容忍分包**：

```typescript
async function consumeSSE(
  response: Response,
  onEvent: (event: StreamEvent) => void,
) {
  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE 以空行分帧；chunk 边界可能切在帧中间，只处理完整帧
    const frames = buffer.split("\n\n");
    buffer = frames.pop()!;

    for (const frame of frames) {
      const event = parseFrame(frame);
      if (event) onEvent(event);
    }
  }
}

function parseFrame(frame: string): StreamEvent | null {
  let id = 0, type = "";
  let data = "";
  for (const line of frame.split("\n")) {
    if (line.startsWith("id: ")) id = Number(line.slice(4));
    else if (line.startsWith("event: ")) type = line.slice(7);
    else if (line.startsWith("data: ")) data += line.slice(6);
  }
  if (!type || !data) return null;
  return { ...JSON.parse(data), id, type } as StreamEvent;
}
```

三个容易踩的坑都在这段代码里处理了：`decoder.decode(value, { stream: true })` 保证多字节中文字符跨 chunk 时不乱码；`frames.pop()` 把不完整帧留到下一轮；`data:` 字段按协议去掉一个空格而不是 `split(" ")[1]`（payload 里可能有空格）。请求侧记得 `signal: AbortSignal`——用户点停止或组件卸载时必须 `abort()`，否则连接和后端的推理都在烧钱。

## 流式渲染：只解决三件事

**增量拼接**。`answer.delta` 的文本追加到状态里，渲染交给既有组件。当前 demo 后端整段发送，未来切换到 token 级增量时客户端逻辑不变——这正是协议分层的好处。

**渲染策略防抖动**。对 Markdown 答案不要每个 token 都重新 parse 整篇：追加期间按“已完成段落”分段渲染，未完段落用纯文本，`run.completed` 后整体重渲染一次。节流到 30–60ms 一帧足够，用户感知的是“打字机”而不是性能问题。

**中断与失败不清屏**。`run.failed` 到达时屏幕上可能已有前几个事件的产出（如检索步骤条）。正确做法：保留已展示的过程信息，在内容区显示结构化错误——把 `run.failed.payload.code` 映射成用户能行动的文案（`insufficient_evidence` → “知识库中没有找到依据，换个问法试试”），而不是把原始 message 直接怼给用户。组件卸载时先 `abort()` 再清理状态。

## 引用与过程可视化

这是前端对可信度贡献最大的部分，素材全在事件流里：

- **来源侧栏**：`citation` 事件到达时往侧栏追加来源卡片（标题、文档版本、定位信息）。编号 `[S1]` 在答案文本中渲染成锚点，点击滚动到对应卡片。注意契约边界——`S1` 只在本响应内有效，点击“查看原文”必须用 `document_id + document_version` 请求受权限保护的接口重新鉴权，不能拿编号当资源 ID（[第 8 章](./agentic-rag-project-citations)的安全设计）。
- **步骤指示器**：`node.started` / `node.completed` 驱动“检索中 → 读取了 N 个来源”的进度条。它回答用户“它在干什么”，也回答“它是不是死了”——超过心跳间隔没有任何事件时应显示异常态。
- **诚实展示降级**：`route_degraded=true` 或 `partial=true` 的响应要有可见标识（如“部分完成”角标），不要把残缺答案伪装成完整答案。

## 断线重连与会话状态

SSE 断线重连的协议基础是 `Last-Event-ID`：客户端自动携带最后收到的事件 `id`，服务端从缓冲补发。**当前配套项目还没有事件重放**（第 12 章边界声明里写明），所以前端策略要按现实设计：

- 流中途断开 → 保留已显示内容，提示“回答中断”，提供“重新提问”按钮而不是自动静默重发（重发意味着后端重新推理、重新计费，应由用户决定）；
- 接入重放后 → 自动重连一次，补齐缺失事件再续渲染。

会话状态方面：`conversation_id` 客户端生成、`localStorage` 持久化，换用户必须清空（服务端按 `(conversation_id, actor_id)` 隔离，跨用户读是 404）。不要做“乐观答案”——用户消息可以立即上屏，但答案区域在 `run.started` 前保持等待态，因为路由可能拒绝、检索可能失败，假装成功只会制造更多错误状态。

## 测试：事件流是可测的

`fetch` 封装成 `consumeSSE(response, onEvent)` 后，测试就是构造一个 `Response`，`body` 用 `new ReadableStream` 喂入预录的 SSE 文本（可以故意在帧中间切块），断言 `onEvent` 收到的事件序列。后端 `APP_PROVIDER=demo` 是全确定性的，前端 e2e 可以连真实后端而不烧一分钱 API 费用——这也是 demo Provider 设计的红利。

## 与 Vercel AI SDK 的关系

现成轮子（`useChat`、AI SDK UI 组件）适合快速原型和标准 OpenAI 协议。但你的事件协议有自己的领域事件（`node.started`、`citation`、`route_degraded`），AI SDK 的抽象对不上时，改造它比自己写解析更绕。**协议是你的产品资产，消费协议的解析层值得自己拥有**——上面全部代码加起来不到一百行。

## 本章小结

AI 前端的核心转变是从“渲染一个响应”到“消费一条事件流”：类型先行固化契约、fetch 手写 SSE 解析、渲染防抖与失败不清屏、引用与过程可视化建立信任、断线策略尊重“重试 = 重新计费”。这些能力建立在你已有的流处理和状态管理经验上——前端工程师在 AI 团队里的不可替代性，就在这一层。

---

## 面试问答

**1. 为什么用 fetch 而不用 EventSource？**

- 两条硬伤：只支持 GET、不能自定义请求头（带不了 `Authorization`）。AI 问答是带身份的 POST，EventSource 直接出局。
- fetch + ReadableStream 的额外收益：能拿到原始字节流自己分帧，能精确控制 abort。
- 加分：知道 SSE 分帧规则（空行分隔）和 chunk 边界问题——`buffer.split("\n\n")` 后 `pop()` 留尾，这是最常见的面试追问点。

**2. 流式回答渲染到一半失败了，UI 怎么办？**

- 不清屏：已展示的过程信息和部分内容保留，错误以结构化条目追加。
- 错误文案从事件码映射（`insufficient_evidence` → 换个问法），不透传原始 message。
- 重新提问是用户的选择而不是自动重试——重试意味着后端重新推理计费。
- 别踩的坑：组件卸载不 abort，后台连接继续烧钱、状态更新打在已卸载组件上。

**3. 答案里的 [S1] 引用怎么设计交互？**

- 渲染成锚点，点击滚动到来源卡片；卡片信息来自 `citation` 事件和响应的 `sources`。
- “查看原文”用 `document_id + document_version` 重新鉴权请求，S 编号只是展示层脚手架，不是资源 ID。
- 加分：说得出为什么——来源编号单响应有效，拿它当资源 ID 等于把授权凭证暴露在文本里。

**4. Markdown 答案逐 token 渲染会抖动，怎么处理？**

- 追加期只渲染已完成段落（纯文本），未完段落不进 Markdown parser；完成后整体重渲染一次。
- 渲染节流到 30–60ms，配合 `requestAnimationFrame` 批量更新。
- 加分：提到代码块跨 chunk 的处理——未闭合的代码围栏先按纯文本渲染，闭合后再高亮。

**5. 后端事件协议升级加了一种新事件，前端会怎样？**

- 判别联合加 default 分支：未知类型记日志、不崩溃——向后兼容是客户端责任。
- 信封里有 `schema_version`，破坏性变更时前端按版本分流处理。
- 加分：契约测试——用预录 SSE 文本做前端的快照测试，后端协议变更在 CI 里就能发现前端未适配。
