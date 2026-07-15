# MySQL 表结构设计

## 这一章解决什么问题

你说自己“建表能力弱”，这通常不是 SQL 语法不会，而是缺少这条链路：

```txt
业务规则 → 实体关系 → 字段约束 → 索引 → SQL → 并发检查
```

前端工程师容易从页面出发：

```txt
页面有什么字段，我就建什么字段
```

后端要从业务对象出发：

```txt
哪些对象有生命周期？
它们之间是什么关系？
哪些规则必须由数据库兜底？
未来查询会按什么条件发生？
```

## 建表的八步法

### 1. 圈出业务名词

例如需求：

> 用户可以创建知识库，向知识库上传文档。文档解析后生成多个切片，每个切片会写入向量库。用户可以查看文档解析状态。

名词有：

```txt
用户
知识库
文档
切片
向量
解析状态
```

不是所有名词都要成表。状态通常是字段，用户、知识库、文档、切片更像实体。

### 2. 判断实体是否需要独立生命周期

判断一个名词要不要单独成表，问五个问题：

```txt
它是否需要自己的 ID？
它是否会独立新增、修改、删除、查询？
它是否有多个属性？
它是否会被多个对象引用？
它是否需要保存历史？
```

比如“文档”需要文件名、大小、状态、上传人、解析时间，所以应该成表。

“解析状态”通常只是文档或任务的字段。

### 3. 判断关系

常见关系只有三类：

```txt
一对一：user 1 ── 1 user_profile
一对多：knowledge_base 1 ── N document
多对多：user N ── N role
```

一对多时，外键放在“多”的一方：

```sql
CREATE TABLE documents (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  knowledge_base_id BIGINT UNSIGNED NOT NULL,
  title VARCHAR(200) NOT NULL
);
```

多对多时，用中间表：

```sql
CREATE TABLE user_roles (
  user_id BIGINT UNSIGNED NOT NULL,
  role_id BIGINT UNSIGNED NOT NULL,
  PRIMARY KEY (user_id, role_id)
);
```

### 4. 设计主键

业务系统里常见做法：

```sql
id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY
```

为什么不用手机号、订单号直接做主键？

- 业务字段可能变。
- 字符串主键索引更大。
- 业务字段有时需要脱敏或迁移。

但业务唯一字段仍然要加唯一索引：

```sql
order_no VARCHAR(64) NOT NULL,
UNIQUE KEY uk_order_no (order_no)
```

### 5. 设计核心字段

常见字段类型：

| 场景 | 推荐类型 | 例子 |
| --- | --- | --- |
| ID | `BIGINT UNSIGNED` | `user_id` |
| 名称 | `VARCHAR(n)` | `name VARCHAR(64)` |
| 长文本 | `TEXT` | `description TEXT` |
| 金额 | `DECIMAL(18,2)` 或整数分 | `amount_cent BIGINT` |
| 状态 | `VARCHAR(32)` 或 `TINYINT` | `status VARCHAR(32)` |
| 时间 | `DATETIME(3)` | `created_at DATETIME(3)` |
| 灵活配置 | `JSON` | `metadata JSON` |

不要所有字段都写 `VARCHAR(255)`。长度应来自业务规则。

### 6. 设计通用字段

大多数业务表都建议有：

```sql
created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
  ON UPDATE CURRENT_TIMESTAMP(3)
```

如果需要软删除：

```sql
deleted_at DATETIME(3) NULL
```

如果需要审计：

```sql
created_by BIGINT UNSIGNED NULL,
updated_by BIGINT UNSIGNED NULL
```

如果需要乐观锁：

```sql
version INT UNSIGNED NOT NULL DEFAULT 0
```

### 7. 设计约束

约束是后端安全感的来源。

常见约束：

```sql
NOT NULL
DEFAULT
PRIMARY KEY
UNIQUE KEY
FOREIGN KEY
CHECK
```

例如同一个知识库下文档名不能重复：

```sql
UNIQUE KEY uk_kb_title (knowledge_base_id, title)
```

这比代码里先查再插更可靠，因为并发场景下两个请求可能同时查到“不存在”。

### 8. 设计索引

索引不是越多越好。先从查询场景出发：

```txt
是否经常按 user_id 查？
是否经常按 status 查？
是否经常按 created_at 排序？
是否经常组合查询 user_id + status？
```

例如任务列表：

```sql
KEY idx_user_status_created (user_id, status, created_at)
```

索引会提升查询，但也会增加写入成本，所以核心是匹配真实查询。

## 示例：知识库文档表

需求：

> 用户创建知识库，上传文档。文档需要记录解析状态、文件信息、失败原因和更新时间。

### 表结构

```sql
CREATE TABLE knowledge_bases (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  owner_id BIGINT UNSIGNED NOT NULL,
  name VARCHAR(100) NOT NULL,
  description VARCHAR(500) NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
    ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uk_owner_name (owner_id, name),
  KEY idx_owner_created (owner_id, created_at)
);

CREATE TABLE documents (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  knowledge_base_id BIGINT UNSIGNED NOT NULL,
  uploader_id BIGINT UNSIGNED NOT NULL,
  title VARCHAR(200) NOT NULL,
  file_key VARCHAR(500) NOT NULL,
  file_sha256 CHAR(64) NOT NULL,
  file_size BIGINT UNSIGNED NOT NULL,
  parse_status VARCHAR(32) NOT NULL DEFAULT 'pending',
  parse_error TEXT NULL,
  parsed_at DATETIME(3) NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
    ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uk_kb_file_hash (knowledge_base_id, file_sha256),
  KEY idx_kb_status_created (knowledge_base_id, parse_status, created_at)
);

CREATE TABLE document_chunks (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  document_id BIGINT UNSIGNED NOT NULL,
  chunk_index INT UNSIGNED NOT NULL,
  content TEXT NOT NULL,
  token_count INT UNSIGNED NOT NULL DEFAULT 0,
  vector_ref VARCHAR(200) NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uk_document_chunk (document_id, chunk_index),
  KEY idx_document_id (document_id)
);
```

### 为什么这样设计

- `knowledge_bases.owner_id + name` 唯一：同一用户下知识库不能重名。
- `documents.knowledge_base_id + file_sha256` 唯一：同一知识库内同一文件不能重复入库。
- `parse_status` 放在文档表：页面经常按文档看解析状态。
- `document_chunks` 独立成表：一个文档会有多个 chunk，chunk 需要独立检索和重建。
- `vector_ref` 不直接存向量：真实向量可能在专门的向量库里，MySQL 保存引用更合适。

## 常见错误

### 错误 1：把数组塞进字符串

```sql
role_ids VARCHAR(255) -- "1,2,3"
```

问题：

- 不好 JOIN。
- 不好加约束。
- 不好查某个角色下有哪些用户。

更好的方式是中间表：

```sql
CREATE TABLE user_roles (
  user_id BIGINT UNSIGNED NOT NULL,
  role_id BIGINT UNSIGNED NOT NULL,
  PRIMARY KEY (user_id, role_id)
);
```

### 错误 2：只靠代码保证唯一

```python
if not exists_user(phone):
    create_user(phone)
```

并发下两个请求可能都判断不存在。正确做法是数据库唯一索引：

```sql
UNIQUE KEY uk_phone (phone)
```

代码捕获重复键错误，返回友好提示。

### 错误 3：状态字段没有规则

```sql
status VARCHAR(32)
```

只有字段不够，还要定义状态机：

```txt
pending → running → success
pending → running → failed
failed → pending
```

否则后续会出现各种非法状态流转。

## 面试怎么说

你可以这样回答建表思路：

> 我不会直接按页面字段建表，而是先拆业务实体和生命周期，再判断实体之间是一对一、一对多还是多对多。然后为核心业务规则设计唯一约束、非空约束和必要索引。对于会被并发修改的表，我会额外考虑版本号、状态流转、事务和幂等字段。这样表结构不只是能存数据，还能帮助系统守住业务正确性。

