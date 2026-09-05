---
title: 企业知识库 Agentic RAG 实战（十四）：入库可靠性与索引一致性
description: 用事务 Outbox、至少一次投递、幂等阶段、租约、补偿扫描和索引版本切换处理重复消息、进程崩溃与部分失败。
---

# 企业知识库 Agentic RAG 实战（十四）：入库可靠性与索引一致性

> 第 6 章已经把入库放进 Worker，但数据库提交后、Redis 投递前仍有丢任务窗口；Worker 也可能在写完一半向量后崩溃。本章不追求“不失败”，而是让重复、延迟和中断都能收敛到可解释状态。

## 当前项目边界

本地项目已经实现 SQLite 任务状态、条件领取、失败重排队、事务内 Outbox 记录、幂等的 Chunk 替换和跨进程持久化验证。它还没有 Redis Relay、租约心跳、候选/活动索引双版本、自动补偿扫描、熔断器或 Agent Checkpoint；本章这些部分描述接入生产依赖时必须增加的机制。

## 从三个故障开始

### 故障 A：数据库有任务，队列没有消息

API 创建 `ingestion_task` 后进程崩溃，来不及投递 Redis。文档永远停在 `processing`。

### 故障 B：消息重复

Worker 完成任务后尚未确认队列消息就崩溃，消息再次投递。第二个 Worker 重复调用 Embedding 并写入相同 Chunk。

### 故障 C：候选索引只写了一半

100 个 Chunk 写入 60 个后数据库连接中断。如果发布逻辑只检查“存在 Chunk”，用户会检索到残缺制度。

目标不是实现分布式“恰好一次”。本项目接受队列至少一次投递，通过业务幂等和版本切换让重复执行得到相同结果。

## 事务 Outbox 消除投递窗口

创建任务和 Outbox 事件位于同一 PostgreSQL 事务：

```python
async with session.begin():
    task = IngestionTask(document_id=document.id, status="queued", ...)
    session.add(task)
    session.add(
        OutboxEvent(
            aggregate_type="ingestion_task",
            aggregate_id=task.id,
            event_type="ingestion.requested",
            payload={"task_id": str(task.id)},
        )
    )
```

独立 Relay 使用 `FOR UPDATE SKIP LOCKED` 批量读取未发布事件，投递 Redis 后记录 `published_at`：

```sql
SELECT * FROM outbox_events
WHERE published_at IS NULL
ORDER BY created_at
FOR UPDATE SKIP LOCKED
LIMIT 100;
```

Relay 可能在成功投递后、更新 `published_at` 前崩溃，因此消息仍可能重复。Outbox 保证“不悄悄丢”，幂等处理重复。

## 每个阶段都有确定幂等键

```text
task_id + stage + input_fingerprint + pipeline_version
```

`input_fingerprint` 包含原文件 ETag、解析配置、Embedding 模型和切分策略。相同输入重试复用结果，任一关键配置变化都会生成新版本。

```python
result = await stage_results.get(idempotency_key)
if result and result.status == "succeeded":
    return result.output_ref
```

外部 Embedding 请求如果支持幂等键就一并传递；不支持时允许重复计算，但写入使用唯一约束覆盖同一个候选版本和 Chunk 位置，不能产生两套身份。

## 候选索引与活动索引分离

```text
document.active_index_version    = idx-v7
task.candidate_index_version     = idx-v8
```

Worker 始终写候选版本。只有满足完整性条件后才切换：

```python
async with session.begin():
    stats = await indexes.lock_and_get_stats(document.id, "idx-v8")
    if stats.chunk_count != task.expected_chunk_count:
        raise IncompleteIndexError()
    if stats.embedding_dimensions != task.expected_dimensions:
        raise InvalidIndexError()
    await documents.activate_index(document.id, "idx-v8")
    await tasks.mark_succeeded(task.id)
```

检索 SQL 只读取 `active_index_version`。写到一半的 `idx-v8` 对用户不可见，切换失败时 `idx-v7` 继续服务。

旧索引不会立即删除。保留一个回滚窗口，后台 GC 确认没有运行或引用依赖后再清理。

## 租约与心跳处理 Worker 崩溃

任务领取时设置 `lease_owner` 和 `lease_expires_at`。Worker 每隔固定时间续租，并在写阶段结果时检查自己仍持有租约：

```sql
UPDATE ingestion_tasks
SET lease_expires_at = now() + interval '60 seconds'
WHERE id = :task_id
  AND lease_owner = :worker_id
  AND status = 'running';
```

租约过期扫描器把任务重新置为 `queued` 并写审计事件。旧 Worker 即使恢复，也因为租约所有者不匹配无法提交最终切换。

系统时钟误差、长时间 GC 和数据库暂停都可能造成误判，因此租约时间应明显大于正常心跳间隔，并让阶段写入保持幂等。

## 补偿扫描修复悬挂资源

定时 Reconciler 检查：

- 有草稿记录但正式对象不存在。
- MinIO 临时对象超过保留时间。
- `queued` 任务没有未发布 Outbox 事件。
- `running` 任务租约已过期。
- 候选索引完成但文档指针未切换。
- 已归档版本仍被普通检索缓存引用。

补偿不是“发现异常就删除”。每类异常有明确修复策略、最大尝试次数和人工队列。例如对象丢失无法自动重建时，把文档标记为 `failed` 并保留数据库证据。

## 模型服务使用超时、退避和熔断

每次外部调用都设置连接、读取和总截止时间。重试只处理可恢复错误，并受任务总预算限制：

```python
policy = RetryPolicy(
    retryable_statuses={429, 502, 503, 504},
    max_attempts=4,
    base_delay_seconds=1,
    max_delay_seconds=30,
)
```

连续故障达到阈值后熔断器短时间拒绝新调用，让队列积压而不是不断压垮供应商。任务状态显示 `retry_wait/provider_unavailable`，管理员可以区分业务文件问题和外部依赖故障。

恢复后半开少量探测请求，成功再逐步放量。不要在熔断时自动切换到不同维度的 Embedding 模型，否则同一索引版本会进入两个向量空间。

## Agent Run 也需要幂等和截止时间

聊天请求带 `Idempotency-Key`。相同用户、相同键重复提交时返回原 Run，而不是启动两张图。工具写操作使用更细的业务幂等键。

运行级截止时间到达后：

- 取消尚未开始的模型调用。
- 已有足够证据时生成受限的部分回答。
- 没有证据时返回可重试错误或拒答。
- 保存 `exit_reason=deadline_exceeded`。

进程崩溃后，从最后 Checkpoint 恢复；恢复前重新加载权限和工具提案状态。

## 故障注入比成功演示更重要

本章准备可控制的故障点：

```env
FAULT_AFTER_OUTBOX_COMMIT=1
FAULT_AFTER_CHUNK_BATCH=3
FAULT_BEFORE_INDEX_SWITCH=1
FAULT_MODEL_STATUS=429
```

依次观察：

1. Outbox Relay 最终补投任务。
2. 重复消息不产生重复 Chunk。
3. 写入中断时旧索引继续回答。
4. 任务在退避后恢复，尝试次数可见。
5. 两个 Worker 竞争同一任务时只有租约所有者提交。

每次实验记录最终文档状态、活动索引版本、Chunk 数量、任务事件和用户可见结果。只看到“任务最终成功”还不够，还要确认中间没有暴露残缺索引。

## 本章小结

当前入库通过持久化任务和事务内 Outbox 记录保留投递事实，并以条件领取和替换 Chunk 保证本地重复执行可收敛。Redis Relay、租约、候选索引切换和故障注入仍是生产化待办，不能在本地项目中宣称已经完成。

继续阅读[第 15 章：RAG 与 Agent 离线评测](./agentic-rag-project-evaluation)，把检索、引用、拒答、权限和 Agent 执行变成可重复指标。以后每次调整模型、切分或路由，都必须用同一数据集比较，而不是凭几次聊天感觉效果变好。
