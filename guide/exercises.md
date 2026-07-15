# 综合练习

## 练习方式

不要一上来就看答案。每个练习按这个顺序做：

1. 圈出实体。
2. 判断关系。
3. 写表结构。
4. 写核心 SQL。
5. 设计 FastAPI 接口。
6. 思考并发和幂等。
7. 用面试语言解释你的设计。

## 通用技巧

### 建表前问

```txt
这个对象是否需要自己的 ID？
是否会独立查询？
是否会被其他对象引用？
是否有状态？
是否要保存历史？
是否有唯一性要求？
```

### 写接口前问

```txt
这个接口是查询还是修改？
是否需要鉴权？
是否会重复调用？
修改了几张表？
是否需要事务？
失败后能否重试？
```

### 写 SQL 前问

```txt
主表是哪张？
过滤条件是什么？
是否需要 JOIN？
是否需要分页？
是否需要排序？
哪个索引能支持这个查询？
```

## 练习 1：用户地址管理

### 需求

用户可以维护多个收货地址。每个用户最多只能有一个默认地址。地址包含收件人、手机号、省市区、详细地址。

### 你要完成

- 设计表结构。
- 写“新增地址”的 SQL 或伪代码。
- 写“设置默认地址”的事务逻辑。
- 设计 FastAPI 接口。

### 思考点

```txt
默认地址如何保证只有一个？
删除默认地址后怎么办？
手机号用字符串还是数字？
地址是否需要软删除？
```

### 参考方向

表：

```sql
CREATE TABLE user_addresses (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  user_id BIGINT UNSIGNED NOT NULL,
  receiver_name VARCHAR(64) NOT NULL,
  phone VARCHAR(32) NOT NULL,
  province VARCHAR(64) NOT NULL,
  city VARCHAR(64) NOT NULL,
  district VARCHAR(64) NOT NULL,
  detail VARCHAR(255) NOT NULL,
  is_default TINYINT(1) NOT NULL DEFAULT 0,
  deleted_at DATETIME(3) NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
    ON UPDATE CURRENT_TIMESTAMP(3),
  KEY idx_user_created (user_id, created_at)
);
```

设置默认地址时，在事务里：

```sql
UPDATE user_addresses
SET is_default = 0
WHERE user_id = ? AND deleted_at IS NULL;

UPDATE user_addresses
SET is_default = 1
WHERE id = ? AND user_id = ? AND deleted_at IS NULL;
```

接口：

```txt
POST /addresses
GET /addresses
PATCH /addresses/{id}
POST /addresses/{id}/set-default
DELETE /addresses/{id}
```

## 练习 2：RBAC 权限

### 需求

系统有用户、角色、权限。一个用户可以有多个角色，一个角色可以有多个权限。

### 你要完成

- 设计 5 张表。
- 查询某个用户拥有的所有权限。
- 给用户分配角色时避免重复。

### 参考方向

核心表：

```txt
users
roles
permissions
user_roles
role_permissions
```

中间表用联合主键：

```sql
PRIMARY KEY (user_id, role_id)
```

查询权限：

```sql
SELECT DISTINCT p.code
FROM users u
JOIN user_roles ur ON ur.user_id = u.id
JOIN role_permissions rp ON rp.role_id = ur.role_id
JOIN permissions p ON p.id = rp.permission_id
WHERE u.id = ?;
```

## 练习 3：文档解析任务

### 需求

用户上传文档后，系统创建解析任务。任务有 pending、running、success、failed 四种状态。失败任务可以重试。

### 你要完成

- 设计 documents 和 parse_jobs。
- 写 worker 抢任务 SQL。
- 防止多个 worker 同时执行同一个任务。
- 设计重试接口。

### 参考方向

任务表：

```sql
CREATE TABLE document_parse_jobs (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  document_id BIGINT UNSIGNED NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'pending',
  retry_count INT UNSIGNED NOT NULL DEFAULT 0,
  error_message TEXT NULL,
  locked_at DATETIME(3) NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
    ON UPDATE CURRENT_TIMESTAMP(3),
  KEY idx_status_created (status, created_at),
  KEY idx_document_id (document_id)
);
```

抢任务可以用条件更新：

```sql
UPDATE document_parse_jobs
SET status = 'running', locked_at = NOW(3)
WHERE id = ?
  AND status = 'pending';
```

影响行数为 1 才算抢到任务。

## 练习 4：库存扣减

### 需求

用户下单购买商品，库存不能扣成负数，同一个请求不能重复创建订单。

### 你要完成

- 设计 products、orders。
- 写扣库存 SQL。
- 设计幂等键。
- 写 FastAPI 伪代码。

### 参考方向

扣库存：

```sql
UPDATE products
SET stock = stock - ?
WHERE id = ? AND stock >= ?;
```

订单表加幂等键：

```sql
UNIQUE KEY uk_idempotency_key (idempotency_key)
```

业务逻辑：

```python
async with session.begin():
    existing = await get_order_by_idempotency_key(session, key)
    if existing:
        return existing

    success = await decrease_stock(session, product_id, quantity)
    if not success:
        raise AppError("OUT_OF_STOCK", "库存不足")

    return await create_order(session, payload)
```

## 练习 5：BI 报表任务

### 需求

用户选择数据集、时间范围和筛选条件后生成报表。相同参数的报表任务不应重复创建。

### 你要完成

- 设计 report_tasks。
- 设计参数 hash。
- 查询当前用户最近 20 个任务。
- 处理重复提交。

### 参考方向

```sql
CREATE TABLE report_tasks (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  user_id BIGINT UNSIGNED NOT NULL,
  dataset_id BIGINT UNSIGNED NOT NULL,
  params_hash CHAR(64) NOT NULL,
  params_json JSON NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'pending',
  result_file_key VARCHAR(500) NULL,
  error_message TEXT NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
    ON UPDATE CURRENT_TIMESTAMP(3),
  UNIQUE KEY uk_user_dataset_params (user_id, dataset_id, params_hash),
  KEY idx_user_created (user_id, created_at)
);
```

## 练习 6：Agent 会话记录

### 需求

用户可以创建 Agent 会话，每个会话包含多条消息。消息分为 user、assistant、tool。需要支持按会话分页加载。

### 你要完成

- 设计 sessions 和 messages。
- 查询某个会话最新 30 条消息。
- 思考消息是否允许修改。
- 设计删除会话策略。

### 参考方向

```sql
CREATE TABLE agent_sessions (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  user_id BIGINT UNSIGNED NOT NULL,
  title VARCHAR(200) NOT NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
    ON UPDATE CURRENT_TIMESTAMP(3),
  KEY idx_user_updated (user_id, updated_at)
);

CREATE TABLE agent_messages (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  session_id BIGINT UNSIGNED NOT NULL,
  role VARCHAR(32) NOT NULL,
  content MEDIUMTEXT NOT NULL,
  metadata JSON NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  KEY idx_session_created (session_id, created_at)
);
```

## 练习 7：把一个模块讲给面试官

任选上面一个练习，用这个模板讲：

```txt
这个模块的核心实体是……
实体之间的关系是……
我设计了哪些唯一约束和索引……
核心接口包括……
涉及多表写入时我会用事务……
涉及重复提交时我会用幂等键……
涉及并发更新时我会用条件更新 / 行锁 / 乐观锁……
这个设计的取舍是……
```

能讲清楚这一段，你的后端感就已经明显比“只会写 CRUD”强很多。

