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

没有 Outbox 时的时间线：

```text
1. BEGIN
2. INSERT ingestion_tasks(status=queued)
3. COMMIT                     ← 任务已成事实
4. redis.publish(...)         ← 进程在这里崩溃
5. Worker 永远收不到消息
6. 文档状态卡在 processing
```

有 Outbox 时的时间线：

```text
1. BEGIN
2. INSERT ingestion_tasks(status=queued)
3. INSERT outbox_events(published_at=NULL)
4. COMMIT                     ← 任务与发送意图同事务落库
5. 进程崩溃，publish 没发生
6. Relay: SELECT ... FOR UPDATE SKIP LOCKED
7. Relay: redis.publish(...)
8. Relay: UPDATE published_at = now()
9. Worker 领取并继续处理
```

面试官若追问“为什么不能先写任务、再另开事务写 Outbox”，答案就在第 3、4 步之间：那是第二个失败窗口，任务已提交、发送意图尚未落库，和“无 Outbox”等价。

### 故障 B：消息重复

Worker 完成任务后尚未确认队列消息就崩溃，消息再次投递。第二个 Worker 重复调用 Embedding 并写入相同 Chunk。

```text
1. Worker-1 领取消息
2. 解析 / Embedding / 写候选 Chunk 全部成功
3. 标记 task=succeeded（或准备 ACK）
4. 进程崩溃，队列未收到 ACK
5. Broker 重投同一条消息
6. Worker-2 再次进入同一阶段
7. 查 stage_results：idempotency_key 已 succeeded → 直接复用 output_ref
8. Chunk 唯一约束挡住“同身份二次插入”
9. ACK；业务结果与第一次相同（no-op）
```

关键点：重复执行可以发生，但**结果身份不能分叉**。允许再算一次 Embedding 账单，不允许出现两套 Chunk ID。

### 故障 C：候选索引只写了一半

100 个 Chunk 写入 60 个后数据库连接中断。如果发布逻辑只检查“存在 Chunk”，用户会检索到残缺制度。

```text
1. Worker 创建 candidate_index_version = idx-v8
2. 写入 Chunk 1..60 / 100
3. 连接中断，进程退出
4. 若此时把 active_index_version 切到 idx-v8
   → 检索命中残缺制度，用户看到半份规章
5. 正确做法：切换事务内校验
   chunk_count == expected_chunk_count
   embedding_dimensions == expected_dimensions
6. 任一条件不满足 → 拒绝切换，active 仍指向 idx-v7
7. 租约过期或补偿扫描后，任务重排队，继续写同一候选或重建候选
```

完整性条件不是“表里有没有行”，而是**与任务声明的期望完全一致**。写一半的候选可以留着给调试，但绝对不能成为 `active`。

目标不是实现分布式“恰好一次”。本项目接受队列至少一次投递，通过业务幂等和版本切换让重复执行得到相同结果。投递语义的通用讨论见 [消息队列](./message-queue)；Outbox 的通用原理见 [分布式一致性](./distributed-consistency)。本章只讲入库域怎么落地。

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

### 为什么必须同事务

对比两种写法：

| 写法 | 失败窗口 | 结果 |
|---|---|---|
| 同事务写 task + outbox | 提交后、Relay 投递前崩溃 | 有未发布事件，Relay 可救 |
| 先提交 task，另事务写 outbox | task 已提交、outbox 未写就崩溃 | 永久静默，和故障 A 无 Outbox 相同 |
| 先发 Redis，再写 task | 消息已出、task 未落库 | Worker 查无任务或重复创建 |

入库域的硬约束是：**发送意图必须和业务事实一起提交**。Relay 是异步补投器，不是第二个业务写入口。

### Relay：`SKIP LOCKED` 与 published 标记

独立 Relay 使用 `FOR UPDATE SKIP LOCKED` 批量读取未发布事件，投递 Redis 后记录 `published_at`：

```sql
SELECT * FROM outbox_events
WHERE published_at IS NULL
ORDER BY created_at
FOR UPDATE SKIP LOCKED
LIMIT 100;
```

多个 Relay 副本同时扫表时，`SKIP LOCKED` 让彼此跳过对方已锁住的行，避免争用同一批事件。认领后的典型步骤：

```text
1. 短事务锁住一批 published_at IS NULL 的行
2. 投递 Redis（事务外或短事务后）
3. UPDATE published_at = now() WHERE id IN (...)
```

投递成功但标 `published_at` 失败时：

```text
1. Redis 已收到消息
2. 行仍是 published_at IS NULL
3. 下一次 Relay 再投一次 → 重复消息
4. 消费者靠幂等键把第二次变成 no-op
```

因此 Outbox 的承诺是“不悄悄丢”，不是“只投一次”。本地项目已有事务内 Outbox **记录**；把这些记录真正推到 Redis 的 Relay 仍是生产待办，面试时不要说成已上线。

## 每个阶段都有确定幂等键

```text
task_id + stage + input_fingerprint + pipeline_version
```

每一项变化的含义：

| 组成部分 | 变了意味着什么 | 典型场景 |
|---|---|---|
| `task_id` | 另一次入库执行 | 用户重提、人工重试生成新任务 |
| `stage` | 流水线中的不同步骤 | `parse` 与 `embedding` 产物不能互相复用 |
| `input_fingerprint` | 输入或关键配置变了 | 原文件 ETag、切分策略、解析器选项变化 |
| `pipeline_version` | 处理逻辑/模型协议变了 | **换 Embedding 模型必须升版本**，否则旧向量与新空间混用 |

`input_fingerprint` 至少包含：原文件 ETag（或内容哈希）、解析配置、Embedding 模型名与维度、切分策略版本。相同输入重试复用结果；任一关键配置变化都会生成新键，强制重算。

### `stage_results` 最小字段

```sql
CREATE TABLE stage_results (
  idempotency_key   TEXT PRIMARY KEY,  -- task_id+stage+fingerprint+pipeline_version
  task_id           TEXT NOT NULL,
  stage             TEXT NOT NULL,
  status            TEXT NOT NULL,     -- running/succeeded/failed
  output_ref        TEXT,              -- 对象存储路径或候选版本号
  error_code        TEXT,
  attempt           INT NOT NULL DEFAULT 0,
  created_at        TIMESTAMPTZ NOT NULL,
  updated_at        TIMESTAMPTZ NOT NULL
);
```

Worker 进入阶段时先查表：

```python
result = await stage_results.get(idempotency_key)
if result and result.status == "succeeded":
    return result.output_ref
```

若状态是 `running` 且租约仍有效，后来者应退出或等待，而不是并行再开一套产物。

### 允许重复算，不允许重复身份

外部 Embedding 请求如果支持幂等键就一并传递；不支持时允许重复计算，但写入使用唯一约束覆盖同一个候选版本和 Chunk 位置，不能产生两套身份：

```sql
-- 同一候选版本、同一文档内位置只能有一条 Chunk
UNIQUE (document_id, index_version, chunk_ordinal)

-- 或用稳定业务 ID：内容哈希 + 版本
UNIQUE (document_id, index_version, content_hash)
```

替换语义通常是：先按 `(document_id, index_version)` 清理或 upsert，再写入本批。面试一句话：**账单可以花两次，主键只能有一份。**

## 候选索引与活动索引分离

```text
document.active_index_version    = idx-v7
task.candidate_index_version     = idx-v8
```

Worker 始终写候选版本。只有满足完整性条件后才切换。

### 切换事务里锁什么、查什么

```python
async with session.begin():
    # 1. 锁住文档行，防止并发发布/回滚抢指针
    doc = await documents.lock_for_update(document.id)

    # 2. 锁住候选索引统计行（或聚合校验）
    stats = await indexes.lock_and_get_stats(document.id, "idx-v8")

    # 3. 完整性条件：数量与维度都必须对齐任务声明
    if stats.chunk_count != task.expected_chunk_count:
        raise IncompleteIndexError()
    if stats.embedding_dimensions != task.expected_dimensions:
        raise InvalidIndexError()

    # 4. 仍持有租约才允许提交（见下一节）
    claimed = await tasks.claim_finalization(task.id, worker_id)
    if not claimed:
        raise LeaseLostError()

    # 5. 原子切换指针并收尾任务
    await documents.activate_index(document.id, "idx-v8")
    await tasks.mark_succeeded(task.id)
```

完整性条件汇总：

- `chunk_count == expected_chunk_count`
- `embedding_dimensions == expected_dimensions`
- 可选：无空向量、无重复 `chunk_ordinal`、校验和一致
- 切换者仍是当前 `lease_owner`

### 检索只读 active；回滚与 GC

检索 SQL 条件一句话：

```sql
WHERE c.document_id = :doc_id
  AND c.index_version = d.active_index_version
  AND d.status = 'published';
```

写到一半的 `idx-v8` 对用户不可见；切换失败时 `idx-v7` 继续服务。

旧索引不会立即删除。保留一个回滚窗口（例如 24–72 小时，或“连续 N 次检索健康检查通过”），后台 GC 确认没有运行中的任务、缓存或审计引用后再清理。回滚是把 `active_index_version` 指回旧版本，而不是从对象存储“撤销写入”。

本地项目目前用幂等 Chunk 替换保证重复写入可收敛；**候选/活动双版本切换仍是生产待办**。

## 租约与心跳处理 Worker 崩溃

任务领取时设置 `lease_owner` 和 `lease_expires_at`。Worker 每隔固定时间续租，并在写阶段结果时检查自己仍持有租约。

### 心跳 SQL

```sql
UPDATE ingestion_tasks
SET lease_expires_at = now() + interval '60 seconds',
    updated_at = now()
WHERE id = :task_id
  AND lease_owner = :worker_id
  AND status = 'running'
  AND lease_expires_at > now();
```

`rowcount = 0` 表示租约已丢：应停止写最终状态，最多把本地缓冲丢弃或写入可丢弃的调试日志。

### 过期扫描

```sql
UPDATE ingestion_tasks
SET status = 'queued',
    lease_owner = NULL,
    lease_expires_at = NULL,
    attempt = attempt + 1
WHERE status = 'running'
  AND lease_expires_at < now()
RETURNING id;
```

扫描器为每个回收的任务写审计事件（`lease_expired`），再依赖 Outbox/任务表让新的 Worker 接手。

### 旧 Worker 醒过来为何提交不了

```text
1. Worker-1 持有租约，写到一半卡住（GC / 网络）
2. 租约过期，扫描器把任务重新 queued
3. Worker-2 领取，lease_owner = worker-2
4. Worker-1 恢复，尝试 activate_index / mark_succeeded
5. UPDATE ... WHERE lease_owner = 'worker-1' → 影响 0 行
6. Worker-1 放弃；只有 Worker-2 能完成切换
```

最终切换语句必须带 `lease_owner` 条件，否则“僵尸提交”会覆盖新 Worker 的进度。

### 时钟漂移与经验值

系统时钟误差、长时间 GC 和数据库暂停都可能造成误判：

| 参数 | 经验起点 | 说明 |
|---|---|---|
| 心跳间隔 | 10–15s | 远小于租约，连续丢几次心跳才过期 |
| 租约时长 | 45–90s | 明显大于心跳，吸收短暂停顿 |
| 时钟容忍 | 数秒级 NTP 偏差可接受 | 跨机房用 DB `now()` 做权威时间 |
| 阶段写入 | 始终幂等 | 误回收后重跑不会腐蚀数据 |

租约时间应明显大于正常心跳间隔，并让阶段写入保持幂等。本地项目的条件领取还不是带心跳的租约；**续租与过期扫描是生产待办**。

## 补偿扫描修复悬挂资源

定时 Reconciler 检查：

- 有草稿记录但正式对象不存在。
- MinIO 临时对象超过保留时间。
- `queued` 任务没有未发布 Outbox 事件。
- `running` 任务租约已过期。
- 候选索引完成但文档指针未切换。
- 已归档版本仍被普通检索缓存引用。

补偿不是“发现异常就删除”。每类异常有明确修复策略、最大尝试次数和人工队列。例如对象丢失无法自动重建时，把文档标记为 `failed` 并保留数据库证据。

建议每条修复路径都产出审计事件：`anomaly_type`、`detected_at`、`action`、`attempts`、`escalated`。没有审计的补偿，排障时无法证明系统曾经自愈过。

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

恢复后半开少量探测请求，成功再逐步放量。不要在熔断时自动切换到不同维度的 Embedding 模型，否则同一索引版本会进入两个向量空间——这正是 `pipeline_version` 必须升级的原因。

## Agent Run 也需要幂等和截止时间

聊天请求带 `Idempotency-Key`。相同用户、相同键重复提交时返回原 Run，而不是启动两张图。工具写操作使用更细的业务幂等键。

运行级截止时间到达后：

- 取消尚未开始的模型调用。
- 已有足够证据时生成受限的部分回答。
- 没有证据时返回可重试错误或拒答。
- 保存 `exit_reason=deadline_exceeded`。

进程崩溃后，从最后 Checkpoint 恢复；恢复前重新加载权限和工具提案状态。Agent 轨迹级的预算、熔断与断点续跑细节见 [Agent 生产可靠性](./agent-reliability)；本章只要求入库与问答共享同一套“至少一次 + 业务幂等”语言。

## 故障注入比成功演示更重要

本章准备可控制的故障点：

```env
FAULT_AFTER_OUTBOX_COMMIT=1
FAULT_AFTER_CHUNK_BATCH=3
FAULT_BEFORE_INDEX_SWITCH=1
FAULT_MODEL_STATUS=429
FAULT_DROP_LEASE_HEARTBEAT=1
```

### 实验记录表模板

| 实验 ID | Fault 开关 | 注入时机 | 期望可观测信号 | 通过标准 | 实际结果 | 结论 |
|---|---|---|---|---|---|---|
| F-A1 | `FAULT_AFTER_OUTBOX_COMMIT=1` | task+outbox 提交后、publish 前杀进程 | outbox 行 `published_at IS NULL`；随后 Relay 日志出现补投 | 任务最终被 Worker 领取；文档不永久卡在 processing | | |
| F-B1 | 完成业务后杀进程（模拟未 ACK） | Worker 成功写完候选后、ACK 前崩溃 | 同一消息二次投递；第二次 stage_results 命中 succeeded | Chunk 数量不增加；唯一约束无冲突；用户可见结果不变 | | |
| F-C1 | `FAULT_AFTER_CHUNK_BATCH=3` | 第 3 批 Chunk 写完后中断 | 候选 `chunk_count < expected`；active 仍为旧版本 | 检索只命中旧索引；无残缺制度暴露 | | |
| F-C2 | `FAULT_BEFORE_INDEX_SWITCH=1` | 完整性校验通过后、指针切换前崩溃 | 候选完整但 `active_index_version` 未变 | 补偿或重试完成后才切换；中间检索仍用旧版 | | |
| F-L1 | `FAULT_DROP_LEASE_HEARTBEAT=1` | Worker-1 停止续租 | 过期扫描把任务重新 queued；Worker-2 成为 lease_owner | Worker-1 恢复后最终提交影响 0 行；只有所有者切换成功 | | |
| F-M1 | `FAULT_MODEL_STATUS=429` | Embedding 连续返回 429 | 任务进入 `retry_wait/provider_unavailable`；熔断打开 | 尝试次数可见；恢复后半开探测成功再放量；未擅自换模型维度 | | |

每次实验记录最终文档状态、活动索引版本、Chunk 数量、任务事件和用户可见结果。只看到“任务最终成功”还不够，还要确认中间没有暴露残缺索引。

## 本章小结

**本地已有**

- SQLite 任务状态机与条件领取
- 失败后人工/接口重排队
- 事务内 Outbox **记录**（发送意图落库）
- 幂等的 Chunk 替换与跨进程持久化验证

**生产待办（本章描述、本地未宣称已实现）**

- Redis Relay：`SKIP LOCKED` 认领、投递、标记 `published_at`
- 租约心跳、过期扫描、防僵尸最终提交
- 候选 / 活动索引双版本、切换事务内完整性校验、回滚窗口与 GC
- 自动补偿扫描与审计
- 模型调用熔断器
- Agent Run 的 Idempotency-Key、截止时间与 Checkpoint 恢复
- 上表所列故障注入实验作为发布门禁

当前入库通过持久化任务和事务内 Outbox 记录保留投递事实，并以条件领取和替换 Chunk 保证本地重复执行可收敛。Redis Relay、租约、候选索引切换和故障注入仍是生产化待办，不能在本地项目中宣称已经完成。

继续阅读[第 15 章：RAG 与 Agent 离线评测](./agentic-rag-project-evaluation)，把检索、引用、拒答、权限和 Agent 执行变成可重复指标。以后每次调整模型、切分或路由，都必须用同一数据集比较，而不是凭几次聊天感觉效果变好。
