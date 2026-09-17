---
title: Spring、数据与中间件：把接口写成可维护的工程
description: Spring IoC 与 Bean 生命周期、分层边界、测试与 Security、MySQL 优化、Redis 缓存体系、消息队列与定时任务，补齐 Java 企业项目的中段能力。
---

# Spring、数据与中间件：把接口写成可维护的工程

这篇覆盖 [Java 企业级进阶路线](./java-enterprise-path) 的阶段二和阶段三：Spring 工程能力，以及数据库与中间件。它是"能写接口"到"能维护一个中等复杂度模块"之间缺的那一段。

对应外部 `java-full-stack` 路线的阶段二（Spring 生态与 Web 开发核心）与阶段三（数据持久化与中间件）。这里按本站习惯压缩成"先讲边界，再讲信号"，框架细节留给官方文档。

## Spring 的核心只有一句话

Spring 的核心不是注解多，而是**对象不由你 new，由容器管理**。你声明"我需要一个 `OrderService`"，容器负责创建、注入、管理它的生命周期。

由此推出三条工程规则：

- Bean 默认单例：单例里的可变实例字段就是共享状态，天然有并发风险（见 [JVM 与并发基础](./java-jvm-concurrency)）。
- 依赖靠构造器注入：字段注入（`@Autowired` 直接打在字段上）会隐藏依赖、妨碍测试。
- 配置绑定集中在 `application.yml` + `@ConfigurationProperties`，不要在代码里散落 `System.getenv`。

## 分层边界：什么逻辑放哪一层

| 层 | 职责 | 不该做 |
|---|---|---|
| Controller | 参数绑定、校验、调 Service、组装响应 | 写业务规则、直接操作数据库 |
| Service | 业务规则、事务边界、编排多个数据操作 | 处理 HTTP 细节、拼 SQL |
| Repository / Mapper | 一条 SQL 对应一个数据操作 | 写业务判断 |
| DTO / VO / Entity | DTO 进出接口，Entity 映射表，VO 给前端展示 | 三者混用，把 Entity 直接序列化给前端 |

自检：把 Controller 里的逻辑搬走后，它还剩参数校验和调 Service 吗？把 Service 里的 `@Transactional` 边界画出来，它是否恰好覆盖"要么都成功要么都失败"的那组操作？这两个问题能定位大部分分层混乱。

## 事务：`@Transactional` 的三个坑

- **自调用失效**：同类里 A 方法调 B 方法，B 上的 `@Transactional` 不生效（没走代理）。解决：拆到另一个 Bean，或注入自身代理。
- **rollbackFor 默认只回滚 RuntimeException**：受检异常默认不回滚，显式写 `@Transactional(rollbackFor = Exception.class)` 更安全。
- **事务里调外部服务**：事务内发 HTTP、发 MQ、调 LLM，会把连接占住还可能回滚不掉已发出的副作用。原则：事务只包数据库操作，外部调用放事务提交后（如 `TransactionSynchronization` 或 MQ 的事务消息）。

## 测试：三个层次各有分工

| 层次 | 写法 | 快慢 |
|---|---|---|
| 单元测试 | 纯 Service 逻辑，Mock 依赖，不启 Spring | 毫秒级，写最多 |
| 切片测试 | `@WebMvcTest` / `@DataJpaTest`，只装配一层 | 中等，测边界 |
| 集成测试 | `@SpringBootTest` + Testcontainers 起真数据库 | 慢，测关键链路 |

底线：核心业务规则必须有单元测试；下单、支付、鉴权这类链路必须有集成测试。Testcontainers 比 H2 内存库更接近生产，尤其是用到 MySQL 方言、锁、JSON 字段时。

## Spring Security：先抓模型再看配置

Security 的配置看起来复杂，模型其实两句话：

- **认证（Authentication）回答"你是谁"**：JWT 过滤器解析 token → 构造 `Authentication` → 放进 `SecurityContext`。
- **授权（Authorization）回答"你能做什么"**：按 URL 规则、方法注解（`@PreAuthorize`）或业务代码判断权限。

常见工程问题都出在两者混在一起：把"未登录"和"没权限"返回同一个错误；把角色判断写在 Controller 里；JWT 里塞了过多信息导致改权限必须重发 token。本站 [登录与接口鉴权](./java-auth) 有完整落地方案。

## MySQL：索引与慢查询的最小工作集

深入内容见 [MySQL 进阶](./mysql-advanced)，这里只给每天会用的部分：

- **索引命中三问**：这个查询用了哪个索引（`EXPLAIN`）？组合索引是否满足最左前缀？是否有隐式类型转换（字符串列用数字查）导致索引失效？
- **慢查询定位**：开 slow query log，按 `Rows_examined / Rows_sent` 比例找坏查询——扫描一万行只返回十条，多半是索引问题。
- **深分页**：`LIMIT 100000, 20` 会扫描十万行，改成游标方式（`WHERE id > last_id LIMIT 20`）。
- **大事务**：一个事务里更新几万行会拖垮主从延迟和锁等待，拆批处理。

## Redis 缓存体系：三个问题 + 三个经典故障

用缓存前先回答三个问题：这个数据能容忍多久不一致？读多写多还是读多写少？缓存挂了数据库能不能扛住？

三个经典故障与对策：

| 故障 | 场景 | 对策 |
|---|---|---|
| 穿透 | 查不存在的 key，每次都打到 DB | 空值缓存短 TTL；布隆过滤器 |
| 击穿 | 热 key 过期瞬间大量请求打 DB | 互斥锁重建；逻辑过期不真删 |
| 雪崩 | 大量 key 同时过期 | TTL 加随机抖动；多级缓存；限流兜底 |

缓存一致性最常用的是"先更新数据库，再删缓存"（Cache-Aside），并接受删除失败带来的短暂不一致——用延迟双删或订阅 binlog 补偿。追求强一致就不要用缓存。

更多场景见 [Redis 深入](./redis-deep) 与 [Redis 实战场景](./redis-practice)。

## 消息队列：为什么用，以及代价

MQ 解决两个问题：**削峰**（瞬时流量排队处理）和**解耦**（下单方不关心下游有谁）。代价是引入了异步的复杂性，必须回答：

- **消息丢了怎么办**：生产者确认、broker 持久化、消费者手动 ack，三段都要开。
- **重复消费怎么办**：消费端必须幂等——用业务唯一键 + 去重表/状态机，不要假设"只投递一次"。
- **消费失败怎么办**：有限次重试 → 死信队列 → 人工/补偿任务处理，不要无限重试堵住队列。

选型上，本站项目用 RabbitMQ/Redis Stream 起步足够；Kafka 适合高吞吐日志流，RocketMQ 在事务消息和定时消息上有现成能力。原理与对比见 [消息队列](./message-queue)。

## 定时任务与批处理

Spring 的 `@Scheduled` 够用但有两个边界：多实例部署会重复执行（需要分布式锁或任务分片），失败没有重试和告警。任务多了再考虑 XXL-Job 这类调度平台。批处理（对账、报表、数据迁移）注意分页读取、失败断点续跑、限速避免打爆在线库。

## 阶段自检

- 你能画出当前项目的事务边界，并解释为什么这样划分吗？
- 一次接口慢查询，你能说出 EXPLAIN 里该看哪几个字段吗？
- 消息被消费三次，你的业务状态会不会错？依据是什么？
- 缓存与数据库不一致时，你能接受多久、靠什么机制收敛？

## 下一步

- [分布式、云原生与架构](./java-distributed-cloud-architecture)：服务拆开之后的问题。
- [MySQL 表结构设计](./mysql-table-design)、[MySQL 进阶](./mysql-advanced)、[Redis 深入](./redis-deep)、[消息队列](./message-queue)：按需深入。

## 来源与授权说明

本篇吸收并改写自 [umlink/java-full-stack](https://github.com/umlink/java-full-stack) 阶段二（Spring 生态与 Web 开发核心）与阶段三（数据持久化与中间件）的主题结构，已取得作者授权。原项目采用 [MIT License](https://github.com/umlink/java-full-stack/blob/main/LICENSE)。
