---
title: 企业知识库 Agentic RAG 实战（十六）：可观测性、测试与部署
description: 用 Trace、结构化日志、指标和成本记录定位 Agent 问题，通过分层检查与 Docker Compose 部署完整服务，并演练备份恢复。
---

# 企业知识库 Agentic RAG 实战（十六）：可观测性、测试与部署

> 离线评测告诉我们版本之间谁更好，生产可观测性要回答某一次请求为什么慢、贵或失败。本章把 API、Worker、Retriever、LangGraph、模型与存储串进同一条 Trace，并给出可重复启动和恢复的部署形态。

## 当前项目边界

配套代码目前提供 `/health`、`/health/live`、`/health/ready`、Dockerfile、Compose 单机启动、结构化评测输出和 44 个自动化测试。它没有 OpenTelemetry SDK、Redis/MinIO/PostgreSQL Compose 服务、数据库迁移、备份脚本或真实 Trace 后端；本章生产观测和恢复段落应作为下一阶段实现清单阅读。

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

瓶颈清楚地位于回答模型，不需要先怀疑 pgvector 或 FastAPI。Trace 同时记录降级、预算、模型和来源数量，但不默认保存完整 Prompt 与原文。

## Trace、日志和指标各自回答不同问题

| 信号 | 适合回答 |
|---|---|
| Trace | 单次请求跨服务经过了哪些步骤，时间花在哪里 |
| 结构化日志 | 某个错误发生时的离散上下文和审计事件 |
| 指标 | 一段时间内错误率、延迟、队列、Token 和成本趋势 |

三者共享 `request_id`、`run_id`、`task_id` 等关联字段。日志文本不要依赖人工拼接：

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

不要记录 JWT、API Key、完整预签名 URL和默认完整文档内容。调试采样需要显式开关、访问控制和保留期限。

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

Trace 的父子关系与图节点一致，才能从一次失败回到具体 Plan、查询和退出原因。

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
- Rerank 降级率和无结果率。

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

  postgres:
    image: pgvector/pgvector:pg17

  redis:
    image: redis:8-alpine

  minio:
    image: minio/minio
```

API、Worker 和 Relay 使用同一镜像，不同启动命令。数据库迁移作为独立一次性 Job 执行，不能让多个 API 实例启动时同时跑迁移。

镜像使用锁文件安装依赖、非 root 用户运行，并设置内存和 CPU 限制。模型密钥由运行环境注入，不写入镜像和 Compose 文件。

## 健康检查区分存活与就绪

```text
/health/live   进程事件循环仍能响应
/health/ready  数据库迁移完成，关键依赖可用，实例可以接流量
```

模型供应商短暂不可用不一定让 API 实例退出就绪，可根据产品降级策略返回 `degraded`。PostgreSQL 完全不可用则不能认证、检索或创建 Run，应退出就绪。

Worker 就绪还要检查能否访问数据库、队列和对象存储。健康检查本身设置短超时，不能因为依赖卡死占满探针线程。

## 迁移采用向后兼容顺序

部署不假设所有实例同时更新：

1. 先增加可空字段或新表。
2. 部署同时兼容新旧结构的代码。
3. 后台回填数据并观察。
4. 切换读取路径。
5. 后续版本再增加非空约束或删除旧字段。

Embedding 模型切换也按类似方式创建新索引版本、双读评估、原子切换和延迟清理。不要直接修改向量列维度让线上旧数据失效。

## 备份需要恢复演练

需要备份：

- PostgreSQL：业务元数据、Chunk、任务、Outbox、Checkpoint 和审计。
- MinIO：不可变原文件和阶段产物。
- 配置：模型/Profile/Prompt 版本和迁移版本。

Redis 队列不作为唯一事实来源，可以从 PostgreSQL 的任务和 Outbox 重建。恢复顺序是 PostgreSQL、MinIO、迁移校验、候选索引核对、补投任务，最后开放流量。

一次恢复演练至少验证：

1. 已发布文档仍能检索并打开引用。
2. 无权用户仍然无法访问团队文档。
3. 未完成任务能够重新投递。
4. 文档 `active_index_version` 对应完整 Chunk。
5. 审计和 Checkpoint 没有跨用户错配。

只有生成备份文件而没有做过恢复，不能证明备份可用。

## 部署后的首轮观察

```bash
docker compose up -d
docker compose run --rm migrate
docker compose run --rm seed-fixtures
```

启动后完成一条公共制度问答、一条研发权限对照、一份文件入库和一次 Worker 故障恢复。随后运行固定评测集并保存环境信息。

容量和告警阈值从这些真实结果开始建立。教程不会先声称支持多少并发；可以给出测量环境、请求组合和瓶颈，再据此做容量估算。

## 本章小结

当前系统可通过健康探针、固定评测和自动化测试验证本地链路，并用 Compose 启动 API 与 Worker。统一 Trace、Redis/MinIO/PostgreSQL 拓扑、备份恢复和指标后端仍未在配套项目中实现，不能把示例配置当成已完成部署。

继续阅读[第 17 章：项目复盘与求职表达](./agentic-rag-project-career)，把已经实现和验证的内容整理成演示脚本、架构说明、真实指标和求职材料，保证每一句项目描述都能在代码、测试或报告中找到证据。
