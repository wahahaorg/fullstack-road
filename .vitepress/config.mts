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
      { text: '知识地图', link: '/guide/knowledge-map' },
      {
        text: 'AI 工程',
        items: [
          {
            text: 'Agent 工程',
            items: [
              { text: '工程总览', link: '/guide/agent-intro' },
              { text: '范式与框架选型', link: '/guide/agent-patterns' },
              { text: 'LangGraph 状态机', link: '/guide/agent-langgraph' },
              { text: 'Tool Calling 与 MCP', link: '/guide/agent-tool-calling' },
              { text: 'Multi-Agent 与人工兜底', link: '/guide/agent-multi-agent' },
              { text: 'SSE 流式', link: '/guide/agent-streaming' },
              { text: 'Text2SQL', link: '/guide/agent-text2sql' },
            ]
          },
          {
            text: 'RAG 检索',
            items: [
              { text: '入库链路', link: '/guide/rag-pipeline' },
              { text: '混合检索与 Rerank', link: '/guide/rag-retrieval' },
              { text: '引用溯源与拒答', link: '/guide/rag-citation' },
              { text: '多模态文档', link: '/guide/rag-multimodal' },
            ]
          },
          {
            text: '生产化',
            items: [
              { text: 'Prompt 注入攻防', link: '/guide/agent-security' },
              { text: '可观测性、成本与性能', link: '/guide/agent-observability' },
              { text: '生产可靠性', link: '/guide/agent-reliability' },
              { text: '上下文工程', link: '/guide/agent-context' },
              { text: 'Agent 与 RAG 评测', link: '/guide/agent-eval' },
            ]
          },
        ]
      },
      {
        text: 'Python 后端',
        items: [
          {
            text: 'Python',
            items: [
              { text: '语法入门', link: '/guide/python-intro' },
              { text: '深入理解类', link: '/guide/python-class' },
              { text: '工程进阶', link: '/guide/python-engineering' },
            ]
          },
          {
            text: 'FastAPI',
            items: [
              { text: '基础', link: '/guide/fastapi-basics' },
              { text: 'MySQL 项目实战', link: '/guide/fastapi-mysql-project' },
              { text: '进阶', link: '/guide/fastapi-advanced' },
            ]
          },
        ]
      },
      {
        text: 'Node 后端',
        items: [
          {
            text: 'Node.js',
            items: [
              { text: '运行时原理', link: '/guide/node-runtime' },
              { text: '模块系统', link: '/guide/node-module-system' },
              { text: '异步与错误处理', link: '/guide/node-async' },
              { text: 'Stream 与 Buffer', link: '/guide/node-stream' },
              { text: 'HTTP 与 BFF', link: '/guide/node-http' },
              { text: 'HTTP、TCP、TLS 与网络排障', link: '/guide/network-troubleshooting' },
            ]
          },
          {
            text: 'NestJS',
            items: [
              { text: '核心原理', link: '/guide/nestjs-intro' },
              { text: '请求生命周期', link: '/guide/nestjs-pipeline' },
              { text: '数据与接口', link: '/guide/nestjs-dto' },
              { text: '认证与授权', link: '/guide/nestjs-auth' },
              { text: '工程与通信', link: '/guide/nestjs-advanced' },
              { text: '项目架构蓝图', link: '/guide/nestjs-project-blueprint' },
            ]
          },
        ]
      },
      {
        text: '运维',
        items: [
          { text: 'Docker 与部署', link: '/guide/docker-deployment' },
          { text: 'Dockerfile 进阶', link: '/guide/dockerfile-practice' },
          { text: 'Compose 与进程守护', link: '/guide/docker-compose-network' },
          { text: 'Nginx 流量治理', link: '/guide/nginx-core' },
          { text: 'Worker 与异步任务', link: '/guide/background-worker' },
          { text: 'Redis 深入', link: '/guide/redis-deep' },
          { text: 'Redis 实战场景', link: '/guide/redis-practice' },
          { text: '消息队列', link: '/guide/message-queue' },
        ]
      },
      {
        text: 'Go',
        items: [
          { text: 'Go 快速入门', link: '/guide/go-intro' },
          { text: '类型系统与泛型', link: '/guide/go-advanced-types' },
          { text: '并发模式与工程实践', link: '/guide/go-advanced-concurrency' },
          { text: '工程化实战', link: '/guide/go-advanced-engineering' },
        ]
      },
      {
        text: 'Java',
        items: [
          { text: '学习路线', link: '/guide/java-learning-path' },
          { text: '1. Java 去陌生化', link: '/guide/java-intro' },
          { text: '2. Java 核心语法', link: '/guide/java-core-syntax' },
          { text: '3. 常用数据结构', link: '/guide/java-data-structures' },
          { text: '4. 理解 Java 工程', link: '/guide/java-engineering' },
          { text: '5. Spring Boot 入门', link: '/guide/java-springboot-intro' },
          { text: '6. 数据库基础', link: '/guide/java-database' },
          { text: '7. 登录与鉴权', link: '/guide/java-auth' },
          { text: '8. 调用 Python Agent', link: '/guide/java-call-python' },
          { text: '9. 实战项目', link: '/guide/java-project-practice' },
          { text: '10. 阅读陌生项目', link: '/guide/java-reading-project' },
          { text: '11. 招聘要求判断', link: '/guide/java-job-requirements' },
        ]
      },
    ],
    sidebar: [
      {
        text: '🧭 开始这里',
        collapsed: false,
        items: [
          { text: '全栈知识地图', link: '/guide/knowledge-map' },
          { text: '这套教程怎么学', link: '/guide/learning-path' },
          { text: '后端思维补齐', link: '/guide/backend-thinking' },
        ]
      },
      {
        text: '🤖 AI 工程',
        collapsed: true,
        items: [
          {
            text: 'Agent 工程',
            collapsed: false,
            items: [
              { text: '工程总览', link: '/guide/agent-intro' },
              { text: '范式与框架选型', link: '/guide/agent-patterns' },
              { text: 'LangGraph 状态机与 Checkpoint', link: '/guide/agent-langgraph' },
              { text: 'Tool Calling、工具安全与 MCP', link: '/guide/agent-tool-calling' },
              { text: 'Multi-Agent 编排与人工兜底', link: '/guide/agent-multi-agent' },
              { text: 'SSE 流式与事件协议', link: '/guide/agent-streaming' },
              { text: 'Text2SQL 与 Schema Linking', link: '/guide/agent-text2sql' },
            ]
          },
          {
            text: 'RAG 检索',
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
            ]
          },
        ]
      },
      {
        text: '🐍 Python 后端',
        collapsed: true,
        items: [
          {
            text: 'Python 语言',
            collapsed: false,
            items: [
              { text: '快速入门', link: '/guide/python-intro' },
              { text: '深入理解类', link: '/guide/python-class' },
              { text: '工程进阶', link: '/guide/python-engineering' },
            ]
          },
          {
            text: 'FastAPI 开发',
            collapsed: false,
            items: [
              { text: '基础', link: '/guide/fastapi-basics' },
              { text: 'MySQL 项目实战', link: '/guide/fastapi-mysql-project' },
              { text: '进阶', link: '/guide/fastapi-advanced' },
            ]
          },
        ]
      },
      {
        text: '🗄️ 数据库与建模',
        collapsed: true,
        items: [
          { text: '表结构设计', link: '/guide/mysql-table-design' },
          { text: 'SQL 基础与查询', link: '/guide/sql-basics' },
          { text: 'SQL 进阶与查询优化', link: '/guide/mysql-advanced' },
          { text: 'MySQL 日志、备份恢复与复制', link: '/guide/mysql-recovery' },
          { text: 'PostgreSQL 基础与实战', link: '/guide/postgresql' },
          { text: 'MongoDB 与 Mongoose', link: '/guide/mongodb-mongoose' },
        ]
      },
      {
        text: '🔐 并发与事务',
        collapsed: true,
        items: [
          { text: '并发、事务与一致性', link: '/guide/concurrency-transaction' },
          { text: '锁机制与并发控制', link: '/guide/locking' },
          { text: '分布式一致性与可靠消息', link: '/guide/distributed-consistency' },
          { text: '综合练习', link: '/guide/exercises' },
        ]
      },
      {
        text: '🟢 Node 后端',
        collapsed: true,
        items: [
          {
            text: 'Node.js 基础',
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
        text: '🐳 Docker 与部署',
        collapsed: true,
        items: [
          { text: 'Docker 与部署', link: '/guide/docker-deployment' },
          { text: 'Dockerfile 进阶', link: '/guide/dockerfile-practice' },
          { text: 'Compose、网络与进程守护', link: '/guide/docker-compose-network' },
          { text: 'Nginx：反向代理与流量治理', link: '/guide/nginx-core' },
        ]
      },
      {
        text: '📦 基础设施',
        collapsed: true,
        items: [
          { text: 'Worker 与异步任务', link: '/guide/background-worker' },
          { text: 'Redis 深入', link: '/guide/redis-deep' },
          { text: 'Redis 实战：五个业务场景', link: '/guide/redis-practice' },
          { text: '消息队列', link: '/guide/message-queue' },
        ]
      },
      {
        text: '🔵 Go 语言',
        collapsed: true,
        items: [
          { text: 'Go 快速入门', link: '/guide/go-intro' },
          { text: '类型系统与泛型', link: '/guide/go-advanced-types' },
          { text: '并发模式与工程实践', link: '/guide/go-advanced-concurrency' },
          { text: '工程化实战', link: '/guide/go-advanced-engineering' },
        ]
      },
      {
        text: '☕ Java 快速入门',
        collapsed: true,
        items: [
          { text: '学习路线', link: '/guide/java-learning-path' },
          { text: '1. Java 去陌生化', link: '/guide/java-intro' },
          { text: '2. Java 核心语法', link: '/guide/java-core-syntax' },
          { text: '3. 常用数据结构', link: '/guide/java-data-structures' },
          { text: '4. 理解 Java 工程', link: '/guide/java-engineering' },
          { text: '5. Spring Boot 入门', link: '/guide/java-springboot-intro' },
          { text: '6. 数据库基础', link: '/guide/java-database' },
          { text: '7. 登录与鉴权', link: '/guide/java-auth' },
          { text: '8. 调用 Python Agent', link: '/guide/java-call-python' },
          { text: '9. 实战项目', link: '/guide/java-project-practice' },
          { text: '10. 阅读陌生项目', link: '/guide/java-reading-project' },
          { text: '11. 招聘要求判断', link: '/guide/java-job-requirements' },
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
