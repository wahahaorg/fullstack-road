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

## 面试怎么说

> 我会根据复杂查询、约束和扩展需求评估 PostgreSQL。建模时用 CHECK、唯一索引和外键把规则下沉；金额用 numeric，时间明确时区。并发上理解 MVCC，但不会把它当成无锁：锁定读、死锁和序列化失败仍要处理。索引按谓词选择 B-tree、GIN、GiST 或 BRIN，用 EXPLAIN ANALYZE 验证。JSONB 只承载变化字段，稳定字段正规化。迁移 MySQL 时重点重做类型、隔离级别、分页、唯一约束、SQL 方言和恢复演练。

## 官方参考

- [PostgreSQL 并发控制与 MVCC](https://www.postgresql.org/docs/current/mvcc.html)
- [PostgreSQL 索引](https://www.postgresql.org/docs/current/indexes.html)
- [PostgreSQL 约束](https://www.postgresql.org/docs/current/ddl-constraints.html)
- [PostgreSQL JSON 类型](https://www.postgresql.org/docs/current/datatype-json.html)
- [PostgreSQL VACUUM](https://www.postgresql.org/docs/current/routine-vacuuming.html)
