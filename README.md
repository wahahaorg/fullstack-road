# 全栈之路

面向前端开发者、全栈开发者和 AI 应用工程师的中文知识库。内容从语言与 Web 后端延伸到 Agent、RAG、数据库、并发一致性、基础设施和部署，重点回答两个问题：一个功能为什么这样设计，以及它在真实项目中怎样可靠运行。

在线阅读：[全栈知识站](https://wahahaorg.github.io/fullstack-road/)

## 适合谁

- 有前端经验，正在补 Python、Node.js、NestJS、Java 或 Go 后端能力。
- 已经会调用大模型 API，希望继续学习 RAG、Agent 编排和生产化。
- 正在准备全栈、后端或 AI 应用开发岗位的面试。
- 希望通过业务场景理解数据库、事务、锁、消息队列和部署，而不只背概念。

本站不要求从侧边栏第一篇顺序读到底。先打开[全栈知识地图](./guide/knowledge-map.md)，根据当前目标选择一条主线，遇到缺少的底层知识再横向补充。

## 内容方向

| 方向 | 主要内容 | 推荐入口 |
|---|---|---|
| Agent 工程 | Agent 范式、LangGraph、Tool Calling、Multi-Agent、流式输出、安全、可靠性、评测与可观测性 | [Agent 工程总览](./guide/agent-intro.md) |
| RAG | 文档入库、结构化切分、混合检索、RRF、Rerank、引用、拒答和多模态文档 | [RAG 入库链路](./guide/rag-pipeline.md) |
| Python 后端 | Python 语言、工程化、FastAPI、Pydantic、SQLAlchemy 和项目结构 | [Python 快速入门](./guide/python-intro.md) |
| Node.js 与 NestJS | 运行时、异步模型、Stream、依赖注入、AOP、鉴权、数据层、微服务与生产清单 | [Node.js 运行时](./guide/node-runtime.md) · [NestJS 架构](./guide/nestjs-intro.md) |
| Java | 面向 TS、Node.js 和 Python 开发者的 Java、Spring Boot、数据库、鉴权与项目实战 | [Java 学习路线](./guide/java-learning-path.md) |
| Go | 语言迁移、类型与泛型、goroutine、channel、并发模式和工程化 | [Go 快速入门](./guide/go-intro.md) |
| 数据与一致性 | SQL、MySQL、PostgreSQL、外键、事务、锁、分布式一致性和可靠消息 | [数据库与一致性路线](./guide/knowledge-map.md) |
| 工程与部署 | Worker、Redis、消息队列、Docker、Compose、Nginx 和 CI/CD | [Docker 与部署](./guide/docker-deployment.md) |

## 推荐学习路线

### AI 应用开发

```text
Agent 工程总览
  → Agent 范式与框架选型
  → LangGraph 状态机
  → Tool Calling 与 MCP
  → RAG 入库与混合检索
  → 引用、拒答与评测
  → 安全、可靠性和可观测性
```

### 前端转 Python 后端

```text
Python 快速入门
  → Python 类与工程化
  → FastAPI 基础
  → 数据库建模与 SQL
  → FastAPI 项目
  → Worker、Redis 与部署
```

### 后端面试补全

```text
运行时与 Web 框架
  → SQL 与表结构设计
  → 事务、锁与并发一致性
  → Redis 与消息队列
  → Docker、Nginx 与故障排查
  → 完整项目复盘
```

更多按目标划分的入口见[知识地图](./guide/knowledge-map.md)。

## 建设中的综合实战

仓库计划增加一套 **Python + FastAPI + LangGraph 企业知识库 Agentic RAG 项目**。它会从空目录开始，逐步完成文档上传与审核、异步入库、混合检索、引用回答、权限隔离、多轮检索、工具调用、Checkpoint、SSE、可靠性、评测和部署。

这套教程不会把普通 CRUD 写成逐行操作记录，也不会把 NestJS 项目简单翻译成 Python。每章必须产生可运行的项目增量，解释关键设计取舍，并验证正常路径和失败路径。完整范围、17 章路线与发布标准见 [Agentic RAG 实战教程写作契约](./AGENTIC_RAG_PROJECT_SPEC.md)。

## 内容原则

- **从业务场景进入**：先说明要解决的问题，再引入技术。
- **机制和实践结合**：解释原理，同时给出可以运行或验证的实现。
- **覆盖失败路径**：除了成功示例，也讨论超时、重复、并发、权限和恢复。
- **重视方案边界**：说明方案适用条件、替代选择和引入成本。
- **用证据支撑结果**：性能、准确率和容量结论应写清测试环境与口径。
- **服务项目和面试**：既能用于开发，也能帮助读者解释架构与技术取舍。

## 本地运行

准备当前 Node.js LTS 和 npm，然后执行：

```bash
git clone https://github.com/wahahaorg/fullstack-road.git
cd fullstack-road
npm ci
npm run docs:dev
```

按照终端输出打开本地地址即可预览。

构建静态站点：

```bash
npm run docs:build
```

构建结果位于 `.vitepress/dist`。推送到 `main` 后，GitHub Actions 会构建并发布 GitHub Pages。

## 仓库结构

```text
fullstack-road/
├── index.md                         # 站点首页
├── guide/                           # 公开教程文章
├── .vitepress/                      # 导航、侧边栏、主题与构建配置
├── public/                          # 图片等静态资源
├── AGENTIC_RAG_PROJECT_SPEC.md      # Agentic RAG 综合实战写作基准
└── .github/workflows/deploy.yml     # GitHub Pages 发布流程
```

新增或调整文章时，需要同步检查知识地图、导航和相关文章之间的连接。提交前至少运行一次：

```bash
npm run docs:build
```

## 从哪里开始

- 第一次访问：从[全栈知识地图](./guide/knowledge-map.md)选择目标。
- 学 Agent：[Agent 工程总览](./guide/agent-intro.md)。
- 学 RAG：[RAG 入库链路](./guide/rag-pipeline.md)。
- 转 Python：[Python 快速入门](./guide/python-intro.md)。
- 系统学习 NestJS：[NestJS 架构概览](./guide/nestjs-intro.md)。
- 准备 Java 岗位：[Java 学习路线](./guide/java-learning-path.md)。
