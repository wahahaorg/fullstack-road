# Python 工程进阶

> 本章补充 Python 从“能写脚本”到“能开发生产服务”所需的核心知识：异步编程、项目工程化、类型系统、性能优化与运行时实践。

学完基础语法和类之后，你已经可以写出能运行的程序。但真实项目还要求代码在并发、协作、数据异常和长期维护下保持可靠。本章不再介绍新的语法，而是回答一个问题：怎样把 Python 写成工程？

## 异步编程与并发模型

### 协程、线程与进程

三者解决的问题不同：

| 模型 | 调度者 | 适合场景 | 主要代价 |
|---|---|---|---|
| 协程 | 事件循环 | 大量 I/O 等待 | 阻塞调用会卡住整个事件循环 |
| 线程 | 操作系统 | 阻塞 I/O、调用同步库 | 线程切换和共享状态管理 |
| 进程 | 操作系统 | CPU 密集型计算 | 进程创建与进程间通信 |

协程可以理解为“能够暂停和恢复的函数”。执行到 `await` 时，如果等待的操作尚未完成，协程会暂时交还控制权，让事件循环继续执行其他任务。

```python
import asyncio

async def fetch_data(name: str, delay: float) -> str:
    await asyncio.sleep(delay)  # 模拟网络 I/O
    return f"{name} finished"

async def main() -> None:
    results = await asyncio.gather(
        fetch_data("task-a", 1),
        fetch_data("task-b", 1),
    )
    print(results)

asyncio.run(main())
```

两个任务会在约 1 秒后一起完成，而不是串行等待约 2 秒。这里的关键不是“同时执行 Python 代码”，而是在一个任务等待 I/O 时执行另一个任务。

### 不要在异步函数中执行阻塞操作

下面的写法虽然处在 `async def` 中，却仍然会阻塞事件循环：

```python
import time

async def wrong() -> None:
    time.sleep(3)  # 阻塞整个事件循环
```

如果库提供异步接口，应优先使用异步接口；如果必须调用同步阻塞函数，可以交给线程执行：

```python
import asyncio
import time

def blocking_work() -> str:
    time.sleep(1)
    return "done"

async def main() -> None:
    result = await asyncio.to_thread(blocking_work)
    print(result)
```

### 生产代码还要处理边界

并发代码不能只追求“跑得快”，还要控制失败范围：

- 用 `Semaphore` 限制最大并发数，避免压垮数据库或第三方服务；
- 为所有外部调用设置超时；
- 只对可恢复错误重试，并使用退避策略；
- 保存并等待创建的 Task，避免后台任务悄悄失败；
- 复用 HTTP 和数据库连接池，不要每次请求重新创建；
- 服务关闭时停止接收新任务，并等待正在执行的任务收尾。

```python
import asyncio

semaphore = asyncio.Semaphore(10)

async def guarded_call(item_id: int) -> str:
    async with semaphore:
        async with asyncio.timeout(3):
            return await call_remote_service(item_id)
```

异步只适合以等待为主的 I/O 密集任务。图片处理、大量数学运算等 CPU 密集任务应该考虑多进程、任务队列或由原生代码实现的库。

## 从脚本到工程化项目

### 按职责划分模块

当所有代码都堆在 `main.py` 中时，接口、业务规则和数据库操作会互相缠绕。常见的后端分层是：

```text
API / Router       接收请求、调用业务、组织响应
Schema             定义输入输出的数据契约
Service            实现业务规则和流程
Repository         封装数据库访问
Infrastructure     第三方 API、缓存、消息队列等具体实现
```

分层不是固定模板。小项目不需要为了形式创建大量空文件；只有当一段逻辑有独立职责、需要替换或需要单独测试时，才值得抽离。

### 依赖抽象而不是具体实现

`Protocol` 可以定义对象必须具备的能力，而不要求实现类继承某个基类：

```python
from typing import Protocol

class UserRepository(Protocol):
    def find_by_id(self, user_id: int) -> dict[str, object] | None: ...

class UserService:
    def __init__(self, repository: UserRepository) -> None:
        self.repository = repository

    def get_user(self, user_id: int) -> dict[str, object] | None:
        return self.repository.find_by_id(user_id)
```

业务层只依赖 `UserRepository` 约定。生产环境可以传入数据库实现，测试时可以传入内存实现，不必启动真实数据库。

### 设计模式用来隔离变化

不要为了使用设计模式而使用设计模式。先找到项目中经常变化的部分，再选择合适的组织方式：

- 策略模式：同一业务有多种可替换算法，例如支付渠道、价格计算；
- 工厂模式：对象创建过程复杂，或需要根据配置选择实现；
- 装饰器模式：在不改变核心函数的前提下增加日志、计时、缓存或权限；
- 观察者模式：一个事件发生后，需要触发多个互相独立的后续动作。

```python
from collections.abc import Callable
from functools import wraps
from time import perf_counter
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")

def timer(func: Callable[P, R]) -> Callable[P, R]:
    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        started_at = perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            elapsed = perf_counter() - started_at
            print(f"{func.__name__}: {elapsed:.4f}s")

    return wrapper
```

## 测试与代码质量

### 用 pytest 保护业务行为

单元测试应该验证业务行为，而不是重复实现细节。外部数据库、缓存和网络请求可以用假对象替换：

```python
from unittest.mock import Mock

def test_get_user_reads_repository() -> None:
    repository = Mock()
    repository.find_by_id.return_value = {"id": 1, "name": "Ada"}
    service = UserService(repository)

    user = service.get_user(1)

    assert user == {"id": 1, "name": "Ada"}
    repository.find_by_id.assert_called_once_with(1)
```

一个成熟项目通常包含：

- 单元测试：验证单个函数、类或业务规则；
- 集成测试：验证 API、数据库等模块能正确协作；
- Fixture：统一准备和清理测试数据；
- 参数化测试：用同一条规则覆盖多组输入；
- 覆盖率：寻找没有被验证的关键路径，而不是盲目追求 100%。

### 让工具自动把关

常见 Python 质量工具包括：

- Ruff：代码检查和格式化；
- mypy 或 Pyright：静态类型检查；
- pytest：自动化测试；
- coverage.py：统计测试覆盖率；
- pre-commit：提交前自动运行检查。

这些命令应当进入 CI。只有在每次提交都会执行时，团队规范才不是一份无人遵守的文档。

## 类型系统与数据契约

### 类型注解不只是 `int` 和 `str`

类型注解能让编辑器和检查工具提前发现参数、返回值和空值处理错误。

```python
from typing import TypeVar

T = TypeVar("T")

def first(items: list[T]) -> T | None:
    return items[0] if items else None
```

这里的泛型表示：传入 `list[int]` 就返回 `int | None`，传入 `list[str]` 就返回 `str | None`。

常用的进阶类型还有：

- `Protocol`：描述对象需要具备的方法或属性；
- `TypedDict`：为字典中的每个键定义类型；
- `Literal`：把值限制在几个明确选项中；
- `Callable`：描述函数参数和返回值；
- `Annotated`：为类型附加验证等元数据。

### 静态检查与运行时验证分工

类型注解默认不会在运行时拦截错误输入。来自 HTTP、配置文件和消息队列的数据仍需运行时验证。Pydantic 可以把类型、验证和序列化集中在一个模型中：

```python
from pydantic import BaseModel, Field

class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=50)
    age: int = Field(ge=0, le=150)
```

可以这样理解二者的职责：

```text
mypy / Pyright：检查开发者写的代码是否符合类型契约
Pydantic：检查程序运行时收到的外部数据是否符合契约
```

在大型项目中，可以先为新代码启用严格检查，再逐步覆盖旧模块，避免一次性产生大量无法处理的错误。

## 性能分析与优化

### 先测量，再优化

性能优化应该遵循固定流程：

```text
确定指标 → 建立基准 → 定位瓶颈 → 修改代码 → 重新测量
```

常用工具包括：

- `cProfile`：查看函数级耗时；
- py-spy：以采样方式观察运行中的 Python 进程；
- line-profiler：定位到具体代码行；
- memory-profiler：分析内存使用。

如果慢的是数据库查询，就应该检查执行计划、索引和 N+1 查询；如果慢的是外部接口，就应该检查连接复用、超时和并发策略。不要因为 Python 循环看起来慢，就在没有数据的情况下重写全部代码。

### 使用批量计算代替 Python 循环

NumPy 和 Pandas 的许多操作在底层原生代码中批量执行，通常比逐项 Python 循环更快：

```python
import numpy as np

values = np.arange(1_000_000)
result = values * 2  # 向量化操作
```

处理表格数据时，优先考虑列运算、布尔索引和批量合并，避免 `iterrows()`。同时选择合适的数据类型，并用分块读取处理无法一次装入内存的大文件。

### 用流式处理控制内存

生成器不会一次性保存全部结果，适合读取大文件或处理长数据流：

```python
from collections.abc import Iterator

def read_non_empty_lines(path: str) -> Iterator[str]:
    with open(path, encoding="utf-8") as file:
        for line in file:
            value = line.strip()
            if value:
                yield value
```

如果热点确实在 CPU 计算，可以优先寻找 NumPy 等成熟原生库；确认仍不能满足要求后，再评估多进程、Numba、Cython 或 Rust/C 扩展。

## Python 服务的运行时实践

代码写完不等于服务可以上线。一个可交付的 Python 服务至少还需要：

- 固定依赖版本并保证环境可复现；
- 用非 root 用户运行容器；
- 提供健康检查和优雅关闭；
- 使用结构化日志，不在生产代码中到处 `print`；
- 记录请求量、错误率和延迟等指标；
- 在 CI 中执行格式检查、类型检查和测试；
- 根据 ASGI 服务的特点配置进程数、超时和资源限制。

Docker、CI/CD、监控和 Kubernetes 的完整内容放在本站的 [Docker 与部署](./docker-deployment) 章节。本章只需要记住：Python 工程师不仅要让代码在本地运行，还要让它在目标环境中可观察、可恢复、可重复部署。

## 综合练习

实现一个批量数据处理服务，把本章知识串起来：

1. 使用 FastAPI 接收批量任务。
2. 使用 Pydantic 定义请求和响应模型。
3. 使用异步客户端调用第三方接口，并设置并发上限和超时。
4. 把业务逻辑与数据访问拆开，通过接口注入依赖。
5. 使用 pytest 覆盖成功、超时、部分失败和重复提交。
6. 用 profiler 或压测工具找到一个真实瓶颈并优化。
7. 使用 Docker 运行，并输出结构化日志和基础指标。

完成后，你应该能够解释每一项设计解决了什么问题，而不只是展示用了哪些库。

## 本章小结

- `async/await` 的核心是等待期间让出控制权，不适合 CPU 密集计算。
- 工程化的目标是明确职责、隔离变化和方便测试，而不是堆叠目录。
- 静态类型检查和运行时数据验证解决的是不同问题。
- 性能优化必须从测量开始，并保留优化前后的对比。
- 测试、CI、日志和部署共同决定一段代码能否成为可靠服务。

下一步可以继续学习 [FastAPI 基础](./fastapi-basics)，把这些 Python 能力应用到 Web 服务中。
