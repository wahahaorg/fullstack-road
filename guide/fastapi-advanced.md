---
title: FastAPI 进阶：生产级用法
---

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

适合注入：数据库 Session、当前用户、权限校验、分页参数、配置。FastAPI 的 Depends 更接近 Nest 的 Guard + 参数装饰器组合，而不是全局 IoC 容器——它解决的是**请求级**装配，进程级资源仍放 lifespan / `app.state`。

### 基础写法与 Annotated 别名

```python
from typing import Annotated
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer = HTTPBearer(auto_error=False)

async def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> User:
    if not creds:
        raise HTTPException(401, "missing token")
    return await decode_and_load_user(creds.credentials)

# 类型别名：路由签名只写别名，OpenAPI / 校验 / 注入一次声明
CurrentUser = Annotated[User, Depends(get_current_user)]
DB = Annotated[AsyncSession, Depends(get_db)]

@router.get("/me", response_model=UserRead)
async def read_me(current_user: CurrentUser):
    return current_user
```

**Annotated 别名最佳实践：**

- 一个依赖只建一个别名（`CurrentUser` / `DB`），全项目复用，避免每个路由手写 `Depends(get_current_user)`。
- 别名放 `app/core/deps.py`，路由只 import 别名，不直接碰底层函数。
- 需要参数化的依赖（角色、资源）用**工厂函数返回 Depends 可调用对象**，不要把参数塞进别名本身。

### 依赖组合：认证 → 角色 → 资源

链式组合的心智是「上一环的输出是下一环的输入」。典型 RAG 路径：先认出人，再看角色，最后校验对某个 knowledge base 有没有访问权——这和检索侧按权限过滤是同一条心智，只是落点在 API 入口。

```python
from collections.abc import Callable
from fastapi import Request

def require_roles(*roles: str) -> Callable:
    """工厂：返回一个 Depends 可调用对象，闭包住允许的角色集合"""
    async def checker(user: CurrentUser) -> User:
        if not set(roles) & set(user.roles):
            raise HTTPException(403, "insufficient role")
        return user
    return checker

def require_kb_access(param: str = "kb_id") -> Callable:
    """资源级校验：从路径参数取 kb_id，查用户对该库的 ACL / 租户归属"""
    async def checker(
        request: Request,
        user: CurrentUser,
        db: DB,
    ) -> KnowledgeBase:
        kb_id = int(request.path_params[param])
        kb = await kb_repo.get_if_accessible(db, user_id=user.id, kb_id=kb_id)
        if kb is None:
            # 不区分「不存在」和「无权限」，避免枚举探测
            raise HTTPException(404, "knowledge base not found")
        return kb
    return checker

KbAdmin = Annotated[User, Depends(require_roles("admin", "kb_admin"))]
AccessibleKB = Annotated[KnowledgeBase, Depends(require_kb_access())]

@router.post("/kb/{kb_id}/query")
async def query_kb(kb: AccessibleKB, user: CurrentUser, payload: QueryIn):
    # 进到这里时：已登录、对该 kb 有权；检索过滤可直接用 user.id / kb.id
    return await rag_service.query(kb.id, user.id, payload.question)
```

角色校验解决「能不能进这类接口」，资源校验解决「能不能碰这条数据」。RAG 问答还要在检索层再滤一次可见 chunk——API Depends 挡的是入口，不是召回，两边都要有，见 [检索与重排](./rag-retrieval)。

### 同一请求内的缓存语义

Depends 默认 `use_cache=True`：**同一个请求里，同一个依赖函数只执行一次**，后续注入直接拿缓存结果。

| 会缓存 | 不会缓存 / 易踩坑 |
|---|---|
| `get_current_user` 被角色依赖和路由各声明一次 → 只解码一次 JWT | `use_cache=False` 的依赖，每次注入都重跑 |
| 子依赖树共享同一个 `get_db` → 同一条请求共用一个 Session | 「看起来一样」但函数对象不同（包了一层 lambda / 每次工厂新建）→ 视为不同依赖 |
| 请求结束前结果一直有效 | 跨请求不共享——**不要把 Depends 当全局单例**；进程级对象放 lifespan |

`yield` 型依赖（如 `get_db`）在响应发送后再跑 `finally` 做清理；中途抛 `HTTPException` 也会走清理。不要在依赖里开了连接却假设「异常时不用关」。

### 和 Nest Guard 的对照

| 关注点 | FastAPI Depends | NestJS |
|---|---|---|
| 认证「是谁」 | `get_current_user` + `HTTPBearer` | `AuthGuard('jwt')` + Passport Strategy |
| 授权「能不能」 | `require_roles` / `require_kb_access` 工厂 | Guard + `@SetMetadata` / `@Permissions()`，见 [认证](./nestjs-auth) 与 [授权](./nestjs-authorization) |
| 取出当前用户 | `CurrentUser` 类型别名 | `@CurrentUser()` 参数装饰器 |
| 失败怎么表达 | 依赖里 `raise HTTPException(401/403/404)` | Guard `return false` 或抛 `ForbiddenException` |
| 请求级共享 | 默认按依赖函数缓存 | 同一请求内 provider 默认单例（REQUEST scope 另论） |
| 测试替换 | `app.dependency_overrides[fn] = stub` | `overrideProvider` / Testing Module |

前端转过来的直觉：Nest 把「拦不拦」放 Guard、「取用户」放装饰器；FastAPI 把两件事都收进 Depends 链，路由签名即文档。

### 测试时覆盖依赖

```python
async def override_user():
    return User(id=1, email="tester@example.com", roles=["kb_admin"])

async def override_kb():
    return KnowledgeBase(id=9, name="demo", tenant_id="t1")

app.dependency_overrides[get_current_user] = override_user
app.dependency_overrides[require_kb_access()] = override_kb  # 注意：工厂每次返回新函数时，要覆盖路由实际用的那一个

# 测完务必清掉，避免污染后续用例
app.dependency_overrides.clear()
```

更完整的 `AsyncClient` + fixture 写法见下文「测试」一节。关键点：覆盖的是**函数对象本身**，不是别名字符串；参数化工厂要拿到路由闭包里同一个可调用对象再覆盖。

---

## 应用生命周期：lifespan 与 app.state

连接池、编译好的 Agent 图、后台容器这类资源需要“启动时建一次、关闭时释放”。旧写法是 `@app.on_event("startup")` / `"shutdown"` 两个分散的钩子，FastAPI 已将其废弃，统一为 lifespan：

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request

@asynccontextmanager
async def lifespan(app: FastAPI):
    # yield 之前：启动逻辑（建连接池、初始化表、预热缓存）
    await container.documents.initialize()
    yield
    # yield 之后：关闭逻辑（释放连接、停后台任务）

app = FastAPI(lifespan=lifespan)
app.state.rag = container   # 进程级资源挂到 app.state

def get_rag(request: Request) -> RagContainer:
    return request.app.state.rag
```

三条边界要分清：

- **lifespan 管进程级，Depends 管请求级**。Depends 在同一请求内缓存结果、请求结束即销毁；lifespan 里构建的对象活整个进程。数据库引擎、模型客户端、编译好的编排图属于前者，当前用户、请求内 Session 属于后者。
- **进程级资源放 `app.state`，用 Request 或 Depends 取**。`get_rag` 这种一行的取值函数包成 `Depends`，路由签名里它和其他依赖长一个样，测试时也好替换。
- **启动即失败**。连接池在 lifespan 里初始化，配置错误会在应用启动时抛出，被部署流程的健康检查拦住，而不是等第一个请求才炸。

踩坑连接：把“每请求构建一次”的重对象（比如 `builder.compile()` 出来的图、它内部的连接池）挪进 lifespan 构建一次、挂到 `app.state`，是高 QPS 下最常见的一处修复——见 [LangGraph 状态机](./agent-langgraph)的编译踩坑。

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

### CPU 密集任务与 BackgroundTasks 边界

PDF OCR、大文件解析、本地推理、长 Agent 跑批——这些都不该堵在 API 事件循环里。可选去处：

- 进程池（`ProcessPoolExecutor`）——短 CPU 爆发、可接受请求内等待
- 独立 worker / 任务队列（Arq、Celery、Redis Stream）——要持久化、重试、观测
- FastAPI `BackgroundTasks`——**仅**请求返回后顺手做的轻量副作用

```python
from fastapi import BackgroundTasks

def write_audit_log(user_id: int, action: str) -> None:
    # 短、可丢、失败不阻塞主流程
    logger.info("audit", user_id=user_id, action=action)

@router.post("/documents/{doc_id}/touch")
async def touch_doc(doc_id: int, user: CurrentUser, bg: BackgroundTasks):
    await doc_service.touch(doc_id, user.id)
    bg.add_task(write_audit_log, user.id, f"touch:{doc_id}")
    return {"ok": True}
```

| 维度 | BackgroundTasks | Arq / Celery | Redis Stream / MQ |
|---|---|---|---|
| 持久化 | 无，进程内存 | Broker 持久化 | Stream / 队列持久化 |
| 进程重启 | **任务丢失** | 重启后继续消费 | 同左 |
| 重试 / 死信 | 无 | 内置重试、可配 DLQ | 要自己做 ACK / DLQ |
| 观测 | 几乎没有 | Flower / 自带结果后端 | 要自建消费滞后指标 |
| 适用 | 发邮件、打点、清缓存 | PDF 解析、向量化、长 Agent 跑批 | 多消费者、需要回放或扇出 |
| 和请求的关系 | 同进程，响应已发出后执行 | 与 API 进程解耦 | 同左 |

**能丢 BackgroundTasks：** 写审计日志、发欢迎邮件、刷新本地缓存、向网关打点——丢了可接受或可补偿。

**必须上队列：** 文档解析与切分、embedding 写入向量库、批量评测、跨分钟的 Agent 调研——需要「提交后可查进度、失败可重试、发布不丢任务」。接口返回 `202` + `task_id`，进度走轮询或另一条 SSE。

完整任务表设计、幂等、心跳与优雅停机见 [Worker 与异步任务](./background-worker)；Broker 选型与文档解析管线见 [消息队列](./message-queue)。

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

JWT 的结构、攻击面、双 token 刷新细节见 [Nest 认证](./nestjs-auth)，这里不重复讲原理，只落 FastAPI 侧的提取、签发和资源级 Depends。

### Bearer 提取

优先用 `HTTPBearer`，OpenAPI 会自动带上小锁；需要兼容多种头时再手写 Header。

```python
# core/security.py
from datetime import datetime, timedelta, timezone
import jwt
from passlib.context import CryptContext
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi import Header

pwd_context = CryptContext(schemes=["bcrypt"])
SECRET_KEY = settings.secret_key
ALGORITHM = "HS256"
bearer_scheme = HTTPBearer(auto_error=False)  # False：缺 token 时走我们自己的 401 文案

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def create_access_token(user_id: int, expires_minutes: int = 30) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "exp": now + timedelta(minutes=expires_minutes),
        "iat": now,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def decode_access_token(token: str) -> dict:
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

# 写法 A：HTTPBearer（推荐）
async def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(401, "missing bearer token")
    try:
        data = decode_access_token(creds.credentials)
    except jwt.PyJWTError:
        raise HTTPException(401, "invalid token")
    user = await user_repo.get(int(data["sub"]))
    if user is None or not user.enabled:
        raise HTTPException(401, "user disabled")
    return user

# 写法 B：手动 Header（要兼容 Cookie / 自定义头时用）
async def get_token_from_header(
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "missing bearer token")
    return authorization.split(" ", 1)[1]
```

### 登录与续期取舍

```python
@router.post("/auth/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: DB):
    user = await user_repo.get_by_email(db, payload.email)
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(401, "Invalid credentials")
    return {"access_token": create_access_token(user.id), "token_type": "bearer"}
```

Access token 本身无状态，**撤销和长会话**要额外设计。Agent / RAG 产品常见二选一：

| 方案 | 做法 | 优点 | 代价 | 适用 |
|---|---|---|---|---|
| 短 access + refresh | access 15–30min；refresh 存 HttpOnly Cookie 或服务端表，旋转发放 | 被盗窗口短；可按设备撤销 | 要处理并发 401 只刷一次；refresh 表要清理 | 多端 Web / App，要「踢下线」 |
| 短 access + 服务端会话 | access 里只放 `sid`；会话状态（用户、权限版本）在 Redis | 权限变更即时生效；登出即删会话 | 每请求多一次 Redis；多副本依赖外部存储 | 权限变更频繁、强合规、要全局吊销 |

不要两套都上全量实现。内部工具、租户少、权限几乎不变 → 短 access + refresh 够用；要「改角色立刻全站失效」→ 上服务端会话。Nest 侧双 token 与并发刷新见 [认证与登录状态](./nestjs-auth)。

### 资源级权限 Depends（对接 RAG）

角色只能回答「是不是管理员」。知识库问答还要回答「这个人能不能碰这个 kb / 这个租户」——这是资源级校验，和检索时按 ACL 过滤 chunk 是同一条链的前后两环。

```python
async def require_tenant_member(
    request: Request,
    user: CurrentUser,
    db: DB,
) -> Tenant:
    tenant_id = request.path_params["tenant_id"]
    tenant = await tenant_repo.get_membership(db, user.id, tenant_id)
    if tenant is None:
        raise HTTPException(403, "not a tenant member")
    return tenant

# 和上文 require_kb_access 组合：先租户，再知识库
@router.post("/tenants/{tenant_id}/kb/{kb_id}/query")
async def tenant_kb_query(
    user: CurrentUser,
    tenant: Annotated[Tenant, Depends(require_tenant_member)],
    kb: AccessibleKB,
    payload: QueryIn,
):
    if kb.tenant_id != tenant.id:
        raise HTTPException(404, "knowledge base not found")
    # 检索层继续带 user.id / kb.id 做文档级过滤，API 层不替代召回过滤
    return await rag_service.query(kb.id, user.id, payload.question)
```

**踩坑：** API 返回 404 而不是 403 隐藏资源存在性；检索侧仍必须按权限过滤——只靠入口 Depends，换一条内部工具链仍可能越权读到文档。权限模型演进见 [Nest 授权](./nestjs-authorization)，RAG 过滤心智见 [检索与重排](./rag-retrieval)。

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

Agent 标配不是「把模型输出转成流」，而是**阶段事件协议**：检索和工具阶段一个 token 都没有，如果不往外推 `stage` / `citation`，用户盯的是空白。协议字段、前端消费、LangGraph 映射的完整版见 [SSE 流式与阶段事件协议](./agent-streaming)；这里只落 FastAPI 服务端要点，两边事件名必须一致。

### 阶段事件协议（与 agent-streaming 对齐）

| event | 时机 | data 要点 |
|---|---|---|
| `stage` | 进入新阶段 | `stage`、`label`、`seq` |
| `token` | 生成增量 | `text`（JSON，禁止裸换行） |
| `citation` | 引用确定 | `id`、`title`、`source`、`snippet`、`score` |
| `error` | 流中失败 | `code`、`message`、`retryable` |
| `done` | 正常或异常结束 | `finish_reason`、`message_id`、`usage` |

`stage` 枚举固定为 `understanding` / `retrieving` / `tool_calling` / `generating` / `verifying`，前端才能做文案映射。未知 event 前端忽略，协议可加版本头 `X-Stream-Protocol: 1`。

```python
import asyncio, json
from fastapi import Request
from fastapi.responses import StreamingResponse

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",          # 关掉 Nginx 缓冲，见下节
    "X-Stream-Protocol": "1",
}

def sse(event: str, data: dict, event_id: int | None = None) -> str:
    head = f"id: {event_id}\n" if event_id is not None else ""
    # data 必须 JSON：模型输出里的换行不能裸进 data 行
    return f"{head}event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

@router.post("/chat/stream")
async def chat_stream(payload: ChatRequest, request: Request, user: CurrentUser):
    async def gen():
        seq = 0
        try:
            async for ev in run_agent(payload.question, user.id, payload.session_id):
                if await request.is_disconnected():
                    await cancel_agent(payload.session_id)  # 停下游 LLM / 工具，别继续计费
                    break
                seq += 1
                yield sse(ev["event"], ev["data"], seq)
        except asyncio.CancelledError:
            await cancel_agent(payload.session_id)
            raise
        except Exception:
            # 流已打开后不能再改 HTTP 状态码，错误只能是事件
            yield sse("error", {"code": "internal", "message": "服务暂时不可用", "retryable": True})
            yield sse("done", {"finish_reason": "error"})
            return
        # 业务生成器若已发 done 可省略；约定「谁开头谁收尾」避免双 done
        yield sse("done", {"finish_reason": "stop"})

    return StreamingResponse(gen(), media_type="text/event-stream", headers=SSE_HEADERS)
```

### 客户端断开与取消下游

`request.is_disconnected()` 要在**每次 yield 前**查。前端点「停止生成」或关页只会断 TCP；若不检测，Agent 仍在跑检索和 LLM，token 照样计费。取消信号建议写 Redis（按 `session_id`），多副本才能互相看见——纯进程内 flag 在水平扩展下无效，见 [agent-streaming 生产坑](./agent-streaming)。

### 反代缓冲：为什么必须关

Nginx 默认缓冲上游响应，典型现象：本地直连 uvicorn 逐 token，上环境却「卡十几秒一次性吐出」。

| 手段 | 作用 |
|---|---|
| 响应头 `X-Accel-Buffering: no` | 按响应关闭 Nginx 缓冲，只影响这条流，推荐 |
| `proxy_buffering off;` | location 级关闭；别误关到普通 JSON 接口 |
| 该路径 `gzip off` | 压缩也会攒块，流式路径直接关 |
| `proxy_http_version 1.1` + 调大 `proxy_read_timeout` | HTTP/1.0 不支持流式 keep-alive；超时要大于最长 Agent 执行 |

### 心跳注释行

检索 / 工具阶段可能十几秒无输出，LB 会按空闲超时掐连接。超过间隔就发 SSE 注释行（客户端忽略）：

```python
async def with_heartbeat(source, interval: float = 15.0):
    queue: asyncio.Queue = asyncio.Queue()

    async def pump():
        async for item in source:
            await queue.put(item)
        await queue.put(None)

    task = asyncio.create_task(pump())
    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=interval)
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"
                continue
            if item is None:
                return
            yield item
    finally:
        task.cancel()
```

### 错误是事件，不是 HTTP 500

第一个字节发出后状态码已钉死为 200。模型超时、工具失败、内容审核拦截，只能在同一条流里发 `event: error`，再发 `event: done`，让客户端 `close()`。**不要断开连接假装失败**——`EventSource` 会自动重连，一次异常被放大成持续的 Agent 重跑。完整失败矩阵见 [agent-streaming 错误与降级](./agent-streaming)。

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

> FastAPI 项目里我会按 router → schema → service → repository → model 分层。用 Pydantic 拆分请求/响应模型；Depends 链做认证 → 角色 → 知识库资源校验，并用 Annotated 别名复用。Agent 接口走 SSE，事件协议与前端约定 `stage` / `token` / `citation` / `error` / `done`，断线用 `is_disconnected` 取消下游，错误发事件而不是改状态码。耗时任务不进 BackgroundTasks，用 Worker / MQ；测试用 pytest + httpx.AsyncClient，`dependency_overrides` 换鉴权。线上 uvicorn + gunicorn，Docker 部署。

