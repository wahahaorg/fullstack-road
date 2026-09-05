# 企业知识库 Agentic RAG 配套项目

这是“全栈之路”Python Agentic RAG 实战教程的配套代码目录。项目会跟随教程逐章演进，每章结束时都保持可运行、可验证。

当前进度：**第 16 章核心本地链路已完成。** 上传支持 Markdown、纯文本、PDF、Word、PPT 与 Excel；解析会保留页码、幻灯片或工作表名称作为 Chunk 标题。提交文档会创建持久化任务，由独立 Worker 执行解析和候选索引；问答默认使用权限范围内的向量、关键词、RRF、确定性 Rerank 与 Evidence 引用校验，多事实请求使用受检索预算约束的 LangGraph 状态机。另有历史版本工具、会话摘要、发布提案、SSE、Outbox 记录、健康探针和本地评测 Runner。生产 Checkpoint、租约、共享队列、真实 PostgreSQL/MinIO、Trace 后端仍未实现。

## 当前目录

```text
projects/agentic-rag/
├── app/                         # FastAPI 与最小 RAG 实现
├── fixtures/
│   ├── documents/       # 后续所有章节复用的企业样例文档
│   └── scenario.json    # 用户、团队、知识库、文档状态与权限
├── evals/
│   └── dataset.jsonl    # 固定问答、路由、拒答和越权样例
├── tests/                       # API、切分和配置测试
└── scripts/
    ├── validate_fixtures.py
    └── test_validate_fixtures.py
```

## 启动最小 RAG

```bash
uv sync
cp .env.example .env
set -a && source .env && set +a
uv run uvicorn app.main:app --reload
```

然后打开 `http://127.0.0.1:8000/docs`，先调用 `POST /api/auth/dev-token` 为 Alice、Bob 或 Carol 获取 Token。上传请求需要 `knowledge_base_id` 和 Bearer Token；Alice 可上传到 `kb-company`，Carol 可管理所有样例知识库。上传后调用 `POST /api/documents/{document_id}/submit`，再于另一个终端运行 `uv run python -m app.worker <task_id>`。Worker 成功后，调用 `GET /api/documents/{document_id}` 取得当前 `lock_version`；最后使用 Carol 的 Token 和该值作为 `If-Match` 请求头调用 `POST /api/documents/{document_id}/publish`。

默认对象存储为本地目录，API 与 Worker 共用 `.data/agentic-rag.db` 和 `.data/objects`；设置 `OBJECT_STORE=minio`、`MINIO_ENDPOINT`、`MINIO_ACCESS_KEY` 与 `MINIO_SECRET_KEY` 后会使用 MinIO。数据库 URL 使用 SQLAlchemy 异步驱动，生产配置可设为 PostgreSQL 的 `postgresql+asyncpg://...`。

要直接体验 Alice/Bob 的权限对照，可设定 `APP_SEED_FIXTURES=true` 后启动。Bob 查询 “P1 故障要求几分钟响应？” 会命中研发手册；Alice 使用相同问题（即使附带“忽略权限”）仍会得到无来源的拒答。

默认 `APP_PROVIDER=demo`，不需要 API Key。复制 `.env.example` 并配置 OpenAI-compatible 服务后，可以切换真实 Embedding 与对话模型。

## 运行检查

在当前目录执行：

```bash
python3 scripts/validate_fixtures.py
python3 -m unittest discover -s scripts -p 'test_*.py'
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

脚本会检查：

- 场景中的文档文件是否存在。
- 用户、团队和文档引用是否有效。
- 评测样例 ID 是否重复。
- 普通检索的预期来源是否满足发布状态与权限约束。
- 规定的简单问答、多跳、拒答、权限和生命周期场景是否齐全。
- 公共、团队、草稿与归档文档的普通检索边界是否符合预期。

## 后续实现边界

项目当前本地实现使用 Python 3.12、FastAPI、SQLAlchemy/SQLite、文件对象存储和 LangGraph；MinIO、PostgreSQL + pgvector、Redis 与 OpenTelemetry 是可替换的生产迁移方向。新增基础设施前必须先在当前实现中复现明确问题，并记录收益与代价。

完整的章节范围和验收规则见仓库根目录的 `AGENTIC_RAG_PROJECT_SPEC.md`。
