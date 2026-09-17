import { defineConfig } from 'vitepress'
import { withMermaid } from 'vitepress-plugin-mermaid'

const repoName = process.env.GITHUB_REPOSITORY?.split('/')[1]
const isUserOrOrgPage = repoName?.endsWith('.github.io')
const githubPagesBase =
  process.env.GITHUB_ACTIONS && repoName && !isUserOrOrgPage ? `/${repoName}/` : '/'

export default withMermaid(defineConfig({
  title: '全栈知识站',
  description: 'Python · Go · Node.js · NestJS · Java — 写给前端与 AI 应用开发者的全栈学习路径',
  lang: 'zh-CN',
  base: process.env.VITEPRESS_BASE ?? githubPagesBase,
  cleanUrls: true,
  lastUpdated: true,
  ignoreDeadLinks: true,
  // prep/ 是本地私有的面试答辩材料，不参与站点构建，也已加入 .gitignore
  srcExclude: ['prep/**'],
  themeConfig: {
    logo: '/logo.svg',
    siteTitle: '全栈知识站',
    nav: [
      { text: '首页', link: '/' },
      {
        text: '学习指南',
        items: [
          { text: '🗺️ 全栈知识地图', link: '/guide/knowledge-map' },
          { text: '🧭 这套教程怎么学', link: '/guide/learning-path' },
          { text: '💡 后端思维补齐', link: '/guide/backend-thinking' },
          { text: '📝 综合场景练习', link: '/guide/exercises' },
        ]
      },
      {
        text: 'AI 工程',
        items: [
          {
            text: 'Agent 核心工程',
            items: [
              { text: '系统学习路线', link: '/guide/python-ai-agent-path' },
              { text: 'LLM 与 Prompt 基础', link: '/guide/llm-prompt-foundations' },
              { text: '工程总览与心智模型', link: '/guide/agent-intro' },
              { text: '框架生态与进阶能力', link: '/guide/agent-frameworks-and-capabilities' },
              { text: 'LangGraph 状态机', link: '/guide/agent-langgraph' },
              { text: 'Tool Calling 与 MCP', link: '/guide/agent-tool-calling' },
              { text: 'Text2SQL 工程实践', link: '/guide/agent-text2sql' },
            ]
          },
          {
            text: 'RAG 检索系统',
            items: [
              { text: '入库链路', link: '/guide/rag-pipeline' },
              { text: '混合检索与 Rerank', link: '/guide/rag-retrieval' },
              { text: '引用溯源与拒答', link: '/guide/rag-citation' },
              { text: '多模态文档与区域引用', link: '/guide/rag-multimodal' },
            ]
          },
          {
            text: '综合实战项目',
            items: [
              { text: '项目目标与架构', link: '/guide/agentic-rag-project' },
              { text: '最小 RAG 闭环', link: '/guide/agentic-rag-project-minimal' },
              { text: '项目代码入口与运行', link: '/guide/agentic-rag-project-code' },
              { text: '权限与文档生命周期', link: '/guide/agentic-rag-project-permissions' },
              { text: '项目复盘与求职表达', link: '/guide/agentic-rag-project-career' },
            ]
          },
          {
            text: '生产化与交付',
            items: [
              { text: '项目阶梯与生产交付', link: '/guide/agent-projects-and-delivery' },
              { text: 'Agent 与 RAG 评测方法', link: '/guide/agent-eval' },
              { text: 'Prompt 注入攻防', link: '/guide/agent-security' },
              { text: '可观测性、成本与性能', link: '/guide/agent-observability' },
              { text: '生产可靠性：预算与熔断', link: '/guide/agent-reliability' },
              { text: '部署与交付', link: '/guide/agent-deploy' },
            ]
          },
        ]
      },
      {
        text: '后端技术栈',
        items: [
          {
            text: 'Python & FastAPI',
            items: [
              { text: 'Python 快速入门', link: '/guide/python-intro' },
              { text: 'Python 工程进阶', link: '/guide/python-engineering' },
              { text: 'FastAPI 基础', link: '/guide/fastapi-basics' },
              { text: 'FastAPI MySQL 项目', link: '/guide/fastapi-mysql-project' },
              { text: 'FastAPI 生产进阶', link: '/guide/fastapi-advanced' },
            ]
          },
          {
            text: 'Node.js & NestJS',
            items: [
              { text: 'Node.js 运行时原理', link: '/guide/node-runtime' },
              { text: '异步编程与 Stream', link: '/guide/node-async' },
              { text: 'NestJS 核心架构', link: '/guide/nestjs-intro' },
              { text: 'NestJS 认证与授权', link: '/guide/nestjs-auth' },
              { text: 'NestJS 项目架构蓝图', link: '/guide/nestjs-project-blueprint' },
            ]
          },
          {
            text: 'Java & Spring Boot',
            items: [
              { text: 'Java 快速接手路线', link: '/guide/java-learning-path' },
              { text: 'Java 企业级进阶路线', link: '/guide/java-enterprise-path' },
              { text: 'Spring Boot 入门', link: '/guide/java-springboot-intro' },
              { text: 'JVM 与并发基础', link: '/guide/java-jvm-concurrency' },
              { text: 'Spring、数据与中间件', link: '/guide/java-spring-data-middleware' },
              { text: '分布式、云原生与架构', link: '/guide/java-distributed-cloud-architecture' },
            ]
          },
          {
            text: 'Go 语言',
            items: [
              { text: '学习路线与能力地图', link: '/guide/go-learning-path' },
              { text: 'Go 快速入门', link: '/guide/go-intro' },
              { text: '类型系统与泛型', link: '/guide/go-advanced-types' },
              { text: '并发模式与工程实践', link: '/guide/go-advanced-concurrency' },
              { text: '工程化实战', link: '/guide/go-advanced-engineering' },
            ]
          },
        ]
      },
      {
        text: '架构与运维',
        items: [
          {
            text: '数据库与建模',
            items: [
              { text: '表结构设计与规范', link: '/guide/mysql-table-design' },
              { text: 'SQL 基础与高级查询', link: '/guide/sql-basics' },
              { text: 'SQL 进阶与查询优化', link: '/guide/mysql-advanced' },
              { text: 'PostgreSQL 基础与实战', link: '/guide/postgresql' },
              { text: 'MySQL 日志与容灾备份', link: '/guide/mysql-recovery' },
            ]
          },
          {
            text: '并发与事务',
            items: [
              { text: '并发、事务与一致性', link: '/guide/concurrency-transaction' },
              { text: '锁机制与并发控制', link: '/guide/locking' },
              { text: '分布式一致性与可靠消息', link: '/guide/distributed-consistency' },
            ]
          },
          {
            text: '中间件与异步',
            items: [
              { text: 'Redis 深入与底层原理', link: '/guide/redis-deep' },
              { text: 'Redis 实战：业务场景', link: '/guide/redis-practice' },
              { text: '消息队列：解耦与异步', link: '/guide/message-queue' },
              { text: 'Worker 与异步任务', link: '/guide/background-worker' },
            ]
          },
          {
            text: '容器与部署',
            items: [
              { text: 'Docker 与部署', link: '/guide/docker-deployment' },
              { text: 'Dockerfile 进阶实践', link: '/guide/dockerfile-practice' },
              { text: 'Compose 与进程守护', link: '/guide/docker-compose-network' },
              { text: 'Nginx：反代与流量治理', link: '/guide/nginx-core' },
              { text: '网络排障与系统诊断', link: '/guide/network-troubleshooting' },
            ]
          },
        ]
      },
    ],
    sidebar: [
      {
        text: '🧭 学习指南与思维',
        collapsed: false,
        items: [
          { text: '全栈知识地图', link: '/guide/knowledge-map' },
          { text: '这套教程怎么学', link: '/guide/learning-path' },
          { text: '后端思维补齐', link: '/guide/backend-thinking' },
          { text: '综合场景练习', link: '/guide/exercises' },
        ]
      },
      {
        text: '🤖 AI Agent & RAG 实战',
        collapsed: true,
        items: [
          {
            text: 'Agent 核心工程',
            collapsed: false,
            items: [
              { text: '系统学习路线（基础 → 工程化）', link: '/guide/python-ai-agent-path' },
              { text: 'LLM 与 Prompt 基础', link: '/guide/llm-prompt-foundations' },
              { text: '框架生态与进阶能力', link: '/guide/agent-frameworks-and-capabilities' },
              { text: '项目阶梯与生产交付', link: '/guide/agent-projects-and-delivery' },
              { text: '工程总览', link: '/guide/agent-intro' },
              { text: '范式与框架选型', link: '/guide/agent-patterns' },
              { text: 'LangGraph 状态机与 Checkpoint', link: '/guide/agent-langgraph' },
              { text: 'Tool Calling、工具安全与 MCP', link: '/guide/agent-tool-calling' },
              { text: 'Multi-Agent 编排与人工兜底', link: '/guide/agent-multi-agent' },
              { text: 'SSE 流式与事件协议', link: '/guide/agent-streaming' },
              { text: 'AI 应用前端：消费事件流', link: '/guide/agent-frontend' },
              { text: 'Text2SQL 与 Schema Linking', link: '/guide/agent-text2sql' },
            ]
          },
          {
            text: 'RAG 检索系统',
            collapsed: true,
            items: [
              { text: '入库链路', link: '/guide/rag-pipeline' },
              { text: '混合检索：BM25 + 向量 + RRF', link: '/guide/rag-retrieval' },
              { text: '引用溯源、拒答与降级', link: '/guide/rag-citation' },
              { text: '多模态文档与区域级引用', link: '/guide/rag-multimodal' },
            ]
          },
          {
            text: '生产化与评测',
            collapsed: true,
            items: [
              { text: 'Prompt 注入攻防与守护栏', link: '/guide/agent-security' },
              { text: '可观测性、成本与性能', link: '/guide/agent-observability' },
              { text: '生产可靠性：预算与熔断', link: '/guide/agent-reliability' },
              { text: '上下文工程与长任务', link: '/guide/agent-context' },
              { text: 'Agent 与 RAG 评测方法', link: '/guide/agent-eval' },
              { text: '部署与交付：从本地 Demo 到可上线', link: '/guide/agent-deploy' },
            ]
          },
          {
            text: '综合实战：企业知识库 Agentic RAG',
            collapsed: true,
            items: [
              { text: '项目代码入口与运行 (projects/agentic-rag)', link: '/guide/agentic-rag-project-code' },
              { text: '1. 项目目标与架构', link: '/guide/agentic-rag-project' },
              { text: '2. 跑通最小 RAG 闭环', link: '/guide/agentic-rag-project-minimal' },
              { text: '3. 用户、团队与检索权限', link: '/guide/agentic-rag-project-permissions' },
              { text: '4. 文件存储与文档生命周期', link: '/guide/agentic-rag-project-lifecycle' },
              { text: '5. 多格式解析与结构化切分', link: '/guide/agentic-rag-project-parsing' },
              { text: '6. 异步入库与任务状态', link: '/guide/agentic-rag-project-async-ingestion' },
              { text: '7. 混合召回与 Rerank', link: '/guide/agentic-rag-project-retrieval' },
              { text: '8. 上下文、引用与拒答', link: '/guide/agentic-rag-project-citations' },
              { text: '9. 问题分类与执行路线', link: '/guide/agentic-rag-project-routing' },
              { text: '10. LangGraph 多轮检索', link: '/guide/agentic-rag-project-langgraph' },
              { text: '11. 工具、记忆与人工介入', link: '/guide/agentic-rag-project-tools-memory' },
              { text: '12. SSE 流式事件协议', link: '/guide/agentic-rag-project-streaming' },
              { text: '13. 权限安全与越权测试', link: '/guide/agentic-rag-project-security' },
              { text: '14. 入库可靠性与索引一致性', link: '/guide/agentic-rag-project-reliability' },
              { text: '15. RAG 与 Agent 离线评测', link: '/guide/agentic-rag-project-evaluation' },
              { text: '16. 可观测性、测试与部署', link: '/guide/agentic-rag-project-operations' },
              { text: '17. 项目复盘与求职表达', link: '/guide/agentic-rag-project-career' },
            ]
          },
        ]
      },
      {
        text: '🐍 Python & FastAPI',
        collapsed: true,
        items: [
          {
            text: 'Python 语言基础',
            collapsed: false,
            items: [
              { text: '快速入门', link: '/guide/python-intro' },
              { text: '深入理解类', link: '/guide/python-class' },
              { text: '工程进阶', link: '/guide/python-engineering' },
            ]
          },
          {
            text: 'FastAPI 服务开发',
            collapsed: false,
            items: [
              { text: '基础', link: '/guide/fastapi-basics' },
              { text: 'MySQL 项目实战', link: '/guide/fastapi-mysql-project' },
              { text: '生产级进阶', link: '/guide/fastapi-advanced' },
            ]
          },
        ]
      },
      {
        text: '🟢 Node.js & NestJS',
        collapsed: true,
        items: [
          {
            text: 'Node.js 运行时底座',
            collapsed: false,
            items: [
              { text: '运行时与底层模型', link: '/guide/node-runtime' },
              { text: '模块系统（CJS/ESM）', link: '/guide/node-module-system' },
              { text: '异步编程与错误处理', link: '/guide/node-async' },
              { text: 'EventEmitter · Buffer · Stream', link: '/guide/node-stream' },
              { text: 'HTTP 与 BFF', link: '/guide/node-http' },
              { text: '性能与稳定性', link: '/guide/node-perf' },
              { text: '综合场景与实战练习', link: '/guide/node-practice' },
            ]
          },
          {
            text: 'NestJS 核心与请求',
            collapsed: true,
            items: [
              { text: '简介与架构概览', link: '/guide/nestjs-intro' },
              { text: '装饰器体系', link: '/guide/nestjs-decorators' },
              { text: '元数据与 Reflector', link: '/guide/nestjs-metadata-reflector' },
              { text: '依赖注入', link: '/guide/nestjs-di' },
              { text: '动态模块与配置管理', link: '/guide/nestjs-dynamic-module' },
              { text: '请求生命周期与 AOP', link: '/guide/nestjs-pipeline' },
              { text: 'RxJS 与 Interceptor', link: '/guide/nestjs-rxjs-interceptor' },
              { text: '参数校验与异常处理', link: '/guide/nestjs-validation-filter' },
            ]
          },
          {
            text: 'NestJS 数据与认证',
            collapsed: true,
            items: [
              { text: 'DTO、序列化与 Swagger', link: '/guide/nestjs-dto' },
              { text: '数据库操作（TypeORM）', link: '/guide/nestjs-database' },
              { text: 'Prisma ORM', link: '/guide/nestjs-prisma' },
              { text: 'GraphQL 接口契约', link: '/guide/nestjs-graphql' },
              { text: '认证与登录状态', link: '/guide/nestjs-auth' },
              { text: '授权模型与三方登录', link: '/guide/nestjs-authorization' },
            ]
          },
          {
            text: 'NestJS 工程与架构',
            collapsed: true,
            items: [
              { text: '文件上传与大文件处理', link: '/guide/nestjs-file-upload' },
              { text: '日志与可观测性', link: '/guide/nestjs-logging' },
              { text: '定时任务与事件驱动', link: '/guide/nestjs-schedule-events' },
              { text: '生产环境清单', link: '/guide/nestjs-advanced' },
              { text: '实时通信：WebSocket 与 SSE', link: '/guide/nestjs-realtime' },
              { text: '微服务与跨语言通信', link: '/guide/nestjs-microservice' },
              { text: '项目架构蓝图', link: '/guide/nestjs-project-blueprint' },
            ]
          },
        ]
      },
      {
        text: '☕ Java & Spring Boot',
        collapsed: true,
        items: [
          {
            text: '进阶路线与架构深水区',
            collapsed: false,
            items: [
              { text: 'Java 学习路线', link: '/guide/java-learning-path' },
              { text: '企业级进阶路线', link: '/guide/java-enterprise-path' },
              { text: 'JVM 与并发基础', link: '/guide/java-jvm-concurrency' },
              { text: 'Spring、数据与中间件', link: '/guide/java-spring-data-middleware' },
              { text: '分布式、云原生与架构', link: '/guide/java-distributed-cloud-architecture' },
            ]
          },
          {
            text: '快速接手主线（1-8 章）',
            collapsed: false,
            items: [
              { text: '1. Java 去陌生化', link: '/guide/java-intro' },
              { text: '2. Java 核心语法', link: '/guide/java-core-syntax' },
              { text: '3. 常用数据结构', link: '/guide/java-data-structures' },
              { text: '4. 理解 Java 工程', link: '/guide/java-engineering' },
              { text: '5. Spring Boot 入门', link: '/guide/java-springboot-intro' },
              { text: '6. 数据库基础', link: '/guide/java-database' },
              { text: '7. 登录与鉴权', link: '/guide/java-auth' },
              { text: '8. 调用 Python Agent', link: '/guide/java-call-python' },
            ]
          },
          {
            text: '综合实战与求职（9-11 章）',
            collapsed: false,
            items: [
              { text: '9. 实战项目 (projects/study-tracker)', link: '/guide/java-project-practice' },
              { text: '10. 阅读陌生项目', link: '/guide/java-reading-project' },
              { text: '11. 招聘要求判断', link: '/guide/java-job-requirements' },
            ]
          },
        ]
      },
      {
        text: '🔵 Go 语言',
        collapsed: true,
        items: [
          { text: '学习路线与能力地图', link: '/guide/go-learning-path' },
          { text: 'Go 快速入门', link: '/guide/go-intro' },
          { text: '类型系统与泛型', link: '/guide/go-advanced-types' },
          { text: '并发模式与工程实践', link: '/guide/go-advanced-concurrency' },
          { text: '工程化实战', link: '/guide/go-advanced-engineering' },
        ]
      },
      {
        text: '🗄️ 数据库与一致性',
        collapsed: true,
        items: [
          {
            text: '数据库建模与查询',
            collapsed: false,
            items: [
              { text: '表结构设计', link: '/guide/mysql-table-design' },
              { text: 'SQL 基础与查询', link: '/guide/sql-basics' },
              { text: 'SQL 进阶与查询优化', link: '/guide/mysql-advanced' },
              { text: 'MySQL 日志、备份恢复与复制', link: '/guide/mysql-recovery' },
              { text: '数据库外键：理论、实践与取舍', link: '/guide/foreign-keys' },
              { text: 'PostgreSQL 基础与实战', link: '/guide/postgresql' },
              { text: 'MongoDB 与 Mongoose', link: '/guide/mongodb-mongoose' },
            ]
          },
          {
            text: '并发控制与分布式一致性',
            collapsed: false,
            items: [
              { text: '并发、事务与一致性', link: '/guide/concurrency-transaction' },
              { text: '锁机制与并发控制', link: '/guide/locking' },
              { text: '分布式一致性与可靠消息', link: '/guide/distributed-consistency' },
            ]
          },
        ]
      },
      {
        text: '🚀 中间件与运维部署',
        collapsed: true,
        items: [
          {
            text: '缓存与中间件',
            collapsed: false,
            items: [
              { text: 'Redis 深入', link: '/guide/redis-deep' },
              { text: 'Redis 实战：五个业务场景', link: '/guide/redis-practice' },
              { text: '消息队列', link: '/guide/message-queue' },
              { text: 'Worker 与异步任务', link: '/guide/background-worker' },
            ]
          },
          {
            text: '容器与运维部署',
            collapsed: false,
            items: [
              { text: 'Docker 与部署', link: '/guide/docker-deployment' },
              { text: 'Dockerfile 进阶', link: '/guide/dockerfile-practice' },
              { text: 'Compose、网络与进程守护', link: '/guide/docker-compose-network' },
              { text: 'Nginx：反向代理与流量治理', link: '/guide/nginx-core' },
              { text: '网络排障与系统诊断', link: '/guide/network-troubleshooting' },
            ]
          },
        ]
      },
    ],
    socialLinks: [
      { icon: 'github', link: 'https://github.com/wahahaorg/fullstack-road' }
    ],
    editLink: {
      pattern: 'https://github.com/wahahaorg/fullstack-road/edit/main/:path',
      text: '在 GitHub 上编辑此页'
    },
    search: {
      provider: 'local'
    },
    outline: {
      level: [2, 3],
      label: '本页目录'
    },
    docFooter: {
      prev: '上一章',
      next: '下一章'
    },
    lastUpdated: {
      text: '最后更新'
    }
  }
}))
