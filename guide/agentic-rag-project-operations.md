---
title: 企业知识库 Agentic RAG 实战（十六）：可观测性、测试与部署
description: 用 Trace、结构化日志、指标和成本记录定位 Agent 问题，通过分层检查与 Docker Compose 部署完整服务，并演练备份恢复。
---

# 企业知识库 Agentic RAG 实战（十六）：可观测性、测试与部署

> 离线评测告诉我们版本之间谁更好，生产可观测性要回答某一次请求为什么慢、贵或失败。本章把 API、Worker、Retriever、LangGraph、模型与存储串进同一条 Trace，并给出可重复启动和恢复的部署形态。

## 当前项目边界

配套代码目前提供 `/health`、`/health/live`、`/health/ready`、Dockerfile、Compose 单机启动、结构化评测输出和 44 个自动化测试。它没有 OpenTelemetry SDK、Redis/MinIO/PostgreSQL Compose 服务、数据库迁移、备份脚本或真实 Trace 后端；本章生产观测和恢复段落应作为下一阶段实现清单阅读。

通用概念见 [可观测性、成本与性能](./agent-observability) 与 [部署与交付](./agent-deploy)。本章只回答「本项目一次问答 / 一次入库如何定位、告警和恢复」。

## 一次请求可以沿 Trace 定位

用户报告“上海差旅问题等了十秒”。Trace 展示：

```text
chat.request                         10.2 s
├─ auth.resolve_actor                8 ms
├─ route.classify                  310 ms
├─ graph.plan                      620 ms
├─ retrieval.hybrid                190 ms
│  ├─ embedding.query               72 ms
│  ├─ postgres.vector               31 ms
│  ├─ postgres.keyword              18 ms
│  └─ rerank                        63 ms
├─ graph.assess                    540 ms
├─ model.answer                    7.9 s
└─ citation.validate                12 ms
```

### 口述步骤：怎么判断瓶颈在模型而不是检索

接到“慢了十秒”时，不要先猜 pgvector 或 FastAPI。按这条口令往下读：

1. **看根 Span 总时长与子 Span 之和是否接近。** 这里 `chat.request = 10.2s`，子项加总约 `9.6s`，没有大块“失踪时间”，说明主要开销都在已打点节点里。
2. **先排除鉴权与协议层。** `auth.resolve_actor = 8ms`、`citation.validate = 12ms`，不可能是用户感知延迟的主因。
3. **看检索子树占比。** `retrieval.hybrid = 190ms`，不到总时长的 2%。即使 Embedding、向量、关键词、Rerank 全部叠加，也只有百毫秒级。
4. **看规划与评估。** `graph.plan + graph.assess ≈ 1.16s`，有贡献，但不是 10 秒的主体。
5. **看模型 Span。** `model.answer = 7.9s`，约占 77%。再读模型属性：Provider、模型名、输入/输出 Token、首 Token 延迟、重试次数、HTTP 状态。若首 Token 就很晚、输出 Token 正常，多半是上游排队或模型本身慢；若重试 > 0，要先查 429/5xx。
6. **给出可执行结论。** 本例应查模型配额、并发、Prompt 长度与是否误升到多轮 Agent，而不是先扩容 PostgreSQL。

Trace 同时记录降级、预算、模型和来源数量，但不默认保存完整 Prompt 与原文。

### 对比：检索慢时 Trace 长什么样

同一接口、同样用户话术，若瓶颈在检索，骨架会更像：

```text
chat.request                          4.8 s
├─ auth.resolve_actor                 7 ms
├─ route.classify                   280 ms
├─ graph.plan                       510 ms
├─ retrieval.hybrid                 3.6 s
│  ├─ embedding.query               1.1 s   ← 外部 Embedding 排队
│  ├─ postgres.vector               1.7 s   ← 慢查询 / 缺索引 / 锁等待
│  ├─ postgres.keyword              420 ms
│  └─ rerank                        310 ms
├─ graph.assess                     390 ms
├─ model.answer                     620 ms
└─ citation.validate                 11 ms
```

读法对照：

| 观察 | 模型慢（上例） | 检索慢（本例） |
|---|---|---|
| 最大子 Span | `model.answer` | `retrieval.hybrid` |
| 检索占比 | < 5% | > 70% |
| 下一步 | Provider 延迟、Token、重试、路线升级 | Embedding SLA、`EXPLAIN`、Rerank 超时、索引版本 |

两张 Trace 都要带上 `request_id` / `run_id`，才能把用户投诉、SSE 事件和后端 Span 对上号。

## Trace、日志和指标各自回答不同问题

| 信号 | 适合回答 |
|---|---|
| Trace | 单次请求跨服务经过了哪些步骤，时间花在哪里 |
| 结构化日志 | 某个错误发生时的离散上下文和审计事件 |
| 指标 | 一段时间内错误率、延迟、队列、Token 和成本趋势 |

三者共享关联字段。日志文本不要依赖人工拼接：

```python
logger.info(
    "retrieval_completed",
    request_id=request_id,
    actor_scope_hash=scope.hash,
    profile=profile.name,
    candidate_count=len(candidates),
    selected_count=len(evidence),
    degraded=rerank_degraded,
)
```

不要记录 JWT、API Key、完整预签名 URL 和默认完整文档内容。调试采样需要显式开关、访问控制和保留期限。

## 关联字段必须出现在哪条链路上

| 字段 | 必须出现的链路 | 作用 | 缺失时的症状 |
|---|---|---|---|
| `request_id` | HTTP 入口 → 中间件 → 结构化日志 → 根 Trace → 错误响应头 | 把一次外部调用从网关串到进程内所有日志 | 用户只报“刚才很慢”，无法精确回放 |
| `run_id` | `run.started` SSE → LangGraph Checkpoint → Agent Span → 成本账本 | 标识一次问答执行；取消、恢复、评测都靠它 | SSE 事件与模型调用对不上；人工审批无法 resume |
| `task_id` | 入库 API → Outbox payload → Redis 消息 → Worker 领取 → 阶段结果表 | 标识一次文档处理；幂等键和租约都挂在它上面 | Relay 补投后 Worker 找不到任务；重试生成幽灵任务 |
| `actor_scope_hash` | 检索日志 → 缓存键 → 评测报告 → 安全审计 | 在不落明文权限列表的前提下证明“按谁的可见范围检索” | 无法证明缓存未串租户；越权复盘缺证据 |

补充约定：

- `request_id` 可以由客户端透传，服务端必须校验格式并在缺失时生成；响应头回写，方便前端一键报障。
- `run_id` 只属于问答 / Agent 执行，不要拿它当入库任务 ID。
- `task_id` 只属于入库流水线；Outbox 的 `payload` 至少包含它。
- `actor_scope_hash` 是权限集合的稳定哈希，不是用户 ID；日志里可以同时有 `actor_id`，但缓存键必须用 scope hash，避免“同用户换团队后命中旧缓存”。

## 为 Agent 节点建立 Span

每个 LangGraph 节点创建 Span：

```python
with tracer.start_as_current_span("agent.retrieve") as span:
    span.set_attribute("agent.run_id", run_id)
    span.set_attribute("retrieval.profile", profile.name)
    span.set_attribute("retrieval.round", budget.retrieval_rounds)
    span.set_attribute("evidence.count", len(evidence))
```

模型 Span 记录 Provider、模型、输入输出 Token、首 Token 延迟、总延迟、重试与状态码。工具 Span 记录工具名和结果类型，不记录敏感参数原文。

Trace 的父子关系与图节点一致，才能从一次失败回到具体 Plan、查询和退出原因。本地仓库尚未接入 OpenTelemetry；上面是接入后的约定，不是当前可导出的 Jaeger 画面。

## 关键指标围绕用户结果

### API 与 Agent

- 请求量、错误率、P50/P95/P99。
- 首事件和首 Token 延迟。
- 成功、部分回答、拒答、取消比例。
- 每条路线的执行次数和升级比例。
- 每个 Run 的模型调用、检索轮数和 Token。

### 检索

- 向量、关键词、Rerank 各阶段延迟。
- 候选数、去重数、最终 Evidence 数。
- Rerank 降级率和空结果率。

### 入库

- 各状态任务数量、队列等待时间和处理时长。
- 每阶段失败率、重试次数、租约过期数。
- 候选索引积压和 Outbox 未投递数量。

### 依赖与成本

- PostgreSQL 连接池、慢查询、锁等待。
- Redis 队列长度和消费者滞后。
- MinIO 容量与失败请求。
- 按模型、路线和知识库聚合的 Token 与估算费用。

告警要指向可行动问题，例如“Outbox 最老未投递事件超过 60 秒”，而不是只报告 CPU 短暂升高。

## 指标 → 告警：阈值思路与对应动作

从上面清单挑出最容易在生产里“拖死用户体验或数据一致性”的几项：

| 指标 | 阈值思路 | 对应动作 |
|---|---|---|
| Outbox 最老未投递年龄 | 持续 > 60s，或未投递条数短时陡增 | 查 Relay 是否存活、Redis 是否可写；必要时手工 `SELECT ... FOR UPDATE SKIP LOCKED` 补扫；见 [消息队列](./message-queue) |
| Worker 租约过期次数 | 5 分钟内明显多于基线，或同一 `task_id` 反复过期 | 查 Worker OOM / 死锁 / 阶段超时；调大租约或拆长阶段；避免盲目加并发把数据库打满 |
| Rerank 降级率 | 滚动窗口 > 5%–10%，或连续 N 分钟非零 | 查 Rerank 服务延迟与超时配置；确认降级路径仍做权限过滤；在 SSE `run.warning` 中可观测 |
| 禁用来源泄漏次数 | **任何非零立即告警**，与评测门槛 `forbidden_source_leakage_rate: 0` 同口径 | 阻断发布 / 切流量；按 `request_id` 回放检索 SQL、缓存键与 Trace；见 [第 13 章](./agentic-rag-project-security)、[第 15 章](./agentic-rag-project-evaluation) |
| 问答 P95 延迟 | 相对基线升高 > 20%，或绝对超过产品承诺 | 先用 Trace 分桶（模型 vs 检索 vs 规划）；不要先扩 API 副本 |
| Redis 队列深度 / 消费滞后 | 深度持续上升且 Worker CPU 未打满，或滞后 > 入库 SLO | 查领取失败、毒消息、租约；扩 Worker 前先确认幂等与 DB 连接池 |

阈值数字要在首轮真实观察后标定；上表给的是“从哪类信号出发”，不是假装本地已经接了 Prometheus 规则。

## 测试按风险分层

```text
单元测试
  权限策略、Chunk、RRF、引用映射、预算和状态转换

集成测试
  PostgreSQL 权限 SQL、pgvector、MinIO、Redis、Outbox 和迁移

契约测试
  模型适配器、SSE 事件 Schema、工具输入输出

端到端测试
  上传 -> 处理 -> 审核 -> 问答 -> 引用 -> 权限

评测
  固定数据集上的检索与 Agent 质量
```

不是每个函数都需要测试。重点锁住跨边界行为：无权内容不进入候选、失败索引不切换、重复消息不重复写、引用只来自本次 Evidence、流一定产生终态。

模型相关测试使用录制或受控 Fake 验证协议，少量真实 Provider 冒烟用于发现兼容差异。不能让全部 CI 都依赖不稳定外部网络。

## Docker Compose 体现真实服务边界

下面是**本章示例 / 生产清单**中的拓扑草案，不是本地仓库已经落地的 Compose 文件。本地目前只有 API（及可选同镜像 Worker）的单机启动路径，没有把 Redis / MinIO / PostgreSQL 写进配套 `docker-compose.yml`。

```yaml
services:
  api:
    build: .
    command: uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
    depends_on:
      postgres: {condition: service_healthy}
      redis: {condition: service_healthy}
      minio: {condition: service_healthy}

  worker:
    build: .
    command: uv run python -m app.worker

  outbox-relay:
    build: .
    command: uv run python -m app.outbox_relay

  migrate:
    build: .
    command: uv run alembic upgrade head
    profiles: ["migrate"]

  postgres:
    image: pgvector/pgvector:pg17

  redis:
    image: redis:8-alpine

  minio:
    image: minio/minio
```

### 哪些是本地已有，哪些是本章示例

| 组件 | 状态 |
|---|---|
| 应用 Dockerfile、非 root 运行约定 | 本地已有 |
| `/health`、`/health/live`、`/health/ready` | 本地已有 |
| Compose 拉起 API（及演示用 Worker 命令） | 本地已有单机路径 |
| `postgres` / `redis` / `minio` 服务定义 | **本章示例**，生产清单项 |
| `outbox-relay` 独立进程 | **本章示例**；本地有 Outbox 表脚手架，无 Redis Relay 消费 |
| `migrate` 一次性 Job | **本章示例**；本地仍以 SQLite / 启动建表为主 |
| OTel Collector / Jaeger / Prometheus | **不在本章示例里宣称**，属后续观测后端 |

### 为什么 API / Worker / Relay 同镜像、不同 command

1. **同一份业务代码与依赖锁文件。** 入库状态机、权限常量、Schema 版本必须一致；分三个镜像容易出现“API 已升级、Worker 仍写旧 Chunk 格式”。
2. **构建与漏洞扫描只做一次。** CI 产出一个 digest，部署时按角色覆盖 `command`。
3. **进程职责不同，扩展方式不同。** API 按 SSE/QPS 扩；Worker 按队列深度扩；Relay 通常少量副本即可，但必须能抢占 Outbox 行。
4. **密钥与配置注入点统一。** 模型 Key、数据库 URL 来自运行环境，不写入镜像层，也不进 Compose 明文。

数据库迁移作为独立一次性 Job 执行，不能让多个 API 实例启动时同时跑迁移。镜像使用锁文件安装依赖、非 root 用户运行，并设置内存和 CPU 限制。更完整的交付清单见 [部署与交付](./agent-deploy)。

## 健康检查区分存活与就绪

```text
/health/live   进程事件循环仍能响应
/health/ready  数据库迁移完成，关键依赖可用，实例可以接流量
```

伪代码级判断：

```python
async def live() -> dict:
    # 只证明事件循环没卡死；不查外部依赖
    return {"status": "ok"}


async def ready(deps) -> tuple[int, dict]:
    checks = {}
    try:
        await deps.db.execute("SELECT 1")
        checks["postgres"] = "ok"
    except Exception as exc:
        checks["postgres"] = f"down:{type(exc).__name__}"
        # 不能认证、不能检索、不能创建 Run → 退出就绪，摘流量
        return 503, {"status": "not_ready", "checks": checks}

    try:
        await deps.redis.ping()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "down"
        # 若问答强依赖队列/缓存，同样 503；若仅入库受影响，可按角色拆探针
        return 503, {"status": "not_ready", "checks": checks}

    model_status = await deps.model.health()
    if model_status == "ok":
        checks["model"] = "ok"
        return 200, {"status": "ready", "checks": checks}

    if model_status in {"timeout", "429"}:
        # 模型短暂不可用：实例仍可接流量，走降级/拒答/只读检索策略
        checks["model"] = "degraded"
        return 200, {"status": "degraded", "checks": checks}

    checks["model"] = "down"
    return 200, {"status": "degraded", "checks": checks}
```

要点：

- **PostgreSQL down → `ready` 必须 false（503）。** 没有元数据与权限真相，不能假装健康。
- **模型 429 / 短暂超时 → 可选 `degraded`。** 是否继续接流量取决于产品：可以拒答、降级到固定 RAG，或对写路径返回明确错误；不要因此让编排层疯狂重启容器。
- Worker 就绪还要检查能否访问数据库、队列和对象存储。
- 健康检查本身设置短超时，不能因为依赖卡死占满探针线程。

## 迁移采用向后兼容顺序

部署不假设所有实例同时更新：

1. 先增加可空字段或新表。
2. 部署同时兼容新旧结构的代码。
3. 后台回填数据并观察。
4. 切换读取路径。
5. 后续版本再增加非空约束或删除旧字段。

Embedding 模型切换也按类似方式创建新索引版本、双读评估、原子切换和延迟清理。不要直接修改向量列维度让线上旧数据失效。PostgreSQL 侧的备份、连接与运维基线见 [PostgreSQL](./postgresql)。

## 备份需要恢复演练

需要备份：

- PostgreSQL：业务元数据、Chunk、任务、Outbox、Checkpoint 和审计。
- MinIO：不可变原文件和阶段产物。
- 配置：模型/Profile/Prompt 版本和迁移版本。

Redis 队列不作为唯一事实来源，可以从 PostgreSQL 的任务和 Outbox 重建——这也是 [消息队列](./message-queue) 与事务 Outbox 章节反复强调的一点。恢复顺序是 PostgreSQL、MinIO、迁移校验、候选索引核对、补投任务，最后开放流量。发布与回滚节奏见 [部署与交付](./agent-deploy)。

### 恢复演练检查表

| # | 验证项 | 通过标准 | 失败时优先排查 |
|---|---|---|---|
| 1 | 已发布文档仍能检索并打开引用 | 公共制度问答命中，引用可下载 | PostgreSQL Chunk / MinIO 原对象是否成对恢复 |
| 2 | 无权用户仍然无法访问团队文档 | Alice 查研发库仍无候选、统一 404 | RLS / SearchScope / 恢复后的角色表是否完整 |
| 3 | 未完成任务能够重新投递 | Outbox `published_at IS NULL` 被 Relay 清掉，Worker 继续 | Relay 进程、队列、租约；见 [消息队列](./message-queue) |
| 4 | `active_index_version` 对应完整 Chunk | 活动版本无空洞，检索不混入候选脏数据 | 索引版本表与 Chunk 外键；切流是否过早 |
| 5 | 审计和 Checkpoint 没有跨用户错配 | 按 `run_id` / `actor_id` 抽查无串味 | 恢复范围是否误覆盖会话表；scope hash 是否重算 |

只有生成备份文件而没有做过恢复，不能证明备份可用。把上表打进演练记录：时间、操作人、数据集版本、是否开放流量。

## 部署后的首轮观察

```bash
docker compose up -d
docker compose run --rm migrate
docker compose run --rm seed-fixtures
```

上述命令描述的是**接入完整依赖后的目标流程**。本地若仍是 SQLite 单机，用现有启动方式跑通健康探针与测试即可，不要把未提供的 `postgres`/`redis` 服务假装已经 `up`。

启动后完成一条公共制度问答、一条研发权限对照、一份文件入库和一次 Worker 故障恢复。随后运行固定评测集并保存环境信息。

容量和告警阈值从这些真实结果开始建立。教程不会先声称支持多少并发；可以给出测量环境、请求组合和瓶颈，再据此做容量估算。

## 本章小结

### 本地已有

- `/health`、`/health/live`、`/health/ready` 探针与 Dockerfile。
- Compose 单机启动 API（及演示用 Worker 命令）。
- 结构化评测输出、44 个自动化测试、安全与评测门槛中的泄漏零容忍口径。
- 入库任务状态、条件领取、事务内 Outbox 行等可靠性脚手架。

### 生产待办

- OpenTelemetry SDK、Trace 后端、统一指标与告警规则。
- Redis / MinIO / PostgreSQL 完整 Compose（或等价编排）与迁移 Job。
- Outbox Relay 独立进程、租约心跳、备份脚本与定期恢复演练。
- 将本章关联字段、Span 约定和「指标 → 动作」表落到真实仪表盘。

统一 Trace、完整依赖拓扑、备份恢复和指标后端仍未在配套项目中实现，不能把示例配置当成已完成部署。

继续阅读[第 17 章：项目复盘与求职表达](./agentic-rag-project-career)，把已经实现和验证的内容整理成演示脚本、架构说明、真实指标和求职材料，保证每一句项目描述都能在代码、测试或报告中找到证据。
