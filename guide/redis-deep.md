---
title: Redis 深入
---

# Redis 深入

> 几乎所有后端项目都会用到 Redis。前端开发者最容易把 Redis 当"高级缓存"来理解，但它的能力远不止这点。

## 前端开发者理解 Redis 的角度

可以把 Redis 想象成一个**内存里的超级 Map**：
- Key-Value 存储，读写极快（微秒级）
- 数据可以设置过期时间（TTL）
- 支持 5+ 种数据结构
- 可以持久化到磁盘（重启不丢数据）

它和普通 Map 最大的区别是：**所有后端服务实例共享同一个 Redis**，所以能解决"多实例之间状态同步"的问题。

---

## 五种核心数据结构

### 1. String（字符串）— 最常用

```bash
SET user:1:token "abc123" EX 3600    # 设置，1小时过期
GET user:1:token                       # 获取
INCR page:counter                      # 原子自增
INCRBY article:123:views 5             # 原子增加指定值
SETNX lock:task:1 "worker-1"          # 不存在才设置（分布式锁的基础）
```

**适用场景：** 缓存、计数器、分布式锁、限流

### 2. Hash（哈希）

```bash
HSET user:1001 name "张三" age 28 role "admin"
HGET user:1001 name            # "张三"
HGETALL user:1001              # 所有字段
HINCRBY user:1001 age 1        # 年龄+1
```

**适用场景：** 存储对象（比 JSON 字符串更灵活，支持单独读写字段）

### 3. List（列表）

```bash
LPUSH queue:tasks "job-1"      # 从左侧推入
RPUSH queue:tasks "job-2"      # 从右侧推入
LPOP queue:tasks               # 从左侧弹出（实现队列）
RPOP queue:tasks               # 从右侧弹出
LRANGE queue:tasks 0 -1        # 全部元素
LLEN queue:tasks               # 长度
```

**适用场景：** 消息队列（轻量级）、最新消息列表、日志队列

### 4. Set（集合—无序不重复）

```bash
SADD article:1001:tags "前端" "后端" "Redis"
SMEMBERS article:1001:tags     # 全部元素
SISMEMBER article:1001:tags "前端"  # 是否存在
SINTER set1 set2               # 交集
SUNION set1 set2               # 并集
```

**适用场景：** 标签系统、好友关系、共同关注、去重

### 5. Sorted Set（有序集合）

```bash
ZADD leaderboard 100 "用户A"
ZADD leaderboard 80 "用户B" 200 "用户C"
ZREVRANGE leaderboard 0 2 WITHSCORES  # 前三名（带分数）
ZINCRBY leaderboard 10 "用户A"        # 用户A +10分
ZRANK leaderboard "用户B"             # 查看排名
```

**适用场景：** 排行榜、延时队列（时间戳做分数）、限流滑动窗口

---

## 过期策略

### 设置过期时间

```bash
SET code:123456 "9527" EX 300          # 300秒后自动删除
EXPIRE cache:key 3600                  # 对已有key设置过期
TTL cache:key                          # 查看剩余时间（-2=已过期,-1=永不过期）
PERSIST cache:key                      # 移除过期时间
```

### 键淘汰策略（内存满了怎么办）

Redis 默认 64MB 内存（可配置），满了之后：

| 策略 | 行为 |
|------|------|
| `noeviction`（默认） | 写操作报错 |
| `allkeys-lru` | 淘汰最近最少使用的 key（最常用） |
| `volatile-lru` | 只在有过期时间的 key 里淘汰最近最少使用的 |
| `allkeys-ttl` | 淘汰即将过期的 key |
| `volatile-random` | 随机淘汰有过期时间的 key |

**生产推荐：** `maxmemory-policy allkeys-lru`

---

## 缓存使用的最佳实践

### Cache Aside 模式（最常用）

```python
async def get_user(user_id: int):
    # 1. 先查缓存
    cached = await redis.get(f"user:{user_id}")
    if cached:
        return json.loads(cached)

    # 2. 缓存未命中，查数据库
    user = await db.get(User, user_id)
    if not user:
        return None

    # 3. 写入缓存（设过期时间）
    await redis.setex(f"user:{user_id}", 3600, user.json())
    return user
```

### 更新缓存时的陷阱

```python
# ❌ 错误：先更新数据库，再删除缓存，但中间有并发问题
await db.update(user)
await redis.delete(f"user:{user.id}")

# ✅ 推荐做法：延迟双删（第二次删除延迟执行）
await db.update(user)
await redis.delete(f"user:{user.id}")
# 延迟 500ms 后再删一次（解决并发读写的缓存不一致）
await asyncio.sleep(0.5)
await redis.delete(f"user:{user.id}")
```

### 缓存穿透

**问题：** 查询一个一定不存在的数据（如用户ID=-1），每次都穿透到数据库

**解决方案：**

```python
async def get_user(user_id: int):
    cached = await redis.get(f"user:{user_id}")
    if cached:
        # 即使是空值缓存，也直接返回
        return None if cached == "NULL" else json.loads(cached)

    user = await db.get(User, user_id)

    # 无论是否存在都写缓存
    if user:
        await redis.setex(f"user:{user_id}", 3600, user.json())
    else:
        # 空值也缓存，但过期时间短一些，防止长期空占
        await redis.setex(f"user:{user_id}", 60, "NULL")

    return user
```

### 缓存雪崩

**问题：** 大量 key 在同一时间过期，所有请求同时落到数据库

**解决方案：**

```python
# 过期时间加随机偏移
import random
expire = 3600 + random.randint(0, 600)  # 1小时 ± 10分钟
await redis.setex(f"user:{user_id}", expire, user.json())
```

### 缓存击穿

**问题：** 热点 key 过期的一瞬间，大量请求同时打向数据库

**解决方案：**

```python
# 互斥锁（只让一个请求去加载数据）
async def get_hot_article(article_id: int):
    cache_key = f"hot_article:{article_id}"
    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)

    # 尝试加锁（只有第一个请求能拿到锁）
    lock_key = f"lock:{cache_key}"
    locked = await redis.setnx(lock_key, "1")
    if locked:
        await redis.expire(lock_key, 10)  # 避免死锁
        article = await db.get(Article, article_id)
        await redis.setex(cache_key, 3600, article.json())
        await redis.delete(lock_key)
        return article

    # 没抢到锁就等一会再查缓存
    await asyncio.sleep(0.1)
    return await get_hot_article(article_id)
```

---

## 分布式锁

前面的 `SETNX` 是一个简单的分布式锁，但有坑。更稳的写法：

```python
import uuid
import time

class RedisLock:
    def __init__(self, redis, key: str, ttl: int = 10):
        self.redis = redis
        self.key = f"lock:{key}"
        self.ttl = ttl
        self.token = str(uuid.uuid4())  # 唯一标识，防止释放别人的锁

    async def acquire(self) -> bool:
        """获取锁，成功返回 True"""
        return await self.redis.setnx(self.key, self.token) and \
               await self.redis.expire(self.key, self.ttl)

    async def release(self):
        """释放锁：只释放自己的锁"""
        # Lua 脚本保证原子性（查询和删除在一个命令里）
        script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        await self.redis.eval(script, 1, self.key, self.token)
```

**注意：**
- 必须设置过期时间（防止死锁）
- 必须用唯一 token（防止误删别人的锁）
- 释放锁要原子操作（Lua 脚本）

---

## Redis 在生产上的常见用法

| 场景 | 方案 |
|------|------|
| 登录态/Token | `SET token:xxx user_id EX 7200` |
| 验证码 | `SET code:phone 123456 EX 300` |
| 接口限流 | 滑动窗口（Sorted Set + 时间戳） |
| 分布式锁 | `SETNX` + Lua 脚本 |
| 排行榜 | ZADD / ZREVRANGE |
| 延时任务 | Sorted Set（时间戳做分数） |
| 计数器 | INCR / DECR |
| 轻量队列 | LPUSH + RPOP / BRPOP |
| 缓存 | GET / SETEX |
| 布隆过滤器 | Redis Stack 模块 |

---

## 面试问答

**1. 缓存穿透、击穿、雪崩怎么区分，分别怎么处理？**

- 穿透：查的是一定不存在的数据（比如 ID=-1），每次都穿透到数据库。空值也写缓存但过期时间设短（60 秒），下次直接返回，不再回源
- 击穿：一个热点 key 过期的一瞬间，大量请求同时压向数据库。用 SETNX 互斥锁，只放一个请求去回源加载数据，其他请求等一会再查缓存
- 雪崩：大量 key 在同一时间集中过期，所有请求同时落到数据库。过期时间加随机偏移，比如 1 小时 ± 10 分钟
- 加分：能说清三者触发条件不同——穿透是「数据不存在」，击穿是「单个热点 key 失效」，雪崩是「大面积同时失效」

**2. Redis 内存满了会发生什么？淘汰策略怎么选？**

- 默认 `noeviction`，内存写满后所有写操作直接报错，线上表现是突然大面积写入失败
- 生产推荐 `allkeys-lru`，淘汰最近最少使用的 key；`volatile-lru` 只在设了过期时间的 key 里淘汰，范围小得多
- 别踩的坑：默认策略平时毫无异常，只在内存满的那一刻爆炸，上线前先确认 `maxmemory-policy`

**3. 更新数据库后缓存怎么处理？为什么推荐延迟双删？**

- 标准 Cache Aside 是写库后删缓存，但「先更新库、再删缓存」中间有并发窗口，读请求可能把旧值又写回缓存
- 延迟双删：更新数据库 → 删缓存 → 延迟 500ms 再删一次，把并发读写造成的脏缓存清掉
- 第二次删除要延迟执行，目的是等那些「读到了旧值、正要写回缓存」的请求先落地

**4. 对象用 Hash 存还是序列化成 JSON 字符串存？**

- Hash 支持单独读写字段：HGET 取一个字段、HINCRBY 给某字段加值，不用整体读出来改完再写回，比 JSON 字符串更灵活
- JSON 字符串一次取全量更直接，但任何字段更新都要整体覆盖
- 简单键值场景（token、验证码、计数器）用 String 就够，Hash 用在需要按字段操作的对象上

**5. 用 SETNX 做分布式锁，哪几个细节不做就会出事？**

- 必须设置过期时间，否则持有者一崩锁永远不释放，死锁
- value 必须是唯一 token，否则业务超时锁过期易主后，A 释放时会删掉 B 刚拿到的锁
- 释放锁要「比对 token 再删」且两步原子，用 Lua 脚本实现
- 别踩的坑：释放时直接 DEL 不比对 token，锁过期被别人拿走后，删掉的就是别人的锁

**6. 除了缓存，String / List / Sorted Set 还有哪些典型用法？**

- String：分布式锁（SETNX + Lua + 唯一 Token）和计数限流
- List：LPUSH + BRPOP 做轻量 MQ，适合允许少量丢失的低价值场景
- Sorted Set：排行榜和延时队列（score 存执行时间戳，轮询取到期任务）
- 加分：选结构先看访问模式——Hash 要按字段单独读写，ZSET 要按分数范围取，选错了后面全是补丁
