import { defineConfig } from 'vitepress'

const repoName = process.env.GITHUB_REPOSITORY?.split('/')[1]
const isUserOrOrgPage = repoName?.endsWith('.github.io')
const githubPagesBase =
  process.env.GITHUB_ACTIONS && repoName && !isUserOrOrgPage ? `/${repoName}/` : '/'

export default defineConfig({
  title: '全栈知识站',
  description: 'Python · Go · Node.js · NestJS — 写给前端工程师的全栈学习路径',
  lang: 'zh-CN',
  base: process.env.VITEPRESS_BASE ?? githubPagesBase,
  cleanUrls: true,
  lastUpdated: true,
  ignoreDeadLinks: true,
  themeConfig: {
    logo: '/logo.svg',
    siteTitle: '全栈知识站',
    nav: [
      { text: '首页', link: '/' },
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
          { text: 'FastAPI 基础', link: '/guide/fastapi-basics' },
          { text: 'FastAPI 进阶', link: '/guide/fastapi-advanced' },
        ]
      },
      {
        text: 'Node.js',
        items: [
          { text: '运行时原理', link: '/guide/node-runtime' },
          { text: '模块系统', link: '/guide/node-module-system' },
          { text: '异步与错误处理', link: '/guide/node-async' },
        ]
      },
      {
        text: 'NestJS',
        items: [
          { text: '简介与架构', link: '/guide/nestjs-intro' },
          { text: '依赖注入', link: '/guide/nestjs-di' },
        ]
      },
      {
        text: '运维',
        items: [
          { text: 'Docker 与部署', link: '/guide/docker-deployment' },
          { text: 'Redis 深入', link: '/guide/redis-deep' },
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
        text: '出海游戏站',
        items: [
          { text: '教程总览', link: '/game-site/' },
          { text: 'SEO 基础', link: '/game-site/seo-basics' },
        ]
      },
    ],
    sidebar: [
      {
        text: '🐍 Python 语法',
        collapsed: false,
        items: [
          { text: 'Python 快速入门', link: '/guide/python-intro' },
          { text: '深入理解类', link: '/guide/python-class' },
          { text: 'Python 工程进阶', link: '/guide/python-engineering' },
        ]
      },
      {
        text: '⚡ FastAPI 开发',
        collapsed: false,
        items: [
          { text: '学习路线', link: '/guide/learning-path' },
          { text: '后端思维补齐', link: '/guide/backend-thinking' },
          { text: 'FastAPI 基础', link: '/guide/fastapi-basics' },
          { text: 'FastAPI + MySQL 项目结构', link: '/guide/fastapi-mysql-project' },
          { text: 'FastAPI 进阶', link: '/guide/fastapi-advanced' },
        ]
      },
      {
        text: '🗄️ MySQL 与建模',
        collapsed: false,
        items: [
          { text: '表结构设计', link: '/guide/mysql-table-design' },
          { text: 'SQL 基础与查询', link: '/guide/sql-basics' },
        ]
      },
      {
        text: '🔐 并发与事务',
        collapsed: false,
        items: [
          { text: '并发、事务与一致性', link: '/guide/concurrency-transaction' },
          { text: '综合练习', link: '/guide/exercises' },
        ]
      },
      {
        text: '🟢 Node.js',
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
        text: '🏗️ NestJS',
        collapsed: false,
        items: [
          { text: '简介与架构概览', link: '/guide/nestjs-intro' },
          { text: '装饰器体系', link: '/guide/nestjs-decorators' },
          { text: '依赖注入', link: '/guide/nestjs-di' },
          { text: '请求管道', link: '/guide/nestjs-pipeline' },
          { text: '认证与授权', link: '/guide/nestjs-auth' },
          { text: 'DTO 与 Swagger', link: '/guide/nestjs-dto' },
          { text: '数据库操作', link: '/guide/nestjs-database' },
          { text: '进阶特性', link: '/guide/nestjs-advanced' },
        ]
      },
      {
        text: '🐳 Docker 与部署',
        collapsed: false,
        items: [
          { text: 'Docker 与部署', link: '/guide/docker-deployment' },
        ]
      },
      {
        text: '📦 基础设施',
        collapsed: false,
        items: [
          { text: 'Redis 深入', link: '/guide/redis-deep' },
          { text: '消息队列', link: '/guide/message-queue' },
        ]
      },
      {
        text: '🔵 Go 语言',
        collapsed: false,
        items: [
          { text: 'Go 快速入门', link: '/guide/go-intro' },
          { text: '类型系统与泛型', link: '/guide/go-advanced-types' },
          { text: '并发模式与工程实践', link: '/guide/go-advanced-concurrency' },
          { text: '工程化实战', link: '/guide/go-advanced-engineering' },
        ]
      },
      {
        text: '🎮 出海游戏站',
        collapsed: false,
        items: [
          { text: '教程总览', link: '/game-site/' },
          { text: 'SEO 基础概念', link: '/game-site/seo-basics' },
          { text: '关键词调研', link: '/game-site/keyword-research' },
          { text: '第一个实验项目', link: '/game-site/first-project' },
          { text: '技术栈与实现', link: '/game-site/tech-stack' },
          { text: '数据闭环与诊断', link: '/game-site/data-loop' },
          { text: '广告接入', link: '/game-site/ads-monetization' },
          { text: '30 天实践计划', link: '/game-site/30-day-plan' },
          { text: '成本控制与自动化', link: '/game-site/costs-automation' },
          { text: '📋 关键词调研模板', link: '/game-site/keyword-template' },
          {
            text: '💬 群友实战经验',
            collapsed: true,
            items: [
              { text: '总览', link: '/game-site/community/' },
              { text: 'AdSense 审核实录', link: '/game-site/community/adsense-stories' },
              { text: '工具站 vs 内容站', link: '/game-site/community/tool-vs-content' },
              { text: '改版代价与维护', link: '/game-site/community/update-risks' },
              { text: 'SEO 收录与排名', link: '/game-site/community/seo-stories' },
              { text: '关键词实战', link: '/game-site/community/keyword-stories' },
              { text: '外链建设', link: '/game-site/community/backlink-stories' },
              { text: '赚钱与变现', link: '/game-site/community/monetization-stories' },
              { text: 'Bing 流量', link: '/game-site/community/bing-traffic' },
              { text: 'AI 辅助建站', link: '/game-site/community/ai-building' },
              { text: '避坑指南', link: '/game-site/community/pitfalls' },
            ]
          },
        ]
      },
    ],
    socialLinks: [
      { icon: 'github', link: 'https://github.com/' }
    ],
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
})
