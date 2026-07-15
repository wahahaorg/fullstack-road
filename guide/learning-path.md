# 这套教程怎么学

## 读者画像

这套教程默认你具备这些基础：

- 有多年 Web 前端经验。
- 能理解 HTTP、接口、JSON、鉴权、前后端联调。
- 会用 NestJS 或至少理解 Controller、Service、DTO、Module 这些概念。
- 正在用 AI 写 Python 项目，但对后端建模、数据库事务、项目分层还不够踏实。

它不默认你具备：

- 系统的数据库设计经验。
- 熟练的 Python 后端项目经验。
- 深入的并发编程或分布式系统经验。

## 读完后你应该能做什么

目标不是背概念，而是完成这几个动作：

1. 根据业务需求拆出实体、关系、字段和约束。
2. 写出常见 CRUD、JOIN、聚合、分页和事务 SQL。
3. 用 FastAPI 写出清晰的接口、请求模型、响应模型和错误处理。
4. 把代码拆成 router、schema、model、service、repository。
5. 知道什么时候用事务、行锁、唯一约束、乐观锁、幂等键。
6. 在面试中把“我会写接口”升级成“我能设计业务数据流和一致性方案”。

## 学习路线

### 第一阶段：建立后端视角

先读：

- [后端思维补齐](./backend-thinking)
- [MySQL 表结构设计](./mysql-table-design)

这一阶段重点不是代码，而是纠正一个常见误区：

> 表不是页面表单，接口不是函数入口，后端核心是业务状态的长期正确性。

### 第二阶段：掌握可用的 SQL

再读：

- [SQL 基础与查询](./sql-basics)

你不需要一开始就成为 SQL 专家，但必须能写：

```sql
SELECT ... WHERE ...
JOIN ...
GROUP BY ...
ORDER BY ... LIMIT ...
UPDATE ... WHERE ...
```

并且知道哪些 SQL 会影响索引、事务和并发。

### 第三阶段：迁移到 FastAPI

再读：

- [Python 工程进阶](./python-engineering)
- [FastAPI 基础](./fastapi-basics)
- [FastAPI + MySQL 项目结构](./fastapi-mysql-project)

你可以把 NestJS 经验迁移过来：

| NestJS | FastAPI |
| --- | --- |
| Controller | APIRouter |
| DTO | Pydantic Schema |
| Provider / Service | 普通 service 函数或类 |
| Pipe | Pydantic 校验 + Depends |
| Guard | Depends 鉴权依赖 |
| Exception Filter | exception_handler |
| Module | Python package / router 组合 |

### 第四阶段：补真实后端坑

最后读：

- [并发、事务与一致性](./concurrency-transaction)
- [综合练习](./exercises)

后端面试和实战经常卡在这里：

```txt
重复提交怎么办？
多个用户同时更新怎么办？
库存为什么会超卖？
状态流转如何防止覆盖？
AI 文件解析任务如何避免重复执行？
```

这些不是单纯 FastAPI 语法问题，而是“状态 + 数据 + 并发”的问题。

## 每章怎么读

建议你按四步走：

1. 先看业务问题。
2. 自己想表结构或接口。
3. 再看示例答案。
4. 最后用自己的话复述一遍面试表达。

如果只复制代码，你会得到“能跑的项目”；如果能解释取舍，你才真正补上后端能力。
