from app.chunking import split_markdown


def test_split_markdown_keeps_heading_context() -> None:
    chunks = split_markdown(
        "# 差旅制度\n\n## 住宿标准\n\n上海每晚 650 元。\n\n## 交通\n\n高铁二等座。"
    )

    assert [chunk.heading for chunk in chunks] == ["住宿标准", "交通"]
    assert chunks[0].content.startswith("住宿标准\n")
    assert "650" in chunks[0].content


def test_split_markdown_splits_oversized_paragraph() -> None:
    chunks = split_markdown("## 长段落\n\n" + "内容。" * 300, max_chars=120)

    assert len(chunks) > 1
    assert all(len(chunk.content) <= 120 for chunk in chunks)
