# 深入理解 Python 类

> 面向对象是 FastAPI、SQLAlchemy 等框架的基础，理解这些概念才能看懂并修改 AI 生成的代码。

## 属性访问控制

Python 约定：

| 写法 | 含义 |
|---|---|
| `self.name` | 公开属性，外部可随意访问 |
| `self._name` | **约定私有**，外部不应访问（但技术上仍可访问） |
| `self.__name` | 名称改写（name mangling），访问会报 AttributeError |

实践中通常用 `_` 单下划线约定私有，配合 `@property` 提供受控访问：

```python
class Logger:
    def __init__(self, prefix):
        self._prefix = prefix  # 约定私有

    @property
    def prefix(self):
        return self._prefix

    @prefix.setter
    def prefix(self, value):
        if not value:
            raise ValueError("prefix 不能为空")
        self._prefix = value

    def log(self, content):
        print(f"{self._prefix}: {content}")

l = Logger("App")
l.log("started")       # App: started
l.prefix = "Service"   # 调用 setter
l.log("restarted")     # Service: restarted
```

---

## 静态方法 `@staticmethod`

不依赖实例或类，通过**类名直接调用**，没有 `self` 也没有 `cls` 参数：

```python
class Logger:
    def __init__(self, prefix):
        self._prefix = prefix

    def log(self, content):
        print(f"{self._prefix}: {content}")

    @staticmethod
    def version():
        return "2.0.0"

print(Logger.version())  # 2.0.0，不需要创建实例
```

适合：工具函数、纯计算逻辑、与实例状态无关的操作。

---

## 类方法 `@classmethod`

第一个参数是**类本身**（约定命名 `cls`），通过类名调用，常用于工厂模式：

```python
class Logger:
    def __init__(self, prefix):
        self._prefix = prefix

    def log(self, content):
        print(f"{self._prefix}: {content}")

    @classmethod
    def create(cls, prefix):
        # 通过类方法创建实例，子类 override 后可以返回子类实例
        return cls(prefix)

l = Logger.create("App")
l.log("hello")  # App: hello
```

**`@staticmethod` vs `@classmethod`：**

| 对比 | `@staticmethod` | `@classmethod` |
|---|---|---|
| 第一参数 | 无 | `cls`（类本身） |
| 能访问类属性？ | ❌ | ✅ |
| 工厂模式 | 不适合 | 适合 |

---

## 继承

```python
class Event:
    def __init__(self, name):
        self._name = name

    @property
    def name(self):
        return self._name

    def fire(self):
        print(f"Event '{self._name}' fired")


class LoginEvent(Event):
    def fire(self):
        # 重写父类方法（多态）
        print(f"User login event: {self._name}")

    def fire_with_super(self):
        super().fire()  # 调用父类方法
        print("+ login logic")


e = Event("generic")
e.fire()          # Event 'generic' fired

l = LoginEvent("login")
l.fire()          # User login event: login
```

**多继承（Python 支持，MRO 决定解析顺序）：**

```python
class A:
    def hello(self):
        print("A")

class B(A):
    def hello(self):
        print("B")

class C(A, B):    # MRO: C → A → B
    pass

C().hello()  # A
```

---

## 抽象类

没有办法实例化的类，强制子类实现指定方法。Python 通过 `abc` 模块实现：

```python
import abc

class Animal(metaclass=abc.ABCMeta):
    def __init__(self, kind):
        self._kind = kind

    @abc.abstractmethod
    def speak(self):
        """子类必须实现此方法"""
        pass

    def describe(self):
        print(f"I am a {self._kind}")


class Dog(Animal):
    def speak(self):
        print("汪~")


class Cat(Animal):
    def speak(self):
        print("喵~")


# Animal("animal")  # ❌ TypeError: Can't instantiate abstract class
dog = Dog("狗")
dog.speak()     # 汪~
dog.describe()  # I am a 狗
```

---

## 与 FastAPI / SQLAlchemy 的关系

这些概念在框架中频繁出现：

| 概念 | 在框架中的体现 |
|---|---|
| `@property` | Pydantic 模型字段校验、SQLAlchemy 计算属性 |
| `@staticmethod` | 工具类方法、格式转换 |
| `@classmethod` | SQLAlchemy 中的工厂方法（`from_dict`、`create_from`） |
| 继承 | FastAPI 中 `BaseModel` 的扩展、异常类层次结构 |
| 抽象类 | Repository 接口、Service 基类（依赖倒置原则） |

**典型模式——Repository 抽象基类：**

```python
import abc
from typing import Generic, TypeVar

T = TypeVar("T")

class BaseRepository(abc.ABC, Generic[T]):
    @abc.abstractmethod
    async def get_by_id(self, id: int) -> T | None:
        pass

    @abc.abstractmethod
    async def save(self, entity: T) -> T:
        pass


class UserRepository(BaseRepository):
    async def get_by_id(self, id: int):
        # 具体实现：查数据库
        ...

    async def save(self, entity):
        # 具体实现：写数据库
        ...
```

这样业务层（Service）只依赖抽象，不依赖具体数据库实现，更容易测试和替换。
