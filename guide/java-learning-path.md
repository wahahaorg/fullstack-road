---
title: ☕ Java 快速入门：面向前端与 AI 应用开发者
---

# ☕ Java 快速入门：面向前端与 AI 应用开发者

## 读者画像

这套教程默认你具备这些基础：

- 熟悉 TypeScript、JavaScript
- 使用过 React、Vue、Node.js、NestJS
- 使用过 Python、FastAPI
- 了解 REST API、JWT、MySQL、Redis
- 能使用 Docker、Git、Maven 类似的包管理和构建工具
- 正在学习 Agent、RAG、知识库和 AI 应用开发

**你不默认具备：**

- 任何 Java 经验
- 对 JVM 生态的理解
- Spring 框架的使用经验

## 读完后的目标

1. 消除对 Java 招聘要求的恐惧
2. 能看懂常见 Java 和 Spring Boot 项目
3. 能独立编写简单的 REST API
4. 能修改 Controller、Service、DTO、Entity 等常见代码
5. 能使用 Java 服务调用 Python/FastAPI Agent 服务
6. 面试时可以诚实地说自己掌握 Java 和 Spring Boot 基础
7. 后续遇到 Java 项目时，可以借助 AI 快速参与开发

---

## 完整目录

### 第一部分：Java 去陌生化（约 1.5 小时）

> 难度：⭐ | 优先级：**必须掌握**

1. Java、JDK、JRE、JVM 分别是什么
2. Java 项目如何编译和运行
3. Java 与 TypeScript、Python 的主要区别
4. 强类型、编译期检查和运行期检查
5. Java 项目的常见目录结构
6. IDE、JDK、Maven 分别负责什么
7. 创建并运行第一个 Java 项目

[阅读第一章 →](./java-intro)

---

### 第二部分：Java 核心语法（约 3 小时）

> 难度：⭐⭐ | 优先级：**必须掌握**

1. 变量、基本类型、包装类型
2. String 及常用操作
3. null 与空指针问题
4. 条件判断和循环
5. 方法、参数、返回值
6. 类、对象和构造方法
7. 封装、继承和多态
8. 接口与实现类
9. static、final
10. public、private、protected
11. 重载与重写
12. 异常处理
13. 泛型

[阅读第二章 →](./java-core-syntax)

---

### 第三部分：Java 常用数据结构（约 2.5 小时）

> 难度：⭐⭐ | 优先级：**必须掌握**

1. Array
2. List（ArrayList）
3. Set（HashSet）
4. Map（HashMap）
5. 遍历方式对比
6. Lambda 表达式
7. Stream API（map、filter、reduce）
8. Optional 处理空值

[阅读第三章 →](./java-data-structures)

---

### 第四部分：理解 Java 工程（约 2 小时）

> 难度：⭐⭐ | 优先级：**必须掌握**

1. Maven 是什么（对比 npm/pnpm）
2. pom.xml 怎么看（对比 package.json）
3. dependency 是什么（对比 node_modules）
4. Maven 生命周期
5. package 和 import
6. jar 包是什么
7. Java 项目如何启动
8. 环境变量和配置文件
9. application.yml 基础
10. 日志和异常堆栈怎么看

[阅读第四章 →](./java-engineering)

---

### 第五部分：Spring Boot 入门（约 4 小时）

> 难度：⭐⭐⭐ | 优先级：**必须掌握**

1. Spring 和 Spring Boot 的关系
2. Spring Boot 项目结构
3. 启动类的作用
4. Bean 是什么
5. IOC 和依赖注入（对比 NestJS DI）
6. Annotation 注解（对比 NestJS Decorator）
7. Controller（对比 NestJS Controller）
8. Service（对比 NestJS Provider）
9. Repository / Mapper
10. Entity（对比 TypeORM Entity）
11. DTO（对比 Pydantic Schema / NestJS DTO）
12. VO
13. 配置文件
14. REST API 开发
15. JSON 序列化与反序列化
16. 参数校验
17. 全局异常处理
18. 统一返回结构

[阅读第五章 →](./java-springboot-intro)

---

### 第六部分：数据库基础（约 2.5 小时）

> 难度：⭐⭐⭐ | 优先级：**必须掌握**

1. Spring Boot 连接 MySQL
2. 数据库配置
3. Entity 与数据库表映射
4. Mapper（MyBatis-Plus）
5. CRUD 操作
6. 分页查询
7. 条件查询
8. 事务的基本概念（@Transactional）
9. 数据库异常排查

[阅读第六章 →](./java-database)

---

### 第七部分：登录与接口鉴权（约 2 小时）

> 难度：⭐⭐⭐ | 优先级：**看懂即可**

1. 登录接口设计
2. 密码基本处理（BCrypt）
3. JWT 生成与验证
4. 请求拦截器（Interceptor）
5. 获取当前用户
6. 接口权限判断
7. 常见安全问题

[阅读第七章 →](./java-auth)

---

### 第八部分：Java 调用 Python Agent 服务（约 2 小时）

> 难度：⭐⭐⭐ | 优先级：**看懂即可**

1. 为什么企业项目可能采用这种架构
2. Java 与 Python 的职责划分
3. Java 如何发送 HTTP 请求（RestTemplate / WebClient）
4. 如何传递 JSON
5. 如何处理超时
6. 如何处理 Python 服务异常
7. 如何设计统一错误码
8. 同步请求与异步任务的区别
9. 如何避免 Java 服务一直阻塞
10. 如何记录调用日志

[阅读第八章 →](./java-call-python)

---

### 第九部分：实战项目（约 4 小时）

> 难度：⭐⭐⭐ | 优先级：**必须掌握**

实现一个"学习时间记录系统"的 Spring Boot 后端：

1. 开始学习 / 结束学习
2. 查询今日学习时长
3. 查询学习记录
4. 按日期统计
5. 按学习项目分类
6. 用户登录
7. MySQL 数据持久化
8. 参数校验
9. 全局异常处理
10. 统一返回结构

[阅读第九章 →](./java-project-practice)

---

### 第十部分：阅读陌生项目的方法（约 1.5 小时）

> 难度：⭐⭐ | 优先级：**看懂即可**

1. 先看哪个文件
2. 如何找到启动入口
3. 如何找到某个接口
4. 如何从 Controller 追到数据库
5. 如何找到请求参数定义
6. 如何判断是否有鉴权
7. 如何查看数据库配置
8. 如何查看外部服务调用
9. 如何定位异常
10. 如何进行最小范围修改

[阅读第十章 →](./java-reading-project)

---

### 第十一部分：Java 招聘要求判断（约 1 小时）

> 难度：⭐ | 优先级：**看懂即可**

1. 岗位要求分类方法
2. 关键词解读
3. 投递策略建议

[阅读第十一章 →](./java-job-requirements)

---

## 学习优先级总览

| 部分 | 名称 | 优先级 | 预计时间 |
|------|------|--------|----------|
| 一 | Java 去陌生化 | 必须掌握 | 1.5h |
| 二 | Java 核心语法 | 必须掌握 | 3h |
| 三 | Java 常用数据结构 | 必须掌握 | 2.5h |
| 四 | 理解 Java 工程 | 必须掌握 | 2h |
| 五 | Spring Boot 入门 | 必须掌握 | 4h |
| 六 | 数据库基础 | 必须掌握 | 2.5h |
| 七 | 登录与接口鉴权 | 看懂即可 | 2h |
| 八 | Java 调用 Python Agent | 看懂即可 | 2h |
| 九 | 实战项目 | 必须掌握 | 4h |
| 十 | 阅读陌生项目的方法 | 看懂即可 | 1.5h |
| 十一 | Java 招聘要求判断 | 看懂即可 | 1h |

**总计：约 26 小时**

---

## 7 天快速学习计划

> 适合：面试前突击，目标是"能看懂 + 能改代码 + 能诚实说掌握基础"

| 天数 | 内容 | 时间 | 目标 |
|------|------|------|------|
| Day 1 | 第一部分：Java 去陌生化 | 1.5h | 搭建环境，跑通第一个程序 |
| Day 2 | 第二部分：Java 核心语法（上） | 2h | 变量、类型、String、null、条件循环 |
| Day 3 | 第二部分：Java 核心语法（下）+ 第三部分 | 3.5h | 类、接口、继承、异常、泛型 + 数据结构 |
| Day 4 | 第四部分：理解 Java 工程 | 2h | Maven、pom.xml、项目结构 |
| Day 5 | 第五部分：Spring Boot 入门（上） | 2.5h | 项目结构、Bean、IOC、Controller、Service |
| Day 6 | 第五部分：Spring Boot 入门（下）+ 第六部分 | 4h | DTO、校验、异常处理 + 数据库 CRUD |
| Day 7 | 第九部分：实战项目 | 4h | 完整项目实战，串起来所有知识 |

**跳过：** 第七、八、十、十一部分（面试前快速浏览即可）

---

## 21 天完整学习计划

> 适合：有充足时间，目标是"能独立写接口 + 能参与项目开发"

| 天数 | 内容 | 时间 | 目标 |
|------|------|------|------|
| Day 1-2 | 第一部分：Java 去陌生化 | 3h | 环境搭建 + 深入理解编译运行机制 |
| Day 3-5 | 第二部分：Java 核心语法 | 5h | 完整掌握语法，做完全部练习 |
| Day 6-7 | 第三部分：Java 常用数据结构 | 4h | 熟练使用 Stream、Optional、Lambda |
| Day 8-9 | 第四部分：理解 Java 工程 | 3h | 理解 Maven 生命周期，能独立配置项目 |
| Day 10-12 | 第五部分：Spring Boot 入门 | 6h | 熟练写 Controller、Service、DTO |
| Day 13-14 | 第六部分：数据库基础 | 4h | 能独立完成 CRUD + 分页 + 事务 |
| Day 15 | 第七部分：登录与接口鉴权 | 2h | 理解 JWT 鉴权流程 |
| Day 16 | 第八部分：Java 调用 Python Agent | 2h | 理解跨语言服务调用 |
| Day 17-19 | 第九部分：实战项目 | 6h | 完成完整项目，写测试 |
| Day 20 | 第十部分：阅读陌生项目的方法 | 2h | 掌握项目阅读技巧 |
| Day 21 | 第十一部分：Java 招聘要求判断 | 1h | 制定投递策略 |

---

## 第一章预告

**第一部分：Java 去陌生化**

第一章将帮你建立对 Java 生态的整体认知：

1. **Java、JDK、JRE、JVM** — 用 Node.js 和 Python 类比，让你一下就明白
2. **编译和运行** — Java 为什么需要"先编译再运行"，对比 tsc 和 python 直接执行
3. **Java vs TypeScript vs Python** — 一张表说清楚三者的核心差异
4. **强类型与编译期检查** — 为什么 Java 能在"写代码时"就发现很多错误
5. **目录结构** — 一个真实 Spring Boot 项目的目录长什么样
6. **IDE、JDK、Maven 分工** — 对比 VS Code、Node.js、npm
7. **动手实践** — 从零创建并运行第一个 Java 项目

准备好了吗？开始阅读 [第一章：Java 去陌生化 →](./java-intro)