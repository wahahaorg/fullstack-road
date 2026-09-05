---
title: 企业知识库 Agentic RAG 实战（十五）：RAG 与 Agent 离线评测
description: 用固定数据集评估路由、Recall@K、MRR、引用、拒答、越权率、Agent 成功率、延迟和成本，并保存可复现的实验报告。
---

# 企业知识库 Agentic RAG 实战（十五）：RAG 与 Agent 离线评测

> 系统已经有很多可调参数：切分策略、Embedding、候选数、RRF、Reranker、路由器和 Agent 预算。如果每次修改后临时问几个问题，很容易只记住成功案例。本章建立同一数据、同一口径、可比较的评测流程。

## 本地可运行基线

项目提供 `uv run python -m evals.run`。它使用 Demo Provider、固定 fixtures 和 11 条 JSONL 样例，输出数据集哈希、路由准确率、来源召回、拒答准确率、禁用来源泄漏率及逐条失败信息。当前运行结果保存在本地命令输出中：路由准确率 `1.0`、平均来源召回 `0.9545`、禁用来源泄漏率 `0`、拒答准确率 `0.8182`。这些是小样例的基线，不代表生产质量。

## 评测集描述预期事实，不绑定答案措辞

项目从第一章保留的 JSONL 继续使用：

```json
{
  "id": "simple-travel-limit",
  "category": "simple_rag",
  "actor_id": "user-finance-alice",
  "question": "去上海出差，住宿费每晚最多报销多少？",
  "expected_route": "fixed_rag",
  "expected_source_ids": ["doc-travel-v2"],
  "forbidden_source_ids": ["doc-travel-v1"],
  "required_facts": ["上海属于一线城市", "每人每晚上限 650 元"],
  "expect_refusal": false
}
```

不要求答案与参考文本逐字一致。评测关注路线、来源、事实和拒答行为，避免把模型合理改写误判为错误。

每条数据都绑定 `actor_id`。同一个问题可以为 Alice 与 Bob 建两条样例，权限是评测输入的一部分。

## 分层指标定位问题发生在哪

### 路由指标

```text
route_accuracy = 正确路线数 / 总样例数
```

还需要查看混淆矩阵。把 `fixed_rag` 错分成 `agentic_rag` 主要增加成本，把敏感工具错分成普通路线则可能带来安全风险，两者不能只看同一个准确率。

### 检索指标

`Recall@K` 判断期望来源中有多少进入前 K，`MRR` 关注第一个正确来源的排名：

```python
recall_at_k = len(expected_sources & top_k_sources) / len(expected_sources)
mrr = 0 if not ranks else 1 / min(ranks)
```

无期望来源的拒答样例不计入 Recall@K。对需要两份文档的多跳问题，上述 Recall@K 就是 source coverage：只命中一份时得到 `0.5`，不能因为命中任意一份就算成功。

### 引用指标

- Citation precision：返回来源中真正支持 Claim 的比例。
- Citation recall：需要证据的 Claim 中有有效来源的比例。
- Invalid citation rate：引用不存在 `S9` 等来源的比例。
- Version correctness：是否引用当前版本或明确允许的历史版本。

### 拒答指标

```text
refusal_precision = 应拒答且确实拒答 / 所有拒答
refusal_recall    = 应拒答且确实拒答 / 所有应拒答
```

只追求拒答率低会鼓励模型胡答，只追求拒答率高又会让系统失去价值。二者必须一起看。

### 安全指标

`forbidden_source_leakage_rate` 统计禁用来源是否出现在候选、上下文、答案、事件或工具结果中。该指标的发布门槛是零，不用平均值容忍泄漏。

### Agent 指标

- 计划是否覆盖必要子问题。
- 工具选择和参数是否正确。
- 是否在预算内结束。
- 是否存在无信息增量循环。
- 最终任务是否成功、部分成功或正确拒答。

## 评测 Runner 保存完整版本信息

```bash
uv run python -m evals.run \
  --dataset evals/dataset.jsonl \
  --output /tmp/agentic-rag-eval.json
```

报告必须保存：

```json
{
  "git_commit": "...",
  "dataset_hash": "...",
  "retrieval_profile": "hybrid-rerank-v1",
  "embedding_model": "...",
  "reranker_model": "...",
  "chat_model": "...",
  "prompt_versions": {"route":"v2","answer":"v4","assess":"v1"},
  "started_at": "...",
  "environment": "local"
}
```

没有这些信息，两份分数无法复现，也不能确定是代码、模型还是数据变化导致差异。

## 一次运行分阶段执行

```python
for case in dataset:
    actor = fixture_users.get(case.actor_id)
    route = await router.route(case.question, actor)
    retrieval = await retriever.debug(case.question, actor)
    run = await chat_service.ask(case.question, actor)
    result = score_case(case, route, retrieval, run)
    writer.append(result)
```

即使最终答案正确，也保留检索阶段数据。例如模型依靠常识猜中 `650`，但正确来源没有进入 Top K，检索指标仍然失败，引用校验也应该阻止这个答案通过。

评测使用固定温度和明确超时。模型调用失败单独计为 infrastructure error，不能偷偷从分母删除。

## 对比实验一次只改变主要变量

比较检索策略：

```text
baseline        heading-aware + vector
chunking        parent-child + vector
hybrid          parent-child + vector + keyword + RRF
hybrid+rank     parent-child + hybrid + reranker
```

每轮只改变一个主要变量：先比较切分，再在相同切分下加入关键词和 RRF，最后再加入 Reranker。保持数据集、Embedding、回答模型和 Prompt 不变。报告同时展示质量、P50/P95 延迟、模型调用次数和 Token，而不是只挑最好的一个数字。

如果 Rerank 提高 MRR，却让 P95 超过产品预算，需要决定降级、缩小候选或更换模型。评测结果支持取舍，不自动替产品做决定。

## LLM Judge 只能作为一层证据

复杂答案的事实支持度可以使用评审模型：

```python
class JudgeResult(BaseModel):
    supported: bool
    unsupported_claims: list[str]
    missing_facts: list[str]
    reason: str
```

但 Judge 也会受 Prompt、模型版本和顺序影响。因此：

- 数字、来源身份、权限和路线优先使用确定代码。
- Judge Prompt 与模型版本写入报告。
- 发布门槛附近的样例进行人工复核。
- 不让被评模型看到参考答案以外的额外信息。

## 建立回归门槛

配置不直接写一个“总分”，而是按风险设门槛：

```yaml
gates:
  forbidden_source_leakage_rate: 0
  invalid_citation_rate: 0
  retrieval_recall_at_5:
    max_drop: 0.02
  refusal_recall:
    max_drop: 0.02
  p95_latency_ms:
    max_increase: 0.20
```

小数据集上一个样例就可能改变很多百分比，所以报告同时显示分子、分母和失败案例 ID。门槛数字要在实际基线生成后确定，正文不预先虚构已达到的准确率。

## 从失败样例扩充数据集

线上或手工验收发现问题时，先将其最小化成可复现样例：

1. 去除真实敏感内容，保留失败结构。
2. 明确 actor、期望和禁用来源。
3. 在当前版本确认可以复现。
4. 修复后保留为回归样例。

数据集需要覆盖常见事实、多文档、比较、拒答、权限、草稿、注入、版本与工具错误，不能只收集最容易成功的问题。

## 读懂报告中的失败

| 结果 | 可能问题 |
|---|---|
| Recall 低，答案失败 | 切分、Embedding、关键词或权限查询 |
| Recall 高，MRR 低 | 融合与 Rerank |
| 检索正确，引用错误 | 上下文编号或输出校验 |
| 固定 RAG 成功但被路由到 Agent | 路由过度升级 |
| Agent 多轮无新增证据 | Assess、Rewrite 或停止条件 |
| 拒答正确但延迟很高 | 在无证据时仍做多轮模型调用 |
| 禁用来源出现 | 立即阻断发布并检查整个数据路径 |

评测的价值是缩小排查范围，而不是生成一张好看的排行榜。

## 本章小结

路由、来源召回、拒答和越权来源现在有固定数据与计算口径；当前 Runner 尚未接入真实 Provider 的 Token、成本、延迟和 LLM Judge，因此这些指标仍是后续扩展项。每份本地报告绑定数据集哈希，配置变更可以通过同一 Runner 复现比较。

继续阅读[第 16 章：可观测性、测试与部署](./agentic-rag-project-operations)，把这些离线结果与运行时 Trace、日志和指标结合，并用 Docker Compose 启动完整环境，完成健康检查、备份恢复和部署边界。
