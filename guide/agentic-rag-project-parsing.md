---
title: 企业知识库 Agentic RAG 实战（五）：多格式解析与结构化切分
description: 先讲清多格式解析要保留哪些结构信息；配套项目当前交付统一解析入口和按格式定位标题的简化版，ContentBlock、父子 Chunk 与坐标定位是生产扩展方向。
---

# 企业知识库 Agentic RAG 实战（五）：多格式解析与结构化切分

> 前四章已经知道哪些文档可用，但检索质量仍取决于如何把文件变成 Chunk。本章不追求“支持很多后缀”，而是让每个片段既适合召回，又能回到用户看得懂的原文位置。

## 本章交付与边界

配套项目当前交付的是一个刻意简化的解析层，先说清它做了什么：

- `app/parsing.py` 的 `parse_document()` 是统一解析入口：Markdown 与纯文本直接交给切分器；PDF 用 pypdf 逐页提取文本，以“第 N 页”作为 Chunk 标题；Word 按 Heading 样式分节，普通段落归入最近的标题；PPT 以“第 N 张幻灯片”为标题汇总同页文本框；Excel 以“工作表：名称”为标题拼接数据行；不支持的后缀直接报错。
- `app/chunking.py` 按标题与段落切分，600 字上限、约 80 字重叠，尽量对齐句号或换行边界，超长段落用重叠窗口断开。

本章正文讲解的 `ContentBlock`、坐标定位、OCR 阈值、Parser Registry、父子 Chunk 与三种切分策略对比是完整设计参考：一部分在后续章节以简化形式落地，其余属于生产扩展方向。不要把正文中的类和脚本当成仓库里已有的代码，遇到差异以本节为准。

## 先看结构化切分带来的差异

假设差旅制度的住宿标准在 PDF 第 4 页，是一个三行表格。固定每 500 字切分可能得到：

```text
Chunk A: ……住宿标准 城市类别 示例 每人每晚
Chunk B: 上限 一线城市 北京 上海 广州 深圳 650 元……
```

检索虽然可能命中 Chunk B，但它丢失了标题和列名，“650 元”究竟是上限、补贴还是罚款只能靠猜。

结构化解析后，检索使用紧凑的子 Chunk：

```json
{
  "text": "住宿标准｜一线城市｜北京、上海、广州、深圳｜每人每晚上限 650 元",
  "heading_path": ["差旅费用", "住宿标准"],
  "page": 4,
  "block_type": "table_row",
  "parent_id": "section-accommodation"
}
```

回答时再取回包含完整表格的父 Chunk，引用可以显示“第 4 页，住宿标准”。检索文本短而明确，生成上下文仍然完整。

## 解析、切分和展示是三个问题

很多实现把解析器返回的一大段字符串直接送入通用切分器，最终只能保存 `text`。这样做会同时丢掉三类信息：

- 文档结构：标题层级、列表、表格、备注。
- 空间位置：页码、幻灯片编号、工作表、单元格区域。
- 来源身份：解析后的片段对应哪个原始对象、哪个文档版本。

完整实现会先把不同格式归一化为 `ContentBlock`。配套项目当前的 `ChunkDraft`（`heading` + `content`）是它的最小版本，还没有类型、页码和坐标字段，但归一化的思路从这里开始理解：

```python
class ContentBlock(BaseModel):
    id: str
    type: Literal["heading", "paragraph", "table", "image", "list"]
    text: str
    heading_path: list[str]
    page_number: int | None = None
    sheet_name: str | None = None
    cell_range: str | None = None
    bbox: tuple[float, float, float, float] | None = None
    metadata: dict[str, str] = {}
```

解析器负责产生结构块，Chunker 负责把结构块组合成检索单元，引用渲染器负责把元数据变成页码、工作表和高亮区域。三个职责分开后，替换 PDF 解析器不会迫使检索层理解解析库的私有对象。

这与[多模态 RAG](./rag-multimodal)中的原则一致：文本只是检索表示，原始区域才是用户最终核验证据的位置。

## 为每种格式保留真正有用的结构

### PDF：页码和区域优先

PDF 页面保存的是绘制指令，不一定包含正确阅读顺序。解析器需要输出页码、文本块坐标和表格区域。对于扫描件，只有文本层为空或质量过低时才进入 OCR，避免所有 PDF 都承担昂贵的视觉处理。

```python
class PdfParser:
    async def parse(self, file: BinaryIO) -> ParsedDocument:
        pages = await extract_layout(file)
        if text_quality(pages) < settings.ocr_threshold:
            pages = await ocr_pages(file)
        return normalize_pdf_pages(pages)
```

页眉页脚要在 Chunk 前去重，否则“公司内部资料”“第 N 页”会出现在每个向量里，挤占真正语义。

### Word：标题样式和表格优先

Word 文档的 Heading 1/2/3 是天然层级。普通段落继承最近的标题路径，表格整体保留，并为每一行生成检索表示。文本框、批注和修订内容需要明确是否纳入，而不是悄悄忽略。

### PPT：一页是一段表达，不是一串文本框

幻灯片中的标题、正文、图表说明和演讲者备注需要区分。检索 Chunk 可以使用“页面标题 + 文本框 + 图表摘要”，引用则定位到幻灯片编号。不要按文本框逐个建 Chunk，否则问题命中一个数字时看不到同页图表的含义。

### Excel：工作表、表头和单元格区域优先

Excel 不能简单按行调用 `str(row)`。以渠道折扣表为例，每个数据行都必须携带多级表头：

```text
工作表：2026 渠道政策
区域：A6:D6
年合同额：100 万元
客户级别：金牌
最大折扣：85 折
审批人：销售总监
```

合并单元格的值要向所属区域传播，公式应同时保存表达式和缓存结果。引用展示时返回工作表名与区域，而不是虚构页码。

## Parser Registry 隔离格式差异

上传接口只识别媒体类型并选择解析器：

```python
class Parser(Protocol):
    supported_media_types: frozenset[str]

    async def parse(self, source: StoredObject) -> ParsedDocument: ...


parser = registry.for_media_type(document.media_type)
parsed = await parser.parse(source)
```

如果文件后缀是 `.pdf`，但文件头不是 PDF，解析任务应失败并记录明确原因。不能只信前端传来的 `Content-Type`。不支持的加密 PDF、损坏 Office 文件和超大工作表都进入可重试或需人工处理的失败状态。

## 父子 Chunk 同时满足召回和上下文

只用大 Chunk，向量容易混入多个主题；只用小 Chunk，答案又缺少限定条件。生产实现通常采用两层结构，这也是本章的设计目标：

- 子 Chunk：100～300 个有效字符，面向检索和 Rerank。
- 父 Chunk：一个完整小节、一张表格或一页幻灯片，面向 LLM 上下文和引用展示。

```python
@dataclass(frozen=True)
class SearchChunk:
    id: str
    parent_id: str
    document_id: str
    text: str
    embedding_text: str
    heading_path: tuple[str, ...]
    locator: SourceLocator
```

`embedding_text` 可以补入标题和列名，`text` 保留用户应看到的原文。不要为了提高召回修改原文内容，否则引用展示会把机器补写的文字冒充文档原句。

检索命中多个相邻子 Chunk 后，按 `parent_id` 去重并取父内容。配套项目尚未实现这一层，当前由第 8 章的 Evidence 预算组装（上下文预算、每文档限量、来源编号）承担同样职责，父子 Chunk 列为检索优化的扩展项：

```python
child_hits = await retriever.search(query, top_k=20)
ranked_parents = collapse_by_parent(child_hits)
context = await parent_store.fetch(ranked_parents[:5])
```

## 表格不能被普通空行切分

上一章的 Markdown 切分器遇到表格时恰好保留了整段，但超长表格仍可能从任意字符断开。完整实现把表格视为结构对象：

1. 保存完整表格作为父 Chunk。
2. 将表头与每一行拼成子 Chunk。
3. 超宽表格按列组拆分，但始终重复关键主键列。
4. 跨页表格合并重复表头，并记录涉及的页码范围。

对于“北京和成都住宿标准相差多少”，两个城市行可能分别被召回。父 Chunk 让模型看到统一列名，后续 Agent 才能可靠计算差值。

## 用同一组问题比较切分策略

不要凭视觉感觉决定 Chunk 大小。生产实现通常保留多种策略并输出中间结果：

```text
fixed-500       固定字符窗口
heading-aware   标题与段落切分
parent-child    结构块 + 父子 Chunk
```

配套项目当前只落地了 heading-aware 一种，且没有现成的预览脚本。你可以在项目目录用几行代码直接观察切分结果：

```bash
cd projects/agentic-rag && uv run python -c "
from pathlib import Path
from app.parsing import parse_document

raw = Path('fixtures/documents/travel-policy-v2.md').read_bytes()
for draft in parse_document('travel-policy-v2.md', raw):
    print(f'[{draft.heading}] {len(draft.content)} 字')
    print(draft.content[:120], '...')
"
```

把文件名换成其他格式的 fixture，即可对比各格式的解析输出；补齐多策略对比脚本是一个值得自己完成的练习。随后用固定问题集比较：

- “上海住宿每晚最多报销多少？”是否命中正确表格行。
- “北京和成都相差多少？”是否同时取到两行和共同表头。
- 引用是否能够定位到真实页码或单元格区域。

本章先观察检索输入是否正确。Recall@K、MRR 和 Rerank 的完整实验留到第 7、15 章，避免在解析问题还没解决时过早调排序参数。

## 解析失败不能留下半套索引

生产实现会为解析产物引入独立的候选/生效索引版本（`index_version`），只有全部结构块和向量准备完成后才切换检索入口。下面的机制是第 14 章可靠性要展开的设计参考：

```python
try:
    parsed = await parser.parse(source)
    chunks = chunker.build(parsed)
    await chunk_repository.replace_candidate(document.id, index_version, chunks)
except UnsupportedEncryptedFile as exc:
    await documents.mark_failed(document.id, code="encrypted_file", detail=str(exc))
```

当前配套项目用更简单的保证实现同一目标：解析失败时任务被标记 `parse_error` 并停止推进，文档不会进入 `review_pending`，已发布的旧版本继续参与检索（第 4 章的版本归档保证旧版本不被新上传覆盖）。用户看到的是旧版本或明确的失败原因，而不是缺了后半部分的新制度；候选/生效双索引切换列入生产扩展。

## 本章小结

现在，六种常见格式都有统一解析入口，Chunk 保留页码、幻灯片或工作表级别的定位标题；解析失败会让任务停在 `parse_error`，不会把半套索引推进检索。`ContentBlock`、父子 Chunk 和坐标级定位是这一层走向生产时的扩展方向，先理解它们解决什么问题，再决定何时引入。

继续阅读[第 6 章：异步入库与任务状态](./agentic-rag-project-async-ingestion)，把耗时的解析、切分、Embedding 和索引过程移出 HTTP 请求，加入后台 Worker、任务状态、进度和可重试错误。
