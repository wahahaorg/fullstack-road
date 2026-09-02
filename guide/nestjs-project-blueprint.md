# 项目架构蓝图：四类系统怎么搭

> 不是第五个 CRUD 教程。四类典型系统的架构决策——需求里出现什么信号就该选什么技术、难点在哪、坑在哪，以及文末两张能直接拿去对照新需求的表。

## 怎么读这一篇

写过几个项目之后会发现，难的从来不是写 controller，而是**看到需求的第一天就判断出该用什么**。判断错了，后面所有代码都在为一个错误的选择打补丁。

所以这篇按「系统类型」而不是「技术栈」组织，每类系统统一写四段：需求特征与选型 → 数据模型要点 → 一到两个真正的难点及解法 → 这类系统的坑。四类系统覆盖了后端最常见的四种难点：**并发抢占、结构化数据建模、长连接与状态、检索与双写一致**。

具体的框架用法不在这里重复，都链到对应篇目。

---

## 预订类系统：难点只有一个，并发抢占

会议室、酒店房间、门票、诊所号源、球场时段是同一套模型：**有限资源 × 时间段**。

### 需求特征与选型

| 需求特征 | 选型与理由 |
|---|---|
| 资源可枚举、量小（几十到几千），冲突必须硬拒绝 | **单体** Nest + MySQL + TypeORM：强关系、强一致，唯一约束和事务是免费的正确性保障（见 [TypeORM 集成](/guide/nestjs-database)） |
| 占用单位是「资源 + 时间段」，唯一性不是单列 | 这是全类系统最麻烦的一点，下面单独讲 |
| 读多写少，但写必须准 | Redis 只缓存展示数据、做通知节流，**绝不承担「是否可订」的判断** |
| 四个模块（用户 / 资源 / 预订 / 统计）耦合紧、一起发布 | 拆微服务纯亏，模块化单体就够 |
| 带审批流、管理端要报表 | 状态机 + 定时预聚合（见[定时任务与事件](/guide/nestjs-schedule-events)） |

### 数据模型要点

第一个决策比建表更重要：**时间段是自由区间，还是固定格子？**

| | 固定格子（按 30 分钟切片） | 自由区间（start / end 任意） |
|---|---|---|
| 存储 | 一行 = 一个格子，跨两小时的预订写 4 行 | 一行 = 一次预订 |
| 防并发 | `UNIQUE(resource_id, slot_start)`，数据库替你拒绝 | **没有任何单列唯一索引能表达「区间不重叠」**，只能靠锁 |
| 查可用 | 一次 `IN` 就知道哪些格子被占 | 每个候选区间都要做一次重叠判断 |

会议室、球场、号源天然就是格子，**能接受固定粒度就选格子**——它把最难的并发问题下沉给了数据库。只有酒店（按天）、租车（按分钟计费）这种真正连续的场景才值得用自由区间。

```sql
resource(id, name, capacity, location, status)
booking(id, resource_id, user_id, start_at, end_at, status, note)
booking_slot(booking_id, resource_id, slot_start, UNIQUE KEY uk_slot (resource_id, slot_start))
```

两个别犯的错：**不要在 `resource` 上放 `is_booked` 布尔字段**，它表达不了「什么时候被占」，一定会和 `booking` 打架，占用状态只该由预订记录推导；**`status` 用 tinyint 加 TS 枚举**，别存中文字符串，改文案就得刷数据。

### 难点一：两个人同时订同一时段

「先查有没有冲突，没有就插入」在单线程里对，在并发下错——两个请求同时查、同时都发现没冲突、同时都插进去。

| 方案 | 怎么做 | 正确性 | 代价 |
|---|---|---|---|
| 悲观锁 | 事务里 `SELECT ... FOR UPDATE` 查冲突，再插 | 对，但依赖 gap lock 锁住「还不存在的行」，和隔离级别绑定 | 锁的持有期跨越整段业务逻辑，热门资源上排队 |
| 乐观锁 | `resource` 上加 `version`，`UPDATE ... WHERE version = :v`，`affectedRows = 0` 就重试 | 对，但要求所有冲突都更新同一行，等于给整个资源串行化 | 冲突多时重试风暴，不相关的时段也互相阻塞 |
| **唯一索引兜底** | 「资源 + 格子」做成唯一键，直接 INSERT，捕重复键错误 | 最强：由数据库保证，不依赖隔离级别，也不依赖谁记得加锁 | 必须是固定格子；跨格子预订在一个事务里插 N 行，任一行冲突整笔回滚 |

默认选第三种，它的核心优势是**正确性不依赖代码路径**——将来有人加了个新入口忘了加锁，数据库照样拦得住。

```typescript
async create(dto: CreateBookingDto) {
  const slots = splitIntoSlots(dto.startAt, dto.endAt)     // 30 分钟一格
  try {
    return await this.dataSource.transaction(async (m) => {
      const booking = await m.save(Booking, { ...dto, status: BookingStatus.Pending })
      await m.insert(BookingSlot, slots.map((slotStart) => ({
        bookingId: booking.id, resourceId: dto.resourceId, slotStart,
      })))
      return booking
    })
  } catch (e) {
    // mysql2 的重复键是 ER_DUP_ENTRY（errno 1062）；Prisma 抛 P2002
    if ((e as { code?: string })?.code === 'ER_DUP_ENTRY') {
      throw new ConflictException('所选时段已被占用，请刷新后重选')
    }
    throw e
  }
}
```

> ⚠️ 用唯一索引拦并发有个前提：**冲突必须是真冲突**。被驳回、已取消的预订不该继续占格子，所以取消时要删掉对应的 `booking_slot` 行，而不是只改 `booking.status`。锁与事务的原理见[并发与事务](/guide/concurrency-transaction)。

### 难点二：时间段重叠的 SQL

自由区间下重叠判断要自己写，而这是整类系统最容易写错的一行：

```sql
SELECT 1 FROM booking
WHERE resource_id = :rid
  AND status IN (0, 1)        -- 已驳回、已解除的不算占用
  AND start_at < :new_end     -- 严格小于，不是 <=
  AND end_at   > :new_start
LIMIT 1;
```

**两个区间相交 ⟺ A.start < B.end 且 A.end > B.start。** 就这一条，没有别的等价写法。

| 错误写法 | 漏掉什么 |
|---|---|
| `start_at >= :s AND end_at <= :e` | 只查到被新区间完全包住的，漏掉部分重叠和反向包含 |
| `start_at <= :s AND end_at >= :e` | 只查到完全包住新区间的——最常见的错，因为手工测试时看着是对的 |
| `start_at BETWEEN :s AND :e` | 漏掉开始时间在窗口之前、结束时间伸进窗口的那些 |

用严格 `<` 是因为「上一场 10:00 结束、下一场 10:00 开始」不算冲突，区间语义是左闭右开。另外三件事必须一起做：`status` 参与过滤（不然驳回的预订永远占坑）；插入前校验 `start_at < end_at`（一条 end 早于 start 的脏数据能穿过所有重叠检查）；索引建 `(resource_id, start_at)`，`end_at > :start` 那一半只能回表过滤，量大了就该换格子表。执行计划怎么读见 [MySQL 进阶](/guide/mysql-advanced)。

### 审批流与报表

状态流转写成**带前置条件的 UPDATE**，而不是「读出来、判断、存回去」：`UPDATE booking SET status = :next WHERE id = :id AND status = :expected`。`affectedRows = 0` 就说明状态已被别人改过，返回 409 而不是覆盖。再配一张合法转移表集中声明规则（`Pending → Approved | Rejected | Cancelled`，`Approved → Released`，其余是终态）。这一条同时解决了状态机和并发——两个管理员同时点「通过」和「驳回」，只有一个会生效。支付、工单、订单履约都是同一套写法。

报表不要实时 `GROUP BY`。管理端的「按月 × 按部门 × 按资源」交叉查询要扫全表加排序，随数据线性变慢，而它是天天刷的页面。定时任务每天把昨天的数据打成 `booking_daily_stat(stat_date, resource_id, dept_id, booking_count, used_minutes)`，报表只查这张宽表，当天数据实时算再 union 上去。任务要幂等（按 `stat_date` 先删后插或 upsert），多实例下要加分布式锁。

### 这类系统的坑

| 坑 | 后果 | 对策 |
|---|---|---|
| 用 `is_booked` 布尔表达占用 | 表达不了时间维度，双写必然不一致 | 占用只由预订记录推导 |
| 外键 `RESTRICT` 撞上「资源要能删」 | 删资源直接报错 | 资源软删（`deleted_at`），历史预订保留 |
| 列表接口 join 出 user 实体 | 密码等敏感字段泄露 | DTO 白名单序列化，见 [DTO 与序列化](/guide/nestjs-dto) |
| 前端先选时段、提交后才被拒 | 体验差、无效请求多 | 提供「可用格子」接口让前端只能选空位，服务端仍要兜底 |
| 时间用本地字符串传 | 跨时区错位 | 一律 UTC 时间戳或带 offset 的 ISO 串 |
| 提醒 / 催办邮件不节流 | 点十次发十封 | Redis `SET key NX EX` 做时间窗口 |

---

## 考试答题类系统：拆服务与 JSON schema

出题、答卷、判卷、分析。这是四类里唯一一个**值得考虑拆服务**的，理由不是代码整洁，是负载画像。

### 为什么这个场景适合拆

| 模块 | 读写特征 | 峰值形态 | 迭代节奏 |
|---|---|---|---|
| 出题 | 编辑器保存，写少读少 | 平稳 | 最高：题型天天加 |
| 答卷 | 写密集 | **考试开始那一瞬间的尖峰** | 低 |
| 判卷 | 吃 CPU，主观题要调模型 | 跟着交卷走 | 中 |
| 分析 | 重查询、多维聚合 | 考后集中 | 中 |

拆分的真实理由是两条：**答卷的尖峰不能影响出题的可用性，判卷的算力不能和 Web 进程抢 CPU。** 判卷如果只是比对字符串，就别单独拆；一旦主观题要走模型，它就必须是独立服务（Python + GPU），这时候拆是被技术栈逼的，不是选的。拆的方式、共享代码怎么放、通信用什么，见[微服务与跨语言通信](/guide/nestjs-microservice)。

反过来说个实话：很多号称微服务的考试系统，服务之间从来没真正调用过——那说明它其实只需要模块化单体，白付了分布式的成本。

### 数据模型要点：题目该不该拆表

这是全篇最值得想清楚的一个建模决策。题型会一直加——单选、多选、判断、填空、排序、连线、代码题、附件题——每种题型的字段都不一样。

| | 每种题型一张表 | 一张 `question` 表 + JSON 字段 |
|---|---|---|
| 加新题型 | 建表、写实体、改 controller、改前端 | 只改前端编辑器和一份 schema |
| 查一张试卷的所有题 | N 次查询或 N 路 union | 一次查询 |
| 数据库能校验字段 | 能 | 不能，得在应用层校验 |
| 按题干搜索 | 直接 SQL | JSON 函数，或另存一份纯文本冗余列 |

**选 JSON。** 题目的结构是「业务上会持续变化、但数据库从不按它的内部字段查询」的典型——这正是 JSON 列的适用场景。MySQL 8 的 `JSON` 类型、Postgres 的 `jsonb` 都够用，MongoDB 也是天然选择（见 [MongoDB 与 Mongoose](/guide/mongodb-mongoose)）。

```sql
paper(id, title, owner_id, total_score, duration_min, status, content JSON, version, deleted_at)
answer_sheet(id, paper_id, paper_version, user_id, content JSON, score, status, submitted_at)
```

代价要认下来：**数据库不再替你把关，schema 必须在应用层强制。** 用 TS 判别联合类型 + class-validator 的 `@ValidateNested` 按 `type` 分派校验，写入前一律过一遍（见[参数校验与异常处理](/guide/nestjs-validation-filter)）。

```typescript
type Question =
  | { id: string; type: 'single'; score: number; stem: string; options: string[]; answer: number }
  | { id: string; type: 'multiple'; score: number; stem: string; options: string[]; answer: number[] }
  | { id: string; type: 'blank'; score: number; stem: string; answers: string[]; ignoreCase: boolean }
  | { id: string; type: 'essay'; score: number; stem: string; rubric?: string }
```

两个细节现在不做以后一定后悔：**每道题要有稳定的 `id`**（用 nanoid，不要用数组下标——插入一道题就把所有答卷的对应关系错开了）；**正确答案不能跟着题目一起下发**。答题接口返回的必须是剥掉 `answer` / `answers` / `rubric` 的投影，别指望前端不看网络面板。

### 难点一：试卷改了，已交的卷子按哪版判

老师在考试期间修改了试卷，这是必然会发生的事。答案是**快照**：交卷时把当时的题目结构连同答案一起写进 `answer_sheet.content`，同时记下 `paper_version`。判卷只认快照，永不回头读 `paper` 表。

`paper` 每次保存 `version + 1`；正在进行的考试用「开考时锁定版本」而不是「禁止修改试卷」——后者会被老师绕过（复制一份新试卷），前者才是真约束。

### 难点二：自动判卷

客观题判卷是纯函数，**必须写成不依赖数据库和框架的纯函数**，这样才能单测覆盖到每种题型的边界（见 [nestjs-advanced 的测试一节](/guide/nestjs-advanced)）。

| 题型 | 判分规则里的坑 |
|---|---|
| 单选 / 判断 | 未作答和答错要区分——统计要用 |
| 多选 | 全对给满分、漏选给一半、错选给零，这条规则必须可配置，学校之间不一样 |
| 填空 | 要不要忽略大小写、要不要 trim、多个空是否有序、同义答案怎么配 |
| 排序 / 连线 | 部分正确怎么给分，比较前要归一化 |
| 主观题 | 走队列异步判，不能卡在交卷请求里 |

主观题是**唯一需要异步**的部分：交卷立刻返回客观题得分和「主观题待批」，把判卷任务丢进队列（见 [Worker 与异步任务](/guide/background-worker)）。调模型判卷要设超时和重试上限，失败落到人工队列而不是无限重试。

### 难点三：开考瞬间的写尖峰

一千人在同一秒点「开始答题」，然后每 30 秒自动保存一次草稿。

| 场景 | 别这么做 | 该这么做 |
|---|---|---|
| 自动保存草稿 | 每次都 `UPDATE` 数据库 | 写 Redis（`answer:{sheetId}` hash），交卷时才落库 |
| 交卷 | 同步判卷 + 同步写统计 | 落库 + 发事件，判卷和统计都异步 |
| 排行榜 | 每次查询实时 `ORDER BY score` | Redis ZSET 增量维护（见 [Redis 实战](/guide/redis-practice)） |
| 防重复交卷 | 靠前端禁用按钮 | `UNIQUE(paper_id, user_id)` + 条件 UPDATE |

草稿放 Redis 要接受「Redis 挂了草稿丢」这个风险——可以接受，因为草稿本来就不是承诺。但**交卷必须落库后才返回成功**，这条不能让。

### 这类系统的坑

| 坑 | 后果 | 对策 |
|---|---|---|
| 题目 `id` 用数组下标 | 改题就错位，历史答卷全废 | 稳定 id（nanoid） |
| 答题接口带出正确答案 | 打开控制台就能看答案 | 服务端做字段投影 |
| 判卷逻辑写在 service 里、依赖注入一堆东西 | 测不了，边界全靠上线验证 | 抽成纯函数 |
| 试卷直接硬删 | 历史答卷失去上下文 | 软删 + 回收站 |
| `duration_min` 由前端计时 | 改本地时间就能作弊 | 服务端记 `started_at`，交卷时校验 |
| 大题库 `SELECT *` 带 JSON 列做列表 | 一次查出几十 MB | 列表只查摘要列，JSON 按需取 |

---

## 聊天类系统：长连接与在线状态

私聊、群聊、好友申请、未读数。难点从「数据对不对」变成「连接和状态放哪」。

### 需求特征与选型

| 需求特征 | 选型与理由 |
|---|---|
| 服务端要主动推给客户端 | WebSocket（Socket.IO），不是轮询（见[实时通信](/guide/nestjs-realtime)） |
| 消息量大、结构简单、几乎只按会话+时间查 | MongoDB 或 MySQL 都行；**消息表要能按时间分片**，这是唯一硬要求 |
| 在线状态、未读数、最近会话列表 | Redis，这三样都不该落库 |
| 多实例部署 | Socket.IO Redis adapter，**否则跨实例的两个人收不到彼此的消息** |
| 图片、语音、文件 | 对象存储直传（见[文件上传](/guide/nestjs-file-upload)） |

### 数据模型要点

```sql
conversation(id, type, name, avatar, owner_id, last_message_id, last_active_at)
conversation_member(conversation_id, user_id, role, joined_at, last_read_message_id, muted,
                    PRIMARY KEY (conversation_id, user_id))
message(id, conversation_id, sender_id, type, content, client_msg_id, created_at,
        INDEX idx_conv_time (conversation_id, id))
```

四个决策：

**私聊也建 conversation。** 别为私聊单独设计一张 `direct_message` 表——群聊和私聊的读写路径完全一样，分两套等于所有功能写两遍。私聊就是 `type = 'direct'` 且成员固定两人的会话，用 `UNIQUE(小 uid, 大 uid)` 保证两人之间只有一个会话。

**未读数不存在 `message` 上，存 `last_read_message_id`。** 一条消息发到 500 人群里，如果给每人写一行 `message_read`，就是一次写扩散 500 倍。存「读到哪」，未读数 = 比这个 id 大的消息条数，Redis 缓存这个计数。

**消息 id 用有序 id（雪花 / ULID），不用 UUID v4。** 消息永远是「按会话取最近 N 条、再往前翻页」，有序 id 让分页变成 `WHERE conversation_id = ? AND id < ?cursor ORDER BY id DESC LIMIT 20`，走索引且稳定。用 `OFFSET` 分页在持续插入的表上会漏消息和重复。

**发送方要带 `client_msg_id`。** 弱网重发是常态，服务端靠它去重（`UNIQUE(sender_id, client_msg_id)`）；前端也靠它把「本地待发」的气泡换成服务端返回的真实消息。

### 难点一：状态放在内存里就完了

最容易写错的一版：在 Gateway 里用一个 `Map<userId, Socket>` 记谁在线。单实例能跑，扩到两个实例立刻废掉——A 连实例 1、B 连实例 2，A 发给 B 的消息在实例 1 的 Map 里找不到 B。

| 状态 | 放哪 | 怎么做 |
|---|---|---|
| 在线与否 | Redis | `SET online:{uid} {instanceId} EX 60`，客户端心跳续期，key 过期即离线 |
| 多端登录 | Redis Set | `SADD conn:{uid} {socketId}`，断开时 `SREM`，空集合才算离线 |
| 跨实例投递 | Socket.IO Redis adapter | 让 `io.to(room).emit()` 自动广播到所有实例 |
| 房间成员 | 不自己维护 | 连接时按 `conversation_member` 把 socket `join` 进各房间 |

在线状态**必须用 TTL 兜底**，不能只靠 `disconnect` 事件——进程被 kill、网线拔掉都不会触发它，那样用户会永远显示在线。

### 难点二：消息可靠性

WebSocket 的 `emit` 是「发出去就不管了」，不代表对方收到。要不要做确认取决于产品定位：

| 级别 | 做法 | 适用 |
|---|---|---|
| 不保证 | 直接 emit | 输入中、在线状态这类可丢的信号 |
| 落库 + 拉取补齐 | 消息先落库，客户端上线时按 `last_read_message_id` 拉增量 | **绝大多数 IM，推荐** |
| 逐条 ACK | 客户端回 ack，未 ack 的重推 | 强一致要求，复杂度高很多 |

第二种是性价比最高的：**推送只是「快」的手段，正确性由「落库 + 拉取」保证。** 推送丢了无所谓，客户端一上线就补齐了。

### 这类系统的坑

| 坑 | 后果 | 对策 |
|---|---|---|
| 用 `Map` 存连接 | 多实例互相看不见 | Redis + Socket.IO adapter |
| 只靠 `disconnect` 判离线 | 幽灵在线用户 | 心跳 + TTL |
| WebSocket 握手不鉴权 | 任何人可连、可加入任意房间 | 握手时校验 token，加房间前查成员表（见[请求生命周期](/guide/nestjs-pipeline)的 WS 上下文一节） |
| 群消息给每个成员写一行已读 | 写放大数百倍 | `last_read_message_id` |
| 消息分页用 `OFFSET` | 翻页时漏消息、重复 | 游标分页（`id < cursor`） |
| 消息表不分片 | 单表上亿后什么都慢 | 按会话或按月分表，冷数据归档 |
| HTTP 接口和 WS 两套鉴权逻辑 | 一边改了另一边忘 | 同一个 Guard 适配两种上下文 |

---

## 内容平台：检索与双写一致

博客、文档站、商品库、知识库是同一类：**内容为主，读远多于写，搜索是核心功能。**

### 需求特征与选型

| 需求特征 | 选型与理由 |
|---|---|
| 全文搜索、要分词、要相关性排序、要高亮 | Elasticsearch。**`LIKE '%关键词%'` 不是搜索**——不走索引、不分词、无相关性 |
| 内容本体要强一致（作者要能相信自己的草稿存住了） | MySQL 作为唯一真相源，ES 只是索引副本 |
| 读多写少，首页/详情页高频 | Redis 缓存 + CDN；缓存策略见 [Redis 实战](/guide/redis-practice) |
| 关联查询多（标签、分类、作者、评论） | 关系型 + 适度反范式 |
| 富文本、附件、封面图 | 对象存储，正文存 HTML 或 Markdown |

选型的分界线很清楚：**如果搜索只是「按标题模糊匹配」，MySQL 加个前缀索引就够，别上 ES**——运维一个 ES 集群的成本远超它带来的价值。需要分词、需要按相关性排序、需要搜正文，才值得。

### 数据模型要点

```sql
post(id, author_id, title, slug, summary, content, cover_url, status,
     published_at, view_count, INDEX idx_status_pub (status, published_at))
tag(id, name, slug)
post_tag(post_id, tag_id, PRIMARY KEY (post_id, tag_id))
comment(id, post_id, user_id, parent_id, content, status, created_at)
```

三个决策：**`slug` 做唯一索引**用于 SEO 友好的 URL，改标题不改 slug（改了旧链接就死）；**`view_count` 是冗余字段**，它的正确来源是 Redis 计数 + 定时回写（见[定时任务与事件驱动](/guide/nestjs-schedule-events)）；**评论用 `parent_id` 单层嵌套就够**，真做成无限层树，前端渲染和分页都会变成噩梦，微博/知乎的实际形态都是两层。

### 难点：MySQL 和 ES 的双写一致

写 MySQL 成功、写 ES 失败，搜索里就查不到这篇文章。这是所有「主库 + 索引副本」架构的通用问题。

| 方案 | 一致性 | 复杂度 | 说明 |
|---|---|---|---|
| 同一个事务里写两边 | 假的 | 低 | ES 不参与 MySQL 事务，回滚不了 |
| 写库后同步调 ES | 弱 | 低 | ES 抖动就丢索引，且拖慢写接口 |
| **写库后发事件 → 队列 → 消费者写 ES** | 最终一致 | 中 | **推荐**：写接口只依赖 MySQL，失败可重试 |
| 订阅 binlog（Canal / Debezium） | 最终一致 | 高 | 业务代码零侵入，适合多个下游都要同步 |

推荐第三种，并且必须配两条兜底：**消费者要幂等**（同一篇文章重复索引结果相同，用 `post.id` 作为 ES 文档 id，`index` 而不是 `create`）；**要有全量重建入口**（一个内部接口按 `updated_at` 分批重刷，ES 索引结构变更或消息丢失时靠它兜底）。

```typescript
@Injectable()
export class PostService {
  async publish(id: number, dto: PublishPostDto) {
    const post = await this.dataSource.transaction(async (m) => {
      await m.update(Post, id, { ...dto, status: PostStatus.Published, publishedAt: new Date() })
      return m.findOneByOrFail(Post, { id })
    })
    // 事务提交后再发事件——事务里发事件，回滚了消费者却已经读到了
    this.events.emit('post.published', { postId: post.id })
    return post
  }
}
```

> ⚠️ 发事件的时机必须在**事务提交之后**。事务内发事件是个高频错误：消费者可能在事务提交前就去查库，查到旧数据甚至查不到。

搜索接口本身要注意：查询词要做长度和字符限制（防深分页和恶意查询）、`from + size` 深分页在 ES 里同样有上限（超过 10000 要用 `search_after`）、搜索结果只返回 id + 高亮片段，正文回 MySQL 取或直接存 ES 但不参与 `_source` 返回。

### 这类系统的坑

| 坑 | 后果 | 对策 |
|---|---|---|
| 用 `LIKE '%kw%'` 当搜索 | 全表扫描，中文根本搜不准 | 小项目用 MySQL 全文索引，正经搜索上 ES |
| ES 当唯一数据源 | ES 挂了数据就没了 | ES 永远只是副本，可随时重建 |
| 事务内发事件 | 消费者读到未提交/已回滚的数据 | 提交后再发 |
| 详情页缓存不设过期也不主动失效 | 改了文章前台不变 | 更新时删 key + 兜底 TTL |
| 缓存 key 不带版本 | 结构改了读到旧格式反序列化炸 | key 里带版本号前缀 |
| 评论做无限层嵌套 | 分页与渲染复杂度爆炸 | 两层：主评论 + 回复 |
| 浏览量每次都 `UPDATE` | 热文章行锁争抢 | Redis `INCR` + 定时回写 |

---

## 通用决策：这些每个项目都要定

### 目录结构

```
src/
├── main.ts
├── app.module.ts
├── common/              # 跨模块的横切代码
│   ├── decorators/  filters/  guards/  interceptors/  pipes/
│   └── utils/
├── config/              # 配置定义与校验
├── database/
│   ├── entities/        # 或放各模块内，见下
│   └── migrations/
└── modules/
    ├── users/
    │   ├── users.module.ts
    │   ├── users.controller.ts
    │   ├── users.service.ts
    │   ├── dto/
    │   └── entities/
    └── posts/ ...
```

**按业务分模块，不要按技术层分目录。** 「所有 controller 一个目录、所有 service 一个目录」在改一个功能时要跳四个目录，而按业务分只动一个文件夹。这也是 Nest CLI `nest g resource` 的默认行为。

至于 `domain / application / infrastructure` 那种整洁架构分层：**大多数项目不需要**。它换来的是「业务逻辑不依赖框架和数据库」，代价是每个功能多写两层映射。真正需要它的信号是「同一套业务逻辑要服务多个入口（HTTP + 定时任务 + 消息消费 + CLI），且已经因此重复过」。没到那一步之前，`controller → service → repository` 三层足够。

Repository 要不要单独抽一层？TypeORM 的 `Repository` 已经是一层了，再包一层自定义 Repository 的收益只在「将来可能换 ORM」时存在——而这件事基本不会发生。**默认让 service 直接用 `Repository`**，只有当某个查询逻辑（复杂 QueryBuilder）被三处以上复用时才抽出来。

### 数据建模的通用取舍

| 决策点 | 选项与判断 |
|---|---|
| 主键 | 默认自增 `bigint`：索引紧凑、插入顺序好。需要「id 不可猜」或「客户端先生成 id」时用 UUID v7 / ULID（有序，比 v4 对索引友好得多）。别用 UUID v4 做聚簇主键 |
| 删除 | 面向用户的内容一律软删（`deleted_at`），日志/中间表硬删。软删要记得**唯一索引要带 `deleted_at`**，否则删掉的记录还占着名字 |
| 时间 | 数据库存 UTC（`timestamp` 或 `datetime` + 全局 UTC），接口传 ISO 8601 带偏移，展示时前端转本地。**永不存本地时间字符串** |
| 枚举 | 存 `tinyint` + TS 枚举，或存短字符串常量。别存中文——改文案要刷数据，也没法建有意义的索引 |
| 金额 | `decimal(18,2)` 或整数存「分」。**绝不用 float/double**，`0.1 + 0.2 !== 0.3` 在钱上是事故 |
| 冗余字段 | 读多写少且计算昂贵时值得（`view_count`、`comment_count`、`last_message_id`）。前提是**必须有一条能重算它的路径**，不然一旦不一致就永远错了 |
| 布尔 | 两态用 `tinyint(1)`；只要有第三种可能（待审核、已过期）就直接上 `status` 枚举，别用两个布尔拼 |

### 接口契约

统一响应格式有两个流派，都说得通：

| | 包一层 `{ code, data, message }` | 直接返数据 + HTTP 状态码 |
|---|---|---|
| 优点 | 业务错误码比 HTTP 状态码表达力强；前端一个拦截器统一处理 | 符合 HTTP 语义；网关、CDN、监控都能直接理解；不用「200 里藏错误」 |
| 缺点 | 所有响应都是 200，监控看不出错误率；违背 HTTP 语义 | 业务错误细分要靠响应体里的 `code` 字段，HTTP 状态码不够用 |
| 适合 | 内部系统、前后端同团队 | 对外 API、要走网关和 CDN |

**建议：HTTP 状态码表达「请求层面对不对」（401/403/404/409/422/429），响应体里的 `code` 表达「业务上哪种错」，两者都要。** 别把业务错误统统塞进 200。实现见[参数校验与异常处理](/guide/nestjs-validation-filter)的全局 Filter 一节。

其余几条定下来就别改：分页统一 `page` / `pageSize`（从 1 开始）+ 返回 `{ items, total, page, pageSize }`，大数据量列表额外提供游标分页；字段名接口层用 camelCase、数据库用 snake_case，映射交给 ORM 的 `naming strategy` 而不是手写；时间字段统一 ISO 8601；列表接口默认不返回大字段（正文、JSON 详情）。

### 不要过早做的事

| 技术 | 真正需要它的信号 | 过早引入的代价 |
|---|---|---|
| 微服务 | 不同模块的负载画像/发布节奏/技术栈已经真的冲突 | 分布式单体：所有缺点，没有优点 |
| GraphQL | 多个差异大的客户端各要不同字段组合，且接口数量已经爆炸 | N+1 查询、缓存失效、权限要按字段做（见 [GraphQL](/guide/nestjs-graphql)） |
| CQRS / 事件溯源 | 读写模型真的分离，且需要完整变更历史（审计、财务） | 代码量翻倍，调试要重放事件 |
| 多级缓存 | 单层 Redis 已被打穿，且有实测数据支撑 | 三份数据三种失效时机，排查「为什么还是旧的」耗尽耐心 |
| 读写分离 | 读 QPS 确实压到主库瓶颈 | 主从延迟导致「刚写完读不到」，业务要处处感知 |
| 分库分表 | 单表已过千万且优化手段用尽 | 跨库 join / 事务 / 分页全部要重写，扩容是大手术 |
| 消息队列 | 有真正的异步需求（耗时任务、削峰、解耦） | 多一个要运维的组件，要处理重复消费和顺序 |

判断标准只有一条：**这个复杂度是被真实数据逼出来的，还是被「以后可能会」想出来的。** 后者永远等到真的需要时再做——那时你对需求的理解也远比现在准。

### Nest 板块的阅读顺序

| 阶段 | 篇目 |
|---|---|
| 必读基础 | [简介与架构](/guide/nestjs-intro) → [装饰器体系](/guide/nestjs-decorators) → [依赖注入](/guide/nestjs-di) → [请求生命周期](/guide/nestjs-pipeline) |
| 每个项目都会用到 | [DTO 与序列化](/guide/nestjs-dto)、[参数校验与异常](/guide/nestjs-validation-filter)、[数据库操作](/guide/nestjs-database)、[认证与登录状态](/guide/nestjs-auth)、[授权与三方登录](/guide/nestjs-authorization) |
| 理解框架原理 | [元数据与 Reflector](/guide/nestjs-metadata-reflector)、[动态模块与配置](/guide/nestjs-dynamic-module)、[RxJS 与 Interceptor](/guide/nestjs-rxjs-interceptor) |
| 按需深入 | [文件上传](/guide/nestjs-file-upload)、[定时任务与事件](/guide/nestjs-schedule-events)、[实时通信](/guide/nestjs-realtime)、[Prisma](/guide/nestjs-prisma)、[GraphQL](/guide/nestjs-graphql)、[微服务](/guide/nestjs-microservice) |
| 上线前必看 | [日志与可观测性](/guide/nestjs-logging)、[生产环境清单](/guide/nestjs-advanced)、[Docker 部署](/guide/docker-deployment)、[Nginx 流量治理](/guide/nginx-core) |

---

## 面试怎么说

**被问「你怎么设计一个预订系统」**：先说清占用单位是格子还是自由区间——能接受固定粒度就切格子，把「不能重复预订」下沉成 `UNIQUE(resource_id, slot_start)`，直接 INSERT 捕重复键错误。这比悲观锁和乐观锁都好，因为正确性不依赖「谁记得加锁」。自由区间才需要自己写重叠判断，条件是 `A.start < B.end AND A.end > B.start`，严格小于。

**被问「JSON 字段该不该用」**：判断标准是「数据库会不会按它的内部字段查询」。题目结构、商品扩展属性、配置快照这类「业务上一直变、但从不按内部字段查」的数据适合 JSON；代价是数据库不再校验，schema 必须在应用层强制，且要有稳定的元素 id。

**被问「WebSocket 多实例怎么办」**：连接状态不能放进程内存。在线状态用 Redis + TTL（不能只靠 `disconnect` 事件，进程被 kill 不会触发），跨实例投递用 Socket.IO 的 Redis adapter。消息可靠性靠「落库 + 客户端上线拉增量」，推送只负责快，不负责准。

**被问「MySQL 和 ES 怎么保持一致」**：不要试图强一致。写库成功后发事件，消费者异步写 ES，接受最终一致。两条兜底：消费者幂等（用业务 id 做 ES 文档 id），以及一个能按 `updated_at` 分批全量重刷的入口。事件必须在事务提交之后发。

**被问「为什么不上微服务」**：拆服务的理由应该是负载画像、发布节奏或技术栈真的冲突了，而不是代码看起来乱。乱是模块边界没立住，拆开只会变成分布式单体。边界先在单体里立住，再拆——从模块化单体到 Monorepo 多 app 的工作量接近于搬目录。


