---
title: SQL 基础与查询
---

# SQL 基础与查询

## 这一章解决什么问题

你不需要先把 SQL 学成 DBA，但必须掌握后台开发最常用的 SQL：

```txt
增删改查
条件过滤
排序分页
JOIN
聚合统计
事务更新
```

这些能力会直接影响你能不能设计 FastAPI 接口。

## SELECT：先把数据查出来

```sql
SELECT id, name, created_at
FROM users
WHERE status = 'active'
ORDER BY created_at DESC
LIMIT 20 OFFSET 0;
```

关键点：

- `SELECT` 决定返回哪些字段。
- `FROM` 决定查哪张表。
- `WHERE` 决定过滤条件。
- `ORDER BY` 决定排序。
- `LIMIT/OFFSET` 决定分页。

不要在接口里默认 `SELECT *`。返回字段越多，接口越难演进，也更容易泄漏敏感字段。

## INSERT：创建数据

```sql
INSERT INTO users (username, phone, status)
VALUES ('sizhe', '13800000000', 'active');
```

如果手机号唯一：

```sql
ALTER TABLE users
ADD UNIQUE KEY uk_phone (phone);
```

并发注册时，不要只靠“先查是否存在”。唯一索引才是最终兜底。

## UPDATE：修改数据

普通更新：

```sql
UPDATE users
SET nickname = 'Xiang'
WHERE id = 1;
```

后台开发里，`UPDATE` 最重要的是 `WHERE` 条件。

库存扣减不要写成：

```sql
SELECT stock FROM products WHERE id = 1;
UPDATE products SET stock = 0 WHERE id = 1;
```

更稳的写法是条件更新：

```sql
UPDATE products
SET stock = stock - 1
WHERE id = 1 AND stock > 0;
```

然后检查影响行数。如果影响行数是 0，说明库存不足或商品不存在。

## DELETE：删除数据

物理删除：

```sql
DELETE FROM addresses
WHERE id = 10 AND user_id = 1;
```

很多业务更适合软删除：

```sql
UPDATE documents
SET deleted_at = NOW(3)
WHERE id = 10;
```

软删除适合：

- 需要恢复。
- 需要审计。
- 其他表仍然引用这条数据。
- 删除只是对用户不可见。

## JOIN：把关系查出来

用户和地址是一对多：

```sql
SELECT
  u.id AS user_id,
  u.username,
  a.id AS address_id,
  a.city,
  a.detail
FROM users u
LEFT JOIN addresses a ON a.user_id = u.id
WHERE u.id = 1;
```

常见 JOIN：

| 类型 | 含义 |
| --- | --- |
| `INNER JOIN` | 两边都匹配才返回 |
| `LEFT JOIN` | 左表一定返回，右表没有则为 NULL |
| `RIGHT JOIN` | 右表一定返回，较少用 |

后台接口里最常见的是 `LEFT JOIN` 和 `INNER JOIN`。

## GROUP BY：统计数据

统计每个状态的任务数量：

```sql
SELECT status, COUNT(*) AS total
FROM document_parse_jobs
GROUP BY status;
```

统计每天新增文档：

```sql
SELECT DATE(created_at) AS day, COUNT(*) AS total
FROM documents
WHERE created_at >= '2026-07-01'
GROUP BY DATE(created_at)
ORDER BY day;
```

BI、报表、后台管理系统里经常用聚合。

## 子查询：先查一批 ID，再查详情

查询有失败任务的文档：

```sql
SELECT *
FROM documents
WHERE id IN (
  SELECT document_id
  FROM document_parse_jobs
  WHERE status = 'failed'
);
```

实际项目里，很多子查询可以改写成 JOIN。选择哪种写法，要看可读性和执行计划。

## 事务：多步修改一起成功

创建订单并扣库存：

```sql
START TRANSACTION;

UPDATE products
SET stock = stock - 1
WHERE id = 1 AND stock > 0;

INSERT INTO orders (user_id, product_id, status)
VALUES (100, 1, 'created');

COMMIT;
```

如果中间任何一步失败：

```sql
ROLLBACK;
```

事务解决的是：

```txt
多条 SQL 要么全部成功，要么全部失败
```

但事务不是魔法。你仍然需要正确的条件、索引、约束和隔离级别。

## 分页：OFFSET 和游标

普通后台列表：

```sql
SELECT id, title, created_at
FROM documents
WHERE knowledge_base_id = 1
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 40;
```

数据量大时，深分页会变慢。可以用游标分页：

```sql
SELECT id, title, created_at
FROM documents
WHERE knowledge_base_id = 1
  AND (created_at, id) < ('2026-07-05 10:00:00', 123)
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

前端无限滚动、消息列表、日志列表常用游标分页。

## SQL 和索引一起想

如果接口经常这样查：

```sql
SELECT *
FROM documents
WHERE knowledge_base_id = ?
  AND parse_status = ?
ORDER BY created_at DESC
LIMIT 20;
```

可以考虑：

```sql
KEY idx_kb_status_created (knowledge_base_id, parse_status, created_at)
```

索引设计不要脱离查询。你可以把索引理解成后端接口的“数据访问路径”。

## 练习前技巧

写 SQL 前先标注：

```txt
我要查哪张主表？
过滤条件是什么？
是否要关联其他表？
是否要聚合？
排序字段是什么？
分页方式是什么？
需要哪些索引支持？
```

这比直接写 SQL 更重要。

## 面试怎么说

> 我写 SQL 时会先从接口查询场景出发，确认主表、过滤条件、关联关系、排序和分页方式。对于更新类 SQL，我会特别注意 WHERE 条件和影响行数；涉及多表修改时使用事务；涉及并发时优先使用唯一约束、条件更新或行锁保证最终正确性。

---

## 面试问答

**1. 并发场景下，哪些正确性要交给数据库兜底？**

- 并发注册时不要只靠"先查是否存在"，给手机号加唯一索引 `UNIQUE KEY uk_phone (phone)` 才是最终兜底。
- 库存扣减不要"先查再改"，条件更新 `SET stock = stock - 1 WHERE id = 1 AND stock > 0` 把判断和修改放进一条 SQL，更稳。
- 执行后检查影响行数：为 0 说明库存不足或商品不存在，不要继续往下走。
- 加分：后台开发里 `UPDATE` 最重要的是 WHERE 条件，更新类 SQL 出事故多半出在条件上。

**2. 物理删除和软删除怎么选？**

- `DELETE` 直接删数据，适合地址这类删了就删了的数据；WHERE 里记得带上归属条件（`id = 10 AND user_id = 1`）。
- 需要恢复、需要审计、其他表仍然引用、或者删除只是"对用户不可见"时，用 `deleted_at` 软删除——本质是一条 UPDATE。

**3. 子查询和 JOIN 怎么选？**

- "先查一批 ID，再查详情"的子查询直观，但实际项目里很多子查询可以改写成 JOIN。
- 选择标准是可读性和执行计划，不是固定偏好。
- 加分：写 SQL 前先过一遍清单——主表、过滤条件、关联、聚合、排序、分页、需要哪些索引支持；索引设计不要脱离查询。

**4. 事务能保证什么，不能保证什么？**

- 保证多条 SQL 要么全部成功、要么全部失败：扣库存和创建订单放在一个事务里，扣减失败就不应该有订单。
- 不保证业务正确：你仍然需要正确的条件、索引、约束和隔离级别。
- 别踩的坑：把事务当魔法，以为包一层事务就万事大吉，条件写错照样扣错数据。

**5. 分页用 OFFSET 还是游标？**

- 普通后台列表用 `LIMIT 20 OFFSET 40` 就够，直观。
- 数据量大时深分页会变慢；前端无限滚动、消息列表、日志列表改用游标分页，拿上一页最后一条的 `(created_at, id)` 当下一页的起点。
- 加分：`ORDER BY created_at DESC, id DESC` 和游标的字段比较必须配套，排序怎么定，游标就怎么比。

