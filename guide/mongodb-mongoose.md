---
title: MongoDB 与 Mongoose：什么时候不用关系型
---

# MongoDB 与 Mongoose：什么时候不用关系型

> "存 JSON 很方便"不是选择 MongoDB 的理由。这篇先讲清它凭什么值得用、代价是什么，再讲文档建模、聚合管道、索引，以及在 Nest 里怎么接。

## 凭什么用它

文档数据库和关系型数据库的差别不在语法，在**数据的形状**。关系型把一个业务对象拆散到多张表，查询时再用 JOIN 拼回来；文档型直接把它整块存下来。

```javascript
{ _id: ObjectId("66d1..."), title: "订单确认页改版",
  author: { id: 12, name: "阿明" },          // 内嵌，不用 JOIN users
  tags: ["frontend", "ux"],                 // 数组是一等公民，不用中间表
  meta: { source: "figma", version: 3 },    // 每篇文章的 meta 可以完全不同
  createdAt: ISODate("2026-08-20T10:00:00Z") }
```

三个真实优势：

| 优势 | 具体表现 |
|---|---|
| schema 灵活 | 加字段不用 `ALTER TABLE`，不用停机、不用改表锁。同一个集合里的文档可以有不同字段 |
| 嵌套避免 JOIN | 一次查询拿到完整对象，读多的场景省掉多次关联和多次网络往返 |
| 水平扩展是内建能力 | 分片（sharding）是官方一等功能，不用像 MySQL 那样自己引入中间件做分库分表 |

### 代价必须说清楚

| 代价 | 说明 |
|---|---|
| 事务是后来才补上的 | 单文档更新一直是原子的，**跨文档事务** 4.0 才支持，且要求副本集部署（本地单机 mongod 直接用会报错）、有 60 秒默认时长上限、性能不如 MySQL 的事务 |
| 关联查询弱 | `$lookup` 能做左连接，但优化能力远不如 SQL 的 JOIN，多表关联和分页组合起来很快就写不下去 |
| 冗余带来一致性负担 | 把作者名内嵌进 1000 篇文章，作者改名就要更新 1000 处。这个代价是你主动换来的，得有人记得维护 |
| 容易被当成"不设计表结构的借口" | 这是最大的坑。schema 灵活不等于不需要 schema，只是把约束从数据库挪到了应用层——挪走之后**必须有人接住**，否则半年后同一个集合里躺着五种格式的文档 |

### 什么数据放 MongoDB，什么留在 MySQL

| 适合 MongoDB | 为什么 |
|---|---|
| 日志与埋点事件 | 结构随版本变、写入量大、只按时间范围查、可以用 TTL 索引自动过期 |
| 聊天消息、通知 | 天然按会话分片，几乎不需要跨文档事务，一次拉一页 |
| 爬取或第三方同步的异构内容 | 每个来源字段都不一样，先原样存下来再慢慢清洗 |
| CMS 内容、活动页配置 | 结构由运营决定、嵌套很深、整块读取整块写入 |
| AI 应用的会话历史与工具调用记录 | 一次对话是一棵形状不固定的树，拆成关系表非常别扭 |

| 不适合 MongoDB | 为什么 |
|---|---|
| 订单、支付、账务 | 需要强事务、需要金额的精确约束、需要复杂对账报表 |
| 库存、余额这类并发争抢的数据 | 需要行锁、条件更新和唯一约束兜底，见 [并发、事务与一致性](/guide/concurrency-transaction) |
| 强关联的业务主数据（用户、权限、组织架构） | 到处都要 JOIN，实体之间关系比实体本身更重要 |
| 需要灵活多维分析的报表 | SQL 的 JOIN + 窗口函数在这类查询上是压倒性优势，见 [SQL 进阶与查询优化](/guide/mysql-advanced) |

现实中最常见的组合是**两个都用**：交易数据在 MySQL，日志、消息、非结构化内容在 MongoDB。判断标准不是"哪个更先进"，而是这份数据**有没有强约束、要不要跨实体事务、查询是整块读还是多维关联**。

---

## 概念映射

| MongoDB | 关系型 | 说明 |
|---|---|---|
| database | database | 一样 |
| collection | table | 集合不需要预先定义结构 |
| document | row | 一个 BSON 文档，上限 16MB |
| field | column | 每个文档的字段可以不同 |
| 内嵌文档 / 数组 | 关联表 + 中间表 | 文档型最大的表达力差异 |
| `$lookup` | `JOIN` | 能力弱得多 |
| index | index | 概念一致，同样有最左前缀 |

### _id 与 ObjectId

每个文档都有 `_id`，不指定时 MongoDB 自动生成一个 12 字节的 `ObjectId`：

```txt
66d1a4f0   8c3e21b90d   0a1f
└ 4 字节：秒级时间戳   └ 5 字节随机   └ 3 字节自增计数
```

带时间戳这个设计很实用：

```javascript
doc._id.getTimestamp()            // 直接拿到创建时间，不必额外存 createdAt
db.logs.find().sort({ _id: -1 })  // 按 _id 倒序 ≈ 按创建时间倒序，还能复用主键索引
// 按时间范围查询也能构造 ObjectId 边界，不用给 createdAt 单独建索引
```

代价是 `ObjectId` 只精确到秒，同一秒内的顺序由随机位和计数器决定，不能当成严格的时间序。要严格排序仍然得存一个时间字段。

BSON 比 JSON 多几个类型，这几个要知道：`ObjectId`、`ISODate`（真正的日期类型，别用字符串存时间）、`NumberLong`（64 位整数）、`Decimal128`（存金额用它，别用浮点 `double`）、`Binary`。JS 驱动会自动转换，但**金额字段一定要显式用 `Decimal128` 或整数分**，和 MySQL 里不用 `FLOAT` 是同一个理由。

---

## 基础 CRUD

```javascript
// 写入
db.articles.insertOne({ title: "a", tags: ["x"], views: 0 })
db.articles.insertMany([{ title: "b" }, { title: "c" }], { ordered: false })  // 一条失败不影响其余
```

查询操作符，全部写在字段名的对象里：

```javascript
db.articles.find({
  views:     { $gt: 100, $lte: 1000 },        // 比较：$eq $ne $gt $gte $lt $lte
  status:    { $in: ["published", "review"] },// 集合：$in $nin
  tags:      { $all: ["frontend", "ux"] },    // 数组同时包含多个值
  cover:     { $exists: false },              // 字段存不存在（不是等于 null）
  title:     { $regex: /改版$/ },              // 正则，注意左模糊无法用索引
  $or: [{ authorId: 12 }, { coAuthorIds: 12 }],
})

// 数组里的对象要整体匹配同一个元素，必须用 $elemMatch
db.orders.find({ items: { $elemMatch: { productId: 7, qty: { $gte: 2 } } } })
```

`$elemMatch` 是最容易写错的一个。不用它时，`{ "items.productId": 7, "items.qty": { $gte: 2 } }` 的语义是"**某个**元素 productId 是 7，**某个**元素 qty ≥ 2"——可以是两个不同的元素，结果多出一堆不该有的文档。

投影、排序、分页：

```javascript
db.articles
  .find({ status: "published" }, { title: 1, views: 1, _id: 0 })  // 1 保留 0 排除，不能混用（_id 例外）
  .sort({ views: -1, _id: -1 })
  .skip(20).limit(20)
```

`skip` 和 SQL 的 `OFFSET` 一样会随页数劣化（要一路数过去），深翻同样应该改成游标式的 `{ _id: { $lt: lastId } }`。

更新操作符——**不能直接传一个对象**，那样会整个替换掉文档：

```javascript
db.articles.updateOne({ _id: id }, {
  $set:   { title: "新标题", "meta.version": 4 },  // 点号可以直接改嵌套字段
  $unset: { draftContent: "" },                    // 删字段
  $inc:   { views: 1 },                            // 原子自增，并发安全
  $push:  { tags: { $each: ["a", "b"], $slice: -10 } },  // 追加并只保留最后 10 个
  $addToSet: { likedBy: userId },                  // 已存在就不重复加
  $pull:  { tags: "outdated" },                    // 按值删数组元素
})

db.counters.updateOne({ _id: "order" }, { $inc: { seq: 1 } }, { upsert: true })  // 不存在就创建
db.logs.deleteMany({ createdAt: { $lt: cutoff } })
```

**单文档的更新永远是原子的**，所以 `$inc` 计数器、`$addToSet` 去重这类操作不需要事务也不会丢。这是文档模型一个被低估的优势：把需要一起变的数据放在同一个文档里，就绕过了大部分事务需求。

---

## 文档建模：嵌套还是引用

这是 MongoDB 唯一真正需要动脑的决策，也是它和关系建模最大的区别：**关系型按"数据是什么"建模，文档型按"数据怎么被读"建模。**

判断依据：

| 情形 | 选择 | 理由 |
|---|---|---|
| 一对少（几个到几十个），且总是和父文档一起读 | **嵌套** | 一次查询搞定，不需要关联 |
| 一对多且子项会被独立查询、独立分页 | **引用** | 嵌套后无法只查子项，每次都要把整个父文档拉出来 |
| 子项数量无上限增长（评论、日志、消息） | **引用** | 16MB 上限迟早撞上，且文档不断变大会导致存储层反复搬移 |
| 子项会被多个父文档共享 | **引用** | 否则一处改动要同步 N 份 |
| 多对多 | **双向引用或中间集合** | 双向存 ID 数组，或退回关系型的中间集合思路 |
| 子项字段更新频率远高于父文档 | **引用** | 避免每次小改动都重写整个大文档 |

三个具体例子：

**文章与标签 → 嵌套。** 标签就是几个短字符串，永远和文章一起显示，不需要"标签"这个独立实体：

```javascript
{ _id: 1, title: "...", tags: ["frontend", "ux"] }
// 反查也很自然，给 tags 建索引即可：db.articles.find({ tags: "ux" })
```

MongoDB 的多键索引（multikey index）会为数组里每个值建一个索引项，所以按标签查文章不需要中间表。这是文档模型相对关系型的净胜局。

**订单与订单项 → 嵌套。** 数量有上限（一单几十件商品）、和订单一起创建、一起读取、下单后不再单独修改；更关键的是**订单项要记录下单当时的价格和商品名**，本来就该是一份快照而不是引用：

```javascript
{
  _id: ObjectId("..."), userId: 12, status: "paid",
  items: [
    { productId: 7, name: "机械键盘", priceCent: 39900, qty: 1 },   // 快照，商品改价不影响历史订单
    { productId: 9, name: "键帽",     priceCent: 8900,  qty: 2 },
  ],
  totalCent: 57700,
}
```

顺带一提：这个例子只说明"形状适合嵌套"。真实的订单业务需要强事务和对账，仍然应该放在 MySQL——**建模合适**和**该用哪个数据库**是两个独立判断。

**用户与关注关系 → 引用。** 多对多、无上限增长、双向都要查（我关注了谁、谁关注了我）：

```javascript
// ❌ 把关注列表嵌进用户文档：大 V 有 500 万粉丝，直接撞 16MB
{ _id: 12, name: "阿明", followerIds: [/* 五百万个 id */] }

// ✅ 独立集合，每条关系一个文档
{ _id: ObjectId("..."), followerId: 12, followeeId: 88, createdAt: ISODate("...") }
// 建两个索引分别支撑两个方向的查询，再加唯一索引防重复关注
```

这个例子里 MongoDB 并没有比关系型好，就是同一套中间表思路。数据关系天生是图状时，文档模型没有优势——如果关注关系还要做"共同关注""二度人脉"，那更该考虑 Redis 的集合运算（见 [Redis 实战](/guide/redis-practice)）或图数据库。

### 16MB 是嵌套的硬边界

单个 BSON 文档上限 16MB，超了直接报错。这不只是一个上限数字，它是**判断"能不能嵌套"的第一道筛子**：只要子项数量没有明确上界，就不要嵌套。

即使远没到 16MB，大文档也有隐性成本：MongoDB 的更新以文档为单位，改一个字段可能要重写整个文档；查询即使只投影一个字段，服务端也要先把整个文档读进内存。所以经验值是**单文档控制在几十 KB 以内、数组元素控制在几百个以内**，超出就该拆。要"最近 20 条"这种有界列表，可以用 `$push` 配合 `$slice: -20` 让数组自己保持定长。

---

## 聚合管道

聚合管道是一个数组，数据从第一个阶段流到最后一个阶段，每个阶段的输出是下一个阶段的输入。前端读者可以直接套用数组链式调用的心智模型：

| 管道阶段 | 数组方法 | 作用 |
|---|---|---|
| `$match` | `filter` | 过滤文档 |
| `$project` / `$addFields` | `map` | 改变字段形状 |
| `$group` | `reduce` | 按 key 折叠并累加 |
| `$sort` | `sort` | 排序 |
| `$limit` / `$skip` | `slice` | 截取 |
| `$unwind` | `flatMap` | 把数组展开成多条文档 |

```javascript
db.orders.aggregate([
  { $match: { status: "paid", createdAt: { $gte: ISODate("2026-01-01") } } },
  { $group: { _id: "$userId", total: { $sum: "$totalCent" }, cnt: { $sum: 1 } } },
  { $sort: { total: -1 } },
  { $limit: 10 },
  { $project: { _id: 0, userId: "$_id", totalYuan: { $divide: ["$total", 100] }, cnt: 1 } },
])
```

三条规则决定聚合快不快：

- **`$match` 必须放最前面。** 只有位于管道开头的 `$match` 能用上索引，一旦前面有了 `$group` 或 `$project`，后面的 `$match` 就只能在内存里过滤。
- **`$sort` 尽量紧跟能用索引的 `$match`**，否则要做内存排序（超过 100MB 会报错，需要 `allowDiskUse: true`）。
- **`$project` 放在需要它的位置**，早点裁掉不用的大字段能显著减少内存占用。

`$group` 的 `_id` 就是分组键，写 `null` 表示全局聚合。常用累加器：`$sum` / `$avg` / `$max` / `$min` / `$push`（收集成数组）/ `$first` / `$last`（依赖前面的 `$sort`）/ `$addToSet`。

### $lookup 和它为什么比 JOIN 弱

```javascript
db.orders.aggregate([
  { $match: { status: "paid" } },
  { $lookup: {
      from: "users",           // 要关联的集合
      localField: "userId",
      foreignField: "_id",
      as: "user",              // 结果总是一个数组
  }},
  { $unwind: "$user" },        // 一对一时展开成对象，否则后面要处理 user[0]
  { $project: { totalCent: 1, "user.name": 1 } },
])
```

三个必须知道的限制：

| 限制 | 影响 |
|---|---|
| 结果是数组 | 一对一关联也要配 `$unwind` 或 `$arrayElemAt` 才能当对象用 |
| 执行方式接近嵌套循环 | 被关联集合的 `foreignField` **必须有索引**，否则每个文档都触发一次集合扫描 |
| 优化能力弱 | 没有 SQL 那样的连接顺序重排、hash join、条件下推。关联 + 排序 + 分页组合起来经常慢到不可用 |

结论：**`$lookup` 适合报表和后台的低频查询，不适合高 QPS 接口。** 如果你发现主要业务查询都要靠 `$lookup` 才能完成，说明这份数据的形状本质是关系型的，选错了数据库。合理的替代是适度冗余（把用到的几个字段内嵌一份）——用一致性维护成本换查询性能，这个交换在文档模型里是常态而不是妥协。

### $unwind 与 $facet

```javascript
// 统计每个标签下的文章数：先把 tags 数组展开成多条文档，再分组
db.articles.aggregate([
  { $unwind: "$tags" },
  { $group: { _id: "$tags", cnt: { $sum: 1 } } },
  { $sort: { cnt: -1 } },
])
```

`$facet` 让一次查询产出多组互不相干的统计，省掉多次往返——列表页同时要"数据 + 总数 + 侧边栏筛选项"时特别合适：

```javascript
db.articles.aggregate([
  { $match: { status: "published" } },
  { $facet: {
      page:      [{ $sort: { createdAt: -1 } }, { $skip: 0 }, { $limit: 20 }],
      total:     [{ $count: "value" }],
      byCategory:[{ $group: { _id: "$categoryId", cnt: { $sum: 1 } } }],
  }},
])
```

> ⚠️ `$facet` 里的每个分支都在**同一份 `$match` 结果**上重新跑一遍，分支越多内存占用越高，而且分支内部用不上索引。它省的是网络往返，不是计算量。

### 实战：按时间维度聚合

```javascript
// 按天统计 GMV 和订单数，用 $dateToString 把时间截断到天
db.orders.aggregate([
  { $match: { status: "paid", createdAt: { $gte: ISODate("2026-08-01") } } },
  { $group: {
      _id: { $dateToString: { format: "%Y-%m-%d", date: "$createdAt", timezone: "Asia/Shanghai" } },
      gmv: { $sum: "$totalCent" },
      cnt: { $sum: 1 },
  }},
  { $sort: { _id: 1 } },
])
```

`timezone` 一定要显式写。不写就按 UTC 切分，凌晨 8 点之前的订单会被算到前一天——这是所有"按天统计"报表的共同陷阱，和 MySQL 那边的时区问题同源。

### 实战：分组取 Top N

每个品类里销量最高的 3 个商品：

```javascript
db.products.aggregate([
  { $sort: { categoryId: 1, sales: -1 } },
  { $group: { _id: "$categoryId", top: { $push: { name: "$name", sales: "$sales" } } } },
  { $project: { top: { $slice: ["$top", 3] } } },
])
```

思路是先排好序，`$push` 会保持顺序，再用 `$slice` 截前三个。MongoDB 5.0 起可以直接用 `$topN` 累加器（`{ $topN: { output: [...], sortBy: { sales: -1 }, n: 3 } }`）更省内存，因为它不需要把整个分组都 `$push` 出来。

---

## 索引

索引概念和 MySQL 基本一致——B 树、最左前缀、区分度——但有几种 MySQL 没有的类型很实用。

```javascript
db.articles.createIndex({ authorId: 1, createdAt: -1 })              // 复合索引，1 升 -1 降
db.users.createIndex({ email: 1 }, { unique: true })                 // 唯一索引
db.users.createIndex({ inviteCode: 1 }, { unique: true, sparse: true })  // 稀疏：跳过没有该字段的文档
db.users.createIndex(                                                // 部分索引：比 sparse 更灵活
  { phone: 1 },
  { unique: true, partialFilterExpression: { deletedAt: null } },     // 只对未删除的用户约束唯一
)
db.logs.createIndex({ createdAt: 1 }, { expireAfterSeconds: 604800 })   // TTL：7 天后自动删
db.articles.createIndex({ title: "text", content: "text" })          // 全文索引
```

| 类型 | 用途 | 注意 |
|---|---|---|
| 单字段 / 复合 | 同 MySQL，`{a:1,b:1}` 能支撑 `a`、`a+b`，不能只支撑 `b` | 排序方向也参与匹配，`{a:1,b:-1}` 和 `ORDER BY a ASC, b DESC` 才对得上 |
| 唯一 | 约束 + 索引 | 已有重复数据时建不上；`null` 也算一个值，所以多个"没填"的文档会互相冲突 |
| 稀疏 sparse | 跳过不含该字段的文档，让唯一约束只作用于填了值的文档 | 新代码优先用 partial index，语义更明确 |
| TTL | 到期自动删除 | 见下 |
| 文本 | `$text: { $search: "关键词" }` | **一个集合只能有一个文本索引**；中文分词效果很弱，认真做搜索要上 Elasticsearch |
| 多键 multikey | 数组字段自动生成，支撑 `tags: "ux"` 这类查询 | 不能对两个数组字段建同一个复合索引 |

复合索引的字段顺序有个比 MySQL 更好记的口诀 **ESR**：等值（Equality）的字段在前，排序（Sort）的字段在中间，范围（Range）的字段在最后。原因和 MySQL 的"范围之后失效"完全一样。

### TTL 索引

```javascript
// 验证码集合：写入 5 分钟后自动消失，不需要定时任务
db.verify_codes.createIndex({ createdAt: 1 }, { expireAfterSeconds: 300 })
```

TTL 是 MongoDB 最省事的功能之一，日志、验证码、临时会话、导出任务的中间结果都适合。三个细节：字段必须是**日期类型**（存字符串或数字不会生效，也不报错）；后台线程**每 60 秒**扫一次，所以删除有最多一分钟延迟，不能用它做精确到秒的过期判断；只能建在单个字段上。

需要每个文档有不同的过期时间时，把 `expireAfterSeconds` 设为 0，然后在文档里存一个"应当过期的时刻"字段——到点即删。

> ⚠️ 短生命周期、要求毫秒级过期精度的数据（登录 token、限流计数器、分布式锁）不该用 TTL 索引，Redis 的过期机制才是对的工具，见 [Redis 深入](/guide/redis-deep)。

### 读执行计划

```javascript
db.articles.find({ authorId: 12 }).sort({ createdAt: -1 }).explain("executionStats")
```

只看四个数字，就能判断一个查询好不好：

| 字段 | 好的样子 |
|---|---|
| `winningPlan.stage` | `IXSCAN`（走索引）。出现 `COLLSCAN` 就是全集合扫描 |
| `totalKeysExamined` | 扫了多少索引项 |
| `totalDocsExamined` | 扫了多少文档。**它和 `nReturned` 的比值接近 1 才算健康**，10 倍以上说明索引选择性太差 |
| `executionStages` 里的 `SORT` | 出现 `SORT` 阶段就等于 MySQL 的 `Using filesort`，说明排序没走索引 |

`totalDocsExamined` 为 0 而 `nReturned` 大于 0，意味着覆盖索引生效了（`PROJECTION_COVERED`）——所有需要的字段都在索引里，没回文档。判断逻辑和 MySQL 的覆盖索引完全一样。

---

## Mongoose 在做什么

MongoDB 本身不管你存什么形状的文档。Mongoose 的全部价值就是**在应用层补上数据库放弃的那一层约束**：schema 定义、类型转换、校验、默认值、钩子。前端类比是给一个 `any` 的接口套上 zod——数据库那头没变，但代码这头有了类型和校验。

```typescript
import { Schema, model, Types } from 'mongoose'

const ArticleSchema = new Schema({
  title:   { type: String, required: true, trim: true, maxlength: 200 },
  slug:    { type: String, required: true, unique: true },
  status:  { type: String, enum: ['draft', 'published', 'archived'], default: 'draft' },
  views:   { type: Number, default: 0, min: 0 },
  tags:    [{ type: String }],
  authorId:{ type: Types.ObjectId, ref: 'User', required: true, index: true },
  meta:    { type: Schema.Types.Mixed },          // 明确不校验的自由字段
  email:   {
    type: String,
    validate: { validator: (v: string) => /.+@.+\..+/.test(v), message: '邮箱格式不对' },
  },
}, {
  timestamps: true,        // 自动维护 createdAt / updatedAt
  versionKey: false,       // 不要 __v 字段
})

export const Article = model('Article', ArticleSchema)
```

> ⚠️ `unique: true` **不是校验规则**，它只是声明要建一个唯一索引。重复插入时抛出的是 MongoDB 的 `E11000 duplicate key error`（错误码 11000），不是 Mongoose 的 `ValidationError`——错误处理里两者要分别捕获。而且索引是异步建的，生产环境应该用迁移脚本显式建索引并关掉 `autoIndex`，否则启动时可能悄悄失败。

### ref 和 populate

```typescript
const article = await Article.findById(id).populate('authorId', 'name avatar')
// article.authorId 从 ObjectId 变成了 { _id, name, avatar }
```

**`populate` 不是数据库 JOIN，是应用层的多次查询。** Mongoose 先查文章，取出所有 `authorId`，再发一条 `User.find({ _id: { $in: [...] } })`，最后在 Node 内存里把结果拼回去。

| | `populate` | `$lookup` | SQL `JOIN` |
|---|---|---|---|
| 执行位置 | 应用层，多次往返 | 数据库内，单次往返 | 数据库内，单次往返 |
| 能否按关联表字段过滤 / 排序 | ❌ 只能拿回来后自己过滤 | 可以，但写起来复杂 | ✅ 原生支持 |
| 请求数 | 每个 populate 路径 1 条额外查询 | 1 条 | 1 条 |

所以嵌套 populate（`populate({ path: 'comments', populate: 'author' })`）会成倍放大查询次数，列表接口上一不小心就是几十条查询。三条纪律：**只 populate 真正要展示的字段**（第二个参数一定要写）、**列表接口尽量不 populate**（改成适度冗余，把作者名直接内嵌）、**需要按关联字段过滤或排序时用 `$lookup` 或重新建模**。

### 虚拟字段、toJSON 与钩子

```typescript
ArticleSchema.virtual('excerpt').get(function () {
  return this.content?.slice(0, 100) ?? ''      // 不存进数据库，读的时候算
})

ArticleSchema.set('toJSON', {
  virtuals: true,                                // 序列化时带上虚拟字段
  transform: (_doc, ret) => {
    ret.id = ret._id                             // 给前端 id 而不是 _id
    delete ret._id
    delete ret.__v
    return ret
  },
})

// 钩子：保存前自动做点什么
UserSchema.pre('save', async function (next) {
  if (!this.isModified('password')) return next()          // 只有密码变了才重新哈希
  this.password = await bcrypt.hash(this.password, 10)
  next()
})
```

> ⚠️ `pre('save')` **只在 `doc.save()` 和 `Model.create()` 时触发**，`findOneAndUpdate`、`updateOne`、`updateMany` 走的是另一套查询中间件，完全不经过它。用 `User.updateOne({ _id }, { password: '明文' })` 改密码，会把明文直接写进数据库——这是 Mongoose 最经典的安全事故。要么统一走 `save()`，要么额外给 `pre('findOneAndUpdate')` 也挂一个钩子。

### lean() 为什么能显著提速

```typescript
const docs = await Article.find({ status: 'published' }).lean()   // 返回普通对象
```

默认情况下 Mongoose 会把每条结果**实例化成一个 Document 对象**：附加 getter/setter、变更追踪（用于 `isModified` 和增量更新）、虚拟字段、实例方法。这层包装在返回上千条数据时开销很明显，内存和耗时都可能差好几倍。

`lean()` 跳过实例化，直接给 MongoDB 驱动返回的 POJO。代价是没有虚拟字段、没有 getter、没有实例方法、不能 `save()`。判断很简单：**只读的查询（列表、导出、给前端返 JSON）一律加 `lean()`；要改数据再保存的才用完整 Document。**

---

## 在 Nest 里集成

```typescript
// app.module.ts —— 连接串走配置，不要硬编码
@Module({
  imports: [
    MongooseModule.forRootAsync({
      inject: [ConfigService],
      useFactory: (config: ConfigService) => ({
        uri: config.get<string>('MONGO_URI'),
        autoIndex: config.get('NODE_ENV') !== 'production',
      }),
    }),
    ArticleModule,
  ],
})
export class AppModule {}
```

Schema 可以用装饰器写，和 Entity 的风格一致：

```typescript
@Schema({ timestamps: true, versionKey: false })
export class Article {
  @Prop({ required: true, trim: true, maxlength: 200 })
  title: string

  @Prop({ required: true, unique: true })
  slug: string

  @Prop({ type: String, enum: ArticleStatus, default: ArticleStatus.Draft })
  status: ArticleStatus

  @Prop({ type: [String], default: [] })
  tags: string[]

  @Prop({ type: Types.ObjectId, ref: 'User', required: true, index: true })
  authorId: Types.ObjectId
}

export type ArticleDocument = HydratedDocument<Article>
export const ArticleSchema = SchemaFactory.createForClass(Article)
ArticleSchema.index({ authorId: 1, createdAt: -1 })     // 复合索引在这里补
```

装饰器写法的好处是类型和 schema 只写一份，坏处是遇到复杂配置（自定义 validator、钩子、discriminator）还是要回到 `ArticleSchema` 上手动挂。**枚举、数组、嵌套对象的 `type` 一定要显式写**，因为 TypeScript 的类型信息在运行时拿不到完整结构。

注册与注入：

```typescript
@Module({
  imports: [MongooseModule.forFeature([{ name: Article.name, schema: ArticleSchema }])],
  providers: [ArticleService],
})
export class ArticleModule {}

@Injectable()
export class ArticleService {
  constructor(@InjectModel(Article.name) private readonly articleModel: Model<Article>) {}

  findPublished(page: number) {
    return this.articleModel
      .find({ status: ArticleStatus.Published })
      .select('title slug createdAt')            // 只取要用的字段
      .sort({ createdAt: -1 })
      .skip((page - 1) * 20).limit(20)
      .lean()                                    // 只读查询一律加
      .exec()
  }
}
```

`forFeature` 在当前模块注册 model 并提供注入 token，机制和 TypeORM 的 `forFeature` 一致，本质是动态模块（见 [动态模块与配置管理](/guide/nestjs-dynamic-module)）。

### 事务与 session

跨集合的写操作要保证一起成功，得显式开 session：

```typescript
@Injectable()
export class OrderService {
  constructor(
    @InjectConnection() private readonly connection: Connection,
    @InjectModel(Order.name) private readonly orderModel: Model<Order>,
    @InjectModel(Stock.name) private readonly stockModel: Model<Stock>,
  ) {}

  async create(dto: CreateOrderDto) {
    const session = await this.connection.startSession()
    try {
      // withTransaction 会在可重试错误（如写冲突）时自动重试整个回调
      return await session.withTransaction(async () => {
        const updated = await this.stockModel.updateOne(
          { productId: dto.productId, qty: { $gte: dto.qty } },
          { $inc: { qty: -dto.qty } },
          { session },                       // ⚠️ 每一个操作都必须带上 session
        )
        if (updated.modifiedCount === 0) throw new ConflictException('库存不足')

        const [order] = await this.orderModel.create([dto], { session })
        return order
      })
    } finally {
      await session.endSession()
    }
  }
}
```

三个坑：**漏传 `session` 的操作不在事务里**（而且不报错，只是静默地不回滚）；**事务要求副本集部署**，本地单机 mongod 会直接报 `Transaction numbers are only allowed on a replica set member`，开发环境需要起单节点副本集；**默认 60 秒上限**，长事务会被强制中止。

更根本的建议是**先想想能不能不用事务**。上面这个例子里 `updateOne` 带条件 `qty: { $gte: dto.qty }` 本身就是原子的，配合幂等键写订单，很多场景不需要事务也能保证正确——这和 MySQL 那边"条件更新 + 唯一约束"的思路是同一个（见 [并发、事务与一致性](/guide/concurrency-transaction)）。**需要频繁开事务，往往是建模时该嵌套的数据被拆开了。**

---

## 四种存储的定位

| | 擅长 | 不擅长 | 典型用途 |
|---|---|---|---|
| MySQL | 强一致、复杂关联查询、事务、精确约束 | 无固定结构的数据、水平扩展 | 订单、账务、用户、权限 |
| MongoDB | 结构灵活、整块读写、内建分片 | 跨文档事务、多表关联、复杂报表 | 日志、消息、CMS 内容、AI 会话记录 |
| Redis | 亚毫秒读写、过期、计数、排行榜、分布式锁 | 持久化保证弱、不适合当主存储、不能复杂查询 | 缓存、会话、限流、队列、排行榜 |
| Elasticsearch | 全文检索、分词、相关性排序、聚合分析 | 强一致、事务、频繁单条更新 | 站内搜索、日志检索、RAG 的关键词召回 |

四者的关系不是替代而是分工：**MySQL 存事实，MongoDB 存形状不定的事实，Redis 存热的和临时的，Elasticsearch 存"用来被搜到"的副本。** 同一份数据出现在多个系统里是正常的，代价是要设计好同步链路——通常靠消息队列做异步同步（见 [消息队列](/guide/message-queue)）。

回到开头那个问题：什么时候不用关系型？当这份数据**没有强约束、不需要跨实体事务、查询是整块读取而不是多维关联、且结构会持续演化**的时候。四个条件同时成立，MongoDB 是更省力的选择；只满足一两个，用 MySQL 加一个 JSON 列往往更划算。

---

## 面试问答

**1. 什么时候选 MongoDB，什么时候留在 MySQL？**

- 判断标准不是"哪个更先进"，而是这份数据：有没有强约束、要不要跨实体事务、查询是整块读还是多维关联、结构是否持续演化。
- 适合 MongoDB 的：日志埋点、聊天消息、CMS 内容、AI 会话历史这类整块读写、结构随版本变的数据；不适合的：订单支付、库存余额、用户权限这类要强事务和复杂关联的主数据。
- 现实中最常见的组合是两个都用：交易数据在 MySQL，日志、消息、非结构化内容在 MongoDB。
- 加分：四个条件只满足一两个时，MySQL 加一个 JSON 列往往比引入一个新存储更划算。

**2. 文档建模时，嵌套还是引用怎么判断？**

- 核心差异：关系型按"数据是什么"建模，文档型按"数据怎么被读"建模。
- 一对少且总跟父文档一起读就嵌套；子项要独立查询分页、数量无上限增长、被多个父文档共享、更新比父文档频繁，就引用。
- 16MB 是硬边界：子项数量没有明确上界就不要嵌套；即使没到上限，经验值也是单文档控制在几十 KB、数组几百个以内，超了就拆。
- 别踩的坑：把关注列表嵌进用户文档——大 V 五百万粉丝直接撞 16MB；多对多且双向查询的关系，老老实实用独立集合，两个方向各建一个索引。

**3. MongoDB 的事务为什么不能当 MySQL 事务用？**

- 跨文档事务 4.0 才支持，要求副本集部署（本地单机 mongod 直接报错），默认 60 秒时长上限，性能也不如 MySQL 的事务。
- 事务里每个操作必须带 session，漏传不报错，只是静默地不回滚。
- 更根本的思路是先想想能不能不用事务：单文档更新永远原子，`$inc`、`$addToSet` 不需要事务也不会丢；需要频繁开事务，往往是建模时该嵌套的数据被拆开了。
- 加分：扣库存的 `updateOne` 带上 `qty: { $gte: dto.qty }` 条件本身就是原子的，配合幂等键写订单，很多场景不开事务也正确。

**4. populate 和 $lookup 有什么区别？**

- populate 不是数据库 JOIN，是应用层的多次查询：先查主文档，再按外键发一条 `find({ _id: { $in: [...] } })`，在 Node 内存里拼回去，每个 populate 路径多一次往返。
- $lookup 在数据库内单次往返，但执行方式接近嵌套循环，foreignField 必须有索引，优化能力远不如 SQL 的 JOIN。
- 结论一致：都适合报表和后台的低频查询，不适合高 QPS 接口；列表接口改成适度冗余，把要展示的几个字段内嵌一份。
- 别踩的坑：嵌套 populate 会成倍放大查询次数，列表接口一不小心就是几十条查询。

**5. Mongoose 有哪些最容易踩的坑？**

- `unique: true` 不是校验规则，只是声明唯一索引：重复插入抛的是 MongoDB 的 E11000 而不是 ValidationError，错误处理要分开捕获；索引是异步建的，生产环境要关 autoIndex、用迁移脚本显式建。
- `pre('save')` 只在 save()/create() 时触发，用 `updateOne` 改密码会把明文直接写进数据库——要么统一走 save()，要么给 `pre('findOneAndUpdate')` 也挂钩子。
- 只读查询（列表、导出、给前端返 JSON）一律加 `lean()`：默认会把每条结果实例化成 Document，上千条数据时内存和耗时都可能差好几倍。
- 加分：说得出 lean() 的代价——没有虚拟字段、getter、实例方法，不能 save()，要改数据再保存的场景不能用。







