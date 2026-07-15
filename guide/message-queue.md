# 消息队列基础

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
   → MQ 保证一条消息不会被两个消费者同时处理
   → 但如果消费者自己开了多线程，或者一个任务改同一个数据，还是有并发问题

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

## 面试怎么说

> 我在项目中用 MQ 做异步任务和系统解耦。比如文档上传后不阻塞请求，而是把解析任务发到 MQ，Worker 异步消费。选型上，轻量场景用 Redis List 或 Stream，需要可靠投递时用 RabbitMQ。消费端我会设计幂等逻辑，用唯一约束或状态机保证重复消息不会产生重复数据。同时监控队列积压，超出阈值时告警或扩容。
