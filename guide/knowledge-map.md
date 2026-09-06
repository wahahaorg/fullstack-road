---
title: 全栈知识地图
description: 按目标、技术栈与能力层级浏览全栈知识站的全部笔记
---

# 全栈知识地图

本站不是按“先学完一门语言，再开始做项目”组织的。你可以从当前任务出发，沿着一条最短路径补齐语言、框架、数据与工程能力。

::: tip 怎么用这张地图
先选一个目标，只读主线文章；遇到不熟悉的概念，再沿“关联能力”横向补课。不要从侧边栏第一篇一路顺序读到底。
:::

## 按目标开始

| 你的目标 | 建议入口 | 接下来读 | 最终产出 |
| --- | --- | --- | --- |
| 做 Agent 应用开发 | [Agent 工程总览](./agent-intro) | [LangGraph 状态机](./agent-langgraph) → [Tool Calling 与 MCP](./agent-tool-calling) → [Multi-Agent 与人工兜底](./agent-multi-agent) | 一条可恢复、可审计、敢接敏感操作的 Agent 链路 |
| 做能溯源的知识库问答 | [RAG 入库链路](./rag-pipeline) | [混合检索与 Rerank](./rag-retrieval) → [引用溯源与拒答](./rag-citation) → [评测方法](./agent-eval) | 一套带引用、能拒答、有评测数据支撑的 RAG 服务 |
| 完成一个 Agent 求职项目 | [企业知识库 Agentic RAG 实战](./agentic-rag-project) | 固定 RAG → 权限与异步入库 → LangGraph 多轮检索 → 评测与部署 | 一套可运行、可验证、能解释设计取舍的 Python AI 项目 |
| 做自然语言取数（Text2SQL） | [Text2SQL 与 Schema Linking](./agent-text2sql) | [SQL 基础与查询](./sql-basics) · [MySQL 日志、备份恢复与复制](./mysql-recovery) · [PostgreSQL 基础与实战](./postgresql) → [评测方法](./agent-eval) | 一条生成受约束、执行有兜底的取数链路 |
| 前端转 Python 后端 | [Python 快速入门](./python-intro) | [FastAPI 基础](./fastapi-basics) → [项目结构](./fastapi-mysql-project) | 一个分层清晰、可连接 MySQL 的 API |
| 强化 Node.js 面试 | [Node.js 运行时](./node-runtime) | [异步编程](./node-async) → [性能与稳定性](./node-perf) → [实战练习](./node-practice) | 能从运行时原理解释线上问题 |
| 系统掌握 NestJS | [NestJS 架构概览](./nestjs-intro) | [依赖注入](./nestjs-di) → [请求生命周期](./nestjs-pipeline) → [认证与登录状态](./nestjs-auth) → [项目架构蓝图](./nestjs-project-blueprint) | 一套可维护的企业级接口骨架 |
| 转向 Java / Spring Boot | [Java 学习路线](./java-learning-path) | [核心语法](./java-core-syntax) → [理解工程](./java-engineering) → [Spring Boot](./java-springboot-intro) | 能读懂并参与 Java 后端项目 |
| 学习 Go 高并发服务 | [Go 快速入门](./go-intro) | [类型与泛型](./go-advanced-types) → [并发模式](./go-advanced-concurrency) → [工程化](./go-advanced-engineering) | 能写并解释并发 HTTP 服务 |
| 补齐数据库与一致性 | [后端思维补齐](./backend-thinking) | [表结构设计](./mysql-table-design) → [SQL](./sql-basics) → [事务与一致性](./concurrency-transaction) | 能设计数据模型并处理并发写入 |
| 掌握部署与异步架构 | [Docker 与部署](./docker-deployment) | [Worker](./background-worker) → [Redis](./redis-deep) → [消息队列](./message-queue) | 能拆分 Web、任务与基础设施 |

## 能力分层

### 0. Agent 与 RAG（AI 应用层）

- **Agent 编排**：[工程总览](./agent-intro) · [范式与框架选型](./agent-patterns) · [LangGraph 状态机](./agent-langgraph) · [Tool Calling 与 MCP](./agent-tool-calling) · [Multi-Agent 与人工兜底](./agent-multi-agent)
- **检索增强**：[入库链路](./rag-pipeline) · [混合检索与 Rerank](./rag-retrieval) · [引用溯源与拒答](./rag-citation) · [多模态文档](./rag-multimodal)
- **数据问答**：[Text2SQL 与 Schema Linking](./agent-text2sql)
- **交互与度量**：[SSE 流式与阶段事件](./agent-streaming) · [AI 应用前端](./agent-frontend) · [评测方法](./agent-eval)
- **上生产**：[Prompt 注入攻防](./agent-security) · [可观测性与成本](./agent-observability) · [预算与熔断](./agent-reliability) · [上下文工程](./agent-context) · [部署与交付](./agent-deploy)
- **综合实战**：[企业知识库 Agentic RAG：项目目标与架构](./agentic-rag-project)

这一层依赖下面所有层：Agent 的异步入库要用[Worker](./background-worker)，会话记忆要用[Redis](./redis-deep)，元数据要靠[表结构设计](./mysql-table-design)，流式接口要靠[FastAPI 进阶](./fastapi-advanced)。**Agent 做不稳，问题通常不在 Prompt，而在这些底座上。**

### 1. 语言与运行时

- **Python**：[语法入门](./python-intro) · [类与 OOP](./python-class) · [工程进阶](./python-engineering)
- **Node.js**：[运行时](./node-runtime) · [模块系统](./node-module-system) · [异步模型](./node-async) · [Stream](./node-stream)
- **Go**：[快速入门](./go-intro) · [类型系统](./go-advanced-types) · [并发模型](./go-advanced-concurrency)
- **Java**：[去陌生化](./java-intro) · [核心语法](./java-core-syntax) · [数据结构](./java-data-structures) · [工程结构](./java-engineering)

### 2. Web 框架与接口设计

- **FastAPI**：[基础](./fastapi-basics) · [MySQL 项目结构](./fastapi-mysql-project) · [生产级进阶](./fastapi-advanced)
- **NestJS**：[架构](./nestjs-intro) · [装饰器](./nestjs-decorators) · [元数据与 Reflector](./nestjs-metadata-reflector) · [依赖注入](./nestjs-di) · [动态模块](./nestjs-dynamic-module) · [请求生命周期](./nestjs-pipeline) · [RxJS 与 Interceptor](./nestjs-rxjs-interceptor) · [校验与异常](./nestjs-validation-filter) · [DTO 与 Swagger](./nestjs-dto) · [TypeORM](./nestjs-database) · [Prisma](./nestjs-prisma) · [GraphQL](./nestjs-graphql) · [文件上传](./nestjs-file-upload) · [日志](./nestjs-logging) · [定时任务与事件](./nestjs-schedule-events) · [实时通信](./nestjs-realtime) · [微服务](./nestjs-microservice) · [生产清单](./nestjs-advanced) · [项目蓝图](./nestjs-project-blueprint)
- **Spring Boot**：[框架入门](./java-springboot-intro) · [数据库](./java-database) · [鉴权](./java-auth) · [调用 Python Agent](./java-call-python)
- **Node 原生能力**：[HTTP 与 BFF](./node-http) · [性能与稳定性](./node-perf)

### 3. 数据、状态与可靠性

- **建模与查询**：[MySQL 表结构设计](./mysql-table-design) · [SQL 基础与查询](./sql-basics) · [数据库外键](./foreign-keys) · [MySQL 日志、备份恢复与复制](./mysql-recovery) · [PostgreSQL 基础与实战](./postgresql)
- **一致性**：[并发、事务与一致性](./concurrency-transaction) · [锁机制与并发控制](./locking) · [分布式一致性与可靠消息](./distributed-consistency) · [Redis 深入](./redis-deep)
- **异步系统**：[Worker 与异步任务](./background-worker) · [消息队列](./message-queue)
- **认证授权**：[NestJS 认证与登录状态](./nestjs-auth) · [授权模型与三方登录](./nestjs-authorization) · [Java 登录与鉴权](./java-auth)

### 4. 工程、部署与实战

- **部署**：[Docker 与部署](./docker-deployment) · [Dockerfile 进阶](./dockerfile-practice) · [Compose 与进程守护](./docker-compose-network) · [Nginx 流量治理](./nginx-core)
- **完整项目**：[企业知识库 Agentic RAG](./agentic-rag-project) · [FastAPI + MySQL 项目](./fastapi-mysql-project) · [Java 学习时间记录系统](./java-project-practice)
- **代码阅读**：[阅读陌生 Java 项目](./java-reading-project)
- **练习与面试**：[综合练习](./exercises) · [Node.js 实战练习](./node-practice) · [Java 招聘要求判断](./java-job-requirements)

## 跨栈对照

同一个后端概念，在不同技术栈里只是名字和实现方式不同：

| 能力 | FastAPI | NestJS | Spring Boot |
| --- | --- | --- | --- |
| 路由入口 | `APIRouter` | `Controller` | `@RestController` |
| 请求校验 | Pydantic Schema | DTO + Pipe | DTO + Bean Validation |
| 依赖管理 | `Depends` | Provider + DI | Bean + DI |
| 鉴权入口 | 鉴权依赖 | Guard | Security Filter Chain |
| 业务逻辑 | Service 函数 / 类 | Service Provider | `@Service` |
| 数据访问 | SQLAlchemy | TypeORM | JPA / MyBatis |

理解这张表后，迁移技术栈时应优先寻找“职责对应关系”，而不是逐行翻译语法。

## 推荐阅读顺序

```mermaid
flowchart LR
  A[选择一个业务目标] --> B[语言与运行时]
  B --> C[框架与接口]
  C --> D[数据建模]
  D --> E[事务与一致性]
  E --> F[部署与可观测运行]
  F --> G[项目复盘与面试表达]
```

如果你还不确定从哪里开始，先读[这套教程怎么学](./learning-path)；如果已经有明确技术方向，直接从上面的目标表进入即可。

## 继续补全的方向

网络排障、锁机制、分布式一致性与可靠消息已加入主线。下一阶段按以下顺序补齐：

1. **Linux 与服务故障排查**：从 CPU、内存、磁盘、端口与连接异常定位原因，衔接已有 Nginx 与 Docker 内容。
2. **后端并发与故障测试实战**：用真实数据库、并发连接和可控故障验证超卖、重复消费与恢复路径。
3. **Java 求职分支**：JVM、Java 并发与性能诊断，按具体求职目标深入。

已完成的 [MySQL 日志、备份恢复与复制](./mysql-recovery) 以及已有的 [SQL 进阶与查询优化](./mysql-advanced)、[Redis 实战](./redis-practice)、[Nginx 流量治理](./nginx-core) 继续作为深入入口。新增章节以“解释机制、复现问题、验证恢复”为标准；通用测试章还未完成，各章练习不等于已有可运行测试工程。

> 信息架构参考：[heibaiying/Full-Stack-Notes](https://github.com/heibaiying/Full-Stack-Notes)。本站仅借鉴其按领域组织并为文章补充摘要的方式，未复制其文章与图片。
