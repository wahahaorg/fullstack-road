---
layout: home

hero:
  name: 全栈知识站
  text: Python · Go · Node.js · NestJS · Java
  tagline: 写给有前端经验、正在补全栈能力的 AI 应用开发者。从语法到框架，从面试到生产。
  image:
    src: /logo.svg
    alt: 全栈知识站
  actions:
    - theme: brand
      text: 🧭 打开知识地图
      link: /guide/knowledge-map
    - theme: brand
      text: Python 快速入门
      link: /guide/python-intro
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
  - icon: 🐍
    title: Python 语法 + FastAPI
    details: 面向 JS 开发者的 Python 快速迁移，配合 FastAPI + SQLAlchemy 2.x + Pydantic v2 的生产级用法。
  - icon: 🟢
    title: Node.js 深度原理
    details: 事件循环、Stream、模块系统、async/await、错误处理，覆盖 2026 年最新面试高频题，附 7 个实战练习。
  - icon: 🏗️
    title: NestJS 工程实践
    details: 从装饰器体系到 DI/IoC，从 JWT 鉴权到 TypeORM 事务，60 道面试题全面覆盖，剔除过时内容。
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

本站已有 47 篇笔记。你可以先打开[全栈知识地图](/guide/knowledge-map)，按目标、技术栈与能力层级找到最短路径；也可以直接选择下面的方向。

### 按当前任务进入

| 我现在想做什么 | 从这里开始 | 继续深入 |
|---|---|---|
| 从前端转向 Python 后端 | [Python 快速入门](/guide/python-intro) | [FastAPI + MySQL 项目](/guide/fastapi-mysql-project) |
| 准备 Node.js / NestJS 面试 | [Node.js 运行时](/guide/node-runtime) | [NestJS 架构概览](/guide/nestjs-intro) |
| 接手 Java / Spring Boot 项目 | [Java 学习路线](/guide/java-learning-path) | [阅读陌生项目](/guide/java-reading-project) |
| 处理慢接口、重复任务和并发写入 | [后端思维补齐](/guide/backend-thinking) | [并发、事务与一致性](/guide/concurrency-transaction) |
| 把服务部署到生产环境 | [Docker 与部署](/guide/docker-deployment) | [Worker 与异步任务](/guide/background-worker) |

## 分方向学习

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
NestJS 简介与架构 → 装饰器体系 → 依赖注入
  → 请求管道（Middleware/Guard/Interceptor/Pipe）
  → 认证与授权（JWT）→ DTO 与 Swagger
  → 数据库操作（TypeORM）→ 进阶特性
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
| **Python** | 3 章 | 基础语法、类与 OOP、异步、类型系统 |
| **FastAPI** | 4 章 | 基础 → 项目结构 → 进阶（测试/中间件/WebSocket） |
| **MySQL** | 2 章 | 建模 + SQL 查询 |
| **并发事务** | 2 章 | 事务原理 + 综合练习 |
| **Node.js** | 7 章 | 运行时 / 模块 / 异步 / Stream / HTTP / 性能 / 实战 |
| **NestJS** | 8 章 | 介绍 / 装饰器 / DI / 管道 / 鉴权 / DTO / 数据库 / 进阶 |
| **Docker 与部署** | 1 章 | 容器化 / docker-compose / nginx / PM2 / CI/CD |
| **基础设施** | 3 章 | Worker 与异步任务 / Redis 深入 / 消息队列 |
| **Go** | 4 章 | 快速入门 → 类型与泛型 → 并发模式 → 工程化实战 |
| **☕ Java** | 11 章 | 去陌生化 → 语法 → 数据结构 → 工程 → Spring Boot → 数据库 → 鉴权 → 调用 Python → 实战 → 阅读项目 → 招聘判断 |
