# SQL 进阶与查询优化

> 会写 `SELECT` 和 `LEFT JOIN` 之后，真正拉开差距的是这几件事：JOIN 的条件该放 `ON` 还是 `WHERE`、`IN` 和 `EXISTS` 谁快、窗口函数怎么一句话解决分组 Top N、以及为什么加了索引却没走索引。

事务、隔离级别、锁和并发一致性不在这篇，见 [并发、事务与一致性](/guide/concurrency-transaction)；建表、字段类型和约束设计见 [MySQL 表结构设计](/guide/mysql-table-design)；`SELECT` / `WHERE` / 分页的基础语法见 [SQL 基础与查询](/guide/sql-basics)。下面默认 MySQL 8.0 / InnoDB。

本篇用一组固定的示例表：

```sql
users(id, name, phone, city, age, last_login_at, created_at)
orders(id, user_id, amount_cent, status, created_at)
order_items(id, order_id, product_id, qty, price_cent)
products(id, name, category_id, price_cent, stock, sales)
categories(id, parent_id, name)
```

---

## JOIN 讲透

### 四种 JOIN 的集合语义

| 写法 | 保留哪些行 | 用文字描述 |
|---|---|---|
| `INNER JOIN` | 两边都能匹配上的 | 两个圆的重叠部分 |
| `LEFT JOIN` | 左表全部 + 右表匹配上的 | 左圆整个，加上重叠部分；左表有、右表无的那些行，右表字段全是 NULL |
| `RIGHT JOIN` | 右表全部 + 左表匹配上的 | 与 LEFT 镜像，把表顺序调换即可等价改写 |
| `CROSS JOIN` | 笛卡尔积，左表每行配右表每行 | 两个圆不比较，直接相乘。1000 × 1000 就是一百万行 |

实践中只写 `INNER JOIN` 和 `LEFT JOIN`：`RIGHT JOIN` 会让"主表是谁"变得难读，调换表顺序改成 LEFT 即可；`CROSS JOIN` 只在需要补齐维度时故意用（比如生成连续日期 × 全部品类的空白骨架，再 LEFT JOIN 上真实数据，让没有交易的日子也出现在报表里）。

MySQL 没有 `FULL OUTER JOIN`，要模拟得用 `LEFT JOIN` 的结果 `UNION` `RIGHT JOIN` 的结果。

### 驱动表：多表 JOIN 的性能关键

MySQL 的 JOIN 主要是嵌套循环：取驱动表（外层表）的每一行，拿连接键去被驱动表（内层表）查一次。

```txt
for (row_a of A) {            // A 是驱动表，扫多少行决定循环次数
  for (row_b of B where b.a_id = row_a.id) {   // B 是被驱动表，这里必须走索引
    output(row_a, row_b)
  }
}
```

由此得出两条铁律：**过滤后行数少的表当驱动表**（循环次数少），**被驱动表的连接列必须有索引**（否则每次内层查找都是全表扫，复杂度直接乘起来）。优化器一般能自己选对驱动表，但它依赖统计信息，估错时可以用 `STRAIGHT_JOIN` 强制按书写顺序，或先 `ANALYZE TABLE` 更新统计信息。

`LEFT JOIN` 的语义要求左表全部保留，所以左表基本被固定为驱动表——这也意味着**用 LEFT JOIN 时你放弃了优化器调换顺序的自由**，能用 INNER 就别用 LEFT。MySQL 8.0.18 起有 hash join，被驱动表没索引时不再是灾难，但仍然比走索引慢一个量级。

### ON 和 WHERE 放条件的结果差异

这是 SQL 里最经典的坑。查"每个用户的已支付订单，没有已支付订单的用户也要出现"：

```sql
-- ✅ 正确：条件在 ON 里，只影响"能不能匹配上"
SELECT u.id, u.name, o.id AS order_id
FROM users u
LEFT JOIN orders o ON o.user_id = u.id AND o.status = 'paid';

-- ❌ 错误：条件在 WHERE 里，LEFT JOIN 退化成 INNER JOIN
SELECT u.id, u.name, o.id AS order_id
FROM users u
LEFT JOIN orders o ON o.user_id = u.id
WHERE o.status = 'paid';
```

原因在执行顺序：`ON` 在**连接阶段**判断，匹配不上的左表行照样保留，右表字段填 NULL；`WHERE` 在**连接完成之后**过滤整个结果集，而那些补出来的 NULL 行的 `o.status` 是 NULL，`NULL = 'paid'` 是 UNKNOWN，于是被过滤掉——所有"没有已支付订单的用户"消失了。

| 条件位置 | INNER JOIN | LEFT JOIN |
|---|---|---|
| 写在 `ON` | 结果相同 | 保留左表全部行，条件只决定右表是否匹配 |
| 写在 `WHERE` | 结果相同 | 退化成 INNER JOIN（除 `IS NULL` 判断外） |

唯一该把右表条件写进 `WHERE` 的场景是**反连接**——故意找"右表没有匹配"的行：

```sql
-- 从没下过单的用户
SELECT u.id, u.name
FROM users u
LEFT JOIN orders o ON o.user_id = u.id
WHERE o.id IS NULL;
```

> ⚠️ 左表自己的过滤条件（`u.city = '北京'`）写在 `WHERE` 里是对的，也更利于优化器提前过滤、缩小驱动表。规则是：**左表条件放 WHERE，右表条件放 ON。**

### 自连接

同一张表 JOIN 自己，靠别名区分。两个高频用途：

```sql
-- 1. 层级数据：查每个分类及其父分类名（一层）
SELECT c.id, c.name, p.name AS parent_name
FROM categories c
LEFT JOIN categories p ON p.id = c.parent_id;

-- 2. 找重复：同一手机号注册了多个账号，列出重复的两两组合
SELECT a.id, b.id, a.phone
FROM users a
JOIN users b ON a.phone = b.phone AND a.id < b.id;
```

第二个例子里 `a.id < b.id` 既避免了自己和自己配对，也避免了 (1,2) 和 (2,1) 各出现一次。只是想知道"哪些手机号重复了"用 `GROUP BY phone HAVING COUNT(*) > 1` 更直接；要拿到重复行的完整信息才需要自连接。查任意层级的树见后面的递归 CTE。

---

## 外键与级联

> 本节是快速选型入口；完整的关系建模、删除顺序、级联风险、软删除和“不建外键”时的替代方案见[数据库外键：理论、实践与取舍](./foreign-keys)。

```sql
CREATE TABLE orders (
  id      BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  user_id BIGINT UNSIGNED NOT NULL,
  CONSTRAINT fk_orders_user FOREIGN KEY (user_id) REFERENCES users(id)
    ON DELETE RESTRICT ON UPDATE CASCADE
);
```

删除或更新父行时，子行怎么办：

| 动作 | 语义 | 适合 |
|---|---|---|
| `RESTRICT` | 还有子行就拒绝删除父行，报错 | 默认选择。订单存在就不许删用户 |
| `NO ACTION` | InnoDB 里和 `RESTRICT` 完全一样（不支持延迟检查） | 同上 |
| `CASCADE` | 删父行连带删掉所有子行 | 真正的"从属"数据：订单与订单项、文章与文章图片 |
| `SET NULL` | 子行的外键列置为 NULL，要求该列可空 | 弱关联：删除分类后商品变成"未分类" |

`ON UPDATE CASCADE` 只在主键会变时才有意义，而主键本来就该用不会变的自增 ID，所以实践中通常写 `ON UPDATE RESTRICT` 或干脆不写。

> ⚠️ `ON DELETE CASCADE` 有个真实的危险：删一个用户可能连带删掉几十万行订单，这个删除在**一个事务里**完成，会长时间持锁、把 undo log 撑爆。而且**级联删除不会触发子表的触发器**，靠触发器做审计日志的话会静默丢数据。数据量大时宁可在应用层分批删。

### 生产环境要不要用外键

| 立场 | 理由 |
|---|---|
| 用 | 数据库是最后一道防线。应用有 bug、有人手工执行 SQL、有多个服务写同一张表时，只有外键能保证不出现"订单指向不存在的用户"这种脏数据。脏数据一旦产生，清理成本远高于外键的开销 |
| 不用 | 写入时要额外检查父表并加锁，高并发下是热点；`pt-online-schema-change`、`gh-ost` 这类在线改表工具对外键支持很差；分库分表后父子行可能在不同实例，外键根本无法建立；报错信息（`Cannot add or update a child row`）不好直接给用户看 |

务实的分界线：

- **中小项目、单库、有多个写入方或需要人工维护数据 → 建外键。** 这时一致性的价值远大于性能损耗，"没有脏数据"能省下大量排查时间。
- **高并发写入、已经分库分表、或明确要用在线 DDL 工具 → 用逻辑外键**（只存 ID 不建约束），但必须补上三件事：外键列**一定要建索引**（否则关联查询和级联检查都会全表扫）、跨表写入放在同一个事务里、加对账任务定期扫孤儿数据。
- ORM 的关系声明（TypeORM 的 `@ManyToOne`、Prisma 的 `relation`）默认会生成真外键，不想要就显式关掉。相关配置见 [NestJS 数据库操作](/guide/nestjs-database)。

---

## 子查询与 EXISTS

按返回形状分三类：

```sql
-- 标量子查询：返回 1 行 1 列，可以当一个值用在任何地方
SELECT id, amount_cent,
       amount_cent - (SELECT AVG(amount_cent) FROM orders) AS diff_from_avg
FROM orders;

-- 行子查询：返回 1 行多列，和一组值比较
SELECT * FROM orders
WHERE (user_id, created_at) = (SELECT user_id, MAX(created_at) FROM orders WHERE user_id = 7);

-- 表子查询：返回多行，用在 IN / EXISTS / FROM 后面
SELECT * FROM users WHERE id IN (SELECT user_id FROM orders WHERE status = 'paid');
```

> ⚠️ 标量子查询如果返回多行会直接报错（`Subquery returns more than 1 row`），返回 0 行则得到 NULL 而不是报错——后者更危险，因为它会静默地让整行计算结果变成 NULL。

### IN、EXISTS 和 JOIN 的等价改写

同一个需求"查有已支付订单的用户"，三种写法：

```sql
-- IN：先算出内层结果集，再拿外层的值去里面找
SELECT * FROM users u WHERE u.id IN (SELECT o.user_id FROM orders o WHERE o.status = 'paid');

-- EXISTS：对外层每一行，去内层探测"存在吗"，找到一条立刻返回
SELECT * FROM users u
WHERE EXISTS (SELECT 1 FROM orders o WHERE o.user_id = u.id AND o.status = 'paid');

-- JOIN：需要 DISTINCT，否则一个用户有 3 笔订单就出现 3 次
SELECT DISTINCT u.* FROM users u JOIN orders o ON o.user_id = u.id WHERE o.status = 'paid';
```

选哪个：

| 情形 | 更快的写法 | 原因 |
|---|---|---|
| 外表大、内表小 | `IN` | 内层结果集小，物化成临时表后哈希查找一次搞定 |
| 外表小、内表大且连接列有索引 | `EXISTS` | 逐行探测，命中一条就短路，不需要把内表算完 |
| 需要用到内表的列（取订单金额、数量） | `JOIN` | 子查询拿不到内表字段，只能判断存在性 |
| 只判断存在性 | `EXISTS` | 比 `JOIN` + `DISTINCT` 省掉一次去重排序 |

MySQL 5.6 之后优化器会把 `IN` 子查询改写成半连接（semi-join），5.7 起会把派生表合并进外层查询，所以三种写法的执行计划经常趋同——"`IN` 一定慢"是过时的经验。判断标准只有一个：**用 `EXPLAIN` 看，别背结论。**

`EXISTS (SELECT 1 ...)` 里写 `1` 还是 `*` 没有性能差别，优化器只关心存在性。写 `1` 只是表达意图更清楚。

### NOT IN 遇到 NULL 会返回空集

```sql
-- 想查"没有被任何订单引用过的用户"，如果 orders.user_id 里存在 NULL，结果永远是空
SELECT * FROM users WHERE id NOT IN (SELECT user_id FROM orders);
```

`NOT IN (1, 2, NULL)` 会展开成 `id <> 1 AND id <> 2 AND id <> NULL`。最后一项恒为 UNKNOWN，整个 `AND` 表达式永远不可能为 TRUE，于是一行都不返回——而且**不报错**，只是静默返回空。三种修法：

```sql
WHERE id NOT IN (SELECT user_id FROM orders WHERE user_id IS NOT NULL)   -- 显式排除
WHERE NOT EXISTS (SELECT 1 FROM orders o WHERE o.user_id = users.id)     -- 推荐
-- 或者用前面提过的 LEFT JOIN ... WHERE o.id IS NULL 反连接
```

`NOT EXISTS` 不受 NULL 影响，是排除类查询的默认选择。

### 相关子查询为什么慢

子查询里引用了外层的列（上面 `EXISTS` 里的 `u.id`）就叫相关子查询，它**不能只算一次**，得跟着外层每一行重新执行。写在 `WHERE` 里还能被优化器改写成半连接，写在 `SELECT` 列表里就没救了：

```sql
-- ❌ 外层 10 万行 → 内层执行 10 万次
SELECT u.id, u.name,
       (SELECT COUNT(*) FROM orders o WHERE o.user_id = u.id) AS order_count
FROM users u;

-- ✅ 先聚合一次，再关联
SELECT u.id, u.name, COALESCE(s.cnt, 0) AS order_count
FROM users u
LEFT JOIN (SELECT user_id, COUNT(*) AS cnt FROM orders GROUP BY user_id) s
  ON s.user_id = u.id;
```

数据量小时前一种写法看不出问题，行数一涨就是几秒级的慢查询。看到 `SELECT` 列表里出现子查询，先想能不能改成 JOIN 聚合。

### 派生表与 CTE

写在 `FROM` 后面的子查询叫派生表，必须起别名。嵌套两层以上就没法读了，MySQL 8.0 的 CTE（`WITH`）把它拉平：

```sql
WITH paid_orders AS (
  SELECT user_id, SUM(amount_cent) AS total, COUNT(*) AS cnt
  FROM orders
  WHERE status = 'paid' AND created_at >= '2026-01-01'
  GROUP BY user_id
),
vip AS (
  SELECT user_id FROM paid_orders WHERE total > 1000000
)
SELECT u.name, p.total, p.cnt
FROM vip v
JOIN paid_orders p ON p.user_id = v.user_id
JOIN users u ON u.id = v.user_id
ORDER BY p.total DESC;
```

CTE 相比派生表的三个好处：可以在同一条 SQL 里**被引用多次**（派生表得复制一遍）、从上往下读符合思维顺序、每一段都能单独拿出来验证。代价是 MySQL 的 CTE 可能被物化成临时表，复杂查询里不一定比手写 JOIN 快——所以它主要是**可读性**工具，不是性能工具。

### 递归 CTE 查树形结构

分类树、部门层级、评论盖楼这类无限层级数据，过去要么在应用层递归查 N 次，要么存 path 字符串。MySQL 8.0 可以一条 SQL 搞定：

```sql
WITH RECURSIVE tree AS (
  -- 锚定成员：起点，这里是 id = 1 的根分类
  SELECT id, parent_id, name, 1 AS depth, CAST(name AS CHAR(500)) AS path
  FROM categories WHERE id = 1

  UNION ALL

  -- 递归成员：拿上一轮的结果去找子节点，直到找不到为止
  SELECT c.id, c.parent_id, c.name, t.depth + 1,
         CONCAT(t.path, ' / ', c.name)
  FROM categories c
  JOIN tree t ON c.parent_id = t.id
  WHERE t.depth < 10                     -- 防御性深度限制，避免脏数据成环时无限递归
)
SELECT id, depth, path FROM tree ORDER BY path;
```

要点：`UNION ALL` 上半部分是起点、下半部分引用 CTE 自身；把 `JOIN` 的方向反过来（`c.id = t.parent_id`）就变成从叶子往上查所有祖先。默认递归上限由 `cte_max_recursion_depth` 控制（1000），但**别指望它兜底**——数据成环时会先跑很久再报错，所以自己带一个 `depth` 上限。

---

## 聚合与窗口函数

### GROUP BY、HAVING 和 ONLY_FULL_GROUP_BY

```sql
SELECT city, COUNT(*) AS user_count, AVG(age) AS avg_age
FROM users
WHERE created_at >= '2026-01-01'     -- 分组前过滤行，能用索引
GROUP BY city
HAVING COUNT(*) >= 10                -- 分组后过滤组，可以引用聚合结果
ORDER BY user_count DESC;
```

| 子句 | 时机 | 能否用聚合函数 | 能否用索引 |
|---|---|---|---|
| `WHERE` | 分组之前，逐行判断 | 不能 | 能 |
| `HAVING` | 分组之后，逐组判断 | 能 | 不能（数据已在临时结果里） |

**能写在 `WHERE` 的条件绝不要写进 `HAVING`**：`HAVING city = '北京'` 语法上能跑，但它先把所有城市分完组再扔掉，白算一遍。

`ONLY_FULL_GROUP_BY` 是 MySQL 5.7 起的默认模式，`SELECT` 列表里出现既不在 `GROUP BY` 里、也没被聚合函数包裹的列时直接报错 1055：

```sql
-- ❌ ERROR 1055：一个城市有很多用户，name 到底取谁的？
SELECT city, name, COUNT(*) FROM users GROUP BY city;
```

这个限制是对的——旧版 MySQL 会随便返回一行的值，导致数据看着对其实是随机的。三种正确做法：把列加进 `GROUP BY`、用聚合函数（`MAX(name)`）、或者明确表示"任取一个我认了"用 `ANY_VALUE(name)`。**不要去关掉这个 sql_mode**，报错是在帮你发现逻辑漏洞。真正想要"每组里某一行的完整信息"，用下面的窗口函数。

### 窗口函数：不折叠行的聚合

`GROUP BY` 把多行折叠成一行，窗口函数**保留每一行**，同时在旁边算出一个跨行的值。前端类比：`GROUP BY` 像 `reduce` 把数组压成一个值，窗口函数像 `map` 时还能看到整个数组。

```sql
函数名(...) OVER (
  PARTITION BY 分组列    -- 可选：按什么分窗口，等价于 GROUP BY 但不折叠
  ORDER BY 排序列        -- 可选：窗口内怎么排，排名和累计都依赖它
)
```

三个排名函数的区别，用两个人并列第一举例：

| 函数 | 结果序列 | 含义 |
|---|---|---|
| `ROW_NUMBER()` | 1, 2, 3, 4 | 强行编号，并列也要分先后（谁在前不确定，除非 `ORDER BY` 能唯一确定） |
| `RANK()` | 1, 1, 3, 4 | 并列同名次，之后**跳号**（体育比赛的名次） |
| `DENSE_RANK()` | 1, 1, 2, 3 | 并列同名次，之后**不跳号**（排行榜常用） |

要"每组取一条"用 `ROW_NUMBER()`，要"取前三名含并列"用 `DENSE_RANK()`。

### 实战一：分组内取 Top N

每个品类销量最高的 3 个商品——用 `GROUP BY` 做不到，因为它只能返回聚合值：

```sql
SELECT category_id, id, name, sales
FROM (
  SELECT p.category_id, p.id, p.name, p.sales,
         ROW_NUMBER() OVER (PARTITION BY p.category_id ORDER BY p.sales DESC, p.id) AS rn
  FROM products p
) t
WHERE rn <= 3
ORDER BY category_id, rn;
```

窗口函数在 `SELECT` 之后、`WHERE` 之前就已经算完，所以**不能直接在 `WHERE` 里写 `rn <= 3`**，必须套一层子查询或 CTE。`ORDER BY` 里加上 `p.id` 是为了让销量相同时排名稳定，否则同一条 SQL 两次执行可能返回不同结果。

### 实战二：每日累计与环比

```sql
WITH daily AS (
  SELECT DATE(created_at) AS d, SUM(amount_cent) AS amount
  FROM orders
  WHERE status = 'paid' AND created_at >= '2026-01-01'
  GROUP BY DATE(created_at)
)
SELECT d,
       amount,
       SUM(amount) OVER (ORDER BY d ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cumulative,
       LAG(amount) OVER (ORDER BY d) AS prev_day,
       ROUND((amount - LAG(amount) OVER (ORDER BY d)) * 100.0
             / NULLIF(LAG(amount) OVER (ORDER BY d), 0), 2) AS growth_pct
FROM daily
ORDER BY d;
```

`LAG(x)` 取上一行的值，`LEAD(x)` 取下一行，都可以带偏移量：`LAG(amount, 7)` 就是上周同一天，用来算周同比。`NULLIF(x, 0)` 把 0 变成 NULL 以避免除零——MySQL 除零返回 NULL 而不是报错，但显式写出来意图更清楚。

> ⚠️ `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` 别省。带 `ORDER BY` 的窗口默认帧是 `RANGE`，而 `RANGE` 会把**排序值相同的所有行当成同一个位置一起算**。如果同一天有多行（比如没有先按天聚合），默认帧算出来的"累计"会把当天所有行一次性全加上，看着像 bug。写 `ROWS` 才是严格按行累加。

### 实战三：去重保留最新一条

同一手机号注册了多个账号，只保留最近登录的那条：

```sql
-- 先看要删哪些
WITH ranked AS (
  SELECT id, phone,
         ROW_NUMBER() OVER (PARTITION BY phone ORDER BY last_login_at DESC, id DESC) AS rn
  FROM users
)
SELECT * FROM ranked WHERE rn > 1;

-- 确认无误后再删
DELETE u FROM users u
JOIN (SELECT id FROM (
        SELECT id, ROW_NUMBER() OVER (PARTITION BY phone ORDER BY last_login_at DESC, id DESC) AS rn
        FROM users
      ) x WHERE x.rn > 1) d ON d.id = u.id;
```

多套一层子查询是因为 MySQL 不允许在 `DELETE` 的子查询里直接引用正在删的表。这类清理 SQL 的纪律是**先 SELECT 看清楚再 DELETE**，并且在事务里做、先在从库或备份上演练。

---

## 常用函数速查

字符串：

| 函数 | 作用 | 注意 |
|---|---|---|
| `CONCAT(a, b)` / `CONCAT_WS('-', a, b)` | 拼接 / 带分隔符拼接 | `CONCAT` 任一参数为 NULL 结果就是 NULL，`CONCAT_WS` 会跳过 NULL |
| `SUBSTRING(s, pos, len)` | 截取，下标从 **1** 开始 | 不是 0，和 JS 不一样 |
| `REPLACE(s, from, to)` | 替换全部匹配 | 常用于批量修数据，记得先 SELECT 验证 |
| `TRIM(s)` / `LTRIM` / `RTRIM` | 去空格 | `TRIM(BOTH 'x' FROM s)` 可去指定字符 |
| `LPAD(s, 6, '0')` | 左补位 | 生成固定长度编号 |
| `LENGTH(s)` / `CHAR_LENGTH(s)` | 字节数 / 字符数 | utf8mb4 下一个汉字 3 字节、emoji 4 字节。校验长度一律用 `CHAR_LENGTH` |

时间：

| 函数 | 作用 |
|---|---|
| `NOW()` / `CURDATE()` / `UTC_TIMESTAMP()` | 当前时间 / 当前日期 / 当前 UTC 时间 |
| `DATE_FORMAT(t, '%Y-%m-%d %H:%i')` | 格式化。分钟是 `%i`，`%m` 是月份 |
| `DATE_ADD(t, INTERVAL 7 DAY)` / `DATE_SUB` | 加减，单位可为 `SECOND` 到 `YEAR` |
| `DATEDIFF(a, b)` | 相差天数，**只看日期部分**，忽略时分秒 |
| `TIMESTAMPDIFF(HOUR, a, b)` | 按指定单位算差值，要精确到小时分钟就用它 |
| `UNIX_TIMESTAMP(t)` / `FROM_UNIXTIME(n)` | 与秒级时间戳互转 |

时区是这里最容易踩的坑，症状永远是"时间差了 8 小时"：

| 类型 | 存储 | 读取 |
|---|---|---|
| `DATETIME` | 原样存字面值，**不带时区信息** | 原样返回，谁读都一样 |
| `TIMESTAMP` | 转成 UTC 存储 | 按当前连接的 `time_zone` 转回来，同一行不同连接可能读到不同值 |

三个来源会各自设置时区：MySQL 服务器的 `time_zone`、连接会话的 `time_zone`、以及 Node 驱动的解析设置（`mysql2` 的 `timezone` 选项，默认按本地时区解析 `DATETIME`）。结论：**统一用 UTC 存、在展示层转换**，连接串里显式写死时区，别依赖服务器默认值——服务器换个机房、容器换个基础镜像，默认时区就变了。

数值与条件：

| 函数 | 说明 |
|---|---|
| `ROUND(x, 2)` / `CEIL` / `FLOOR` / `ABS` / `MOD(a, b)` | 常规数学函数 |
| `CASE WHEN a THEN x WHEN b THEN y ELSE z END` | 多分支，能写在 `SELECT`、`ORDER BY`、`SUM()` 里 |
| `IF(cond, x, y)` | 两分支简写，MySQL 特有 |
| `IFNULL(a, b)` | a 为 NULL 时取 b，只接受两个参数 |
| `COALESCE(a, b, c)` | 返回第一个非 NULL 的值，标准 SQL，多参数 |
| `NULLIF(a, b)` | a 等于 b 时返回 NULL，常用于防除零 |

`CASE WHEN` 配合聚合函数可以做行转列，这是报表里最常用的一招：

```sql
SELECT DATE(created_at) AS d,
       SUM(CASE WHEN status = 'paid'     THEN 1 ELSE 0 END) AS paid_cnt,
       SUM(CASE WHEN status = 'refunded' THEN 1 ELSE 0 END) AS refunded_cnt
FROM orders GROUP BY DATE(created_at);
```

JSON：

```sql
-- profile 是 JSON 列，内容形如 {"nickname":"阿明","tags":["vip","new"]}
SELECT profile->>'$.nickname'        AS nickname,      -- ->> 取值并去掉引号
       profile-> '$.tags[0]'         AS first_tag,     -- -> 保留 JSON 引号
       JSON_EXTRACT(profile, '$.tags') AS tags
FROM users
WHERE JSON_CONTAINS(profile->'$.tags', '"vip"');
```

`->` 是 `JSON_EXTRACT` 的语法糖，`->>` 等于再套一层 `JSON_UNQUOTE`——查出来要直接展示或比较字符串时用 `->>`，否则会带着引号。

什么时候该用 JSON 列，什么时候说明你该建表了：

| 适合 JSON 列 | 该建表 / 建列 |
|---|---|
| 结构不定的扩展属性，不同业务方各存各的 | 需要按这个字段**过滤、排序、聚合**（JSON 上默认没有索引） |
| 第三方接口的原始响应，留档用 | 需要唯一约束、非空约束、外键 |
| 埋点上下文、审计快照这类只写不查的数据 | 需要和别的表 JOIN |
| 字段数量多但绝大多数请求不读 | 这个字段是业务核心，会出现在需求文档里 |

需要在 JSON 里的某个键上查询又不想拆表，可以建生成列再加索引：`ALTER TABLE users ADD COLUMN nickname VARCHAR(64) AS (profile->>'$.nickname') STORED, ADD INDEX idx_nickname (nickname);`。但如果你开始给三四个键都建生成列，那就是数据库在提醒你：这些字段该是真列了。

---

## 索引与执行计划

### B+ 树为什么适合数据库

InnoDB 的索引是 B+ 树，它和二叉树、哈希表的区别决定了它擅长什么：

| 特点 | 带来的好处 |
|---|---|
| 一个节点存几百个键（一页 16KB） | 树高只有 3~4 层就能装千万级数据，查一行最多 3~4 次磁盘 IO |
| 非叶子节点只存键和指针，不存数据 | 同样大小的节点能存更多键，进一步压低树高 |
| 所有数据都在叶子节点，且叶子之间用双向链表串起来 | **范围查询只要定位到起点，顺着链表往后扫即可**，不用反复回到根节点 |

最后一条是关键：哈希索引查单值是 O(1)，但 `WHERE age BETWEEN 20 AND 30`、`ORDER BY created_at` 完全用不上它，因为哈希打散了顺序。B+ 树的有序叶子链表同时支撑了范围查询、排序和分页，这是它成为默认结构的原因。

### 聚簇索引、二级索引与回表

```mermaid
flowchart LR
  A["二级索引 idx_city<br/>叶子存：city + 主键 id"] -->|"拿到 id = 42"| B["聚簇索引 PRIMARY<br/>叶子存：整行数据"]
  B --> C["取出 name、age、created_at…"]
```

| 索引 | 叶子节点存什么 | 一张表能有几个 |
|---|---|---|
| 聚簇索引（主键索引） | **整行数据** | 1 个。没定义主键时 InnoDB 会用唯一非空索引，再没有就自己造一个隐藏列 |
| 二级索引（普通索引） | 索引列的值 + **主键值** | 多个 |

因为二级索引里没有整行数据，用它查到主键后还要再去聚簇索引查一次完整行——这个动作叫**回表**。所以一次 `WHERE city = '北京'` 查 100 行，实际是 1 次索引范围扫描 + 100 次回表随机 IO。回表次数多到一定程度，优化器干脆放弃索引直接全表扫，因为顺序 IO 比大量随机 IO 更快。这就是"明明有索引却走了全表扫描"最常见的原因。

主键要短、要单调递增，正是因为它被每个二级索引复制了一份：主键用 UUID（36 字节）会让所有二级索引膨胀，且随机插入导致页分裂。

### 覆盖索引消除回表

如果查询需要的所有列都在索引里，就不需要回表：

```sql
-- 索引 idx_user_created (user_id, created_at)
SELECT user_id, created_at FROM orders WHERE user_id = 7;   -- ✅ 覆盖索引，EXPLAIN 显示 Using index
SELECT * FROM orders WHERE user_id = 7;                     -- ❌ 要 amount_cent、status，必须回表
```

这是**不要写 `SELECT *`** 的一个硬性理由，不只是"少传字段省带宽"。把高频列表查询需要的列一起放进联合索引（`(user_id, created_at, status, amount_cent)`），能把回表彻底消掉。代价是索引变宽、写入变慢、占更多内存，所以只对真正的热点查询这么做。

### 联合索引的最左前缀原则

联合索引 `(a, b, c)` 的排序规则是：先按 a 排，a 相同再按 b 排，b 相同再按 c 排——和电话簿按"姓、名、中间名"排序完全一样。所以**知道姓才能定位，只知道名没法查**。

| 查询条件 | 能用到索引的部分 | 说明 |
|---|---|---|
| `a = 1` | a | 最左列，可用 |
| `a = 1 AND b = 2` | a, b | 连续前缀 |
| `a = 1 AND b = 2 AND c = 3` | a, b, c | 全部命中 |
| `a = 1 AND c = 3` | 只有 a | b 断了，c 用不上（但 c 可能被索引条件下推优化） |
| `b = 2` / `b = 2 AND c = 3` | 用不上 | 缺最左列，只能全表扫或全索引扫 |
| `a = 1 AND b > 5 AND c = 3` | a, b | **范围之后失效**：b 是范围，c 在索引里不再有序 |
| `a = 1 ORDER BY b` | a 过滤 + b 排序 | 排序也吃最左前缀，能省掉 filesort |
| `ORDER BY a, b` | a, b | 排序方向要一致，一升一降用不上（8.0 起支持降序索引） |
| `a IN (1,2,3) AND b = 2` | a, b | `IN` 是等值的集合，后续列仍可用 |

推论：写 `WHERE` 条件的顺序**不影响**索引使用（优化器会重排），但联合索引里**列的定义顺序至关重要**。定义顺序的经验法则是：等值查询的列放前面，范围查询和排序的列放后面；区分度高的列放前面。

### 索引失效的六种典型写法

```sql
-- 1. 函数或运算包裹了索引列 → 索引存的是原值，算完的值不在索引里
WHERE DATE(created_at) = '2026-01-01'        -- ❌
WHERE created_at >= '2026-01-01' AND created_at < '2026-01-02'   -- ✅ 改成范围
WHERE amount_cent / 100 > 50                 -- ❌
WHERE amount_cent > 5000                     -- ✅ 把运算移到常量侧

-- 2. 隐式类型转换 → phone 是 VARCHAR，传数字会让 MySQL 把整列转成数字比较
WHERE phone = 13800000000                    -- ❌ 全表扫
WHERE phone = '13800000000'                  -- ✅ 加引号

-- 3. 左模糊 → B+ 树按前缀有序，不知道开头就无法定位
WHERE name LIKE '%明'                         -- ❌
WHERE name LIKE '明%'                         -- ✅ 右模糊可用索引
                                              -- 真要左模糊：全文索引或 Elasticsearch

-- 4. OR 连接的列有一侧没索引 → 那一侧必须全表扫，整体就退化了
WHERE user_id = 7 OR remark = 'x'            -- ❌ remark 无索引
WHERE user_id = 7 UNION ALL ... remark = 'x' -- ✅ 拆开写，或给 remark 也加索引

-- 5. 不等号与取反 → 匹配的行太多时优化器主动放弃索引
WHERE status != 'paid'                       -- 通常走全表扫
WHERE status IN ('pending', 'cancelled')     -- ✅ 改成正向枚举

-- 6. 区分度太低 → 索引扫完还要回表，比顺序全表扫更慢
WHERE gender = 1                             -- 只有两个值，索引形同虚设
WHERE is_deleted = 0 AND user_id = 7         -- ✅ 低区分度列只作为联合索引的附属列
```

第 2 条最阴险，因为 SQL 完全正常、结果也对，只是慢——JavaScript 里 `phone` 是数字类型时，ORM 或手写 SQL 很容易就把数字传下去了。MySQL 8.0.13 起支持函数索引（`ADD INDEX ((DATE(created_at)))`），能救第 1 条，但改写查询永远是更好的选择。

### EXPLAIN 怎么读

`EXPLAIN` 前面加在任何 `SELECT` / `UPDATE` / `DELETE` 上，看优化器**打算**怎么执行。重点看五列：

`type`（访问方式，从好到差）：

| type | 含义 | 评价 |
|---|---|---|
| `system` / `const` | 通过主键或唯一索引匹配到最多一行 | 最好 |
| `eq_ref` | JOIN 时用主键 / 唯一索引，对驱动表每行只匹配一行 | 很好 |
| `ref` | 用普通索引等值匹配，可能返回多行 | 好，日常目标 |
| `range` | 索引范围扫描（`BETWEEN`、`>`、`IN`） | 可接受 |
| `index` | 扫了整个索引树 | 危险：行数没减少，只是省了回表 |
| `ALL` | 全表扫描 | 大表上必须优化 |

其余四列：

| 列 | 怎么看 |
|---|---|
| `key` | 实际选中的索引。是 `NULL` 说明没用上任何索引 |
| `rows` | 优化器**估算**要扫多少行。和实际结果行数差一个数量级以上，说明统计信息过期或索引选错 |
| `filtered` | 估算 `WHERE` 过滤后剩余百分比。`rows × filtered` 才是真正参与下一步的行数 |
| `Extra` | 信息量最大的一列，见下 |

`Extra` 的关键字：

| 值 | 含义 |
|---|---|
| `Using index` | ✅ 覆盖索引，不回表 |
| `Using index condition` | ✅ 索引条件下推，在存储引擎层就过滤掉了一部分，减少回表 |
| `Using where` | 索引没能完全过滤，还要在 server 层再筛一遍。不一定是问题，但值得看看能不能补索引 |
| `Using filesort` | ⚠️ 排序无法靠索引完成，要额外排序。数据量大时落磁盘 |
| `Using temporary` | ⚠️ 需要临时表，常见于 `GROUP BY` 和 `DISTINCT` 无索引可用时。比 filesort 更值得警惕 |
| `Using join buffer (hash join)` | 被驱动表没有可用索引，退化成哈希连接 |

MySQL 8.0.18 起还有 `EXPLAIN ANALYZE`，它会**真正执行**并给出每一步的实际耗时和行数，比看估算准得多——但它会真的跑，别对 `UPDATE`、`DELETE` 用。

### 一个完整的优化案例

订单列表接口，某用户的已支付订单按时间倒序取 20 条，线上耗时 1.8 秒：

```sql
SELECT id, amount_cent, status, created_at
FROM orders
WHERE user_id = 7 AND status = 'paid'
ORDER BY created_at DESC
LIMIT 20;
```

第一步，`EXPLAIN` 看现状：

```txt
type: ALL   key: NULL   rows: 1840000   filtered: 1.00   Extra: Using where; Using filesort
```

`type: ALL` + `Using filesort` 说明两件事都没走索引：过滤要扫全表 184 万行，排序还要把结果全部拿出来再排。

第二步，按"等值列在前、排序列在后"建联合索引：

```sql
ALTER TABLE orders ADD INDEX idx_user_status_created (user_id, status, created_at);
```

再看：

```txt
type: ref   key: idx_user_status_created   rows: 312   filtered: 100.00   Extra: NULL
```

`filesort` 消失了——因为索引里 `(user_id, status)` 确定后 `created_at` 天然有序，`LIMIT 20` 只需顺着叶子链表取 20 个再回表 20 次。耗时降到 3ms。

第三步，如果这个接口 QPS 很高，还能把回表也去掉。把返回的列都塞进索引：

```sql
ALTER TABLE orders ADD INDEX idx_cover (user_id, status, created_at, amount_cent);
```

`Extra` 变成 `Using index`。这一步是否值得做要看权衡：索引更宽、写入更慢、占更多 buffer pool，只对确认的热点接口做。

> ⚠️ 加索引前先查 `SHOW INDEX FROM orders` 看有没有能复用的。如果已存在 `(user_id)`，新建的 `(user_id, status, created_at)` 就把它完全覆盖了，旧的应该删掉——冗余索引会白白拖慢每一次写入。线上加索引用在线 DDL（`ALGORITHM=INPLACE`）或 `gh-ost`，别在业务高峰直接 `ALTER`。

---

## 分页深翻为什么越翻越慢

```sql
SELECT * FROM orders ORDER BY created_at DESC LIMIT 1000000, 20;
```

`LIMIT 1000000, 20` 的语义是"取出前 100 万零 20 行，丢掉前 100 万行"。数据库并没有"直接跳到第 100 万行"的能力——走索引也要沿着叶子链表数过去，而且每一行都要**回表**才知道能不能算数，最后 99.998% 的工作都被扔掉。翻到第一页 5ms，翻到第五万页 5 秒。

**解法一：延迟关联。** 先只在索引里数行、拿到 20 个主键，再回表取完整数据：

```sql
SELECT o.* FROM orders o
JOIN (
  SELECT id FROM orders ORDER BY created_at DESC LIMIT 1000000, 20
) t ON t.id = o.id;
```

子查询里只取 `id`，如果 `(created_at, id)` 是覆盖索引，这 100 万行的扫描全在索引里完成，不回表，通常能快一个数量级。限制是**扫描量并没有减少**，只是每行变便宜了，翻到几百万行依然慢。好处是不改接口协议，页码分页照旧。

**解法二：游标分页。** 不要页码，用"上一页最后一条的位置"当起点：

```sql
-- 第一页
SELECT id, created_at FROM orders ORDER BY created_at DESC, id DESC LIMIT 20;
-- 后续页：带上上一页最后一行的 (created_at, id)
SELECT id, created_at FROM orders
WHERE (created_at, id) < ('2026-08-01 10:00:00', 90412)
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

这是真正的 O(1)：索引直接定位到起点，扫 20 行结束，翻到第几页都一样快。限制也很明确：

| 限制 | 说明 |
|---|---|
| 不能跳页 | 只能上一页 / 下一页，没有"第 500 页" |
| 排序字段必须能唯一确定顺序 | 单用 `created_at` 会在同一秒内漏行或重复，必须补一个 `id` 当 tie-breaker |
| 排序方式不能随意切换 | 换排序字段就要换游标定义 |

选择标准很简单：**用户会真的翻到第 100 页吗？** 后台管理列表通常需要页码（那就用延迟关联，并把可翻页数封顶）；App 的信息流、消息列表、日志列表只会一直往下滚（游标分页是唯一正确答案）。要"总共多少页"就还得单独 `COUNT(*)`，而大表上 `COUNT(*)` 本身也很贵——很多产品的"共 xxx 条"其实是估算值或干脆不显示。

---

## 视图、存储过程、函数、触发器

四种"把逻辑放进数据库"的手段，语法最小示例：

```sql
-- 视图：给一条查询起个名字，本身不存数据
CREATE VIEW v_paid_orders AS
SELECT o.id, o.user_id, u.name, o.amount_cent
FROM orders o JOIN users u ON u.id = o.user_id
WHERE o.status = 'paid';

-- 存储过程：能写流程控制的一段脚本，用 CALL 调用
DELIMITER //
CREATE PROCEDURE archive_old_orders(IN before_date DATE, OUT moved INT)
BEGIN
  INSERT INTO orders_archive SELECT * FROM orders WHERE created_at < before_date;
  DELETE FROM orders WHERE created_at < before_date;
  SET moved = ROW_COUNT();
END //
DELIMITER ;

-- 函数：必须有返回值，可以出现在 SELECT 里
CREATE FUNCTION fn_level(total INT) RETURNS VARCHAR(10) DETERMINISTIC
RETURN CASE WHEN total > 100000 THEN 'gold' WHEN total > 10000 THEN 'silver' ELSE 'normal' END;

-- 触发器：某张表被写入时自动执行
CREATE TRIGGER trg_order_log AFTER UPDATE ON orders FOR EACH ROW
INSERT INTO order_logs (order_id, old_status, new_status)
VALUES (NEW.id, OLD.status, NEW.status);
```

### 为什么现代应用基本不用存储过程和触发器

不是因为它们性能差——把计算放在数据里、少几次网络往返，性能往往更好。真正的问题是工程性的：

| 问题 | 具体表现 |
|---|---|
| 版本管理 | 逻辑活在数据库里而不是 git 里。改了没人知道改了什么、谁改的、能不能回滚。就算用迁移脚本管起来，也没法 diff 和 code review |
| 调试与测试 | 没有断点、没有堆栈、没有日志框架，排查靠 `SELECT` 打印。单元测试要起一个真数据库并灌数据 |
| 逻辑散落 | 读应用代码时看到一句 `UPDATE orders`，完全不知道背后还触发了三个触发器和一次级联。**触发器是最典型的"看不见的副作用"**，新人接手时必踩 |
| 扩容受限 | 应用服务器加机器就能扩，数据库是全系统最难水平扩展的一环。把 CPU 密集的逻辑塞进数据库，等于把压力压在最脆弱的地方 |
| 迁移与云化 | 存储过程语法是 MySQL 方言，换数据库、上云托管、做读写分离时全部要重写 |
| 可观测性 | APM、链路追踪、错误上报都覆盖不到数据库内部，线上出问题看不到 |

判断：**业务逻辑写在应用层，数据库只负责存储和约束。** 例外是三类：

- **视图**可以留着，用来做权限隔离（给报表账号一个不含手机号的视图）或字段改名后的兼容层。注意视图不能建索引，别在视图上再套视图。
- **一次性的数据修复和归档脚本**用存储过程写没问题，它本来就是临时的。
- **强一致的审计需求**如果法务要求"任何路径的修改都必须留痕"，触发器是唯一能挡住手工 SQL 的手段——这种时候它的"隐式"反而是优点。

---

## Node 侧连接 MySQL

ORM 之外还有一层：`mysql2` 裸驱动。知道它怎么用，才能在 ORM 生成的 SQL 不够好时接手。

### execute 与 query 的区别

```typescript
import mysql from 'mysql2/promise'

const pool = mysql.createPool({
  host: process.env.DB_HOST,
  user: process.env.DB_USER,
  password: process.env.DB_PASSWORD,
  database: process.env.DB_NAME,
  connectionLimit: 10,        // 单个进程最多持有 10 条连接
  waitForConnections: true,   // 池满时排队而不是立即报错
  queueLimit: 0,              // 排队长度不限（生产建议设一个上限，快速失败好于雪崩）
  timezone: 'Z',              // 显式声明按 UTC 解析时间，别用默认
})

// ✅ execute：服务端预编译，SQL 结构和参数分开传输
const [rows] = await pool.execute(
  'SELECT id, name FROM users WHERE city = ? AND age > ? LIMIT ?',
  [city, minAge, 20],
)

// ❌ 字符串拼接：city 传入 "' OR 1=1 --" 就能拖走整张表
const [bad] = await pool.query(`SELECT * FROM users WHERE city = '${city}'`)
```

| | `query` | `execute` |
|---|---|---|
| 协议 | 文本协议，SQL 拼好后整条发过去 | 二进制协议，先 `PREPARE` 再传参 |
| 防注入 | 用 `?` 占位符时由驱动做客户端转义，安全；一旦手工拼接就完全没有防护 | 参数**从不参与 SQL 解析**，注入在原理上不可能 |
| 性能 | 每次都要解析 SQL | 同一条 SQL 反复执行时复用执行计划 |
| 默认选择 | 只在 `execute` 用不了时用 | ✅ 默认用它 |

**注入的根源不是用了哪个方法，而是有没有拼接字符串。** 参数化是唯一可靠的防线，ORM 也只是替你做了这件事。

三个实践坑：

- **表名、列名不能参数化。** `ORDER BY ?` 传进去会变成一个字符串常量，排序失效。动态排序字段必须走白名单映射（`const SORT = { time: 'created_at', amount: 'amount_cent' }`），或用 `mysql2` 的 `??` 标识符转义。这是排序、筛选类接口最容易被注入的地方。
- **变长 `IN` 列表会撑爆预处理缓存。** `WHERE id IN (?,?,?)` 每换一个长度就是一条新 SQL，`execute` 会为每条缓存一个 prepared statement。要么用 `query('... IN (?)', [ids])` 让驱动展开数组，要么把占位符数量对齐到固定档位。
- **批量插入用 `query`。** `query('INSERT INTO t (a, b) VALUES ?', [[[1, 2], [3, 4]]])` 会展开成多值 INSERT，一次网络往返写几千行；`execute` 不支持这种嵌套数组展开。

### 连接池与连接泄漏

`connectionLimit` 的取值：不是越大越好。MySQL 的 `max_connections` 默认 151，而每个连接在服务端都要占内存和一个线程。算法是 `每实例池大小 × 实例数 + 运维预留 < max_connections`，通常单实例 10~20 就够——数据库能真正并发执行的查询数受限于 CPU 和磁盘，池子开到 100 只会让请求在数据库内部排队，反而更慢。

需要事务时必须手动取连接，因为事务是连接级别的状态：

```typescript
const conn = await pool.getConnection()
try {
  await conn.beginTransaction()
  await conn.execute('UPDATE products SET stock = stock - ? WHERE id = ? AND stock >= ?', [qty, pid, qty])
  await conn.execute('INSERT INTO orders (user_id, amount_cent) VALUES (?, ?)', [uid, amount])
  await conn.commit()
} catch (e) {
  await conn.rollback()
  throw e
} finally {
  conn.release()          // ⚠️ 少了这一行就是连接泄漏
}
```

`release()` 必须在 `finally` 里。忘了它的症状很有辨识度：**服务刚启动一切正常，跑一段时间后所有数据库请求一起卡住、没有报错、只是永远不返回**，因为池子里 10 条连接全被借走没还，新请求在队列里等一个永远不会回来的连接。确认方法是在 MySQL 里 `SHOW PROCESSLIST`，看到一堆 `Sleep` 状态且时间很长的连接就是它。

### 什么时候直接用驱动比 ORM 更合适

| 场景 | 原因 |
|---|---|
| 复杂报表 | 多层 CTE、窗口函数、`STRAIGHT_JOIN` 这类 ORM 表达不了或表达得很别扭的 SQL，硬用 ORM 拼出来比手写 SQL 更难维护 |
| 批量导入 | 多值 INSERT、`INSERT ... ON DUPLICATE KEY UPDATE`、`LOAD DATA`。ORM 逐条 save 会慢几十倍 |
| 大结果集导出 | 驱动的流式查询能一行行处理，ORM 通常先把全部结果实例化成对象，内存直接爆 |
| 明确要控制执行计划 | 需要看 `EXPLAIN` 逐字调优的热点查询，ORM 生成的 SQL 不可控 |
| 数据修复脚本 | 一次性任务，不值得为它建 Entity |

两者可以共存：日常 CRUD 用 ORM 保证类型安全和开发效率，上面这几类用 `getRawConnection`（TypeORM 的 `query`、Prisma 的 `$queryRaw`）落到原生 SQL。判断标准是"这段逻辑的核心价值在业务对象上，还是在 SQL 本身"。

---

## 综合练习

用前面那组表。建议先自己写，再看答案。

**1.** 列出所有用户，以及每人 2026 年的已支付订单数和总金额；没有订单的用户也要出现，数量显示 0。

::: details 参考答案
```sql
SELECT u.id, u.name,
       COUNT(o.id) AS paid_cnt,
       COALESCE(SUM(o.amount_cent), 0) AS total_cent
FROM users u
LEFT JOIN orders o
  ON o.user_id = u.id AND o.status = 'paid' AND o.created_at >= '2026-01-01'
GROUP BY u.id, u.name;
```
两个条件必须写在 `ON` 里。写进 `WHERE` 会把无订单的用户过滤掉；`COUNT(o.id)` 而不是 `COUNT(*)`，因为后者会把 NULL 行也数成 1。
:::

**2.** 找出注册超过 30 天但从未下过任何订单的用户。

::: details 参考答案
```sql
SELECT u.id, u.name
FROM users u
WHERE u.created_at < DATE_SUB(NOW(), INTERVAL 30 DAY)
  AND NOT EXISTS (SELECT 1 FROM orders o WHERE o.user_id = u.id);
```
也可以用 `LEFT JOIN ... WHERE o.id IS NULL`。用 `NOT IN (SELECT user_id FROM orders)` 则有 NULL 陷阱。
:::

**3.** 判断题：`SELECT * FROM products WHERE category_id NOT IN (SELECT category_id FROM categories_off)` 在 `categories_off.category_id` 存在 NULL 时返回什么？

::: details 参考答案
返回空集，且不报错。`NOT IN` 展开后含 `category_id <> NULL`，恒为 UNKNOWN，整个 `AND` 永不为 TRUE。改用 `NOT EXISTS`，或在子查询里加 `WHERE category_id IS NOT NULL`。
:::

**4.** 每个品类里销量最高的 3 个商品，输出品类 ID、商品名、销量、名次。

::: details 参考答案
```sql
SELECT category_id, name, sales, rn
FROM (
  SELECT category_id, name, sales,
         ROW_NUMBER() OVER (PARTITION BY category_id ORDER BY sales DESC, id) AS rn
  FROM products
) t
WHERE rn <= 3;
```
要"含并列的前三名"就把 `ROW_NUMBER` 换成 `DENSE_RANK`。窗口函数不能直接写在 `WHERE` 里，必须套一层。
:::

**5.** 取出每个用户最近一笔订单的完整信息（不只是时间）。

::: details 参考答案
```sql
SELECT * FROM (
  SELECT o.*, ROW_NUMBER() OVER (PARTITION BY o.user_id ORDER BY o.created_at DESC, o.id DESC) AS rn
  FROM orders o
) t WHERE rn = 1;
```
经典错误写法是 `SELECT user_id, MAX(created_at), amount_cent ... GROUP BY user_id`——在 `ONLY_FULL_GROUP_BY` 下会报错，关掉它则 `amount_cent` 取到的是随机某行的值。
:::

**6.** 输出 2026 年每天的已支付 GMV、截至当天的累计 GMV，以及相比前一天的增长率。

::: details 参考答案
```sql
WITH daily AS (
  SELECT DATE(created_at) AS d, SUM(amount_cent) AS amount
  FROM orders WHERE status = 'paid' AND created_at >= '2026-01-01'
  GROUP BY DATE(created_at)
)
SELECT d, amount,
       SUM(amount) OVER (ORDER BY d ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cumulative,
       ROUND((amount - LAG(amount) OVER (ORDER BY d)) * 100.0
             / NULLIF(LAG(amount) OVER (ORDER BY d), 0), 2) AS growth_pct
FROM daily ORDER BY d;
```
先按天聚合再开窗，否则默认的 `RANGE` 帧会把同一天的多行算在一起。
:::

**7.** 已有索引 `idx_uc (user_id, status, created_at)`，判断下面四个查询各能用到索引的哪几列。

```sql
-- A: WHERE user_id = 7 AND status = 'paid' ORDER BY created_at DESC
-- B: WHERE status = 'paid' AND created_at > '2026-01-01'
-- C: WHERE user_id = 7 AND created_at > '2026-01-01'
-- D: WHERE user_id = 7 AND status > 'p' AND created_at = '2026-01-01'
```

::: details 参考答案
A：三列全用上，且 `ORDER BY` 靠索引天然有序，无 filesort——这是最理想的形态。
B：**用不上**（缺最左列 `user_id`），只能全表扫或全索引扫。
C：只用到 `user_id`，`created_at` 因为中间的 `status` 断了而无法定位，但可能出现索引条件下推。
D：用到 `user_id` 和 `status`；`status` 是范围条件，之后的 `created_at` 在索引里不再有序，失效。
:::

**8.** 优化这条慢查询（`orders` 表 200 万行）：`SELECT * FROM orders WHERE DATE(created_at) = '2026-08-01' ORDER BY id DESC LIMIT 100000, 20;`

::: details 参考答案
两个问题叠在一起。第一，`DATE()` 包裹了索引列，改成范围条件：`WHERE created_at >= '2026-08-01' AND created_at < '2026-08-02'`。第二，深翻分页要么改延迟关联（子查询只取 `id`，靠 `(created_at, id)` 覆盖索引扫描），要么改成游标分页 `WHERE created_at >= ... AND id < 上一页最后一个 id`。同时把 `SELECT *` 收窄成真正需要的列，为覆盖索引留出可能。
:::

---

## 小结

一条 SQL 从"能跑"到"能上生产"，要过四道关：**语义对不对**（`ON` 和 `WHERE` 放错位置结果就变了）、**NULL 处理对不对**（`NOT IN`、`COUNT`、聚合函数遇到 NULL 的行为都不一样）、**能不能走索引**（最左前缀、别用函数包列）、**数据量涨十倍还行不行**（深翻分页、相关子查询、`SELECT *` 都是随规模劣化的写法）。

`EXPLAIN` 是唯一可靠的裁判。任何"这样写更快"的经验，包括这篇里的，都应该在你自己的数据量上验证一遍。












