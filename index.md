---
layout: home

hero:
  name: 全栈知识站
  text: Agent · RAG · Python · Go · Node.js · Java
  tagline: 写给有前端经验、正在补全栈与 AI 应用能力的开发者。从语法到框架，从 Agent 编排到生产落地。
  image:
    src: /logo.svg
    alt: 全栈知识站
  actions:
    - theme: brand
      text: 🧭 打开知识地图
      link: /guide/knowledge-map
    - theme: brand
      text: 🤖 Agent 工程总览
      link: /guide/agent-intro
    - theme: brand
      text: Python 快速入门
      link: /guide/python-intro
    - theme: alt
      text: 🔍 RAG 入库链路
      link: /guide/rag-pipeline
    - theme: alt
      text: Node.js 面试题
      link: /guide/node-runtime
    - theme: alt
      text: NestJS 完全指南
      link: /guide/nestjs-intro
    - theme: alt
      text: ☕ Java 快速入门
      link: /guide/java-learning-path

features:
  - icon: 🤖
    title: Agent 工程
    details: LangGraph 状态机与 Checkpoint、Tool Calling 与工具安全分级、Multi-Agent 编排与人工兜底、MCP 协议。从能跑到能上生产的那段路。
  - icon: 🔍
    title: RAG 检索
    details: 解析与层级切分、元数据设计、BM25 + 向量双路召回、RRF 融合与 Rerank 精排、引用溯源与拒答降级，附评测方法。
  - icon: 🐍
    title: Python 语法 + FastAPI
    details: 面向 JS 开发者的 Python 快速迁移，配合 FastAPI + SQLAlchemy 2.x + Pydantic v2 的生产级用法。
  - icon: 🟢
    title: Node.js 深度原理
    details: 事件循环、Stream、模块系统、async/await、错误处理，覆盖 2026 年最新面试高频题，附 7 个实战练习。
  - icon: 🏗️
    title: NestJS 工程实践
    details: 20 章完整体系。从装饰器与元数据底层，到 DI、动态模块、AOP 五件套，再到 TypeORM/Prisma、鉴权、微服务与 gRPC 跨语言调用。
  - icon: 🗄️
    title: MySQL 与并发一致性
    details: 表结构设计、SQL 查询优化、事务隔离级别、分布式锁，从业务场景出发，不只是背概念。
  - icon: 🐳
    title: Docker 与部署
    details: Dockerfile、docker-compose、nginx 反向代理、PM2 进程管理、GitHub Actions CI/CD 完整部署工作流。
  - icon: 📦
    title: Redis · MQ · 基础设施
    details: Redis 五种数据结构和缓存策略，消息队列选型与实战，幂等消费设计，前后端衔接的完整方案。
  - icon: 🔵
    title: Go 语言入门
    details: 面向 JS/Python 开发者的 Go 快速迁移。静态类型、编译型、内置 goroutine+channel 并发模型，从语法到 HTTP 服务一步到位。
  - icon: ☕
    title: Java 快速入门
    details: 面向 TS/Node.js/NestJS/Python 开发者的 Java 教程。用类比消除陌生感，从环境搭建到 Spring Boot 实战，11 章覆盖面试与开发。
---

## 学习路径

本站的笔记可以先从[全栈知识地图](/guide/knowledge-map)进入，按目标、技术栈与能力层级找到最短路径；也可以直接选择下面的方向。

### 按当前任务进入

| 我现在想做什么 | 从这里开始 | 继续深入 |
|---|---|---|
| 搞懂 Agent 怎么编排和落地 | [Agent 工程总览](/guide/agent-intro) | [LangGraph 状态机](/guide/agent-langgraph) → [Tool Calling 与 MCP](/guide/agent-tool-calling) |
| 做一个能溯源的知识库问答 | [RAG 入库链路](/guide/rag-pipeline) | [混合检索与 Rerank](/guide/rag-retrieval) → [引用溯源与拒答](/guide/rag-citation) |
| 让自然语言查询变成可控的 SQL | [Text2SQL 与 Schema Linking](/guide/agent-text2sql) | [Agent 与 RAG 评测方法](/guide/agent-eval) |
| 从前端转向 Python 后端 | [Python 快速入门](/guide/python-intro) | [FastAPI + MySQL 项目](/guide/fastapi-mysql-project) |
| 准备 Node.js / NestJS 面试 | [Node.js 运行时](/guide/node-runtime) | [NestJS 架构概览](/guide/nestjs-intro) |
| 接手 Java / Spring Boot 项目 | [Java 学习路线](/guide/java-learning-path) | [阅读陌生项目](/guide/java-reading-project) |
| 处理慢接口、重复任务和并发写入 | [后端思维补齐](/guide/backend-thinking) | [并发、事务与一致性](/guide/concurrency-transaction) |
| 把服务部署到生产环境 | [Docker 与部署](/guide/docker-deployment) | [Worker 与异步任务](/guide/background-worker) |

## 分方向学习

### 🤖 Agent 与 RAG 工程（AI 应用方向）

```
Agent 工程总览（能力阶梯 / 什么时候不该上 Agent）
  → Agent 范式与框架选型（ReAct / Plan-Execute / Agentic RAG）
  → LangGraph 状态机与 Checkpoint
  → Tool Calling、工具安全与 MCP
  → Multi-Agent 编排、路由与人工兜底
  → SSE 流式与阶段事件协议

RAG 入库链路（解析 / 切分 / 元数据 / 增量重建）
  → 混合检索（BM25 + 向量 + RRF + Rerank）
  → 引用溯源、拒答与降级
  → 多模态文档（扫描件 / 表格 / 图表 / 区域级引用）
  → Text2SQL 与 Schema Linking

上生产：Prompt 注入攻防 → 可观测性与成本 → 预算熔断与断点续跑
  → 上下文工程与长任务 → 评测方法与回归门禁
```

底座能力可横向补：[Worker 与异步任务](/guide/background-worker)、[Redis 深入](/guide/redis-deep)、[FastAPI 进阶](/guide/fastapi-advanced)、[并发与事务](/guide/concurrency-transaction)。

### 🐍 Python 全栈后端（FastAPI 方向）

```
Python 语法入门 → 深入理解类 → Python 工程进阶 → FastAPI 基础
  → FastAPI 进阶（Pydantic/Depends/鉴权）
  → MySQL 建模 → SQL 查询 → FastAPI + MySQL 项目
  → 并发事务 → 综合练习
```

### 🟢 Node.js 全栈（面试强化）

```
Node 运行时与事件循环 → 模块系统（CJS/ESM）
  → 异步编程与错误处理 → Stream 与 Buffer
  → HTTP 与 BFF → 性能与稳定性 → 综合场景练习
```

### 🏗️ NestJS 工程能力

```
核心原理：简介与架构 → 装饰器体系 → 元数据与 Reflector
  → 依赖注入 → 动态模块与配置管理
请求处理：请求生命周期与 AOP → RxJS 与 Interceptor → 参数校验与异常
接口与数据：DTO 与 Swagger → TypeORM → Prisma → GraphQL
认证授权：认证与登录状态 → 授权模型与三方登录
工程实践：文件上传 → 日志与可观测性 → 定时任务与事件 → 生产环境清单
通信与架构：实时通信 → 微服务与 gRPC → 项目架构蓝图
```

### 🐳 部署与基础设施（所有方向通用）

```
Docker 与部署 → Worker 与异步任务 → Redis 深入 → 消息队列
  → 综合练习串联 → 完整项目实战
```

### 🔵 Go 语言（高性能服务方向）

```
Go 快速入门 → 类型系统与泛型 → 并发模式与工程实践 → 工程化实战
```

### ☕ Java（企业级后端方向）

```
Java 去陌生化 → 核心语法 → 数据结构 → 理解 Java 工程
  → Spring Boot 入门 → 数据库基础 → 登录与鉴权
  → 调用 Python Agent → 实战项目 → 阅读项目方法 → 招聘判断
```

## 各章内容速览

| 模块 | 章节数 | 核心内容 |
|---|---|---|
| **🤖 Agent 工程** | 8 章 | 能力阶梯与 ReAct / 范式与框架选型 / LangGraph 状态机与 Checkpoint / Tool Calling 与 MCP / Multi-Agent 与 HITL / SSE 流式 / Text2SQL / 评测方法 |
| **🛡️ Agent 生产化** | 4 章 | Prompt 注入攻防与守护栏 / 可观测性与成本性能 / 预算熔断与断点续跑 / 上下文工程与长任务 |
| **🔍 RAG 检索** | 4 章 | 入库链路（解析·切分·元数据）/ 混合检索（BM25+向量+RRF+Rerank）/ 引用溯源与拒答降级 / 多模态文档与区域级引用 |
| **Python** | 3 章 | 基础语法、类与 OOP、异步、类型系统 |
| **FastAPI** | 4 章 | 基础 → 项目结构 → 进阶（测试/中间件/WebSocket） |
| **数据库与建模** | 4 章 | 表结构设计 / SQL 基础 / SQL 进阶与查询优化 / MongoDB 与 Mongoose |
| **并发事务** | 2 章 | 事务原理 + 综合练习 |
| **Node.js** | 7 章 | 运行时 / 模块 / 异步 / Stream / HTTP / 性能 / 实战 |
| **NestJS** | 21 章 | 核心原理（架构·装饰器·元数据·DI·动态模块）/ 请求处理（生命周期·RxJS·校验异常）/ 接口与数据（DTO·TypeORM·Prisma·GraphQL）/ 认证授权 / 工程实践（上传·日志·定时任务·生产清单）/ 通信与架构（实时·微服务·项目蓝图） |
| **Docker 与部署** | 4 章 | 容器化与部署 / Dockerfile 进阶 / Compose 与进程守护 / Nginx 流量治理 |
| **基础设施** | 4 章 | Worker 与异步任务 / Redis 深入 / Redis 实战场景 / 消息队列 |
| **Go** | 4 章 | 快速入门 → 类型与泛型 → 并发模式 → 工程化实战 |
| **☕ Java** | 11 章 | 去陌生化 → 语法 → 数据结构 → 工程 → Spring Boot → 数据库 → 鉴权 → 调用 Python → 实战 → 阅读项目 → 招聘判断 |
