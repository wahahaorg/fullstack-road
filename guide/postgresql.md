---
title: PostgreSQL 基础与实战
---

# PostgreSQL 基础与实战

> PostgreSQL 适合复杂查询、严格约束、事务一致性和可扩展数据类型。本文以 PostgreSQL 16+ 的通用能力为主；部署前按实际版本核对语法。它不是“换一个连接字符串就能替换 MySQL”：事务、索引、类型、分页和运维都需要重新验证。对 Agent / RAG 来说，真正决定能不能上生产的，往往不是“会不会写 `<=>`”，而是 **RLS、连接池、元数据索引，以及权限过滤写进同一条 SQL**。

## 什么时候考虑 PostgreSQL

| 场景 | PostgreSQL 的优势 | 注意事项 |
|---|---|---|
| 复杂 JOIN、窗口、CTE | SQL 能力完整，执行计划可解释 | 查询仍需索引与 `EXPLAIN` 验证 |
| 强约束业务模型 | `CHECK`、排他约束、部分唯一索引 | 约束迁移需处理历史脏数据 |
| 地理空间 | PostGIS 生态成熟 | 扩展、坐标系和索引需单独学习 |
| 半结构化字段 | `jsonb`、GIN 索引、丰富操作符 | 热点字段仍应正规化 |
| 高并发事务 | MVCC、行锁、`SKIP LOCKED` | 长事务会阻塞 vacuum，造成膨胀 |
| RAG / Agent 元数据 + 向量 | pgvector + JSONB + RLS 同库 | 千万级以上、极高 QPS 再评估专用向量库 |

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
| 行级安全 | 原生 RLS + Policy | 主要靠应用层 / 视图模拟 |

迁移不能只把 ORM 方言切换掉。先列出 SQL、时间/时区、分页、唯一约束、事务隔离和测试数据库的差异。通用 SQL 进阶（JOIN、窗口、EXPLAIN 读法）见 [MySQL 进阶](./mysql-advanced)；本节只保留迁库时必须重验的差异。

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

RAG 侧常见拆分是 `documents`（文档级权限与状态）+ `document_chunks`（切分文本与向量）。稳定过滤字段（`tenant_id`、`status`、`knowledge_base_id`）做成列；易变属性进 `metadata jsonb`。

## 事务与 MVCC

PostgreSQL 使用 MVCC：更新通常创建新版本，读操作不会因为普通写锁而全部阻塞。默认 Read Committed 下，同一事务的两次 SELECT 可能看到不同已提交结果；需要稳定视图时使用 Repeatable Read，并处理序列化失败。隔离级别与锁语义的对照见 [并发与事务](./concurrency-transaction)、[锁](./locking)。

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

### RAG 元数据：该放什么、不该放什么

```sql
CREATE TABLE documents (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id uuid NOT NULL,
  knowledge_base_id uuid NOT NULL,
  status text NOT NULL DEFAULT 'published',
  title text NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE document_chunks (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  document_id bigint NOT NULL REFERENCES documents(id),
  tenant_id uuid NOT NULL,
  status text NOT NULL DEFAULT 'published',
  chunk_index int NOT NULL,
  content text NOT NULL,
  embedding vector(1024) NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);
```

| 放进列 | 放进 `metadata` | 不要放 |
|---|---|---|
| `tenant_id`、`knowledge_base_id`、`status` | `source`、`author`、`page`、`mime`、标签数组 | 大段原文（已有 `content`） |
| 参与外键 / 唯一约束的字段 | 供应商差异字段、解析器附加信息 | Embedding 本身、临时调试痕迹 |
| 几乎每条查询都过滤的字段 | 低频过滤、偶尔展示的属性 | 密钥、PII、完整 ACL 列表 |

前端类比：列像组件的 `props`——稳定、类型明确、参与渲染决策；`metadata` 像可选的 `data-*`——扩展方便，但不该承载核心路由。权限边界（租户、知识库、发布状态）必须是列，否则 RLS 和索引都无从下手。

### GIN ops 与表达式索引

```sql
-- jsonb_path_ops：只优化 @> 包含查询，索引更小、写入更快
CREATE INDEX documents_metadata_path_ops
ON documents USING GIN (metadata jsonb_path_ops);

-- 默认 jsonb_ops：支持 ?、?&、?|、@> 等更多操作符，体积更大
CREATE INDEX documents_metadata_ops
ON documents USING GIN (metadata);

-- 高频等值过滤：表达式索引比扫整个 GIN 更直接
CREATE INDEX documents_metadata_source_idx
ON documents ((metadata->>'source'));

-- 查询必须与索引表达式一致
SELECT id, title FROM documents
WHERE metadata->>'source' = 'confluence'
  AND tenant_id = $1;
```

| 选择 | 适用 | 代价 |
|---|---|---|
| `jsonb_path_ops` | 主要写 `metadata @> '{"k":"v"}'` | 不支持 `?` 等存在性操作符 |
| 默认 `jsonb_ops` | 多种 jsonb 操作符混用 | 更大、写入更慢 |
| `(metadata->>'key')` 表达式索引 | 单个高频等值 / 排序字段 | 每个热点键一条索引；查询表达式必须一致 |

实操建议：权限与状态走列；一两个热点元数据键建表达式索引；其余用 `jsonb_path_ops` 兜底包含查询。入库链路里元数据如何产生，见 [RAG 入库](./rag-pipeline)。

## pgvector：把向量检索放进主库

AI 应用要检索 Embedding 向量。什么时候放进 PostgreSQL 而不是专用向量库：数据量在千万级以下、过滤条件依赖业务表（权限、租户、状态）、团队已有 PostgreSQL 运维能力——用 pgvector 可以让**过滤和向量检索在一条 SQL 里完成**，避免两套存储之间的一致性问题。上亿向量、极高 QPS 或需要 GPU 过滤加速时，再评估 Qdrant/Milvus 等专用库（选型分析见[混合检索与 Rerank](./rag-retrieval)）。

### 建模与距离算子

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE document_chunks (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  document_id bigint NOT NULL REFERENCES documents(id),
  tenant_id uuid NOT NULL,
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

带 `WHERE` 的向量查询是 pgvector 的最大优势也是最容易踩坑的地方：过滤选择性太强（命中行数极少）时，ANN 索引可能扫描大量无效邻居甚至退化为顺序扫描。对策：保持过滤条件相对宽松、把高选择性过滤放到应用层二次截断，或按租户/时间分区；pgvector 0.8+ 可开迭代扫描缓解“LIMIT 取不满”。细节与调参优先级见[混合检索](./rag-retrieval)。

体积要提前估算：`vector(1024)` 每行约 4KB，一百万行仅向量就约 4GB——注意共享缓冲命中率和 TOAST 存储；`halfvec`（半精度）可以把体积和内存减半，精度损失通常可接受。**更换 Embedding 模型 = 新增一列 + 全量回填 + 双读切换**，维度和算子是契约，不能原地覆盖（迁移模式见[部署与交付](./agent-deploy)）。

### 权限过滤 + 向量检索：可抄的完整 SQL

权限过滤必须写进 SQL 的 `WHERE`，与[实战项目检索章](./agentic-rag-project-retrieval)“过滤在打分前”的不变量一致。下面这条把租户、发布状态和余弦距离放在同一句里：

```sql
-- $1 = query embedding (vector)
-- $2 = tenant_id (uuid)
BEGIN;
SET LOCAL hnsw.ef_search = 80;

SELECT
  c.id,
  c.document_id,
  c.content,
  c.metadata,
  c.embedding <=> $1 AS distance
FROM document_chunks c
WHERE c.tenant_id = $2
  AND c.status = 'published'
ORDER BY c.embedding <=> $1
LIMIT 20;
COMMIT;
```

为什么不能“先 ANN Top-200，再在应用层滤权限”：

1. **召回污染**：Top-200 里可能大半属于其他租户，滤完只剩几条弱相关，用户看到的是“搜不到”，根因却是候选被无权行占满。
2. **旁路泄漏**：标题、分数、片段已经进过应用内存、日志或 Trace；即便最终响应删掉，观测链路仍可能留下痕迹。
3. **延迟与成本**：相似度计算和 ANN 遍历花在了永远不会返回的行上。
4. **测试失真**：越权用例若只断言“答案文本不含敏感词”，漏掉了中间候选集——权限测试应落在打分层的 ID 集合上，见[权限章](./agentic-rag-project-permissions)。

前端类比：这不是列表页先拉全量再 `filter()`，而是请求阶段就把 `tenant_id` 带进查询参数；RLS（下一节）则相当于框架层强制注入，防止某个 handler 漏写。

## 行级安全 RLS

应用层 `WHERE tenant_id = ?` 能工作，但依赖每个查询都写对。漏写一次就是串租户。PostgreSQL 的 RLS 把“只能看自己的行”下沉为表策略：即使用超级用户以外的角色写出不带租户条件的 SQL，也返回空集或拒绝写入。

### 启用与策略

```sql
-- 业务连接使用的角色：不要用表所有者 / superuser 跑应用
CREATE ROLE app_user LOGIN PASSWORD '...';
GRANT SELECT, INSERT, UPDATE, DELETE ON document_chunks TO app_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_user;

ALTER TABLE document_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_chunks FORCE ROW LEVEL SECURITY;  -- 表所有者也不绕过

CREATE POLICY chunks_tenant_isolation ON document_chunks
  FOR ALL
  TO app_user
  USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
```

- `USING` 决定**读/更新/删除**哪些现有行可见。
- `WITH CHECK` 决定**插入/更新后**的新行是否合法（防止改成别人的 `tenant_id`）。
- `current_setting('app.tenant_id', true)` 的第二个参数 `true` 表示缺失时返回 `NULL` 而不是报错——再配 `NULLIF(..., '')`，未设置会话变量时策略匹配失败，结果为空。

按操作拆分策略也很常见：`FOR SELECT` 用租户隔离，`FOR INSERT` 额外校验 `status`，管理员角色另建 `BYPASSRLS` 或单独 policy。

### 会话变量：必须用 `SET LOCAL`

```sql
BEGIN;
SET LOCAL app.tenant_id = '11111111-1111-1111-1111-111111111111';
SET LOCAL app.user_id = '22222222-2222-2222-2222-222222222222';
-- 本事务内的所有 SQL 自动带上租户边界
SELECT id, content FROM document_chunks
ORDER BY embedding <=> $1
LIMIT 10;
COMMIT;  -- LOCAL 设置随事务结束消失
```

**绝对不要**在连接池场景用会话级 `SET app.tenant_id`（无 `LOCAL`）。连接归还池后，下一个请求可能继承上一个租户的变量——这是经典的串租户事故。`SET LOCAL` 绑定当前事务，提交/回滚后自动清除，和请求级 `AsyncSession` 生命周期对齐。

### FastAPI / SQLAlchemy：每个请求注入

```python
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

async def set_rls_context(session: AsyncSession, *, tenant_id: str, user_id: str) -> None:
    # 在已开启的事务里设置；配合下面的 get_db 使用
    await session.execute(
        text("SELECT set_config('app.tenant_id', :tid, true)"),
        {"tid": tenant_id},
    )
    await session.execute(
        text("SELECT set_config('app.user_id', :uid, true)"),
        {"uid": user_id},
    )
    # set_config 第三参 true == SET LOCAL（事务级）
```

```python
from collections.abc import AsyncGenerator
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        async with session.begin():
            await set_rls_context(
                session,
                tenant_id=request.state.tenant_id,
                user_id=request.state.user_id,
            )
            yield session
            # 正常结束：begin() 上下文 commit
            # 异常：rollback，SET LOCAL 一并消失
```

鉴权中间件只负责解析 JWT、写入 `request.state`；真正的数据边界由 RLS + `SET LOCAL` 守住。JWT 里带的 `tenant_id` 可以用于设置上下文，但**最终权限仍以服务端查询到的成员关系为准**——与[权限章](./agentic-rag-project-permissions)“JWT 只证明身份”一致。

### RLS vs 应用层 WHERE

| | 应用层 `WHERE tenant_id = ?` | RLS Policy |
|---|---|---|
| 防漏写 | 每个查询/ORM 调用都要记得 | 表级强制，漏写也返回空 |
| 表达力 | 任意复杂业务规则 | 适合稳定的租户/属主边界；复杂 ACL 仍要列或 JOIN |
| 可测性 | 单测易 mock | 需用非 bypass 角色连真实库验证 |
| 性能 | 与手写条件相同 | 策略条件会并进计划；复杂表达式要同样建索引 |
| 不是什么 | 业务权限模型本身 | **也不是**业务权限模型本身 |

RLS 防的是**漏写 WHERE / 错误连接串租户**，不是替代“谁对哪个 knowledge_base 有 reader 角色”这类业务授权。推荐组合：

1. 服务端解析身份 → 得到 `tenant_id` + 允许的 `knowledge_base_ids`（业务权限）。
2. `SET LOCAL app.tenant_id` 激活 RLS（防串租）。
3. SQL `WHERE knowledge_base_id = ANY(:allowed)` 收窄资源范围（业务授权）。
4. 同一句里 `ORDER BY embedding <=> :q`（过滤在打分前）。

第 3、4 步与[检索实战](./agentic-rag-project-retrieval)、[混合检索](./rag-retrieval)中的“权限预过滤”是同一条不变量；RLS 是这条不变量的数据库保险绳。

## SQLAlchemy 2.x + FastAPI 集成

更完整的路由、依赖和生命周期组织见 [FastAPI 进阶](./fastapi-advanced)。这里补上 Agent / RAG 服务落地时绕不开的三点：async 骨架、pgvector 查询方式、连接池容量。

### async engine 与 Session 骨架

```python
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

DATABASE_URL = "postgresql+asyncpg://app_user:pwd@localhost:5432/rag"

engine = create_async_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,   # 借用前探活，避免拿到已被服务端断开的连接
    pool_timeout=30,
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

DB = Annotated[AsyncSession, Depends(get_db)]
```

两种事务风格选一种并在项目里统一：

- **Depends 末尾 commit/rollback**（上面）：适合多数读写请求；handler 里不要再隐式提交。
- **`async with session.begin():`**：适合明确的多语句事务（转账、认领任务）；与 RLS 的 `SET LOCAL` 同处一个 begin 块最干净。

混用容易出现“以为提交了其实没提交”或重复 commit。测试里用同样的 `get_db` 覆盖，避免测试通路绕过 RLS 上下文。

### 用 SQLAlchemy 跑 pgvector：两条路

```python
from sqlalchemy import text

async def search_chunks(
    session: AsyncSession,
    *,
    embedding: list[float],
    tenant_id: str,
    limit: int = 20,
) -> list[dict]:
    # 路径 A：text() 原始 SQL——当前最稳妥
    result = await session.execute(
        text(
            """
            SELECT id, document_id, content, metadata,
                   embedding <=> :embedding AS distance
            FROM document_chunks
            WHERE tenant_id = :tenant_id
              AND status = 'published'
            ORDER BY embedding <=> :embedding
            LIMIT :limit
            """
        ),
        {
            "embedding": str(embedding),  # asyncpg 也可接适配后的向量类型
            "tenant_id": tenant_id,
            "limit": limit,
        },
    )
    return [row._asdict() for row in result]
```

```python
# 路径 B：社区方言 / ORM 扩展（示意）
# pip install pgvector
from pgvector.sqlalchemy import Vector
from sqlalchemy.orm import Mapped, mapped_column

class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    id: Mapped[int] = mapped_column(primary_key=True)
    embedding: Mapped[list[float]] = mapped_column(Vector(1024))
    # 查询时用 (DocumentChunk.embedding.cosine_distance(q)).label("distance")
```

| | `text()` 原始 SQL | 社区方言（`pgvector` Python 包等） |
|---|---|---|
| 成熟度 | 高：SQL 与 `psql` 调试一致 | 中：API 随版本变，文档分散 |
| 表达力 | 任意 SQL、CTE、`SET LOCAL` | 常见 CRUD / 距离表达式够用 |
| 风险 | 字符串拼接要参数化 | 隐式类型转换、迁移工具支持参差 |
| 建议 | **检索与 RLS 相关路径优先** | 表模型声明可以用来；热点查询仍建议落 SQL 文件 |

诚实结论：pgvector 的 **SQL 侧**很成熟，**ORM 侧**够用但不如普通列字段稳。生产 RAG 检索路径用参数化 `text()` / 存储在 `.sql` 文件里的语句，比把距离算子硬塞进 ORM 链式调用更好维护；出了计划问题可以直接贴进 `EXPLAIN`。

### 连接池：总连接数怎么算

PostgreSQL 每个连接通常对应一个后端进程，内存和上下文切换成本高于“纯线程池里的客户端对象”。公式：

```text
应用总连接上限 ≈ 实例数 × workers_per_instance × (pool_size + max_overflow)
```

例：2 个 API 副本，每副本 4 个 Uvicorn worker，`pool_size=5`、`max_overflow=5` → `2 × 4 × 10 = 80`。再加迁移任务、Worker、笔记本上的临时连接，必须低于 `max_connections`（常还要给超管和监控留余量）。

实践要点：

- **先定数据库可接受并发，再倒推每进程池大小**，而不是每个服务各自拍脑袋。
- `pool_pre_ping=True` 几乎总是值得开：代价是一次轻量往返，收益是避免空闲断开后的首请求失败。
- Agent 若还有独立的 ingestion Worker / 检索 Worker，它们各自持池——算总账时不要漏（见[部署](./agent-deploy)）。
- 连接池（PgBouncer）与应用池叠加时，应用池宜小、把排队交给 PgBouncer；事务池模式下会话级 `SET` 更危险，**更要坚持 `SET LOCAL`**。

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

`SKIP LOCKED` 适合队列式认领，不适合需要完整一致结果的报表查询。认领后还要有租约、心跳和过期回收；进程崩溃不能让任务永久停在 running。RAG 异步入库 Worker 同样模式，见[异步入库](./agentic-rag-project-async-ingestion)。

## UPSERT 与冲突语义

```sql
INSERT INTO user_preferences (user_id, theme)
VALUES ($1, $2)
ON CONFLICT (user_id)
DO UPDATE SET theme = EXCLUDED.theme,
              updated_at = now();
```

`ON CONFLICT` 依赖唯一约束或唯一索引。它解决的是同一约束键的写入冲突，不等于任意业务流程都幂等；外部副作用和多表流程仍需幂等键、事务和状态机。文档版本切换、chunk 回填常用 `(document_id, chunk_index)` 或内容哈希做冲突键。

## VACUUM 与运维补强

更新产生旧版本后，VACUUM 负责回收可见性已结束的空间并维护可见性信息；它通常不把文件缩回操作系统。`VACUUM FULL` 会重写表并持有更强锁，不能当作日常调优按钮。长事务和 idle in transaction 是膨胀的常见根因——先杀长事务，再谈调 autovacuum。

连接池容量算法见上一节；这里只强调监控：活跃连接、等待事件、长事务、锁等待、autovacuum 延迟、表/索引体积、共享缓冲命中率。

### 备份：逻辑 vs 基础

| | `pg_dump` 逻辑备份 | 基础备份（`pg_basebackup` / 快照 + WAL） |
|---|---|---|
| 内容 | SQL 或自定义格式的对象导出 | 数据目录的物理拷贝 + WAL 持续归档 |
| 恢复粒度 | 可单表、单 schema | 通常整个实例到某个时间点（PITR） |
| 代价 | 大库慢；恢复后要重建索引统计 | 空间与运维流程更重，RPO/RTO 更好 |
| 适用 | 开发副本、小库、迁移导出 | 生产默认；向量大表尤其不要只靠定期 dump |

有 pgvector 的大表：逻辑备份体积接近“全文 + 向量”，恢复时间常被低估。生产以基础备份 + WAL 归档为主，`pg_dump` 作为逻辑逃生通道。

### 扩展升级（vector）要注意什么

1. **先读变更日志**：pgvector 小版本也可能改默认行为（如迭代扫描、半精度类型）。
2. **索引是否兼容**：跨大版本常需 `REINDEX`；HNSW 重建耗内存与时间，按租户/分区滚动。
3. **扩展升级在事务外**：`ALTER EXTENSION vector UPDATE;` 按官方指引执行；先在影子库验证查询计划与召回。
4. **应用与 SQL 同步**：距离算子、绑定类型、`halfvec` 切换都是契约，扩展开了但代码仍按旧维度读会静默错结果。
5. **回滚预案**：扩展升级往往不可廉价回退——保留旧实例快照再切流量。

## 迁移 PostgreSQL 的检查表

1. 导出真实 SQL 和 ORM 生成 SQL，标记 MySQL 专有语法。
2. 重新设计自增、时间、布尔、枚举、JSON、全文和空间字段。
3. 先在影子库导入并建立约束，再处理历史脏数据。
4. 对关键查询跑 `EXPLAIN (ANALYZE, BUFFERS)`，比较延迟分位数；向量查询单独做召回基线。
5. 用两个真实连接测试事务隔离、锁等待、死锁和 serialization failure。
6. 验证 RLS：用 `app_user`（非 bypass）连接，故意漏写 `tenant_id`，确认结果为空。
7. 验证备份恢复、扩展版本、连接池总账和监控，而不只验证 CRUD。

## 面试问答

**1. PostgreSQL 的 MVCC 意味着没有锁吗？**

- 不是。MVCC 把读写冲突拆成快照读与写写协调：普通 SELECT 不阻塞 UPDATE，但 `FOR UPDATE` 锁定读、唯一约束冲突、死锁和序列化失败依然存在，应用要回滚重试。
- 长事务和 idle in transaction 会阻止旧版本回收，表和索引膨胀，autovacuum 追不上——MVCC 的运维代价主要在这里。
- 加分：能说出默认 Read Committed 与 InnoDB 默认 Repeatable Read 的差异对应用语义的影响。

**2. RAG 系统里，权限过滤为什么必须发生在打分之前？**

- 后过滤意味着无权内容已经进入过候选集：分数、耗时、候选数量都可能泄露，过滤延迟也叠加在检索上。
- 在 pgvector 里把 `tenant_id` / `knowledge_base_id` / `status` 写进同一条 SQL 的 `WHERE`，无权行从不参与相似度计算。
- 别踩的坑：过滤选择性极高时 ANN 索引可能退化成大量无效扫描，要监控计划而不是假设索引永远生效；也不能因为取不满就改回应用层后过滤。

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
- jsonb 的正确位置是“变化部分”：事件 payload、供应商差异字段、临时元数据；RAG 里权限字段绝不能只活在 metadata 里。
- 别踩的坑：把整张业务表塞进一个 `payload` 列，约束、迁移和权限全部退回应用代码。

**6. RLS 能替代应用里的权限模型吗？**

- 不能。RLS 适合强制租户/属主等高稳定边界，防止漏写 `WHERE` 或连接池串会话；“谁对哪个知识库有 reader 角色”仍是业务授权，要在服务端算出 `allowed_ids` 再写进 SQL。
- 连接池场景必须用 `SET LOCAL` / `set_config(..., true)`，事务结束即清除；会话级 `SET` 会在连接复用时串租户。
- 加分：说明应用角色不能是表所有者/superuser，否则默认绕过 RLS；需要时再 `FORCE ROW LEVEL SECURITY`。

**7. 多 Worker 时连接池怎么估？**

- 总连接 ≈ 实例数 × 每实例 worker 数 × `(pool_size + max_overflow)`，再加 Worker 进程与管理连接，必须低于 `max_connections` 并留余量。
- `pool_pre_ping` 避免借用到服务端已断开的空闲连接；池太大不会加快慢查询，只会把数据库先打满。
- 加分：提到 PgBouncer 事务池模式下更不能依赖会话级状态，RLS 上下文必须事务级。

## 官方参考

- [PostgreSQL 并发控制与 MVCC](https://www.postgresql.org/docs/current/mvcc.html)
- [PostgreSQL 索引](https://www.postgresql.org/docs/current/indexes.html)
- [PostgreSQL 约束](https://www.postgresql.org/docs/current/ddl-constraints.html)
- [PostgreSQL JSON 类型](https://www.postgresql.org/docs/current/datatype-json.html)
- [PostgreSQL Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)
- [PostgreSQL VACUUM](https://www.postgresql.org/docs/current/routine-vacuuming.html)
- [pgvector GitHub 与操作符参考](https://github.com/pgvector/pgvector)
- [SQLAlchemy asyncio](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
