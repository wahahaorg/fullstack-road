# 企业知识库 Agentic RAG 配套项目

这是“全栈之路”Python Agentic RAG 实战教程的配套代码目录。项目会跟随教程逐章演进，每章结束时都保持可运行、可验证。

当前进度：**第 2 章，FastAPI 最小 RAG 闭环已完成。** 可以上传 Markdown 或纯文本，通过本地演示模型完成检索和带来源回答；PostgreSQL、权限和文档生命周期将在后续章节加入。

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
uv run uvicorn app.main:app --reload
```

然后打开 `http://127.0.0.1:8000/docs`，先调用 `POST /api/documents` 上传 `fixtures/documents/travel-policy-v2.md`，再调用 `POST /api/chat` 提问“上海住宿每晚最多多少钱？”。

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

项目使用 Python 3.12、FastAPI、PostgreSQL + pgvector、Redis、MinIO、LangChain 和 LangGraph。新增基础设施前必须先在当前实现中复现明确问题，并记录收益与代价。

完整的章节范围和验收规则见仓库根目录的 `AGENTIC_RAG_PROJECT_SPEC.md`。
