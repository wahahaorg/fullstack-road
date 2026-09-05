# 本地评测报告

使用 Demo Provider 和固定 `evals/dataset.jsonl` 运行：

```bash
uv run python -m evals.run --output reports/latest.json
```

2026-09-06 本地基线（11 条样例）：

| 指标 | 结果 |
|---|---:|
| 路由准确率 | 1.0000 |
| 平均来源召回 | 0.9545 |
| 禁用来源泄漏率 | 0.0000 |
| 拒答准确率 | 1.0000 |

这是教学 fixtures 的回归基线，不代表生产质量。报告中的 `missing_facts` 和逐条结果用于定位失败样例。
