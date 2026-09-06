---
title: 部署与交付：从本地 Demo 到可上线
description: Agent 服务的配置与密钥管理、可复现镜像、API/Worker/Relay 进程拓扑与水平扩展四约束、nginx 反代下的 SSE 落地、Alembic 数据库迁移、CI/CD 流水线与评测门禁、滚动发布与回滚策略，以及从教学基线到生产栈的迁移清单。
---

# 部署与交付：从本地 Demo 到可上线

> 普通接口部署的核心是“别挂”；Agent 服务还多了一条“挂得体面”。一次请求十几秒到几分钟、SSE 长连接、挂起等待人工确认的中间态、每次请求都在花钱、模型是带速率限制的外部服务——这些都让“能跑起来”和“敢上线”之间隔着一批工程问题。这一篇把 Agent 服务从本地 Demo 到可上线之间的交付工作一次讲完：配置与密钥、镜像、进程拓扑、反向代理、数据库迁移、CI/CD、发布与回滚，最后给出从教学基线到生产栈的迁移清单。

## 为什么 Agent 服务不能照搬普通 API 的部署

| 维度 | 普通 API | Agent 服务 |
|---|---|---|
| 请求时长 | 毫秒到秒级，连接即用即走 | 秒到分钟级，SSE 长连接，客户端可能中途断开 |
| 请求内状态 | 无状态或会话很短 | 检索缓存、会话记忆、Agent 中间态都容易留在进程里 |
| 挂起态 | 几乎没有 | 等人工审批的 Agent 可以挂几分钟到几天，发布和重启都会碰到它 |
| 一次请求的成本 | 几乎为零 | 十几次模型与工具调用，滥用直接变成账单事故 |
| 关键外部依赖 | 数据库 | 数据库之外还有模型 API：限速、超时、版本漂移 |

结论：Agent 服务的部署清单 = 普通 API 的清单 + 状态外置 + 长连接治理 + 成本护栏。下面逐项展开。

## 配置与密钥：部署的第一个安全边界

### 配置分层

遵循 12-Factor：配置全部来自环境变量，镜像不可变，同一镜像跑遍开发、测试、生产。配置按“不填会怎样”分三类：

- **必填**：模型 API Key、数据库 URL。启动时校验，缺了立即失败，不能等到第一个请求才发现。
- **环境切换**：`APP_PROVIDER`、`OBJECT_STORE` 这类决定走哪条实现的开关。
- **默认可跑**：教学基线的默认值（SQLite、本地目录），让新环境 `docker compose up` 就能起来。

配套项目的 `app/config.py` 就是这个模式：frozen dataclass + `from_env` + `validate()`：

```python
def validate(self) -> None:
    if self.provider == "openai_compatible" and not self.openai_api_key:
        raise RuntimeError("APP_PROVIDER=openai_compatible 需要配置 OPENAI_API_KEY")
    if self.object_store == "minio" and not (self.minio_access_key and self.minio_secret_key):
        raise RuntimeError("OBJECT_STORE=minio 需要 MinIO 访问配置")
```

“启动即失败”比“第一个请求报 500”便宜一个数量级，因为它能被健康检查和部署流程拦住，而不是被用户发现。

### 密钥的三条纪律

1. **不进日志与事件**：错误事件、SSE 事件、trace 属性里只允许出现密钥的指纹（如后四位），不出现值。结构化日志最容易在这里出事。
2. **不进客户端可达面**：配套项目的 `/api/auth/dev-token` 是开发辅助端点，生产部署必须 `APP_ENABLE_DEV_TOKENS=false`。这类“方便之门”要在部署清单里逐个确认，而不是靠记得。
3. **注入走 CI/CD 的 Secret 机制**：GitHub Actions Secrets、K8s Secret、云平台参数存储。PR 来自 fork 时不给生产 Secret——评测和测试都不需要真实 Key，这也是保持 demo Provider 存在的理由之一。

## 镜像：可复现构建

Agent 服务的镜像没有特殊性，但要守住三条：

```dockerfile
FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

FROM python:3.12-slim
RUN useradd --create-home appuser
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY app ./app
ENV PATH="/app/.venv/bin:$PATH"
USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- **锁文件进镜像**：`uv sync --frozen`，CI 构建和本地构建逐字节一致。没有锁文件的 Agent 项目，模型 SDK 的破坏性升级会在某个周一自动上线。
- **依赖层与代码层分离**：先 COPY 依赖清单再 COPY 源码，改代码不重建依赖层。
- **非 root + 健康探针**：配套项目已有 `/health/live` 与 `/health/ready` 两级探针，live 失败重启容器，ready 失败先摘流量——`ready` 应检查数据库连接和模型配置，而不是只返回 200。

## 进程拓扑：API、Worker、Relay 为什么必须分进程

```text
              ┌─ nginx / 负载均衡（SSE 不缓冲）
客户端 ───────┤
              └─ api × N        （无状态：配置与密钥来自环境）
                     │
       ┌─────────────┼────────────────┐
 PostgreSQL+pgvector   Redis（队列/Pub-Sub）   MinIO（对象存储）
                     │
              worker × N       （租约领取入库任务）
                     │
              outbox-relay     （业务事件对外发布）
```

分进程的理由：模型调用和文档解析是长耗时操作，混在 API 进程里会占住事件循环和连接；Worker 需要按队列深度独立伸缩；故障隔离让“解析挂了”不等于“问答挂了”。配套项目的 compose 已是这个拓扑的三进程版（api / worker / outbox-relay），生产要做的不是改拓扑，而是替换它们共享的资源。

### 水平扩展的四个硬约束

API 起第二个副本之前，逐条核对（详细推演见[Multi-Agent 与人工兜底](./agent-multi-agent)的多实例部分）：

1. **进程内状态必须外置**。教学基线里的进程内向量索引、会话记忆 dict，在多副本下会导致两个副本各答各的。替换方案见本章末尾的迁移清单。
2. **任务领取必须互斥**。靠条件更新（`UPDATE ... WHERE status='queued'` 检查 rowcount）或队列的原子消费，两个 Worker 不能拿到同一个任务。
3. **SSE 需要外置广播**。事件目前在请求内生成、请求内推送，天然单连接可用；一旦出现“后台事件要推给已建立的连接”（如任务进度推送），就需要 Redis Pub/Sub 转发，且要么会话粘性、要么每个副本都能收到。
4. **挂起态要能活过发布**。`interrupt()` 等待审批的 Agent 若状态只在进程内存里，滚动发布即丢失；持久化 Checkpoint 加 TTL 审批单是最低要求。

## 反向代理：SSE 的坑在这里落地

[Agent 流式输出](./agent-streaming)讲过协议，这里讲它如何穿过 nginx。三个经典故障的根因都在代理层：

```nginx
upstream agentic_rag_api {
    server api-1:8000;
    keepalive 32;
}

location /api/ {
    proxy_pass http://agentic_rag_api;
    proxy_http_version 1.1;
    proxy_set_header Connection "";

    # SSE 第一坑：响应被缓冲成“最后一口气全吐出来”
    proxy_buffering off;
    proxy_cache off;

    # SSE 第二坑：读超时小于回答时长，连接被代理掐断
    proxy_read_timeout 300s;
    proxy_send_timeout 300s;
}

# SSE 第三坑：event-stream 被 gzip 包住，客户端收不到增量
# 显式排除，或对该 location 关闭 gzip
location /api/answer/stream {
    gzip off;
    proxy_pass http://agentic_rag_api;
    # ... 同上
}
```

应用侧配合两件事：响应头带 `X-Accel-Buffering: no`（对不归你管的代理也生效），心跳间隔必须小于代理的最短超时（如 15s 心跳对 60s 读超时），否则空闲连接会被中间层静默断开。

断线重连的最小实现：事件带递增 id，服务端按会话保留最近事件缓冲；客户端 `EventSource` 自动带 `Last-Event-ID` 重连，服务端从缓冲补发缺失事件。教学项目当前是请求内生成器，没有持久事件表——这一点在第 12 章边界声明里写明，接生产事件总线时按上述协议实现。

## 数据库迁移：Alembic 最小接入

教学基线用 `create_all` 起步没有问题，但生产演进必须有迁移链：改列、回滚、多环境一致性都靠它，“表结构和代码不一致”这类事故只能靠迁移链预防。

```bash
uv add --dev alembic
uv run alembic init -t async migrations
```

`migrations/env.py` 里把数据库 URL 指向配置而不是写死：

```python
from app.config import settings

config.set_main_option("sqlalchemy.url", settings.database_url)
```

之后的工作流：

```bash
# 改了 app/persistence.py 的模型后
uv run alembic revision --autogenerate -m "add ingestion attempt column"
# 本地与 CI 各跑一遍，保证迁移链在干净库上可重放
uv run alembic upgrade head
```

CI 里把“迁移链可重放”变成门禁：在测试 Job 里先 `alembic upgrade head` 到一个全新数据库，再跑测试套件。迁移一旦合入就不可修改（只能追加新迁移），否则别人的环境会永远停在一个不存在的版本号上。

和入库链路的关系：[解析失败的索引一致性](./agentic-rag-project-parsing)要求候选/生效双索引版本切换，迁移只改结构、索引版本切换只改数据可见性，两件事不要混在一个“重建”操作里。

## CI/CD：把评测变成门禁

Agent 项目的流水线比普通项目多一层：**质量不止由测试定义，还由评测集定义**。测试保证行为不变量（权限、幂等、协议），评测保证效果不回退（召回、拒答、路由）——[Agent 与 RAG 评测](./agent-eval)的 CI 门禁在本项目落地成这条流水线：

```text
lint (ruff) ──► test (pytest，demo Provider，全离线) ──► eval (固定评测集，指标落盘) ──► build (docker) ──► deploy
                                                        │
                                                        └─ 指标与基线 diff，由对变错须人工确认
```

配套仓库已按此落地 `.github/workflows/agentic-rag.yml`：

```yaml
name: agentic-rag

on:
  push:
    branches: [main]
    paths: ["projects/agentic-rag/**", ".github/workflows/agentic-rag.yml"]
  pull_request:
    paths: ["projects/agentic-rag/**", ".github/workflows/agentic-rag.yml"]

concurrency:
  group: agentic-rag-${{ github.ref }}
  cancel-in-progress: true

defaults:
  run:
    working-directory: projects/agentic-rag

jobs:
  lint-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: astral-sh/setup-uv@v6
        with:
          enable-cache: true
          cache-dependency-glob: projects/agentic-rag/uv.lock
      - run: uv sync --frozen
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run pytest -q

  eval:
    needs: lint-test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: astral-sh/setup-uv@v6
        with:
          enable-cache: true
          cache-dependency-glob: projects/agentic-rag/uv.lock
      - run: uv sync --frozen
      - run: uv run python evals/run.py
      - uses: actions/upload-artifact@v4
        with:
          name: eval-report
          path: projects/agentic-rag/reports/latest.json

  docker:
    needs: lint-test
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - run: docker build -t agentic-rag:${{ github.sha }} .
```

三个设计点：

- **离线是门禁的前提**。评测和测试都跑 demo Provider，PR 阶段零成本、全确定；接真实模型的重评测放夜间任务，两套基线分开记录口径。
- **评测产物是构件**。`reports/latest.json` 作为 artifact 归档，每次发布都能回答“这次带出去的指标是什么”。
- **镜像在 main 上构建**。deploy Job 把镜像推到registry并按环境发布，Secret 只在受保护分支的部署环境里注入。

## 发布与回滚：Agent 特有的两件事

### 滚动发布杀不死“正在等人的 Agent”

普通服务滚动发布最多断几条连接；Agent 服务要额外处理两类在途状态：

1. **长流式请求**：发布前停止向该实例派新流量，等 SSE 连接自然结束（drain），超时才强杀。客户端拿到 `done` 之外的断连应走 Last-Event-ID 重连。
2. **挂起态**：等待人工审批的 Agent 实例被替换时，审批单还在数据库里。持久化 Checkpoint 让新实例能从断点恢复；审批单要有 TTL 和定时关闭，否则发布三天后批准一个过期请求依然会执行。[Multi-Agent 与人工兜底](./agent-multi-agent)给了完整机制。

### 模型配置也是发布物

Prompt 版本、模型路由表、温度参数、Rerank 开关——这些“配置”实际是行为变更，要走与代码相同的评审、灰度和回滚流程。回滚顺序按耦合关系定：Prompt 和模型路由与代码解耦时可以先回配置；数据库迁移用 expand-contract（先加后删，两版代码共存），让代码回滚永远不需要回滚数据库。

### 灰度用 trace_id

按 `trace_id` 哈希取百分比切流，比按用户切更均匀、比随机可复现。灰度期间盯[可观测性](./agent-observability)里定义的那组指标：拒答率、转人工率、P95、TTFT、单轨迹成本——指标先行，出问题先回滚再定位。

## 生产迁移清单：教学基线 → 可上线

配套项目为教学刻意保留了零依赖基线（见第 1 章与 SPEC 的边界声明）。上线前按下表逐项替换，**顺序按依赖关系**：先数据层，再队列与存储，最后观测。

| 教学基线 | 生产替换 | 为什么不能带上线 | 验证方法 |
|---|---|---|---|
| aiosqlite | PostgreSQL | 写锁把并发写入串行化；缺约束与类型 | 双 Worker 并发摄取测试在 PG 上重跑 |
| 进程内向量索引 | pgvector | 每次查询全量重建；多副本各持一份；内存有上限 | 检索调试端点对比迁移前后召回一致 |
| SQLite 任务表 | Redis / 消息队列 + 租约 | 无可见性超时，Worker 崩溃任务永久卡死 | kill 掉 Worker，任务自动重投给其他副本 |
| 本地文件系统卷 | MinIO / S3 | 共享卷是单点，多副本挂载冲突 | 双副本上传-解析-问答回归 |
| 进程内会话记忆 | Redis / 数据库 | 多副本下同一会话漂移 | 同一会话轮询两个副本答案连续 |
| `create_all` | Alembic | 结构无法演进，回滚无处可去 | 干净库重放迁移链 |
| 无 Trace 后端 | OpenTelemetry | 没有日志、指标和链路等于盲飞 | trace_id 从 HTTP 到模型调用贯穿 |

迁移完成后，重新跑一遍固定评测集：基线是在 demo Provider 和内存向量上建立的，换生产组件后指标口径必须重建，不能拿旧数字当门槛。

## 本章小结

Agent 服务的交付 = 普通后端交付 + 三件特有的事：状态外置（不然扩不了副本）、长连接治理（不然流式全是坑）、成本与效果门禁（不然一次发布就是一次账单和召回事故）。配套项目已经给出了拓扑和离线门禁，本篇补齐的是它边界声明里“生产迁移方向”的那一半——每一项都有明确的替换对象和验证方法，按清单走完，“能跑的 Demo”就变成“敢上线的服务”。

---

## 面试问答

**1. Agent 服务和普通 API 服务在部署上有什么本质区别？**

- 四点：请求长（SSE 长连接要过代理这一关）、状态多（检索缓存、会话记忆、挂起态都容易留在进程里，扩副本前必须外置）、成本敏感（限流和预算护栏要在部署层就有，不能等账单）、外部依赖多一个模型 API（限速、超时、版本漂移都要按“依赖会坏”设计）。
- 加分：能说出“挂起等人工审批的 Agent”是普通服务完全没有的在途状态，发布策略要专门为它设计。

**2. 多副本部署 Agent 服务前要检查什么？**

- 四个硬约束：进程内状态外置、任务领取互斥、SSE 事件外置广播、挂起态可恢复。任何一个不满足，加副本只会引入“两个副本各答各的”这类难以复现的 bug。
- 别踩的坑：内存向量索引在多副本下不是“性能差”，是**召回结果不一致**——同一个问题在不同副本拿到不同证据，用户看来就是答案随机变。

**3. SSE 经过 nginx 后前端一次性收到全部内容，怎么排查？**

- 按序检查：`proxy_buffering` 是否关闭、`proxy_http_version` 是否 1.1、读超时是否小于回答时长、event-stream 是否被 gzip。
- 应用侧自查：响应头带 `X-Accel-Buffering: no`，心跳间隔小于中间层最短超时。
- 加分：提到“客户端用 fetch 而不是 EventSource 也能读流”时，代理配置是同一套——问题几乎总在代理层，不在浏览器。

**4. 数据库迁移怎么做到不停机？**

- expand-contract：先加新列/新表（兼容旧代码），再迁数据，再切读，最后下个版本删旧结构。每一步发布都兼容上一步的代码，回滚永远不需要回滚数据库。
- 配合候选/生效索引版本切换，结构变更和数据可见性变更分开做。
- 别踩的坑：迁移合入后不能修改，只能追加——否则所有已部署环境会停在一个不存在的版本上。

**5. CI 里怎么防止 Agent 质量回退？**

- 双门禁：pytest 保证行为不变量（权限、幂等、协议），固定评测集保证效果指标（召回、拒答、路由）不回退；指标与基线做 diff，“由对变错”的样例必须人工确认后才能更新基线。
- 全部跑 demo Provider：PR 门禁要快、要省、要确定；真实模型的重评测放夜间，两套基线分开记口径。
- 加分：能说出评测产物（报告 JSON）作为 artifact 归档，发布时可追溯“这次带出去的指标”。

**6. 滚动发布时，正在执行和挂起中的 Agent 怎么办？**

- 分两类：请求内的长流式请求靠 drain——摘流量、等连接结束、超时才杀；挂起态靠持久化 Checkpoint 加审批单 TTL——新实例能恢复断点，过期审批自动关闭。
- 回滚按耦合关系定顺序，Prompt/模型路由当发布物管理；数据库用 expand-contract 保证代码回滚不需要回滚数据。
- 别踩的坑：只做“优雅停机”不做“状态外置”，挂起三天的审批流会在发布时全部丢失，而且没有任何报错。

**7. 从教学项目到生产，替换组件的顺序是什么？为什么？**

- 先数据层（SQLite → PostgreSQL+pgvector）：它是其他一切的前提，队列、租约、指标落库都依赖它；再对象存储和队列（解决单点和任务恢复）；最后观测（OTel），因为前两步的效果要靠它验证。
- 每换一个组件重跑一次固定评测集——教学基线的指标口径不自动适用于生产组件。
- 加分：能指出“先上观测再迁移”也是合理顺序，前提是迁移期间有人盯着对比新旧链路的指标。
