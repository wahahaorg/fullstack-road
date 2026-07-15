# Python 语法快速入门

> 面向有 JavaScript 经验的开发者，快速掌握 Python 语法差异与核心用法。

## 基础语法

### 注释

```python
# 单行注释

"""
多行注释
第二行
"""
```

### 缩进代码块

Python 用缩进表示代码块，没有大括号：

```python
if s > 0:
    print("正数")
else:
    print("非正数")
```

### 查看函数定义

```python
>>> help(print)
# print(value, ..., sep=' ', end='\n', file=sys.stdout, flush=False)
```

### 打印

```python
>>> print("a", "b", "c")          # 默认空格分隔
a b c
>>> print("a", "b", "c", sep=",") # 修改分隔符
a,b,c
>>> print("a", "b", "c", end=".")  # 结尾不换行
a b c.
```

---

## 变量与类型

- 命名：数字字母下划线，不能以数字开头，大小写敏感，不需要提前声明
- `_var` 约定为 protected，`__var` 约定为 private

```python
file_name = "temp.txt"
a, b = 1, 2  # 多变量同时赋值
```

**基本类型：**

| 类型 | 说明 | 示例 |
|---|---|---|
| `int` | 任意大小整数（无 long） | `42` |
| `float` | 浮点数，支持科学计数法 | `111e-2` → `1.11` |
| `bool` | 布尔值（注意大写） | `True` / `False` |
| `complex` | 复数，虚部用 j | `64.23+3j` |
| `str` | 字符串（无 char 概念） | `"hello"` |

**类型转换：**

```python
>>> int("12")        # 字符串转 int → 12
>>> float("12.3")    # 字符串转 float → 12.3
>>> hex(16)          # 整数转 16 进制字符串 → '0x10'
```

---

## 运算符

### 下标 `[]`

```python
s = "Python"
s[0]   # 'P'  (从左，从 0 开始)
s[-1]  # 'n'  (从右，从 -1 开始)
```

### 切片 `[left:right]`

包含 left，不包含 right：

```python
s = "123456789"
s[0:2]   # '12'
s[4:]    # '56789'
s[:-3]   # '123456'
```

### 成员运算符 `in / not in`

```python
"123" in "12345"      # True
"123" not in "12345"  # False
```

### 逻辑运算符

```python
# Python 用 and / or / not，而不是 && / || / !
s.startswith("P") and s.endswith("n")  # True
not s.startswith("P")                   # False
```

---

## 字符串

多行字符串使用三引号：

```python
print("""第一行
第二行
第三行""")
```

**f-string（推荐写法，Python 3.6+）：**

```python
year, month, day = 2024, 6, 18
print(f"Today is {year}-{month}-{day}")

# 格式化对齐
for key, value in info.items():
    print(f"{key:10} : {value:10}")
```

**str.format：**

```python
"a{}{}".format("b", "c")                        # 'abc'
"Today is {year} {month}".format(year=2024, month=6)
"Today is {year} {month}".format(**info)         # 解包字典
```

> 字符串是不可变的，不能用索引修改：`s[0] = "T"` 会报 TypeError。

---

## 流程控制

### if / elif / else

```python
if len(s) < 3:
    print("短")
elif len(s) < 5:
    print("中")
else:
    print("长")
```

### for in

```python
# 遍历列表
for word in ["Hello", "World"]:
    print(word)

# range 数字序列
for i in range(3):   # 0, 1, 2
    print(i)

# 同时遍历 key, value
for key, value in info.items():
    print(key, value)

# 同时遍历 index, value
for index, word in enumerate(words):
    print(index, word)
```

### while / else

```python
i = 0
while i < 5:
    print(i)
    i += 1
else:
    # 循环正常结束后执行（break 不触发 else）
    print("done")
```

### pass

语法占位符，什么也不做：

```python
def todo_func():
    pass  # 没有 pass 会报 SyntaxError
```

---

## 列表 list

可变的有序集合：

```python
l = [1, 2, 3]
l.append(4)     # 末尾添加
l[0] = 5        # 修改
l1 = l[0:2]     # 切片（返回新列表）
l.pop()         # 删除并返回最后一个元素
del l[0]        # 删除指定位置
del l[:]        # 清空
```

---

## 元组 tuple

不可变的有序集合：

```python
t = (1, 2, "3")
t[0]       # 1（只能读）
a, b, c = t  # 序列解包
```

---

## 集合 set

无序、不重复：

```python
a = {1, 2, 3}
b = set([2, 3, 4])

a.add(5)       # 添加
a.remove(5)    # 删除
1 in a         # 是否存在

# 集合运算
a - b   # 差集 {1}
a | b   # 并集 {1, 2, 3, 4}
a & b   # 交集 {2, 3}
```

---

## 字典 dict

key-value，任何不可变类型都可作为 key：

```python
temp = {"a": 1, "b": 2}
temp["a"] = 3         # 修改
temp["a"]             # 访问 → 3
del temp["a"]         # 删除

for key, value in temp.items():
    print(key, value)

# 从键值对构造
dict([("a", 1), ("b", 2)])
```

---

## 函数

```python
def add(a, b):
    return a + b

add(1, 2)  # 3
```

### 默认值参数

```python
def greet(name, greeting="Hello"):
    print(f"{greeting}, {name}")

greet("Leo")           # Hello, Leo
greet("Leo", "Hi")     # Hi, Leo
```

> ⚠️ 默认值只执行一次。可变对象（list/dict）作默认值时要用 None：

```python
def f(a, L=None):
    if L is None:
        L = []
    L.append(a)
    return L
```

### 参数解包

```python
def add(a, b):
    return a + b

add(*[2, 3])             # 解包列表 → 5
add(**{"a": 3, "b": 4})  # 解包字典 → 7
```

### lambda 表达式

```python
multiply = lambda x, y: x * y
multiply(3, 4)  # 12
```

### 变量作用域

- 函数内可以**读**全局变量
- 要**修改**全局变量，需用 `global` 声明

```python
count = 0

def increment():
    global count
    count += 1
```

---

## 模块

```python
# logger1.py
def log():
    print("logger1")

# main.py
import logger1
import logger2 as l2   # 别名

logger1.log()
l2.log()
```

判断是被 import 还是直接执行：

```python
if __name__ == "__main__":
    log()  # 直接运行时才执行
```

---

## 类（基础）

```python
class Logger:
    def __init__(self, prefix):
        self.prefix = prefix          # 公开属性
        self.__private = "secret"     # 私有属性（双下划线）

    def log(self, content):
        print(self.prefix + ": " + content)

l = Logger("App")
l.log("started")
```

> 类的深入用法（`@property`、静态方法、继承、抽象类）见下一章：[深入理解类](./python-class)

---

## 异步编程（asyncio）

Python 的 asyncio 和 JavaScript 的 async/await 非常相似：

```python
import asyncio

# async def 定义一个异步函数（类似 JS 的 async function）
async def fetch_data(url: str) -> dict:
    print(f"开始请求: {url}")
    await asyncio.sleep(1)  # 模拟网络请求（类似 JS 的 await）
    return {"url": url, "status": 200}

# 并发执行多个异步任务
async def main():
    # 串行执行（不好）
    # r1 = await fetch_data("/api/users")
    # r2 = await fetch_data("/api/orders")

    # 并发执行（好）
    r1, r2 = await asyncio.gather(
        fetch_data("/api/users"),
        fetch_data("/api/orders"),
    )
    print(r1, r2)

asyncio.run(main())
```

**和 JS 的对应关系：**

| JavaScript | Python |
|---|---|
| `async function` | `async def` |
| `await promise` | `await coroutine` |
| `Promise.all([...])` | `asyncio.gather(...)` |
| `Promise.race([...])` | `asyncio.wait(..., return_when=FIRST_COMPLETED)` |
| `new Promise((resolve) => ...)` | `asyncio.get_event_loop().run_in_executor(...)` |

**在 FastAPI 中的对比：**

```python
# ✅ 正确的异步用法（I/O 密集任务）
@app.get("/async")
async def read_async():
    data = await fetch_from_database()
    return data

# ✅ 同步函数 FastAPI 自动放线程池，不阻塞事件循环
@app.get("/sync")
def read_sync():
    data = fetch_from_database_sync()
    return data
```

---

## 虚拟环境

前端用 `npm install` / `yarn`，Python 用 `pip` + 虚拟环境：

```bash
# 创建虚拟环境
python3 -m venv .venv

# 激活
source .venv/bin/activate       # Mac/Linux
.venv\Scripts\activate          # Windows

# 安装依赖
pip install fastapi uvicorn

# 保存依赖
pip freeze > requirements.txt

# 另一个开发者
pip install -r requirements.txt

# 退出虚拟环境
deactivate
```

**poetry（更现代的依赖管理，类似 package.json）：**

```bash
pip install poetry
poetry init           # 创建 pyproject.toml
poetry add fastapi    # 安装依赖
poetry install        # 根据 pyproject.toml 安装
poetry shell          # 进入虚拟环境
```

### .gitignore 中要忽略的

```txt
.venv/
__pycache__/
*.pyc
.env
*.egg-info/
dist/
build/
```

---

## 类型标注（Type Hints）

Python 3.10+ 原生支持类型标注，是 FastAPI 和 Pydantic 的基础：

```python
# 基础类型
name: str = "Alice"
age: int = 28
is_admin: bool = False
scores: list[int] = [95, 87, 92]
user_data: dict[str, object] = {"name": "Alice", "age": 28}

# 可以为 None
address: str | None = None
# 或 Optional[str]

# 函数签名
def fetch_users(limit: int = 10, include_disabled: bool = False) -> list[dict]:
    ...

# 联合类型（多个可能类型）
def parse_id(id: str | int) -> dict:
    ...

# Literal（限制取值）
from typing import Literal

def set_status(status: Literal["pending", "running", "done"]) -> None:
    ...
```

**记住：Python 的类型标注在运行时不影响代码行为（不像 TypeScript 会编译检查）——它主要用于代码提示和第三方工具（如 FastAPI、Pydantic、mypy）。**

---

## 文件操作

| 模式 | 说明 |
|---|---|
| `r` | 读（默认） |
| `w` | 写（截断原内容） |
| `a` | 追加 |
| `b` | 二进制模式 |

推荐使用 `with` 语句，自动关闭文件：

```python
# 读取全部内容
with open("content.txt", "r", encoding="utf-8") as f:
    print(f.read())

# 逐行读取
with open("content.txt", "r", encoding="utf-8") as f:
    for line in f:
        print(line.rstrip())

# 写入
with open("output.txt", "w", encoding="utf-8") as f:
    f.write("Hello\n")
```

---

## 异常处理

```python
try:
    result = int(input("输入数字: "))
except ValueError as e:
    print(f"格式错误: {e}")
except ZeroDivisionError:
    print("不能除以零")
finally:
    print("一定会执行，通常用来释放资源")
```

主动抛出异常：

```python
def validate(value):
    if value < 0:
        raise ValueError(f"值不能为负：{value}")
```
