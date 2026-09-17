---
title: 这套教程怎么学
description: 按求职目标分流：Python Agent、NestJS、Java，给出最短阅读顺序
---

# 这套教程怎么学

本站已经超过 100 篇。**不要从侧边栏第一篇读到最后一篇。** 先选一个目标，只走主线；遇到陌生概念再横向跳到关联篇。

更细的「按目标 / 按能力层」表见[全栈知识地图](./knowledge-map)。

## 读者画像

默认你具备：

- 多年 Web 前端经验，熟悉 HTTP、JSON、鉴权、前后端联调
- 至少理解一种组件化框架（React / Vue）的状态与副作用模型
- 正在补后端，或已经在用 AI 写 Python / Node 项目

不默认你具备：系统的数据库设计经验、分布式系统经验、科班算法 / ML 背景。

解释后端概念时，本站会尽量用前端心智模型类比（DI ≈ Context、Interceptor ≈ axios 拦截器、Guard ≈ 路由守卫）。

## 三条最短路径（先选一条）

### A. 求职 Python Agent / RAG 工程师（推荐主线）

目标：能讲清一条「可恢复、可审计、带引用」的 Agent + RAG 链路，并有可运行项目支撑。

```
1. 概念地图（建立词汇）
   Agent 工程总览 → LangGraph → Tool Calling 与 MCP → RAG 入库 → 混合检索 → 引用与拒答

2. 底座（否则概念落不了地）
   FastAPI 进阶（Depends / SSE / 鉴权 / Worker 边界）
   → PostgreSQL（JSONB / pgvector / RLS）
   → 消息队列（异步入库投递）→ Worker 与异步任务

3. 综合实战（把概念焊死）
   企业知识库 Agentic RAG 实战（十七章 + 代码入口）
   → 安全 / 评测 / 部署 三章务必做完

4. 面试表达
   项目复盘与求职表达 → Agent 评测方法
```

时间不够时，**先做实战第 1–8 章 + 评测 + 复盘**，再回头补概念深水区。

基础或框架选型有缺口时，走补充线（对应 [Python AI Agent 路线融合指南](./python-ai-agent-path)）：

```
LLM 与 Prompt 基础（手写最小 LLM 调用封装）
→ 框架生态与进阶能力（LangGraph / LlamaIndex / CrewAI / AutoGen 取舍）
→ 项目阶梯与生产交付（L1-L5 分级，选一个垂直项目扩展作品集）
```

### B. 系统掌握 NestJS / Node 后端

目标：能独立搭一套可维护的企业级接口骨架。

```
NestJS 简介与架构 → 装饰器 → 元数据与 Reflector → 依赖注入 → 动态模块
  → 请求生命周期 → RxJS 与 Interceptor → 校验与异常
  → DTO / TypeORM（或 Prisma）→ 认证 → 授权
  → 日志 / 生产清单 → 项目架构蓝图
```

Node 运行时七章按需补（面试常问事件循环 / Stream 时再读）。不必先读完 Java / Go。

### C. 接手 Java / Spring Boot 项目

目标：能读懂并参与现有 Java 后端，而不是从零成为 Java 专家。

```
Java 学习路线 → 去陌生化 → 核心语法 → 理解 Java 工程
  → Spring Boot 入门 → 数据库 → 登录鉴权
  → 调用 Python Agent（前后端协作场景）
  → 阅读陌生项目 → 招聘要求判断
```

接手项目之后想进企业级深水区，走进阶线（对应 [Java 企业级进阶路线](./java-enterprise-path)）：

```
JVM 与并发基础（运行模型、GC、线程池）
→ Spring、数据与中间件（事务、测试、Security、Redis、MQ）
→ 分布式、云原生与架构（微服务、可观测性、架构表达）
```

## 读完一条主线后你应该能做什么

| 主线 | 最低交付 |
|---|---|
| A. Agent | 本地跑通带权限过滤的 RAG 问答；能解释为何过滤在打分前；有离线评测数字 |
| B. NestJS | 一个模块化单体：鉴权、DTO 校验、迁移、日志、健康检查齐全 |
| C. Java | 能画出现有项目的包结构，并独立改一个垂直功能（含测试） |

进阶线走完后，交付升级一档：

| 主线 | 进阶交付 |
|---|---|
| A + Agent 融合路线 | 能手搭最小 Agent、说清五个框架取舍；有 L1-L5 中的两个分级项目交付 |
| C + Java 进阶路线 | 一份 JVM/GC 排查笔记；一个带事务、缓存、MQ 的状态流转流程；3 分钟项目链路讲述 |

## 每章怎么读

1. 先看业务问题，自己想表结构 / 接口 / 失败模式
2. 再看示例与取舍表
3. 用自己的话复述「为什么这样选、什么情况下不该这样」
4. 能写进项目或面试口述，再进入下一章

只复制代码会得到「能跑的仓库」；能解释取舍，才算补上工程能力。

## 相关入口

- [全栈知识地图](./knowledge-map)：按目标与能力层浏览
- [后端思维补齐](./backend-thinking)：纠正「表 = 表单、接口 = 函数」的误区
- [企业知识库 Agentic RAG 实战](./agentic-rag-project)：主线 A 的综合项目
- [Java 企业级进阶路线](./java-enterprise-path)：主线 C 的进阶线
- [Python AI Agent 路线融合指南](./python-ai-agent-path)：主线 A 的基础补充与项目阶梯
