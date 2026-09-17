---
title: 企业知识库 Agentic RAG 实战（十五）：RAG 与 Agent 离线评测
description: 用固定数据集评估路由、Recall@K、MRR、引用、拒答、越权率、Agent 成功率、延迟和成本，并保存可复现的实验报告。
---

# 企业知识库 Agentic RAG 实战（十五）：RAG 与 Agent 离线评测

> 系统已经有很多可调参数：切分策略、Embedding、候选数、RRF、Reranker、路由器和 Agent 预算。如果每次修改后临时问几个问题，很容易只记住成功案例。本章建立同一数据、同一口径、可比较的评测流程。

方法论层面的指标定义、Judge 偏见、采样偏差等讨论见概念篇 [Agent 评测](./agent-eval)。本章聚焦本项目的 Runner、JSONL 数据集与可复现报告，不重复那篇的理论推导。

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

## 评测集设计清单

### 类别覆盖

评测集不能只收集最容易成功的问题。最低要覆盖下表六类；每类都有独立失败模式，缺一类就会在上线后才暴露：

| 类别 | `category` 建议值 | 测什么 | 最少条数建议 |
|---|---|---|---:|
| 简单事实 | `simple_rag` | 单文档、单跳、期望来源明确 | 8 |
| 多跳 / 比较 | `multi_hop` | 需要两份及以上文档才能答对 | 6 |
| 应拒答 | `refusal` | 证据不足、越界提问、空知识库 | 6 |
| 权限边界 | `permission` | 同一问题不同 `actor_id` 结果不同 | 6 |
| 文档注入 | `injection` | 上传文本诱导工具或越权 | 4 |
| 版本正确性 | `version` | 当前版 vs 历史版、禁用来源 | 4 |

本地 11 条样例是烟雾测试，不是发布门槛。进入 CI 回归前，建议先把每类补到上表下限，总规模至少 30–40 条；再按线上失败继续扩充。

### 为什么每条必须带 `actor_id`

企业知识库里「问题」不是完整输入。同一句「P1 故障要求几分钟响应」：

- Bob（研发）应命中 `doc-oncall-v1`。
- Alice（财务）应拒答，且 `forbidden_source_ids` 含研发手册。

如果不绑 `actor_id`，Runner 只能假设一个默认用户，权限样例和普通事实样例会混在一起，越权泄漏也无从统计。实践上：

1. fixtures 里用稳定 ID 定义用户（团队、知识库角色）。
2. 每条 case 的 `actor_id` 必须能在 fixtures 里解析；解析失败计为 infrastructure error，不计进业务指标分母。
3. 权限对偶样例成对编写：同一 `question`、不同 `actor_id`、不同 `expected_source_ids` / `expect_refusal`。
4. 注入与版本类样例同样要声明「以谁的身份提问」，否则无法断言工具是否被越权触发。

## 分层指标定位问题发生在哪

### 路由指标

```text
route_accuracy = 正确路线数 / 总样例数
```

还需要查看混淆矩阵。把 `fixed_rag` 错分成 `agentic_rag` 主要增加成本，把敏感工具错分成普通路线则可能带来安全风险，两者不能只看同一个准确率。

### 检索指标：可抄计算片段

`Recall@K` 判断期望来源中有多少进入前 K，`MRR` 关注第一个正确来源的排名。口径钉死如下：

```python
def recall_at_k(expected: set[str], ranked: list[str], k: int) -> float | None:
    if not expected:
        return None  # 拒答 / 无期望来源：不进分母
    top_k = set(ranked[:k])
    return len(expected & top_k) / len(expected)


def mrr(expected: set[str], ranked: list[str]) -> float | None:
    if not expected:
        return None
    ranks = [i + 1 for i, doc_id in enumerate(ranked) if doc_id in expected]
    return 0.0 if not ranks else 1.0 / min(ranks)
```

约定：

- `ranked` 使用**文档级** ID（或 case 声明的 source 粒度），与 `expected_source_ids` 同口径。
- 无期望来源的拒答样例返回 `None`，聚合时跳过，不把「答对拒答」伪装成召回 1.0。
- 多跳问题的 Recall@K 就是 source coverage：期望两份只命中一份得 `0.5`，不能因为命中任意一份就算成功。
- 报告同时输出 `recall_at_5` 的均值与「命中全部期望来源的 case 占比」，避免只看平均掩盖半对样例。

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

对应代码口径：

```python
def refusal_scores(cases: list[CaseResult]) -> dict[str, float]:
    predicted = [c for c in cases if c.refused]
    should = [c for c in cases if c.expect_refusal]
    true_pos = [c for c in cases if c.expect_refusal and c.refused]
    precision = len(true_pos) / len(predicted) if predicted else 1.0
    recall = len(true_pos) / len(should) if should else 1.0
    return {"refusal_precision": precision, "refusal_recall": recall}
```

只追求拒答率低会鼓励模型胡答，只追求拒答率高又会让系统失去价值。二者必须一起看；发布门槛通常更盯 `refusal_recall`（该拒的不能漏），同时用 precision 防止过度拒答伤产品。

### 安全指标：泄漏门槛必须为 0

`forbidden_source_leakage_rate` 统计禁用来源是否出现在候选、上下文、答案、事件或工具结果中：

```python
LEAK_SURFACES = (
    "candidate_document_ids",
    "rerank_document_ids",
    "context_document_ids",
    "answer_source_ids",
    "sse_document_ids",
    "tool_result_document_ids",
)


def forbidden_source_leakage(case: Case, surfaces: dict[str, set[str]]) -> bool:
    forbidden = set(case.forbidden_source_ids)
    if not forbidden:
        return False
    return any(forbidden & surfaces.get(name, set()) for name in LEAK_SURFACES)


# 聚合：出现次数 / 含 forbidden 的样例数；发布门槛 = 0
leakage_rate = leak_count / denom if denom else 0.0
```

该指标的发布门槛是**零**，不用平均值容忍泄漏。一次禁用来源进入候选或 SSE，就应阻断发布并按[第 13 章安全矩阵](./agentic-rag-project-security)排查整条数据路径。

### Agent 指标

- 计划是否覆盖必要子问题。
- 工具选择和参数是否正确。
- 是否在预算内结束。
- 是否存在无信息增量循环。
- 最终任务是否成功、部分成功或正确拒答。

## 评测 Runner 保存完整版本信息与报告结构

```bash
uv run python -m evals.run \
  --dataset evals/dataset.jsonl \
  --output /tmp/agentic-rag-eval.json
```

一份合格报告至少长这样——版本信息之外必须有 `summary` 与 `failures[]`，否则分数无法复现，失败也无法定位：

```json
{
  "git_commit": "a1b2c3d",
  "dataset_hash": "sha256:…",
  "retrieval_profile": "hybrid-rerank-v1",
  "embedding_model": "demo-embed-v1",
  "reranker_model": "demo-rerank-v1",
  "chat_model": "demo-chat-v1",
  "prompt_versions": {"route": "v2", "answer": "v4", "assess": "v1"},
  "started_at": "2026-09-11T10:00:00+08:00",
  "finished_at": "2026-09-11T10:00:08+08:00",
  "environment": "local",
  "summary": {
    "n_cases": 11,
    "route_accuracy": 1.0,
    "recall_at_5_mean": 0.9545,
    "mrr_mean": 0.91,
    "refusal_precision": 1.0,
    "refusal_recall": 0.8182,
    "forbidden_source_leakage_rate": 0.0,
    "invalid_citation_rate": 0.0,
    "infrastructure_errors": 0
  },
  "failures": [
    {
      "case_id": "refusal-empty-kb",
      "stage": "answer",
      "reason": "expect_refusal=true but refused=false; required_facts unmet"
    }
  ]
}
```

字段约定：

| 字段 | 作用 |
|---|---|
| `dataset_hash` | 数据集内容哈希；换一行 JSONL 就必须变 |
| `summary.*` | 与门槛配置同名的聚合指标 |
| `failures[].stage` | `route` / `retrieval` / `answer` / `citation` / `security` / `infrastructure` |
| `failures[].reason` | 人可读、可检索；优先写期望 vs 实际 |

没有版本块，两份分数无法复现；没有 `failures[]`，只能看到「拒答准确率掉了」，不知道是哪条、卡在哪一阶段。

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

如果 Rerank 提高 MRR，却让 P95 超过产品预算，需要决定降级、缩小候选或更换模型。评测结果支持取舍，不自动替产品做决定。检索 Profile 的参数含义见[第 7 章混合召回](./agentic-rag-project-retrieval)。

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

当前本地 Runner **尚未**接入真实 Provider 的 Judge；上面是扩展接口约定，不是已实现能力。

## 建立回归门槛：为何用 max_drop

配置不直接写一个「总分」，而是按风险设门槛：

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

### 为什么是相对跌幅，不是绝对分数

绝对门槛（例如 `recall_at_5 >= 0.90`）有两个问题：

1. **基线会变**。换 Embedding、扩数据集后，合理基线可能从 `0.95` 变成 `0.88`；写死的绝对线会逼人调门槛而不是查回归。
2. **风险不对称**。安全类指标（泄漏、非法引用）必须绝对为 0；质量类指标更关心「相对上次发布掉了多少」。

因此质量类用 `max_drop`：相对**已锁定的 baseline 报告**，同数据集、同口径下允许的最大跌幅。延迟类用 `max_increase`。安全类继续用绝对零。

比较时必须对齐 `dataset_hash`；哈希不一致时 Runner 应拒绝自动判定，要求人工确认是数据变更还是代码回归。

### 小样本百分比陷阱

本地 11 条样例里，拒答类可能只有 2–3 条。一条从「正确拒答」变成「胡答」，`refusal_recall` 就会从 `1.0` 掉到 `0.67`——看起来像崩盘，其实是分母太小。对策：

- 报告同时打印**分子 / 分母**和失败 `case_id`，不只打印百分比。
- CI 对 `n < 30` 的集合只做烟雾与泄漏零门槛，不把质量 `max_drop` 当作硬发布门。
- 扩充数据集时优先补失败类别，而不是继续堆 `simple_rag`。
- 门槛数字要在实际基线生成后确定，正文不预先虚构已达到的准确率。

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

## 和概念篇的分工

| 问题 | 去哪读 |
|---|---|
| 指标怎么定义、Judge 有什么坑、如何采样 | [Agent 评测](./agent-eval) |
| 本仓库 Runner 怎么跑、JSONL 怎么写、报告长什么样 | 本章 |
| 越权与泄漏如何构造攻击样例 | [第 13 章](./agentic-rag-project-security) |
| 检索 Profile 与调试字段 | [第 7 章](./agentic-rag-project-retrieval) |

## 本章小结

本地 Runner 已具备：固定 JSONL + `actor_id`、路由准确率、来源 Recall@K / MRR、拒答 precision·recall、禁用来源泄漏率（门槛 0）、逐条 `failures[]`、数据集哈希与版本信息。引用非法率、Agent 预算类指标可在同一 `score_case` 上扩展。

仍是扩展项、当前 Demo Provider 未接入的：真实 Token / 成本记账、端到端 P50/P95（需真实网络）、LLM Judge 自动打分。这些可以后挂，但不能替代泄漏零门槛与确定性代码指标。

继续阅读[第 16 章：可观测性、测试与部署](./agentic-rag-project-operations)，把这些离线结果与运行时 Trace、日志和指标结合，并用 Docker Compose 启动完整环境，完成健康检查、备份恢复和部署边界。
