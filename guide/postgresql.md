---
title: PostgreSQL 基础与实战
---

# PostgreSQL 基础与实战

> PostgreSQL 适合复杂查询、严格约束、事务一致性和可扩展数据类型。本文以 PostgreSQL 16+ 的通用能力为主；部署前按实际版本核对语法。它不是“换一个连接字符串就能替换 MySQL”：事务、索引、类型、分页和运维都需要重新验证。

## 什么时候考虑 PostgreSQL

| 场景 | PostgreSQL 的优势 | 注意事项 |
|---|---|---|
| 复杂 JOIN、窗口、CTE | SQL 能力完整，执行计划可解释 | 查询仍需索引与 `EXPLAIN` 验证 |
| 强约束业务模型 | `CHECK`、排他约束、部分唯一索引 | 约束迁移需处理历史脏数据 |
| 地理空间 | PostGIS 生态成熟 | 扩展、坐标系和索引需单独学习 |
| 半结构化字段 | `jsonb`、GIN 索引、丰富操作符 | 热点字段仍应正规化 |
| 高并发事务 | MVCC、行锁、`SKIP LOCKED` | 长事务会阻塞 vacuum，造成膨胀 |

不要按“哪个数据库更高级”选型。先看团队运维能力、云服务、现有 SQL、扩展需求和迁移成本。

## 与 MySQL 的关键差异

| 主题 | PostgreSQL | MySQL / InnoDB |
|---|---|---|
| 自增主键 | `GENERATED ... AS IDENTITY` 或 sequence | `AUTO_INCREMENT` |
| 未加引号标识符 | 折叠为小写 | 常见环境不区分大小写，受系统和配置影响 |
| 空值排序 | 默认 `NULLS LAST`（ASC） | 需显式确认排序语义 |
| 字符串类型 | `text`、`varchar` 通常性能相近 | `varchar` 长度与字符集需重点设计 |
| JSON | `jsonb` 可索引，二进制分解存储 | JSON 类型与函数、索引方式不同 |
| 事务隔离 | 默认 Read Committed | InnoDB 默认 Repeatable Read |
| 连接并发 | 每个连接通常对应后端进程/资源 | 也需连接池，但资源模型不同 |

迁移不能只把 ORM 方言切换掉。先列出 SQL、时间/时区、分页、唯一约束、事务隔离和测试数据库的差异。

## 建模：先让数据库守规则

```sql
CREATE TABLE accounts (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  email text NOT NULL,
  balance numeric(12, 2) NOT NULL DEFAULT 0,
  status text NOT NULL DEFAULT 'active',
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT accounts_balance_nonnegative CHECK (balance >= 0),
  CONSTRAINT accounts_status_valid CHECK (status IN ('active', 'frozen'))
);

CREATE UNIQUE INDEX accounts_email_lower_uq
ON accounts (lower(email));
```

`CHECK`、`NOT NULL`、`UNIQUE` 是数据库级规则，不应只依赖请求校验。`numeric` 适合金额，避免用浮点数保存货币。时间优先明确使用 `timestamptz` 还是无时区时间；展示时再按用户时区转换。

外键默认保证引用存在，但删除策略必须按业务选择：`RESTRICT` 防误删、`CASCADE` 适合明确的从属对象、`SET NULL` 要求列允许空值。大批量导入前先清理历史孤儿记录，否则约束迁移会失败。

## 事务与 MVCC

PostgreSQL 使用 MVCC：更新通常创建新版本，读操作不会因为普通写锁而全部阻塞。默认 Read Committed 下，同一事务的两次 SELECT 可能看到不同已提交结果；需要稳定视图时使用 Repeatable Read，并处理序列化失败。

```sql
BEGIN;
SELECT balance FROM accounts WHERE id = 1 FOR UPDATE;
UPDATE accounts SET balance = balance - 80
WHERE id = 1 AND balance >= 80;
-- 检查影响行数后再写流水
COMMIT;
```

`FOR UPDATE` 是锁定读，锁会在提交或回滚后释放。并发冲突可能产生 deadlock 或 serialization failure；应用应回滚当前事务、有限退避后重新执行完整事务。不要在事务中调用支付、模型或外部 HTTP。

长事务会阻止旧版本清理，让表和索引膨胀；排查要看事务开始时间、idle in transaction 会话和 autovacuum 状态。MVCC 不是不需要锁，而是把读写冲突拆成快照读与写写协调。

## 索引：类型要匹配谓词

PostgreSQL 常见索引类型：

- **B-tree**：等值、范围和排序的默认选择。
- **GIN**：数组、`jsonb` 包含查询、全文搜索倒排结构。
- **GiST**：范围、几何和可扩展相似性操作。
- **BRIN**：按物理顺序自然增长的大表时间列，体积小但依赖相关性。

```sql
CREATE INDEX orders_user_created_idx
ON orders (user_id, created_at DESC);

CREATE INDEX orders_open_idx
ON orders (created_at)
WHERE status = 'open';

CREATE INDEX documents_metadata_gin
ON documents USING GIN (metadata jsonb_path_ops);
```

索引不是越多越好：每次写入都要维护索引，vacuum 和备份也会变慢。函数包住列时，普通索引可能无法使用；可以建立表达式索引，但要确保查询表达式一致。

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM orders
WHERE user_id = 7 ORDER BY created_at DESC LIMIT 20;
```

`EXPLAIN ANALYZE` 会真实执行语句；对 UPDATE/DELETE 先在事务中验证并回滚，生产环境谨慎使用。关注估算行数与实际行数差异、Seq Scan 是否合理、排序是否落盘、共享缓冲命中和总耗时。

## JSONB：把变化部分放进去

`jsonb` 会解析并以二进制结构存储，通常比 `json` 更适合查询和索引；它不保留键顺序和重复键。稳定、经常过滤或参与约束的字段仍应拆成列。

```sql
CREATE TABLE events (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  event_type text NOT NULL,
  payload jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX events_payload_gin ON events USING GIN (payload);
SELECT * FROM events WHERE payload @> '{"source":"web"}';
```

GIN 索引加速包含与存在性查询，但写入和体积有代价。不要把所有业务表设计成一个 `payload`，否则约束、迁移、统计和权限都会退回应用代码。

## pgvector：把向量检索放进主库

AI 应用要检索 Embedding 向量。什么时候放进 PostgreSQL 而不是专用向量库：数据量在千万级以下、过滤条件依赖业务表（权限、租户、状态）、团队已有 PostgreSQL 运维能力——用 pgvector 可以让**过滤和向量检索在一条 SQL 里完成**，避免两套存储之间的一致性问题。上亿向量、极高 QPS 或需要 GPU 过滤加速时，再评估 Qdrant/Milvus 等专用库（选型分析见[混合检索与 Rerank](./rag-retrieval)）。

### 建模与距离算子

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE document_chunks (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  document_id bigint NOT NULL REFERENCES documents(id),
  status text NOT NULL DEFAULT 'published',
  content text NOT NULL,
  embedding vector(1024) NOT NULL          -- 维度在建表时固定
);

-- 余弦距离（最常用的语义相似度）
SELECT id, content, embedding <=> $1 AS distance
FROM document_chunks
WHERE status = 'published'
ORDER BY embedding <=> $1
LIMIT 10;
```

三种距离算子对应三种语义：`<->` 欧氏距离、`<#>` 内积、`<=>` 余弦距离。**算子必须与 Embedding 模型的训练目标匹配**（多数文本模型按余弦归一化训练，用 `<=>`）；换算子而不换模型是常见的静默退化。

### 索引：先精确，后近似

```sql
-- HNSW：查询快、召回高，构建慢、内存大，支持增量插入
CREATE INDEX chunks_embedding_hnsw
ON document_chunks USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
SET hnsw.ef_search = 40;   -- 查询期召回宽度，越大越准越慢

-- IVFFlat：构建快、省内存，需要先有数据再建索引（聚簇依赖样本）
CREATE INDEX chunks_embedding_ivf
ON document_chunks USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);
SET ivfflat.probes = 10;   -- 探测的簇数
```

| | HNSW | IVFFlat |
|---|---|---|
| 构建速度与内存 | 慢、大 | 快、小 |
| 查询召回/QPS | 高，参数 `ef_search` 平滑 | 依赖 `lists`/`probes` 配比 |
| 增量写入 | 友好 | 频繁写入使簇退化，需重建 |
| 建议 | 默认选择 | 静态大表、内存紧张 |

上线顺序固定为：**先用精确搜索（无索引顺序扫描）建立正确性基线，再开 ANN 索引对比召回率与延迟**——跳过基线直接调索引参数，无法回答“召回率掉了几个点”。

### 过滤组合与行体积

带 `WHERE` 的向量查询是 pgvector 的最大优势也是最容易踩坑的地方：过滤选择性太强（命中行数极少）时，ANN 索引可能扫描大量无效邻居甚至退化为顺序扫描。对策：保持过滤条件相对宽松、把高选择性过滤放到应用层二次截断，或按租户/时间分区。权限过滤必须写进 SQL 的 `WHERE`，与[实战项目](./agentic-rag-project-retrieval)“过滤在打分前”的不变量一致。

体积要提前估算：`vector(1024)` 每行约 4KB，一百万行仅向量就约 4GB——注意共享缓冲命中率和 TOAST 存储；`halfvec`（半精度）可以把体积和内存减半，精度损失通常可接受。**更换 Embedding 模型 = 新增一列 + 全量回填 + 双读切换**，维度和算子是契约，不能原地覆盖（迁移模式见[部署与交付](./agent-deploy)）。

## 分页、并发认领与批处理

大偏移分页会扫描并丢弃前面的行。稳定排序的列表优先使用游标分页：

```sql
SELECT id, created_at, title
FROM posts
WHERE (created_at, id) < ($1, $2)
ORDER BY created_at DESC, id DESC
LIMIT 50;
```

游标必须包含唯一的 tie-breaker（这里是 `id`），否则同一时间戳会漏行或重复。

任务认领可以使用：

```sql
BEGIN;
SELECT id FROM jobs
WHERE status = 'pending'
ORDER BY id
FOR UPDATE SKIP LOCKED
LIMIT 20;
UPDATE jobs SET status = 'running', started_at = now()
WHERE id = ANY($1) AND status = 'pending';
COMMIT;
```

`SKIP LOCKED` 适合队列式认领，不适合需要完整一致结果的报表查询。认领后还要有租约、心跳和过期回收；进程崩溃不能让任务永久停在 running。

## UPSERT 与冲突语义

```sql
INSERT INTO user_preferences (user_id, theme)
VALUES ($1, $2)
ON CONFLICT (user_id)
DO UPDATE SET theme = EXCLUDED.theme,
              updated_at = now();
```

`ON CONFLICT` 依赖唯一约束或唯一索引。它解决的是同一约束键的写入冲突，不等于任意业务流程都幂等；外部副作用和多表流程仍需幂等键、事务和状态机。

## VACUUM、连接池与运维

更新产生旧版本后，VACUUM 负责回收可见性已结束的空间并维护可见性信息；它通常不把文件缩回操作系统。`VACUUM FULL` 会重写表并持有更强锁，不能当作日常调优按钮。

连接池要限制应用总连接数，不能每个请求新建连接。PostgreSQL 连接通常更昂贵，多个服务实例的池大小总和不能超过数据库可承受并发。监控活跃连接、等待事件、长事务、锁等待、autovacuum 延迟和磁盘增长。

## 迁移 PostgreSQL 的检查表

1. 导出真实 SQL 和 ORM 生成 SQL，标记 MySQL 专有语法。
2. 重新设计自增、时间、布尔、枚举、JSON、全文和空间字段。
3. 先在影子库导入并建立约束，再处理历史脏数据。
4. 对关键查询跑 `EXPLAIN (ANALYZE, BUFFERS)`，比较延迟分位数。
5. 用两个真实连接测试事务隔离、锁等待、死锁和 serialization failure。
6. 验证备份恢复、扩展版本、连接池和监控，而不只验证 CRUD。

## 面试问答

**1. PostgreSQL 的 MVCC 意味着没有锁吗？**

- 不是。MVCC 把读写冲突拆成快照读与写写协调：普通 SELECT 不阻塞 UPDATE，但 `FOR UPDATE` 锁定读、唯一约束冲突、死锁和序列化失败依然存在，应用要回滚重试。
- 长事务和 idle in transaction 会阻止旧版本回收，表和索引膨胀，autovacuum 追不上——MVCC 的运维代价主要在这里。
- 加分：能说出默认 Read Committed 与 InnoDB 默认 Repeatable Read 的差异对应用语义的影响。

**2. RAG 系统里，权限过滤为什么必须发生在打分之前？**

- 后过滤意味着无权内容已经进入过候选集：分数、耗时、候选数量都可能泄露，过滤延迟也叠加在检索上。
- 在 pgvector 里把 `knowledge_base_id`/`status` 写进同一条 SQL 的 `WHERE`，无权行从不参与相似度计算。
- 别踩的坑：过滤选择性极高时 ANN 索引可能退化成大量无效扫描，要监控计划而不是假设索引永远生效。

**3. HNSW 和 IVFFlat 怎么选？**

- 默认 HNSW：召回和查询性能好、支持增量插入，代价是构建慢、内存大。
- IVFFlat 适合静态大表、内存紧张的场景，但必须先有数据再建索引，频繁写入会让簇退化需要重建。
- 无论选哪个，先用精确搜索建立正确性基线，再对比开索引后的召回率与 P95——没有基线的调参无法归因。

**4. 更换 Embedding 模型时，向量列怎么迁移？**

- 维度和距离算子是契约：新增一列存新向量，全量回填，双读对比召回后切换，旧列下个版本再删——expand-contract。
- 不能原地覆盖：新旧向量空间不可比，混存期间检索结果不可解释。
- 加分：提到半精度（`halfvec`）可以在迁移期缓解体积翻倍的压力。

**5. jsonb 什么时候不该用？**

- 稳定、经常过滤、参与约束或 join 的字段应该正规化成列——jsonb 里没有外键、约束表达力弱、统计要解析。
- jsonb 的正确位置是“变化部分”：事件 payload、供应商差异字段、临时元数据。
- 别踩的坑：把整张业务表塞进一个 `payload` 列，约束、迁移和权限全部退回应用代码。

## 官方参考

- [PostgreSQL 并发控制与 MVCC](https://www.postgresql.org/docs/current/mvcc.html)
- [PostgreSQL 索引](https://www.postgresql.org/docs/current/indexes.html)
- [PostgreSQL 约束](https://www.postgresql.org/docs/current/ddl-constraints.html)
- [PostgreSQL JSON 类型](https://www.postgresql.org/docs/current/datatype-json.html)
- [PostgreSQL VACUUM](https://www.postgresql.org/docs/current/routine-vacuuming.html)
- [pgvector GitHub 与操作符参考](https://github.com/pgvector/pgvector)
