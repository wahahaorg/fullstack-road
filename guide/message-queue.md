---
title: 消息队列基础
---

# 消息队列基础

> 写库与发消息的双写问题、Outbox、事务幂等消费和故障恢复，见 [分布式一致性与可靠消息](./distributed-consistency)。

> 前端开发者很少直接接触 MQ，但在后端架构中它是"削峰填谷、异步解耦"的核心基础设施。

## 为什么需要消息队列

```txt
场景 1：用户上传了一个 PDF，需要解析、切块、向量化
  → 直接在请求里做完？用户等 30 秒？不行
  → 先返回"任务已提交"，后台慢慢处理

场景 2：订单服务需要通知库存、通知物流、通知财务
  → 一个一个同步调用？一个挂了全部失败
  → 扔到 MQ，各服务自己消费

场景 3：双十一流量暴增 10 倍
  → 每个请求都直接操作数据库？数据库撑不住
  → 先堆到 MQ，消费者慢慢处理（削峰填谷）
```

**核心价值：异步、解耦、削峰填谷、失败重试**

---

## 队列模型 vs 发布订阅模型

### 点对点（Queue）

```txt
Producer → [Queue] → Consumer1
                   → Consumer2（竞争消费）

一条消息只会被一个消费者消费
适合：任务队列
```

### 发布/订阅（Topic）

```txt
Producer → [Topic] → Subscriber1
                   → Subscriber2
                   → Subscriber3

一条消息会被所有订阅者各消费一次
适合：事件通知
```

---

## RabbitMQ vs Kafka 选型

| 对比 | RabbitMQ | Kafka |
|------|----------|-------|
| 定位 | 消息代理 | 分布式流处理平台 |
| 吞吐量 | 万级/秒 | 百万级/秒 |
| 延迟 | 微秒级 | 毫秒级 |
| 消息持久化 | 支持 | 支持（磁盘顺序写） |
| 消息顺序 | 单队列有序 | 分区内有序 |
| 失败重试 | 死信队列 + ACK | 消费者位移 + 重设 |
| 学习成本 | 较低 | 较高 |
| 适合场景 | 业务消息、任务调度 | 日志聚合、大数据、事件溯源 |

**新手建议从 RabbitMQ 入手，理解概念后再接触 Kafka。**

---

## 消息队列核心概念

### 生产者（Producer）

发送消息的一方：

```python
# 用 RabbitMQ 发送消息
import pika

connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
channel = connection.channel()

channel.queue_declare(queue='parse_jobs', durable=True)

channel.basic_publish(
    exchange='',
    routing_key='parse_jobs',
    body='{"document_id": 123, "file_path": "/tmp/doc.pdf"}',
    properties=pika.BasicProperties(delivery_mode=2)  # 持久化
)

connection.close()
```

### 消费者（Consumer）

接收并处理消息的一方：

```python
import pika

def callback(ch, method, properties, body):
    print(f"收到任务: {body}")
    # 处理任务...
    # 处理完成后确认
    ch.basic_ack(delivery_tag=method.delivery_tag)

connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
channel = connection.channel()

channel.queue_declare(queue='parse_jobs', durable=True)
channel.basic_qos(prefetch_count=1)  # 每次只取一个
channel.basic_consume(queue='parse_jobs', on_message_callback=callback)

channel.start_consuming()
```

### ACK 确认

```txt
消费者收到消息 →
  处理完成 → 发送 ACK → MQ 删除消息
  处理失败 → 不发送 ACK → MQ 重新投递
  消费者断开 → 未 ACK 的消息重新入队
```

### 死信队列（DLQ）

```txt
消息处理失败达到最大重试次数 →
  → 进入死信队列（DLQ）
  → 人工排查或降级处理
```

---

## 轻量级方案：用 Redis 做 MQ

不需要单独部署 RabbitMQ/Kafka 时，Redis List 和 Stream 可以当轻量 MQ：

```python
# 生产者
await redis.lpush("queue:tasks", json.dumps({"doc_id": 123}))

# 消费者（阻塞等待）
while True:
    task = await redis.brpop("queue:tasks", timeout=0)
    data = json.loads(task[1])
    await process_task(data)
```

**Redis Stream（Redis 5.0+，更可靠的 MQ）：**

```python
# 生产者
await redis.xadd("stream:tasks", {"doc_id": "123", "status": "pending"})

# 消费者组（多消费者竞争消费）
await redis.xgroup_create("stream:tasks", "workers")
while True:
    messages = await redis.xreadgroup("workers", "worker-1", {"stream:tasks": ">"})
    for msg_id, msg in messages:
        await process(msg)
        await redis.xack("stream:tasks", "workers", msg_id)
```

---

## 业务中的典型用法

### 文档解析（最常见的 AI 后端场景）

```txt
用户上传 PDF
  → API 快速返回 {document_id: 123, status: "pending"}
  → 把 parse_job 入库 + 发 MQ
  → Worker 监听 MQ → 收到任务 → 解析 → 更新状态 → ACK
  → 前端轮询接口，看到状态变为 "parsed"
```

```python
# API 层
@app.post("/documents")
async def upload_document(file: UploadFile):
    doc = await save_to_db(file)
    # 发 MQ，异步处理
    await redis.lpush("parse_jobs", json.dumps({"doc_id": doc.id}))
    return {"document_id": doc.id, "status": "pending"}

# Worker（独立进程）
async def worker_loop():
    while True:
        task = await redis.brpop("parse_jobs", timeout=0)
        data = json.loads(task[1])
        try:
            await parse_document(data["doc_id"])
            await update_status(data["doc_id"], "success")
        except Exception as e:
            await update_status(data["doc_id"], "failed")
```

### MQ 不是银弹

常见误区：

```txt
❌ "用了 MQ 就不会丢消息"
   → 如果消费者还没 ACK 就挂了，消息还在（不丢）
   → 但消息已经落库、服务被重启，会导致重复消费
   → 所以消费端必须幂等

❌ "用了 MQ 就不用考虑并发"
   → 重投、连接中断后的重新分配及不同消息访问同一资源，都可能引入并发
   → 消费端仍需数据库约束、幂等和必要的并发控制

❌ "MQ 一定能削峰"
   → MQ 能缓冲，但如果消费者处理速度一直跟不上，队列会无限膨胀
   → 需要监控队列积压，必要时扩容消费者
```

---

## 幂等消费

MQ 不保证"只消费一次"，所以消费者必须幂等：

```python
async def consume_parse_job(data):
    # 方案 1：数据库唯一约束
    # parse_jobs 表有 UNIQUE(document_id)
    try:
        await db.execute(INSERT INTO parse_jobs ...)
    except DuplicateEntry:
        return  # 已处理过，忽略

    # 方案 2：任务表状态机
    updated = await db.execute(
        UPDATE parse_jobs SET status = 'running'
        WHERE id = ? AND status = 'pending'
    )
    if updated == 0:
        return  # 已被其他 worker 处理了
```

---

## 面试问答

**1. 点对点队列和发布订阅模型有什么区别？**

- 点对点（Queue）：一条消息只会被一个消费者消费，多个消费者是竞争关系，适合任务队列
- 发布/订阅（Topic）：一条消息会被所有订阅者各消费一次，适合事件通知
- 选哪种取决于「这条消息是给一个人干的活，还是广播给所有人知道的事」

**2. RabbitMQ 和 Kafka 怎么选？**

- RabbitMQ 是消息代理，吞吐万级/秒、延迟微秒级，学习成本较低，适合业务消息、任务调度
- Kafka 是分布式流处理平台，吞吐百万级/秒、延迟毫秒级、磁盘顺序写，适合日志聚合、大数据、事件溯源
- 加分：能说出顺序保证的差异——RabbitMQ 单队列有序，Kafka 只保证分区内有序

**3. 小项目用 Redis 当消息队列够吗？**

- 够。Redis List 加 BRPOP 阻塞弹出就是一个轻量任务队列；Redis Stream（Redis 5.0+）有消费者组和 XACK，支持多消费者竞争，更可靠
- 不需要单独部署 RabbitMQ/Kafka 时它是最省事的选择；需要可靠投递和成熟的重试、死信机制时再上 RabbitMQ
- 新手路线也类似：从 RabbitMQ 理解概念，再接触 Kafka

**4. 用了 MQ 为什么还会重复消费？幂等怎么做？**

- 消费者处理完成但 ACK 没发出去（进程挂了、连接断了），消息会重新投递——MQ 不保证「只消费一次」
- 方案一是数据库唯一约束：重复 INSERT 捕获 DuplicateEntry 直接 return，当作已处理
- 方案二是任务表状态机：`UPDATE parse_jobs SET status='running' WHERE id=? AND status='pending'`，更新行数为 0 说明已被其他 worker 处理
- 别踩的坑：方案二的 UPDATE 必须带 `AND status='pending'` 条件，靠返回的影响行数判断有没有被抢先处理

**5. 「用了 MQ 就能削峰、就不用考虑并发」，这两句话对吗？**

- 削峰只对一半：MQ 能缓冲，但消费者处理速度一直跟不上，队列会无限膨胀，必须监控积压、必要时扩容消费者
- 并发问题不会消失：消息重投、连接中断后的重新分配、不同消息访问同一资源，都可能引入并发，消费端仍需数据库约束、幂等和必要的并发控制
- MQ 的准确定位是异步、解耦、削峰填谷、失败重试的基础设施，不是正确性的替代品
