---
title: 企业知识库 Agentic RAG 实战（八）：上下文、引用与拒答
description: 在模型调用前选择受预算约束的 Evidence，给来源分配请求内 ID，并校验事实引用与数值支持度。
---

# 企业知识库 Agentic RAG 实战（八）：上下文、引用与拒答

> 检索命中 Chunk 只说明资料进入了候选集。它不能证明最终答案用了正确的版本、没有杜撰数字，或真的能定位来源。本章将“要求模型带引用”变为服务端可检查的协议。

## 本章实际交付

`app/context.py` 在回答前从检索结果选择 Evidence：去除重复内容、每份文档最多两个 Chunk、总正文预算默认 4,000 个字符。服务端随后为这一请求内的 Evidence 分配 `S1`、`S2` 等来源 ID。

`app/citations.py` 校验每个 Claim：

- 至少有一个来源 ID；
- 所有 ID 都必须属于本次请求的 Evidence；
- Claim 中的阿拉伯数字都能在其引用的原文中找到。

验证失败或没有 Claim 时，接口返回 `refused=true` 和稳定的 `refusal_reason`，不会带回候选 Chunk。响应只给出被引用来源的短摘录、文档版本和标题定位。

当前 `demo` 回答器只摘取一条能够直接支持问题的原文，并为它生成一个 Claim；它用于验证协议，不冒充多事实问答模型。OpenAI-compatible 回答器仍使用带 `[S1]` 标记的文本协议，尚未启用供应商 JSON Schema 输出，也没有自动修复重试。这些生产能力应在接入具体供应商时以契约测试实现，不能在教程中写成已经完成。

## 从候选到 Evidence

```python
evidence = build_evidence(
    reranked_hits,
    char_budget=4_000,
    max_per_document=2,
)
```

预算不是把 Top K 原文直接拼接。相邻或重复 Chunk 会浪费上下文，一份长文档也不应占满所有槽位。当前项目使用字符数近似预算，避免引入模型专用 Tokenizer；切换模型后，生产环境需要以对应 Tokenizer 为准，并为系统指令、问题和输出各自预留空间。

Evidence 进入 Prompt 时用数据标签隔离：

```text
<evidence id="S1" file="员工差旅管理制度 V2">
...原文...
</evidence>
```

系统提示明确声明标签中的内容是资料而不是指令。它降低指令与数据混淆，但不替代第 3 章的权限过滤，也不替代第 13 章的 Prompt Injection 防护。

## 响应协议

```json
{
  "answer": "根据当前知识库找到的原文：… [S1]",
  "refused": false,
  "refusal_reason": null,
  "claims": [
    {"text": "一线城市 | 北京、上海、广州、深圳 | 650 元", "source_ids": ["S1"]}
  ],
  "sources": [
    {
      "id": "S1",
      "document_id": "…",
      "document_version": 2,
      "heading": "住宿标准",
      "excerpt": "…",
      "score": 0.03
    }
  ]
}
```

`S1` 只在一次响应内有效，不能作为数据库主键或跨会话授权凭证。前端要预览原文时，应使用 `document_id + version + locator` 请求受权限保护的接口，并重新鉴权。

## 服务端校验拒绝什么

数值校验能拦住最常见且可确定的错误：来源只含 `650`，Claim 写成 `850` 时返回 `unsupported_number`。它不是语义蕴含判断，无法证明“650 元”适用于哪座城市，也不能验证没有数字的错误表述。更强的 NLI 或评审模型可作为后续增强，但必须与固定题集一起评估，不能把模型自评当作事实。

当检索没有结果、Evidence 为空、回答器声明证据不足，或引用校验失败时，接口分别返回：

| 原因 | `refusal_reason` |
|---|---|
| 无检索结果 | `no_retrieval_result` |
| 无足够 Evidence 或未生成 Claim | `insufficient_evidence` |
| 来源 ID 不属于当前请求 | `unknown_source` |
| Claim 数字未出现在来源中 | `unsupported_number` |
| 试图绕过权限 | `policy_bypass_request` |

这让前端可以展示清晰的下一步，也让后续追踪能区分召回问题、生成问题和引用问题。

## 验证点

新增测试验证数值幻觉与跨请求来源 ID 会被拒绝；API 测试验证成功回答的每个 Claim 只引用本次响应中的 Source，且响应不再返回完整 Chunk 正文。运行：

```bash
cd projects/agentic-rag
uv run ruff check .
uv run pytest
```

继续阅读[第 9 章：问题分类与执行路线](./agentic-rag-project-routing)。
