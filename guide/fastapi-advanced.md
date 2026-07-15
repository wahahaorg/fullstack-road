# FastAPI 进阶：生产级用法

> 基于 Python 3.11+、Pydantic v2、SQLAlchemy 2.x，覆盖从设计到部署的核心实践。

## Pydantic v2 模型

### 类型标注是 FastAPI 的核心

FastAPI 通过类型标注判断参数来源、执行校验并生成 OpenAPI：

```python
def find_user(user_id: int, include_disabled: bool = False) -> dict | None:
    ...
```

`Optional[str]` 与 `str | None` 等价，但"可为 None"不等于"参数可省略"：

```python
class Example(BaseModel):
    value1: str | None        # 必须提供，但值可以是 null
    value2: str | None = None # 可以省略
```

### 输入校验

```python
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

class TaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")  # 拒绝未定义字段

    task_type: Literal["RAG", "TEXT_TO_SQL"]
    question: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=50)

    @field_validator("question")
    @classmethod
    def question_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("question cannot be blank")
        return value
```

### 创建 / 更新 / 输出分开

```python
class UserCreate(BaseModel):
    email: str
    password: str = Field(min_length=8)

class UserUpdate(BaseModel):
    nickname: str | None = None
    enabled: bool | None = None

class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)  # 支持 ORM 对象

    id: int
    email: str
    nickname: str | None
    # 不包含 password_hash 等敏感字段
```

**PATCH 只更新传入的字段：**

```python
changes = payload.model_dump(exclude_unset=True)
# exclude_unset 区分"没传"和"明确传 null"
```

> ⚠️ 不要让一个类同时承担 API 校验、数据库映射和业务逻辑。典型分层：`UserCreate`（输入）、`UserRead`（输出）、`User`（ORM 实体）。

---

## 路径、查询与请求体

```python
from typing import Annotated
from fastapi import Body, Path, Query
from pydantic import BaseModel, Field

class ReportCreate(BaseModel):
    dataset_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=128)
    filters: dict[str, object] = Field(default_factory=dict)

@app.post("/datasets/{dataset_id}/reports")
async def create_report(
    dataset_id: Annotated[int, Path(gt=0)],  # 路径参数
    payload: ReportCreate,                    # 请求体（Pydantic 模型）
    preview: Annotated[bool, Query()] = False, # 查询参数
) -> dict:
    ...
```

FastAPI 的自动判断规则：

- 路径模板中的标量参数 → Path
- 其他标量参数 → Query
- Pydantic 模型 → Body
- `Header`、`Cookie`、`File` 需显式声明

---

## 响应模型与状态码

```python
from fastapi import status

@app.post(
    "/users",
    response_model=UserRead,              # 自动序列化 + 过滤敏感字段
    status_code=status.HTTP_201_CREATED,
)
async def create_user(payload: UserCreate):
    ...
```

**常用状态码速查：**

```
200  查询或更新成功
201  创建成功
202  已接受，异步处理中
204  成功但无响应体
400  请求语义错误
401  未认证
403  已认证但无权限
404  资源不存在
409  状态冲突、重复提交、乐观锁失败
422  请求校验失败（FastAPI 自动返回）
429  请求过多
500  未预期服务端错误
503  依赖暂时不可用
```

---

## APIRouter 与项目结构

```text
app/
├── main.py
├── core/
│   ├── config.py      # 配置（pydantic-settings）
│   ├── errors.py      # 自定义异常
│   ├── logging.py
│   └── security.py    # JWT、密码 hash
├── db/
│   ├── session.py     # AsyncSession 工厂
│   └── models/        # SQLAlchemy ORM 模型
├── modules/
│   ├── users/
│   │   ├── router.py
│   │   ├── schemas.py
│   │   ├── service.py
│   │   └── repository.py
│   └── rag/
│       ├── router.py
│       └── ...
└── tests/
```

```python
from fastapi import APIRouter

router = APIRouter(prefix="/users", tags=["users"])

@router.get("/{user_id}", response_model=UserRead)
async def get_user(user_id: int):
    ...

# main.py 注册
app.include_router(user_router, prefix="/api/v1")
```

---

## 依赖注入 Depends

适合注入：数据库 Session、当前用户、权限校验、分页参数、配置。

```python
from typing import Annotated
from fastapi import Depends, Header, HTTPException

async def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    if not authorization:
        raise HTTPException(401, "missing token")
    return await decode_and_load_user(authorization)

# 类型别名，让代码更简洁
CurrentUser = Annotated[User, Depends(get_current_user)]

@router.get("/me", response_model=UserRead)
async def read_me(current_user: CurrentUser):
    return current_user
```

> Depends 会在同一请求内缓存相同依赖的结果，不要把它当成全局单例容器。

---

## async / await 与阻塞陷阱

### 什么时候用 async def

```python
# 有异步 I/O：用 async def + await
@app.get("/documents/{id}")
async def get_document(id: int):
    return await async_repository.get(id)

# 阻塞库：普通 def，FastAPI 自动放线程池
@app.get("/legacy")
def legacy_call():
    return blocking_client.fetch()
```

**错误写法——在 async def 里阻塞事件循环：**

```python
@app.get("/bad")
async def bad():
    time.sleep(5)    # ❌ 直接阻塞整个事件循环
    import requests
    requests.get(url)  # ❌ 同步 HTTP，应换 httpx/aiohttp
```

### CPU 密集任务

PDF OCR、大文件解析、本地推理等不适合在 API 事件循环中处理：

- 进程池（`ProcessPoolExecutor`）
- 独立 worker 进程
- Celery、Arq 等任务队列

> `BackgroundTasks` 不是可靠的任务队列，进程重启会丢任务，只适合发邮件这类轻量操作。

### 并发限制

```python
import asyncio

semaphore = asyncio.Semaphore(8)

async def embed(text: str):
    async with semaphore:
        return await embedding_client.embed(text)
```

---

## 数据库：SQLAlchemy AsyncSession

```python
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

engine = create_async_engine(settings.database_url)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# 依赖注入 Session
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session

DB = Annotated[AsyncSession, Depends(get_db)]
```

**事务控制：**

```python
@router.post("/transfer")
async def transfer(payload: TransferRequest, db: DB):
    async with db.begin():  # 开启事务，异常时自动回滚
        await deduct(db, payload.from_id, payload.amount)
        await add(db, payload.to_id, payload.amount)
```

---

## 异常处理

### 自定义异常 + 全局处理器

```python
# core/errors.py
class AppError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code

class NotFoundError(AppError):
    def __init__(self, resource: str, id: int):
        super().__init__(f"{resource} {id} not found", 404)

# main.py 注册
from fastapi import Request
from fastapi.responses import JSONResponse

@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.message}
    )
```

### 422 校验错误自定义

```python
from fastapi.exceptions import RequestValidationError

@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": exc.body}
    )
```

---

## 鉴权：JWT 实战

```python
# core/security.py
from datetime import datetime, timedelta
import jwt
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"])
SECRET_KEY = settings.secret_key
ALGORITHM = "HS256"

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def create_access_token(user_id: int, expires_minutes: int = 30) -> str:
    payload = {
        "sub": str(user_id),
        "exp": datetime.utcnow() + timedelta(minutes=expires_minutes),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def decode_access_token(token: str) -> dict:
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
```

**登录接口：**

```python
@router.post("/auth/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: DB):
    user = await user_repo.get_by_email(db, payload.email)
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(401, "Invalid credentials")
    return {"access_token": create_access_token(user.id)}
```

---

## 环境配置：pydantic-settings

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    database_url: str
    secret_key: str
    debug: bool = False
    allowed_origins: list[str] = ["http://localhost:3000"]

settings = Settings()
```

---

## 流式响应（SSE）

AI 应用的标配，用于大模型逐 token 输出：

```python
from fastapi import Request
from fastapi.responses import StreamingResponse
import asyncio

async def token_stream(prompt: str):
    async for token in llm.stream(prompt):
        yield f"data: {token}\n\n"
    yield "data: [DONE]\n\n"

@router.post("/chat/stream")
async def chat_stream(payload: ChatRequest):
    return StreamingResponse(
        token_stream(payload.prompt),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no"}
    )
```

---

## 测试

```python
from fastapi.testclient import TestClient
from httpx import AsyncClient
import pytest

# 同步测试（简单场景）
client = TestClient(app)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200

# 异步测试（推荐）
@pytest.mark.asyncio
async def test_create_user():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post("/users", json={"email": "a@b.com", "password": "12345678"})
    assert response.status_code == 201
```

**覆盖依赖（Mock）：**

```python
async def override_get_current_user():
    return User(id=1, email="test@test.com")

app.dependency_overrides[get_current_user] = override_get_current_user
```

**完整测试示例：**

```python
import pytest
from httpx import AsyncClient, ASGITransport

# conftest.py
@pytest.fixture
def app():
    from app.main import app
    return app

@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

@pytest.mark.asyncio
async def test_full_flow(app, client):
    # 1. 注册
    resp = await client.post("/api/v1/auth/register", json={
        "email": "test@example.com",
        "password": "Test123456"
    })
    assert resp.status_code == 201

    # 2. 登录获取 token
    resp = await client.post("/api/v1/auth/login", json={
        "email": "test@example.com",
        "password": "Test123456"
    })
    assert resp.status_code == 200
    token = resp.json()["access_token"]

    # 3. 用 token 访问受保护接口
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.get("/api/v1/users/me", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["email"] == "test@example.com"
```

**测试原则总结：**

```txt
单元测试：测试 repository 和 service，Mock 数据库
集成测试：测试 controller → service → repository 链路
E2E 测试：启动真实数据库，测试完整请求-响应
API 测试：Mock 鉴权，验证状态码和响应结构
并发测试：测试幂等和锁的场景
```

---

## FastAPI 中间件

```python
from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware
import time

app = FastAPI()

# 内置中间件
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://app.example.com"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(GZipMiddleware, minimum_size=1000)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["api.example.com", "localhost"]
)
```

**自定义中间件：**

```python
class TimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.time()
        response = await call_next(request)
        process_time = time.time() - start
        response.headers["X-Process-Time"] = str(process_time)
        return response

app.add_middleware(TimingMiddleware)
```

---

## FastAPI + WebSocket

```python
from fastapi import WebSocket, WebSocketDisconnect

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

manager = ConnectionManager()

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await manager.broadcast(f"{client_id}: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
```

---

## 配置与项目组织

```python
# core/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_name: str = "AI Platform API"
    database_url: str
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str
    debug: bool = False
    allowed_origins: list[str] = ["http://localhost:3000"]

    class Config:
        env_file = ".env"

settings = Settings()
```

---

## 面试怎么说

> FastAPI 项目里我会按 router → schema → service → repository → model 分层。用 Pydantic 拆分请求/响应模型，Depends 注入鉴权和 DB Session。耗时任务不进请求线程，用 MQ 或任务表异步处理。测试用 pytest + httpx.AsyncClient，覆盖单元、集成和 E2E。线上用 uvicorn + gunicorn，Docker 容器化部署。
