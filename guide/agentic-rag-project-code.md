---
title: Agentic RAG 配套项目：代码入口与运行
description: 找到企业知识库 Agentic RAG 教程的完整源码、运行入口、测试命令和章节代码对应关系。
---

# Agentic RAG 配套项目：代码入口与运行

这套实战的完整代码在同一个项目目录中持续演进。文章负责解释设计、取舍和验证结果，项目目录承载可以运行的 API、Worker、评测脚本和测试。

## 代码入口

- **在线源码目录**：[GitHub `projects/agentic-rag`](https://github.com/wahahaorg/fullstack-road/tree/main/projects/agentic-rag)
- **项目运行说明**：[项目 README](https://github.com/wahahaorg/fullstack-road/blob/main/projects/agentic-rag/README.md)
- **本地项目路径**：`projects/agentic-rag/`
- **完整章节范围**：[Agentic RAG 实战写作契约](../AGENTIC_RAG_PROJECT_SPEC)

直接打开源码目录，可以看到 `app/`、`fixtures/`、`evals/`、`tests/`、`Dockerfile` 和 `compose.yaml`。每章都在这套代码上继续增加能力，没有另起一套脱离主项目的示例。

## 本地启动

在仓库根目录执行：

```bash
cd projects/agentic-rag
uv sync
cp .env.example .env
set -a && source .env && set +a
uv run uvicorn app.main:app --reload
```

启动后打开 `http://127.0.0.1:8000/docs`。默认使用 `APP_PROVIDER=demo`，不需要 API Key；上传文档、提交入库任务、运行 Worker 和发起问答的完整步骤见[项目 README](https://github.com/wahahaorg/fullstack-road/blob/main/projects/agentic-rag/README.md)。

## 验证命令

```bash
cd projects/agentic-rag
python3 scripts/validate_fixtures.py
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run python -m evals.run
```

这些命令分别验证样例数据、自动化测试、代码规范和离线评测。评测结果保存在 `reports/latest.json`。

## 文章与代码对应关系

| 章节 | 主要代码入口 |
|---|---|
| 第 2 章 最小 RAG | `app/chunking.py`、`app/embeddings.py`、`app/rag.py`、`app/store.py` |
| 第 3-6 章 知识库后台 | `app/access.py`、`app/lifecycle.py`、`app/parsing.py`、`app/ingestion.py`、`app/worker.py` |
| 第 7-8 章 检索与引用 | `app/retrieval.py`、`app/citations.py`、`app/answering.py` |
| 第 9-12 章 Agent 能力 | `app/routing.py`、`app/agent_graph.py`、`app/tools.py`、`app/memory.py`、`app/streaming.py` |
| 第 13-16 章交付能力 | `app/auth.py`、`app/persistence.py`、`app/outbox_relay.py`、`evals/run.py`、`Dockerfile`、`compose.yaml` |
| 第 17 章 项目复盘 | `README.md`、`reports/latest.json`、全量 `tests/` |

从[第 1 章：项目目标与架构](./agentic-rag-project)开始阅读；如果想先运行代码，先打开本页的[在线源码目录](https://github.com/wahahaorg/fullstack-road/tree/main/projects/agentic-rag)，再回到[第 2 章：最小 RAG 闭环](./agentic-rag-project-minimal)。
