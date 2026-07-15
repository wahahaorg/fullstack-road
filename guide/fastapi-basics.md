# FastAPI 基础

## 这一章解决什么问题

如果你会 NestJS，理解 FastAPI 会很快。它们都在解决类似问题：

```txt
接收 HTTP 请求
校验输入
调用业务逻辑
返回 JSON
生成接口文档
处理错误
```

区别是 FastAPI 更轻，更多依赖 Python 类型标注和函数组合。

## 最小应用

```python
from fastapi import FastAPI

app = FastAPI(title="AI Platform API")

@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
```

运行：

```bash
uvicorn app.main:app --reload
```

常用地址：

```txt
/docs
/redoc
/openapi.json
```

## 路径参数、查询参数、请求体

```python
from typing import Annotated

from fastapi import Body, Path, Query
from pydantic import BaseModel, Field

class DocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    file_key: str = Field(min_length=1)

@app.post("/knowledge-bases/{kb_id}/documents")
async def create_document(
    kb_id: Annotated[int, Path(gt=0)],
    payload: DocumentCreate,
    preview: Annotated[bool, Query()] = False,
) -> dict:
    return {
        "kb_id": kb_id,
        "preview": preview,
        "payload": payload.model_dump(),
    }
```

FastAPI 的判断规则：

- 出现在路径模板里的参数是 Path。
- 普通标量参数默认是 Query。
- Pydantic 模型通常是 Body。
- Header、Cookie、File 需要显式声明。

## Pydantic Schema 就像 DTO

NestJS 里你会写 DTO：

```ts
class CreateUserDto {
  name: string
}
```

FastAPI 里通常写 Pydantic 模型：

```python
from pydantic import BaseModel, ConfigDict, Field

class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=64)
    phone: str = Field(min_length=6, max_length=32)

class UserRead(BaseModel):
    id: int
    username: str
    phone: str
```

建议拆分：

```txt
UserCreate  创建输入
UserUpdate  更新输入
UserRead    输出
User        ORM 实体
```

不要用一个类同时承担请求校验、响应序列化和数据库映射。

## APIRouter：类似 Controller 分组

```python
from fastapi import APIRouter

router = APIRouter(prefix="/documents", tags=["documents"])

@router.get("/{document_id}")
async def get_document(document_id: int) -> dict:
    return {"id": document_id}
```

在主应用挂载：

```python
from fastapi import FastAPI
from app.api.documents import router as documents_router

app = FastAPI()
app.include_router(documents_router)
```

## Depends：依赖注入

FastAPI 没有 NestJS 那种完整 IoC 容器，但 `Depends` 可以处理常见依赖：

```python
from typing import Annotated
from fastapi import Depends, Header, HTTPException

async def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    if not authorization:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return {"id": 1, "name": "Sizhe"}

@app.get("/me")
async def me(user: Annotated[dict, Depends(get_current_user)]) -> dict:
    return user
```

常见用途：

- 获取数据库 session。
- 获取当前用户。
- 权限校验。
- 分页参数。
- 读取配置。

## 错误处理

简单错误：

```python
from fastapi import HTTPException

raise HTTPException(status_code=404, detail="Document not found")
```

业务项目里可以定义统一异常：

```python
class AppError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
```

再用全局异常处理器转成统一响应。

## async/await 怎么理解

`async def` 适合 I/O 密集任务：

- 查数据库。
- 调外部接口。
- 读写对象存储。
- 等待大模型响应。

但不要把 CPU 密集任务直接塞进 async 接口：

```python
@app.post("/parse")
async def parse_pdf():
    # 大 PDF 解析、OCR、向量化不应长期占住请求
    ...
```

这类任务更适合异步队列、后台 worker 或任务表。

## BackgroundTasks 的边界

FastAPI 有 `BackgroundTasks`：

```python
from fastapi import BackgroundTasks

def send_email(to: str) -> None:
    ...

@app.post("/notify")
async def notify(background_tasks: BackgroundTasks):
    background_tasks.add_task(send_email, "user@example.com")
    return {"ok": True}
```

适合轻量任务，例如发通知、写日志。

不适合关键任务：

- 文件解析。
- 支付回调。
- 长时间向量化。
- 必须可靠重试的任务。

关键任务应该入库或进 MQ，让 worker 可重试、可观测、可恢复。

## 面试怎么说

> FastAPI 的核心是基于 Python 类型标注和 Pydantic 做请求校验、序列化和 OpenAPI 生成。项目里我会用 APIRouter 组织接口，用 Pydantic 拆分输入输出模型，用 Depends 处理数据库 session、鉴权和权限校验。对于耗时任务，我不会直接阻塞请求，而是设计任务表或队列异步处理。

