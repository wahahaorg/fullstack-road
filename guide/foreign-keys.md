---
title: 数据库外键：理论、实践与取舍
---

# 数据库外键：理论、实践与取舍

> 外键解决的是**引用完整性**：子表里的 ID 必须指向一个存在的父表记录，或者明确允许为空。它不是权限控制、业务状态机或删除策略的替代品。本文以 MySQL 8.0 / InnoDB 为主，也适用于理解 PostgreSQL 的基本取舍。

## 先从业务关系开始

假设一个系统有用户、订单和订单项：

```txt
users 1 ───── N orders 1 ───── N order_items
```

`orders.user_id`、`order_items.order_id` 是关系字段。没有任何约束时，应用可能留下：

```txt
orders.user_id = 999，但 users 里没有 999
order_items.order_id = 42，但订单 42 已经不存在
```

这种孤儿记录会让 JOIN 少数据、统计不可信、删除和修复困难。外键把“引用必须存在”下沉到数据库，让所有写入者（API、脚本、后台任务）共享同一条硬规则。

外键不保证：

- 用户是否有权限创建订单。
- 订单状态是否允许修改。
- 一个用户最多能有多少订单。
- 删除用户是否符合合规和业务要求。
- 跨数据库、跨服务、跨分片的数据一致性。

这些仍需要授权、`CHECK`、唯一约束、事务、状态机或对账任务。

## 一个最小的外键例子

```sql
CREATE TABLE users (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  email VARCHAR(255) NOT NULL,
  UNIQUE KEY uk_users_email (email)
) ENGINE=InnoDB;

CREATE TABLE orders (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  user_id BIGINT UNSIGNED NOT NULL,
  status VARCHAR(32) NOT NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  KEY ix_orders_user_id (user_id),
  CONSTRAINT fk_orders_user
    FOREIGN KEY (user_id) REFERENCES users(id)
    ON DELETE RESTRICT
    ON UPDATE RESTRICT
) ENGINE=InnoDB;
```

创建 `orders` 时，`user_id` 必须已存在；删除仍被订单引用的用户会失败。外键列需要索引，InnoDB 会自动创建缺少的索引，但建议显式命名，方便查看执行计划和迁移差异。父列必须有索引，通常引用主键或唯一键；两边类型、符号位和长度要匹配。

```sql
INSERT INTO orders (user_id, status) VALUES (999, 'created');
-- ERROR 1452: Cannot add or update a child row
```

应用不应把这个数据库错误原样返回给用户。Service 层可以把它映射成“用户不存在”或并发冲突，同时记录约束名和 request id。

## 删除动作的四种语义

```sql
FOREIGN KEY (user_id) REFERENCES users(id)
  ON DELETE RESTRICT
```

| 选项 | 父记录删除时 | 适合的关系 |
|---|---|---|
| `RESTRICT` | 只要存在子记录就拒绝 | 订单与用户、支付与订单等需要保留历史的关系 |
| `NO ACTION` | InnoDB 中通常等同于 `RESTRICT`，不支持延迟检查 | 与默认拒绝语义相同 |
| `CASCADE` | 自动删除子记录 | 真正从属于父记录且没有独立生命周期的附件、订单项 |
| `SET NULL` | 子列改成 `NULL` | 删除分类后商品保留、作者删除后文章保留等弱关联 |

`SET NULL` 要求子列可空，且应用能处理“关联对象已不存在”。`ON UPDATE CASCADE` 很少需要：主键应保持稳定，业务字段变化应更新普通字段而不是传播主键。

## 你担心的级联删除确实存在

```sql
users
  └─ orders
       └─ order_items
            └─ shipments
```

如果每一层都使用 `ON DELETE CASCADE`，删除一个用户可能在同一条语句和事务中删除所有订单、订单项、物流记录。风险包括：

1. **删除范围不直观**：开发者只看到 `DELETE FROM users`，实际影响了多张表。
2. **锁持有时间变长**：大量子行被扫描、锁定和删除，其他请求排队。
3. **undo 与 binlog 膨胀**：大事务回滚慢，复制和备份也会受到影响。
4. **审计遗漏**：不能把级联删除当作逐行调用应用删除钩子；需要单独记录删除意图和影响范围。
5. **误删难恢复**：事务回滚窗口结束后，只能依赖备份与 binlog，不能靠“再插一条父记录”恢复。

因此，订单、支付、发票、审计日志通常不应因为用户注销就物理级联删除。更常见做法是用户进入 `deactivated` 状态，业务数据保留；需要匿名化时按字段和保留期执行受控任务。

## 删除顺序：为什么通常要从子到父

使用 `RESTRICT` 时，删除顺序必须尊重依赖图：

```txt
先删 order_items
再删 orders
最后删 users
```

生产删除应在同一事务中分批完成，且每批有明确上限：

```sql
START TRANSACTION;

DELETE FROM order_items
WHERE order_id IN (
  SELECT id FROM orders WHERE user_id = ? ORDER BY id LIMIT 500
);

DELETE FROM orders
WHERE user_id = ?
  AND NOT EXISTS (
    SELECT 1 FROM order_items WHERE order_items.order_id = orders.id
  )
LIMIT 500;

COMMIT;
```

上面是流程示意，具体 MySQL 版本、子查询限制和批次游标要在测试库验证。不能用一个无条件的大 `DELETE` 删除几十万行。更稳妥的任务会按主键范围分页、记录进度、设置超时，并在每批后提交；失败后从进度继续，而不是重跑全部。

如果表之间有环（A 引用 B，B 又引用 A），删除顺序无法靠拓扑排序解决，需要先解除关系、允许其中一个引用为空、改为软删除，或重新设计模型。临时关闭 `FOREIGN_KEY_CHECKS` 不是通用修复：它不会检查已写入的脏数据，重新打开也不会自动扫描修复。

## `CASCADE` 什么时候是好选择

判断标准不是“代码少不省事”，而是子记录是否真正没有独立生命周期：

```txt
订单项离开订单没有意义 → 可以 CASCADE
用户的订单有财务与审计价值 → 不要 CASCADE
文章的临时上传分片随文章删除 → 可以 CASCADE
支付记录需要长期留档 → RESTRICT / 软删除 / 匿名化
```

即便选择级联，也要：

- 在迁移评审中画出完整影响图。
- 给每个外键列建索引，避免父删除时扫描子表。
- 对大父表删除做行数预估和低峰演练。
- 用应用审计记录“谁发起了删除、为什么、预计影响多少行”。
- 对关键数据保留恢复方案，而不是依赖事务回滚。

## 五个业务场景怎么选

### 场景一：用户注销，但订单要保留

合规要求用户注销后不能继续登录，但财务和售后还要查历史订单。此时不能让 `users` 的删除级联 `orders`：

```sql
UPDATE users
SET status = 'deactivated', email = CONCAT('deleted+', id, '@invalid.local')
WHERE id = ? AND status = 'active';
```

`orders.user_id` 仍保留物理外键并使用 `ON DELETE RESTRICT`。用户表只做状态变更和必要的匿名化，订单通过 `user_id` 关联展示脱敏后的快照。这里外键保护“订单引用的用户记录还存在”，软删除保护“业务历史不能被误删”。

### 场景二：知识库文档和解析切片

文档删除后，切片、解析任务和向量索引通常都没有独立意义，但清理可能跨 MySQL、对象存储和向量数据库：

```txt
documents → document_chunks → parse_jobs
     └────── object storage file
     └────── vector index entries
```

`document_chunks` 可以使用 `ON DELETE CASCADE`，保证单库内不会留下切片孤儿；对象存储和向量库不能靠外键，需要删除任务记录、幂等清理和定期对账。若文档量大，应用先把文档标记为 `deleting`，后台按批次删切片、向量和文件，最后再物理删除文档，避免一次请求持锁数分钟。

### 场景三：商品分类被删除

商品仍要保留，只是分类不再可用：

```sql
category_id BIGINT UNSIGNED NULL,
FOREIGN KEY (category_id) REFERENCES categories(id)
  ON DELETE SET NULL
```

后台删除分类后，商品变成“未分类”，不会被误删。接口查询要明确是否包含未分类商品；如果分类是必选业务字段，则不能使用 `SET NULL`，应该改为停用分类或把商品迁移到“其他”分类后再 `RESTRICT` 删除。

### 场景四：团队、成员和角色

`team_members(team_id, user_id)` 是关联表，成员离开团队时只删除关联行；用户注销不应级联删除团队本身：

```sql
CREATE TABLE team_members (
  team_id BIGINT UNSIGNED NOT NULL,
  user_id BIGINT UNSIGNED NOT NULL,
  role VARCHAR(32) NOT NULL,
  PRIMARY KEY (team_id, user_id),
  FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT
) ENGINE=InnoDB;
```

删除团队时成员关系确实没有独立意义，可以级联；删除用户时，如果他仍是多个团队成员，`RESTRICT` 会强迫业务先转移所有权或清理关系。这比静默删除团队成员更容易发现权限和所有权问题。

### 场景五：多租户数据隔离

`projects.tenant_id` 和 `documents.project_id` 看似可以分别建外键，但真正的规则是“引用对象必须属于同一个租户”。单列外键无法表达这个条件：

```txt
tenant A 的 document 误引用 tenant B 的 project
```

可以把 `(tenant_id, project_id)` 设计成联合唯一键，再让子表引用联合键；或者在同一事务中做租户条件更新并加数据库约束。跨服务或分库后只能由服务边界、租户条件和对账兜底。**有外键不等于自动完成多租户隔离。**

## 软删除与外键

软删除只是增加状态或 `deleted_at`，不会自动满足所有业务规则：

```sql
UPDATE users SET deleted_at = NOW(3) WHERE id = ?;
```

物理外键仍然认为该用户存在，所以订单可以继续引用它；查询层需要统一加 `deleted_at IS NULL`，或者明确哪些报表包含已删除主体。若业务要求“同一邮箱只能有一个未删除用户”，MySQL 需要额外设计（例如归档表、应用事务或生成列配合唯一索引），不能只靠普通唯一约束。

软删除的优点是保留引用和审计链，代价是所有查询、唯一性和恢复任务都要理解“已删除”状态。它不是无限保留数据的理由，仍需按法规和数据保留政策清理或匿名化。

## 物理外键和逻辑外键

### 物理外键

由数据库强制执行 `FOREIGN KEY`。优点是规则集中、不会被某个写入方绕过；缺点是写入和删除要遵守依赖，DDL、批量导入和高峰期维护需要考虑锁与校验。

适合：

- 单库或同一实例内的核心关系。
- 写入方较多、人工 SQL 较多的系统。
- 数据正确性比极限写吞吐更重要的业务。

### 逻辑外键

只保存 `user_id`，由应用事务、服务协议、唯一约束和定期对账保证关系。它是架构边界的现实选择，不是“完全不需要约束”。

必须补齐：

```txt
写入时检查父对象和权限
跨表写入尽量在同一事务
删除采用状态机或受控任务
外键列建立索引
定期扫描孤儿记录并告警
修复脚本幂等、可审计、可回滚
```

分库分表、跨服务和跨区域时不能建立普通数据库外键；此时由领域服务拥有数据、事件通知和对账闭环更现实。Redis 锁也不能替代外键，它只协调一段时间内的并发。

## 为什么很多工作项目不加外键

“工作中一般不加”有一定现实背景，但不是普遍规则。常见原因是：

1. **分库分表**：父子表不在同一实例，数据库无法跨分片校验。
2. **微服务边界**：订单服务不能直接给用户服务的数据库加约束。
3. **高吞吐写入**：批量写入、归档、在线 DDL 对约束检查和锁等待更敏感。
4. **发布与迁移复杂**：先发应用还是先加约束、历史脏数据如何清理，都需要严格编排。
5. **删除语义复杂**：保留订单、匿名化用户、跨系统清理通常不适合简单级联。

但“不加外键”也会付出代价：

- 每个写入方都可能忘记检查，孤儿数据持续产生。
- 数据库无法保护手工 SQL 和临时脚本。
- 关系规则分散在代码、任务和文档里，排障成本更高。
- 迁移或服务故障后需要对账来发现不一致。

实务判断：

| 架构 | 建议 |
|---|---|
| 单体、单库、核心业务关系 | 默认建物理外键，删除多用 `RESTRICT` |
| 单库但数据量很大 | 核心关系可建；危险的删除用受控任务，慎用大级联 |
| 多服务各自拥有数据库 | 不建跨库外键，用事件、幂等和对账 |
| 分库分表 | 使用逻辑外键，分片键和数据归属要先设计 |
| 临时表、日志、分析宽表 | 按查询和生命周期决定，别为了形式强行互相引用 |

## 迁移和补加外键

给已有表补外键前，不要直接执行 `ALTER TABLE`。先查脏数据：

```sql
SELECT o.user_id, COUNT(*) AS orphan_count
FROM orders o
LEFT JOIN users u ON u.id = o.user_id
WHERE u.id IS NULL
GROUP BY o.user_id;
```

处理策略通常有三类：修复父记录、迁移子记录到合法父记录、隔离并人工确认。删除孤儿记录必须有业务批准和备份。

再确认：

- 子列和父列类型完全兼容。
- 子列索引存在且基数合理。
- 历史导入、回放脚本和 ORM migration 都遵守依赖顺序。
- 加约束的锁、耗时和回滚方案已在影子环境演练。
- 失败时不会留下半套应用和数据库版本。

测试环境至少覆盖：插入不存在父 ID、删除仍被引用父行、级联影响行数、并发删除/插入、批量清理中断恢复，以及恢复备份后的约束状态。

## 官方参考

- [MySQL 外键约束](https://dev.mysql.com/doc/refman/8.0/en/create-table-foreign-keys.html)
- [MySQL InnoDB 外键检查](https://dev.mysql.com/doc/refman/8.0/en/innodb-foreign-key-constraints.html)
- [PostgreSQL 外键约束](https://www.postgresql.org/docs/current/ddl-constraints.html)

---

## 面试问答

**1. 外键到底保证了什么，没保证什么？**

- 保证引用完整性：子表里的 ID 必须指向一个存在的父表记录，所有写入方（API、脚本、后台任务）共享同一条硬规则。
- 不保证业务规则：权限、状态流转、数量上限、删除合规、跨服务跨分片一致性，要靠授权、CHECK、事务、状态机或对账任务。
- 加分：说得出没有约束时的实际痛点——孤儿记录让 JOIN 少数据、统计不可信、删除和修复困难。

**2. `ON DELETE` 的 RESTRICT、CASCADE、SET NULL 怎么选？**

- RESTRICT 是默认选择：还有子记录就拒绝删除，订单存在就不许删用户；`NO ACTION` 在 InnoDB 里和它一样。
- CASCADE 只给真正从属、没有独立生命周期的数据：订单项离开订单没有意义可以级联；支付记录要长期留档就不能。
- SET NULL 适合弱关联：删分类后商品变"未分类"，前提是外键列可空。
- 别踩的坑：层层 CASCADE，删一个用户在一个事务里级联删掉几十万行——锁持有时间变长、undo 和 binlog 膨胀、审计遗漏，事务回滚窗口过后只能靠备份和 binlog。

**3. 为什么很多工作项目不建外键？不建了拿什么兜底？**

- 现实原因：分库分表后父子表不在同一实例、微服务边界不能碰别人的库、高吞吐写入对约束检查和锁等待敏感、发布迁移编排复杂。
- 分界线：单体单库的核心关系默认建物理外键、多用 RESTRICT；分库分表和微服务用逻辑外键。
- 逻辑外键必须补齐：外键列建索引、跨表写入放同一事务、定期扫孤儿记录并告警、修复脚本幂等可审计。
- 无论建不建物理外键，外键列索引、删除顺序、迁移校验和恢复演练都不能省——这些是应用层必须自己扛起来的纪律。
- 加分：说得出"不加外键"的代价——每个写入方都可能忘记检查，数据库也保护不了手工 SQL 和临时脚本。

**4. 用户注销但订单必须保留，怎么设计？**

- 不让 users 的删除级联到 orders，`orders.user_id` 保留物理外键并使用 `ON DELETE RESTRICT`。
- 用户表只做状态变更和匿名化（status 改成 deactivated，邮箱换成占位值），订单通过 user_id 关联展示脱敏快照。
- 外键保护"订单引用的用户记录还存在"，软删除保护"业务历史不能被误删"，两件事各管各的。

**5. 给已有表补外键，能直接 `ALTER TABLE` 吗？**

- 不能。先用 `LEFT JOIN` 父表查孤儿数据，确认有多少子记录指向不存在的父记录。
- 处理策略三类：修复父记录、迁移子记录到合法父记录、隔离并人工确认；删除孤儿记录必须有业务批准和备份。
- 再确认两边类型兼容、子列索引存在，加约束的锁和耗时在影子环境演练过。
- 别踩的坑：临时关 `FOREIGN_KEY_CHECKS` 不是修复——它不检查已写入的脏数据，重新打开也不会自动扫描修复。
