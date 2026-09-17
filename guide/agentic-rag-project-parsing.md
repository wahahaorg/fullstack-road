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

本章正文讲解的 `ContentBlock`、坐标定位、OCR 阈值、Parser Registry、父子 Chunk 与三种切分策略对比是完整设计参考：一部分在后续章节以简化形式落地，其余属于**生产扩展 / 模型预留**。不要把正文中的类和脚本当成仓库里已有的代码，遇到差异以本节为准。通用入库链路与切分取舍见 [RAG 入库管线](./rag-pipeline)。

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

把它们拆开看：

| 问题 | 负责层 | 输入 | 输出 | 失败时影响 |
|---|---|---|---|---|
| 解析 | Parser | 对象存储里的原文件字节 | 结构块（标题、段落、表格、页码/坐标） | 任务 `parse_error`，文档不进审核 |
| 切分 | Chunker | 结构块序列 | 检索单元（子 Chunk / 可选父 Chunk） | 空文档、切碎表格、丢失列名 |
| 展示 | Locator / Citation | Chunk 元数据 + 命中结果 | 页码、工作表、高亮区域、引用编号 | 答案对但无法核验原文 |

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

### 三层数据契约：谁产生什么字段

解析器产结构块，Chunker 组检索单元，引用渲染器把元数据变成页码 / 工作表 / 高亮。拆开后，换 PDF 解析库不必让 Retriever 理解私有 Page 对象。

| 层 | 必产字段 | 可选 / 生产扩展 | 下游 |
|---|---|---|---|
| Parser | `type`、`text`、`heading_path`、页/表定位 | `bbox`、`cell_range`、行列对象 | Chunker |
| Chunker | `chunk_id`、`document_id`、检索/展示文本 | `parent_id`、`ordinal`、`embedding_text` | Retriever |
| Citation | 可核验 locator | 高亮多边形、截图 URL | 回答 UI |

换 Parser（pypdf → 带布局库）时，只要仍吐同一套 `ContentBlock`，Chunker 与 Citation **不必改接口**。Retriever 只认 Chunk 表里的向量与元数据。点到为止的类比：Parser ≈ 编译 AST，Chunker ≈ bundler chunk，Citation ≈ source map——中间表示稳定，才能换工具链。

这与[多模态 RAG](./rag-multimodal)一致：文本是检索表示，原始区域才是核验证据位置。

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

## Parser Registry：格式映射与失败错误码

上传接口只识别媒体类型并选择解析器，不要在业务代码里散落 `if suffix == ".pdf"`：

```python
class Parser(Protocol):
    supported_media_types: frozenset[str]

    async def parse(self, source: StoredObject) -> ParsedDocument: ...


PARSER_REGISTRY: dict[str, Parser] = {
    "application/pdf": PdfParser(),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": DocxParser(),
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": PptxParser(),
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": XlsxParser(),
    "text/markdown": MarkdownParser(),
    "text/plain": PlainTextParser(),
}


def for_media_type(media_type: str) -> Parser:
    parser = PARSER_REGISTRY.get(media_type)
    if parser is None:
        raise UnsupportedMediaType(media_type)
    return parser
```

配套项目当前是**按文件名后缀分流**的简化版；上表是生产 Registry。本地不必先上完整 Registry，但边界要一致：不信任前端 `Content-Type`、不只信后缀；未知格式勿静默当纯文本；失败写稳定错误码而非堆栈原文。

### 魔数校验与异常映射（生产扩展示例）

上传声明与真实字节常不一致。生产在选 Parser 前读文件头；本地可继续后缀分流：

```python
MAGIC_RULES: list[tuple[bytes, str]] = [
    (b"%PDF", "application/pdf"),
    (b"PK\x03\x04", "application/zip"),  # Office 再读 [Content_Types].xml
]

def sniff_media_type(header: bytes, claimed: str) -> str:
    for magic, media in MAGIC_RULES:
        if header.startswith(magic):
            return refine_office_zip(header) if media.endswith("zip") else media
    if claimed == "application/pdf" and not header.startswith(b"%PDF"):
        raise UnsupportedMediaType(claimed)
    if claimed in PARSER_REGISTRY:
        return claimed
    raise UnsupportedMediaType(claimed)


def map_parse_exception(exc: Exception) -> str:
    if isinstance(exc, (UnsupportedMediaType, EncryptedOrCorruptFile)):
        return "parse_error"
    if isinstance(exc, EmptyDocumentError):
        return "empty_document"
    if isinstance(exc, ObjectStoreReadError):
        return "object_read_error"
    return "internal_error"  # 勿把 traceback 当对外 error_code
```

| 场景 | 稳定 `error_code` | 文档状态 | 客户端动作 |
|---|---|---|---|
| 损坏 / 加密 PDF、坏 Office | `parse_error` | `failed` | 提示检查文件；人工替换后重试 |
| 对象读失败 | `object_read_error` | `failed` | 稍后重试或检查对象是否存在 |
| 解析成功但无可用文本 | `empty_document` | `failed` | 提示内容为空 |
| 不支持的媒体类型 / 魔数不符 | `parse_error`（或细分 `unsupported_media`） | `failed` | 提示允许的格式清单 |

错误码、重试与取消见[第 6 章异步入库](./agentic-rag-project-async-ingestion)。本章只要求：解析异常能被 Worker 映射成这些码，而不是未分类的 `internal_error`。

## 父子 Chunk：召回与上下文的取舍

只用大 Chunk，向量容易混入多个主题；只用小 Chunk，答案又缺少限定条件。生产实现通常采用两层结构：

| 层 | 典型大小 | 用途 | 不适合做什么 |
|---|---|---|---|
| 子 Chunk | 100～300 有效字符 | 向量/关键词召回、Rerank | 直接当完整证据展示 |
| 父 Chunk | 一小节 / 一张表 / 一页幻灯片 | LLM 上下文、引用展示 | 单独做细粒度召回 |

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

检索命中多个相邻子 Chunk 后，按 `parent_id` 去重并取父内容：

```python
child_hits = await retriever.search(query, top_k=20)
ranked_parents = collapse_by_parent(child_hits)
context = await parent_store.fetch(ranked_parents[:5])
```

### 本地是否已实现：诚实边界

**配套项目尚未实现父子 Chunk 与相邻块合并。** 第 7 章写明：需持久化父子关系、Chunk 顺序和索引版本，且必须在同一权限范围内扩展。当前由第 8 章 Evidence 预算控上下文量。本节 `parent_id` / `collapse_by_parent` 是**数据模型预留 / 生产扩展**，不是可跑代码路径。

### 落地前必须持久化的字段

若要上父子结构，至少先把这些字段写进 Chunk / 索引表，再谈 `collapse_by_parent`：

| 字段 | 作用 | 缺了会怎样 |
|---|---|---|
| `parent_id` | 子块归属；召回后折叠到父内容 | 只能拼邻居文本，无法稳定取回整节/整表 |
| `ordinal`（同父内顺序） | 相邻子块合并、按阅读序组装 | 合并结果乱序，引用高亮错位 |
| `index_version` | 与文档某次解析产物绑定 | 新旧 Chunk 混检；半套索引难以整体回滚 |
| 权限边界（如 `acl` / `space_id`） | 扩展邻居时做同范围校验 | 可见子块带出不可见父块或跨空间邻居 |

`collapse_by_parent`：按 `parent_id` 去重时保留该父下**最高分**子命中作排序键；取父前校验与命中子块同属一个权限边界。禁止“命中 A 空间子块 → 拼上 B 空间相邻父块”。本章只要求：**扩展不得跨权限拼邻居**。

## 表格不能被普通空行切分

上一章的 Markdown 切分器遇到表格时恰好保留了整段，但超长表格仍可能从任意字符断开。按空行切分对表格尤其危险：

```text
| 城市 | 上限 |
|------|------|
| 北京 | 650 |
| 成都 | 450 |
```

Markdown 表格行之间没有空行；若退化为“按段落”再按字符硬切，可能得到：

```text
Chunk A: | 城市 | 上限 | ------ | ------ | | 北京 | 650 |
Chunk B: | 成都 | 450 |
```

Chunk B 丢失了表头，“450”失去量纲。更糟的失败样例来自真实办公文件：

| 失败样例 | 现象 | 后果 |
|---|---|---|
| 跨页 PDF 表 | 表在页中断开；下页重复表头或只剩数据行 | 子块无列名；页码 locator 只指一半 |
| 多级表头 Excel | 第 1 行是“渠道政策”，第 2 行才是列名；合并单元格跨列 | `str(row)` 得到空值或错位；折扣对不上客户级别 |
| 宽表（很多列） | 按固定字符切断，主键列与度量列分家 | 召回命中度量却看不到“城市/客户”主键 |

最小可行策略（生产扩展，不是本地现成 API）：

1. **整表作为父 Chunk**（或结构对象），不按空行拆。
2. **表头 × 每一行拼成子 Chunk**，检索用行、上下文用表。
3. **超宽表按列组拆分，但始终重复关键主键列**（如城市、客户级别）。
4. **跨页表合并重复表头**，并记录涉及的页码范围。

```python
def chunk_table(table: TableBlock) -> tuple[ParentChunk, list[ChildChunk]]:
    parent = ParentChunk(id=table.id, text=table.render_markdown(), locator=table.locator)
    children = []
    for row in table.rows:
        children.append(
            ChildChunk(
                parent_id=parent.id,
                text=f"{table.title}｜" + "｜".join(f"{h}：{v}" for h, v in zip(table.headers, row)),
                locator=row.locator or table.locator,
            )
        )
    return parent, children
```

本地现状 vs 生产最小策略：

| 维度 | 本地现状 | 生产最小策略 |
|---|---|---|
| Excel | 以“工作表：名称”为标题拼接数据行 | 工作表级父块 + 表头×行子块 + cell_range |
| Markdown 表 | 标题/段落切分下“碰巧”整段保留 | 识别 table block，禁止按空行/定长切断 |
| 跨页 / 多级表头 | 未专项处理 | 合并重复表头；多级表头展开后再分行 |
| 宽表 | 无列组拆分 | 拆列组时重复主键列 |

对于“北京和成都住宿标准相差多少”，两个城市行可能分别被召回。父 Chunk 让模型看到统一列名，后续 Agent 才能可靠计算差值。

## 用同一组问题比较切分策略

不要凭视觉感觉决定 Chunk 大小。生产实现通常保留多种策略并输出中间结果：

```text
fixed-500       固定字符窗口
heading-aware   标题与段落切分
parent-child    结构块 + 父子 Chunk   # 本地未落地，对比时作对照设计
```

配套项目当前只落地了 heading-aware 一种，且没有现成的多策略预览脚本。你可以在项目目录用几行代码直接观察切分结果：

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

把文件名换成其他格式的 fixture，即可对比各格式的解析输出。比较策略时，**固定同一问题集**，一次只改切分变量：

| 固定题 | 观察点 | 失败形态 |
|---|---|---|
| 上海住宿每晚最多报销多少？ | 是否命中正确表格行 | 命中邻行 / 丢表头 |
| 北京和成都相差多少？ | 是否同时取到两行和共同表头 | 只召回一行；无法计算 |
| 引用能否定位真实页码或单元格？ | locator 是否完整 | 只有正文、无页码/区域 |

### 实验纪律与结果记录

记录方法（为第 15 章铺路，本章不算显著性）：

1. 同一 Embedding、同一检索 Profile、同一回答模型。
2. 每题记下：正确 Chunk 是否进 Top K、locator 是否可核验、答案是否靠猜。
3. 只改切分策略，不改 Rerank / Prompt。
4. 写成可复现记录（JSONL 便于以后导入评测脚本）：

```json
{"run_id": "chunk-ab-2026-09", "strategy": "heading-aware", "qid": "travel-lodging-shanghai", "recall_at_5": 1, "citable": true, "note": "hit table row"}
{"run_id": "chunk-ab-2026-09", "strategy": "fixed-500", "qid": "travel-lodging-shanghai", "recall_at_5": 0, "citable": false, "note": "header lost"}
```

本章先观察检索**输入**是否正确。Recall@K、MRR 完整实验留到第 7、[15 章评测](./agentic-rag-project-evaluation)。通用切分对比也可对照 [RAG 入库管线](./rag-pipeline)。

## 解析失败不能留下半套索引

解析与写库之间最危险的状态是：旧 Chunk 已删、新 Chunk 未写完，或写了一半就崩溃。用户检索会看到“新制度缺后半段”，比完全失败更糟。

### 与 `replace_chunks` 事务的关系

第 6 章 Worker 成功路径的关键一步是：

```python
chunks = parse_document(document.filename, raw)
await documents.replace_chunks(document.id, chunks)
await documents.complete_ingestion_task(task.id)  # → review_pending
```

`replace_chunks` 在**一个事务**中先删同文档旧 Chunk 再插新结果。解析抛错则不调用它；写库中失败整事务回滚；取消若发生在写入之后、`complete` 之前则 `discard_chunks`。

### 四条路径对照

| 路径 | 解析 | 写库 | 任务 / 文档 | 检索侧可见 |
|---|---|---|---|---|
| 成功 | 产出 Chunk | `replace_chunks` 提交 | `complete` → `review_pending` | 待审核通过后按发布规则可见 |
| `parse_error` | 抛错 / 空文档 | **不调用** `replace_chunks` | 任务失败码；文档 `failed` | 旧 published 版本（若有）继续可检 |
| 写库中失败 | 已成功 | 事务回滚 | 任务失败；文档不进审核 | 旧 Chunk 仍在，无半套新索引 |
| 取消 | 可能已成功 | 若已写入则 `discard_chunks` | 任务取消；不 `complete` | 不留下 draft 半套候选 |

本地保证是“失败不推进审核 + 写库事务原子”，**不是**生产级的候选/生效双索引切换。生产候选做法：解析产物写入独立的 `index_version`，全部结构块和向量就绪后再切换 `active_index_version` 指针——细节见[第 14 章可靠性](./agentic-rag-project-reliability)。

### 文档状态回滚与旧版本检索

```python
try:
    parsed = await parser.parse(source)
    chunks = chunker.build(parsed)
    await chunk_repository.replace_chunks(document.id, chunks)
except UnsupportedEncryptedFile as exc:
    await documents.mark_failed(document.id, code="parse_error", detail=str(exc))
    # 不进 review_pending；已 published 的同族旧版继续可检索
```

解析失败停在 `parse_error`，文档不进 `review_pending`；用户看到旧版本或明确失败原因，而不是缺后半段的新制度。任务错误码、`discard_chunks` 与重试见[异步入库](./agentic-rag-project-async-ingestion)。

## 从解析输出到可检索 Chunk 的最小清单

落地或 Code Review 时可以用这张表自检：

| 检查项 | 本地现状 | 生产扩展 |
|---|---|---|
| 统一解析入口 | `parse_document(filename, raw)` | Parser Registry + 魔数校验 |
| 结构块类型 | 仅 `heading` + `content` | `ContentBlock`（含 table/list/image） |
| 定位信息 | 页/幻灯片/工作表级标题字符串 | page / sheet / cell_range / bbox |
| 表格 | 整段拼接，无按行子 Chunk | 父表 + 行级子 Chunk |
| 父子关系 | **未实现** | `parent_id` + 发布时同版本持久化 |
| 失败路径 | `parse_error` → 文档 `failed` | 同上 + 候选索引不切换 |
| 写库原子性 | `replace_chunks` 单事务 | `document_id + index_version` 唯一约束 |

### 面试时怎么说清本地与生产

常见追问是“你们做了父子 Chunk 吗”。推荐答法：

1. **问题**：小块利于召回、大块利于生成，单层 Chunk 很难两头兼顾。
2. **本地**：heading-aware 单层切分 + Evidence 预算控上下文；相邻/父子合并**未实现**（第 7 章已写明）。
3. **生产扩展**：持久化 `parent_id` / 顺序 / `index_version`，召回子块、组装父块，且扩展不得跨权限。
4. **验证**：同一固定题集上对比 `heading-aware` 与 `parent-child`，再进入第 15 章的 Recall@K / MRR，而不是凭感觉调 `chunk_size`。

这样既展示设计判断，又不把预留模型说成已交付能力。

## 本章小结

六种常见格式有统一解析入口，Chunk 保留页/幻灯片/工作表级定位；解析失败停在 `parse_error`，不会把半套索引推进检索。解析 / 切分 / 展示职责分离后，换解析库不必重写检索与引用。`ContentBlock`、父子 Chunk、坐标定位是生产扩展——本地尚未实现相邻/父子合并；先用固定题集比较切分策略，再决定何时引入。

继续阅读[第 6 章：异步入库与任务状态](./agentic-rag-project-async-ingestion)，把解析、切分、Embedding 与索引移出 HTTP，加入 Worker、任务状态、进度和可重试错误。
