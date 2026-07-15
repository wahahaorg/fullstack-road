# 并发、事务与一致性

## 这一章解决什么问题

后端项目真正容易出问题的地方，通常不是路由怎么写，而是：

```txt
多个请求同时修改同一份数据
接口被重复调用
任务失败后重试
数据库和缓存不一致
MQ 消息重复消费
```

这些问题的本质是：

```txt
并发 + 状态 + 数据一致性
```

## 先问：共享资源在哪里

回答并发问题时，不要一上来就说“加锁”或“用 MQ”。先判断共享资源在哪一层：

| 共享资源 | 常见方案 |
| --- | --- |
| 单进程内存 | `asyncio.Lock`、线程锁、信号量 |
| MySQL 数据 | 事务、行锁、唯一索引、条件更新、乐观锁 |
| 多实例服务 | 数据库约束、Redis 分布式锁、幂等键 |
| 异步任务 | MQ、任务表、ACK、重试、幂等消费 |
| 缓存和数据库 | Cache Aside、失效重试、最终一致性 |

原则：

> 最终正确性尽量建立在数据所在的系统上。

库存存在 MySQL，就优先用 MySQL 的条件更新、事务和约束保证正确性，而不是只靠 API 进程里的内存锁。

## HTTP 并发为什么会出问题

无论 FastAPI 还是 NestJS，服务器都会同时处理多个请求。

错误库存流程：

```txt
请求 A：读取库存 1 ───────── 写入库存 0
请求 B：      读取库存 1 ───── 写入库存 0
```

两个请求都认为自己成功了，但库存只减少一次，订单可能创建两笔。

前端禁用按钮只能改善体验，不能保证后端正确。用户可以刷新、重试、脚本调用，也可能因为网络抖动重复发送请求。

## 数据库原子更新

扣库存最常用的写法：

```sql
UPDATE products
SET stock = stock - 1
WHERE id = ? AND stock > 0;
```

然后检查影响行数：

```txt
affected_rows = 1  扣减成功
affected_rows = 0  商品不存在或库存不足
```

这个写法比“先查再改”更稳，因为判断和修改在一条 SQL 里完成。

## 事务

事务保证一组 SQL 要么全部成功，要么全部失败。

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

如果扣库存失败，就不应该插入订单。

在 SQLAlchemy 中，通常由 service 控制事务：

```python
async def create_order(session: AsyncSession, user_id: int, product_id: int):
    async with session.begin():
        updated = await decrease_stock(session, product_id)
        if not updated:
            raise AppError("OUT_OF_STOCK", "库存不足")

        order = await create_order_row(session, user_id, product_id)
        return order
```

## 悲观锁：select for update

当你需要先读取一行，再基于当前值做复杂判断，可以用行锁：

```sql
START TRANSACTION;

SELECT id, balance
FROM accounts
WHERE id = 1
FOR UPDATE;

UPDATE accounts
SET balance = balance - 100
WHERE id = 1;

COMMIT;
```

`FOR UPDATE` 会锁住选中的行，其他事务要等你提交或回滚。

适合：

- 余额修改。
- 状态流转判断复杂。
- 必须读取当前值后再决定怎么改。

代价：

- 并发性能下降。
- 容易因为事务过长导致等待。
- 加锁范围依赖索引，索引设计不好可能锁更多数据。

## 乐观锁：version 字段

适合冲突不频繁，但要防止覆盖更新的场景。

表字段：

```sql
version INT UNSIGNED NOT NULL DEFAULT 0
```

更新：

```sql
UPDATE articles
SET title = ?, content = ?, version = version + 1
WHERE id = ? AND version = ?;
```

如果影响行数是 0，说明有人先更新了这条数据，当前用户需要刷新后重试。

适合：

- 内容编辑。
- 审核状态。
- 配置修改。

## 唯一约束和幂等

重复提交最稳的方式之一是幂等键。

例如创建支付单：

```sql
CREATE TABLE payments (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  order_id BIGINT UNSIGNED NOT NULL,
  idempotency_key VARCHAR(128) NOT NULL,
  amount_cent BIGINT NOT NULL,
  status VARCHAR(32) NOT NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  UNIQUE KEY uk_idempotency_key (idempotency_key),
  UNIQUE KEY uk_order_id (order_id)
);
```

客户端或服务端生成 `idempotency_key`，同一次业务操作重复请求时使用同一个 key。数据库唯一索引保证不会重复创建。

## Redis 分布式锁

Redis 锁适合协调多个服务实例：

```txt
多个 worker 抢同一个任务
多个实例只允许一个执行定时任务
某个资源短时间只允许一个操作
```

但要注意：

- 必须设置过期时间。
- value 要用随机 token，释放锁时只释放自己的锁。
- 加锁成功不代表数据库操作一定成功。
- 最终正确性仍要靠数据库约束、事务或幂等兜底。

Redis 锁是协调手段，不是业务正确性的唯一来源。

## MQ 不是万能并发解法

MQ 适合：

```txt
削峰
异步处理
解耦
失败重试
最终一致性
```

但 MQ 不天然保证：

```txt
消息只消费一次
消费者之间没有并发
数据库一定更新成功
业务一定幂等
```

所以消费端仍然要设计：

```txt
幂等表
唯一约束
任务状态机
失败重试
死信队列
补偿机制
```

## AI 应用里的典型场景

### 文档重复导入

问题：

```txt
用户重复上传同一个 PDF
网络重试导致上传接口调用两次
解析 worker 重试导致 chunk 写入两次
```

方案：

```txt
documents: UNIQUE(knowledge_base_id, file_sha256)
document_chunks: UNIQUE(document_id, chunk_index)
parse_jobs: 状态机 + 幂等消费
```

### 报表任务重复生成

问题：

```txt
用户连续点击“生成报表”
同一参数创建了多个任务
```

方案：

```txt
根据 user_id + report_type + params_hash 创建唯一索引
如果已有 pending/running 任务，直接返回已有任务
```

### 审核状态互相覆盖

问题：

```txt
审核人 A 通过
审核人 B 同时驳回
最终状态取决于谁最后写入
```

方案：

```txt
状态流转条件更新
或者 version 乐观锁
必要时记录 audit_logs
```

示例：

```sql
UPDATE articles
SET status = 'published'
WHERE id = ? AND status = 'reviewing';
```

影响行数为 0，说明状态已经变化，不能继续操作。

## 面试怎么说

> 我会先判断共享资源在哪一层。如果是单进程内存，可以用互斥锁或信号量；如果共享资源在 MySQL，比如库存、余额、审核状态，我会优先用事务、条件更新、行锁、乐观锁和唯一约束保证一致性；如果是多实例部署，还要考虑 Redis 分布式锁、幂等键和 MQ 串行化消费。但 MQ 和分布式锁不是最终正确性的替代品，最终落库仍然要靠事务、约束和幂等兜底。

