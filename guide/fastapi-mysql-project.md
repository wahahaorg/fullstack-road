# FastAPI + MySQL 项目结构

## 这一章解决什么问题

AI 很容易生成一个“所有代码写在一个文件里”的 FastAPI 项目：

```txt
main.py
  路由
  SQL
  业务逻辑
  错误处理
  配置
```

能跑，但很快会乱。更适合业务项目的结构是：

```txt
app
├── main.py
├── core
│   ├── config.py
│   └── errors.py
├── db
│   ├── session.py
│   └── models.py
├── api
│   └── documents.py
├── schemas
│   └── document.py
├── services
│   └── document_service.py
└── repositories
    └── document_repository.py
```

## 分层职责

| 层 | 负责什么 | 不该做什么 |
| --- | --- | --- |
| router | HTTP 参数、状态码、依赖注入 | 写复杂业务规则 |
| schema | 请求/响应模型 | 连接数据库 |
| service | 业务规则、事务编排 | 直接处理 HTTP 细节 |
| repository | 数据访问 | 决定业务流程 |
| model | ORM 映射 | 做接口校验 |

NestJS 对照：

```txt
Controller → router
DTO        → schema
Service    → service
Repository → repository
Entity     → model
```

## 数据库连接

SQLAlchemy 2.x async 风格示例：

```python
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DATABASE_URL = "mysql+asyncmy://user:password@localhost:3306/app"

engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
```

在接口中使用：

```python
from typing import Annotated
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

SessionDep = Annotated[AsyncSession, Depends(get_session)]
```

## ORM Model

```python
from sqlalchemy import BigInteger, DateTime, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    knowledge_base_id: Mapped[int] = mapped_column(BigInteger, index=True)
    title: Mapped[str] = mapped_column(String(200))
    file_key: Mapped[str] = mapped_column(String(500))
    parse_status: Mapped[str] = mapped_column(String(32), default="pending")
    parse_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=False), server_default=func.now())
```

Model 只表达数据库映射，不负责请求校验。

## Schema

```python
from pydantic import BaseModel, ConfigDict, Field

class DocumentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    file_key: str = Field(min_length=1, max_length=500)
    file_sha256: str = Field(min_length=64, max_length=64)
    file_size: int = Field(gt=0)

class DocumentRead(BaseModel):
    id: int
    knowledge_base_id: int
    title: str
    file_key: str
    parse_status: str
```

## Repository

Repository 专注数据访问：

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

async def get_document(session: AsyncSession, document_id: int) -> Document | None:
    result = await session.execute(
        select(Document).where(Document.id == document_id)
    )
    return result.scalar_one_or_none()

async def create_document(session: AsyncSession, document: Document) -> Document:
    session.add(document)
    await session.flush()
    return document
```

`flush()` 会把 SQL 发到数据库，让自增 ID 可用，但不等于提交事务。

## Service

Service 负责业务规则：

```python
from sqlalchemy.ext.asyncio import AsyncSession

async def create_document_service(
    session: AsyncSession,
    kb_id: int,
    uploader_id: int,
    payload: DocumentCreate,
) -> Document:
    document = Document(
        knowledge_base_id=kb_id,
        uploader_id=uploader_id,
        title=payload.title,
        file_key=payload.file_key,
        file_sha256=payload.file_sha256,
        file_size=payload.file_size,
        parse_status="pending",
    )
    return await create_document(session, document)
```

如果涉及多步写入，在 service 里编排事务：

```python
async with session.begin():
    document = await create_document_service(session, kb_id, user_id, payload)
    await create_parse_job(session, document.id)
```

## Router

Router 只处理 HTTP：

```python
from fastapi import APIRouter, Depends, status

router = APIRouter(prefix="/knowledge-bases/{kb_id}/documents", tags=["documents"])

@router.post("", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def create_document_api(
    kb_id: int,
    payload: DocumentCreate,
    session: SessionDep,
    current_user: CurrentUserDep,
):
    return await create_document_service(
        session=session,
        kb_id=kb_id,
        uploader_id=current_user.id,
        payload=payload,
    )
```

## 事务放在哪里

经验规则：

```txt
单表简单读写：repository 可以直接执行
涉及业务判断：service 负责
多表写入一致性：service 里开事务
HTTP 状态码和鉴权：router 负责
```

不要让 repository 偷偷提交事务，否则 service 无法把多个操作合并成一个原子流程。

## 常见错误

### 错误 1：每个 repository 都 commit

```python
async def create_order(session, order):
    session.add(order)
    await session.commit()
```

这样 service 就无法保证“创建订单 + 扣库存 + 写日志”一起成功。更好的做法是 service 控制事务边界。

### 错误 2：把 ORM 对象直接当响应

可以返回 ORM，但长期更推荐明确 response model：

```python
@router.get("/{id}", response_model=DocumentRead)
```

避免把数据库内部字段暴露给前端。

### 错误 3：AI 生成代码没有错误边界

要检查：

```txt
数据库异常怎么转成业务错误？
唯一索引冲突怎么提示？
事务失败会不会回滚？
外部服务失败后状态怎么恢复？
```

## 面试怎么说

> 我会把 FastAPI 项目拆成 router、schema、service、repository 和 model。router 只处理 HTTP 和依赖注入，schema 负责输入输出校验，service 承载业务规则和事务编排，repository 负责数据访问，model 只做 ORM 映射。这样代码不会因为接口变多而堆在一个文件里，也方便测试和维护。

