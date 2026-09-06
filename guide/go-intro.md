# Go 快速入门

> 面向有前端 / Python 基础的开发者。Go 不是"更好的 Node"，它是另一种后端思路——简单、直接、擅长并发。

## Go 是什么？前端开发者为什么学它？

```txt
Go = 静态类型 + 编译型 + 内置并发 + 极简语言设计
```

**和 Node.js / Python 的核心区别：**

| 对比维度 | Node.js / Python | Go |
|---------|-----------------|-----|
| 类型系统 | 动态 / 可选类型标注 | 静态强类型 |
| 运行方式 | 解释执行 / JIT | 编译为二进制 |
| 并发模型 | 事件循环 + async/await | goroutine + channel |
| 错误处理 | try/catch | 显式返回 error |
| 依赖管理 | npm / pip | go mod |
| 启动速度 | 中等 | 极快（毫秒级） |
| 二进制体积 | 需要运行时 | 单一可执行文件 |
| 学习曲线 | 较低 | 低（语法极少） |

**Go 适合做什么：**
- API 网关 / BFF 层
- 微服务 / 中间件
- 云原生基础设施（Docker、Kubernetes 用 Go 写的）
- AI 应用的性能敏感模块
- CLI 工具

**不适合做什么：**
- 复杂业务逻辑的前端 SSR（不如 Node）
- 数据分析 / AI 训练（Python 生态更强）
- 快速原型验证（动态语言更快）

---

## 安装与第一个项目

```bash
# Mac
brew install go

# 验证
go version

# 创建新项目
mkdir my-app && cd my-app
go mod init my-app  # 初始化模块（类似 npm init）
```

```go
// main.go — Go 的入口文件
package main  // 每个 Go 文件属于一个包

import "fmt"  // 标准库的格式化 I/O

// main 函数是程序入口
func main() {
    fmt.Println("Hello, 全栈!")
}
```

```bash
go run main.go       # 直接运行（不产生二进制）
go build -o my-app   # 编译成二进制文件
./my-app             # 直接执行
```

---

## 变量与基本类型

### 声明方式

```go
package main

import "fmt"

func main() {
    // 方式 1：var 声明（显式类型）
    var name string = "Alice"
    var age int = 28

    // 方式 2：类型推断（类似 JS 的 let）
    var city = "Beijing"

    // 方式 3：短声明（:= 最常用，只能在函数内）
    score := 95       // int
    isAdmin := true   // bool
    pi := 3.14        // float64

    // 多变量同时声明
    var x, y int = 1, 2
    a, b := "hello", true

    fmt.Println(name, age, city, score)
}
```

**和 JS 的对比：**

| 概念 | JavaScript | Go |
|------|-----------|-----|
| 变量声明 | `let x = 1` | `x := 1` 或 `var x int = 1` |
| 常量 | `const x = 1` | `const x = 1` |
| 默认值 | `undefined` | 零值（`0`、`""`、`false`、`nil`） |
| 类型转换 | 隐式 + 显式 | **必须显式转换** |

### 零值（Zero Values）

Go 变量声明后不赋值也有默认值，没有 `undefined` 或 `null`：

```go
var s string  // ""
var i int     // 0
var f float64 // 0.0
var b bool    // false
var p *int    // nil（指针）
```

### 基本类型

```go
// 整数
var a int     // 平台相关（32/64 位）
var b int8    // -128 ~ 127
var c int64   // 大整数
var d uint    // 无符号整数
var e byte    // uint8 的别名

// 浮点数
var f float32       // 约 7 位精度
var g float64       // 约 15 位精度（推荐）

// 字符串（不可变）
var s string = "你好"

// 布尔
var active bool = true
```

### 字节、rune 与 UTF-8

Go 的 `string` 保存的是 UTF-8 字节序列，不是“字符数组”。`len` 返回字节数，遍历字符串时用 `range` 才会按 Unicode 码点读取：

```go
s := "你好 Go"
fmt.Println(len(s)) // 9：中文每个字符占 3 个 UTF-8 字节

for i, r := range s {
    fmt.Printf("字节位置=%d 字符=%c\n", i, r)
}

bytes := []byte(s) // 适合网络协议、文件和编码处理
runes := []rune(s) // 适合按“字符”截取或统计
fmt.Println(len(bytes), len(runes)) // 9 5
```

`byte` 是 `uint8` 的别名，`rune` 是 `int32` 的别名。不要用 `s[:2]` 截取中文；这可能切断一个 UTF-8 字符。需要按字符截取时先转成 `[]rune`，需要按字节处理时才使用 `[]byte`。

### 常量与 `iota`

常量在编译期确定，适合状态码、权限位和不会在运行时变化的配置。`iota` 会在同一个 `const` 块中从 0 递增：

```go
type Status int

const (
    Draft Status = iota // 0
    Published            // 1，沿用上一行的类型和表达式
    Archived             // 2
)
```

它不是运行时计数器，也不会跨 `const` 块保留值。

---

## 控制流

### if / else

```go
// Go 的 if 不需要括号，但必须有大括号
if score >= 90 {
    fmt.Println("优秀")
} else if score >= 60 {
    fmt.Println("及格")
} else {
    fmt.Println("不及格")
}

// if 中可以直接写一个短语句（作用域在 if 内）
if v := getValue(); v > 10 {
    fmt.Println("大于 10:", v)
}
// 这里不能访问 v
```

### for（Go 只有 for，没有 while）

```go
// 完整 for
for i := 0; i < 10; i++ {
    fmt.Println(i)
}

// 类似 while
n := 0
for n < 5 {
    n++
}

// 无限循环
for {
    // 直到 break
}

// range 遍历（类似 for...of）
nums := []int{10, 20, 30}
for index, value := range nums {
    fmt.Println(index, value)
}

// 只取 key / index
for i := range nums {
    fmt.Println(i)
}

// 遍历 map
for key, value := range map[string]int{"a": 1, "b": 2} {
    fmt.Println(key, value)
}
```

### switch

```go
// switch 不需要 break，默认自动跳出
switch status {
case "pending":
    fmt.Println("待处理")
case "running":
    fmt.Println("运行中")
case "done":
    fmt.Println("已完成")
default:
    fmt.Println("未知状态")
}

// switch 也可以当 if-else 链用
switch {
case score >= 90:
    fmt.Println("A")
case score >= 80:
    fmt.Println("B")
default:
    fmt.Println("C")
}
```

---

## 函数

### 基础函数

```go
// 参数：类型写在变量名后面
// 返回值：类型写在最后
func add(a int, b int) int {
    return a + b
}

// 连续相同类型可以省略前面的
func add(a, b int) int {
    return a + b
}

add(3, 5)   // 8
```

### 多返回值（Go 的特色）

```go
// 返回多个值（最常用于 结果 + 错误）
func divide(a, b int) (int, error) {
    if b == 0 {
        return 0, fmt.Errorf("除数不能为 0")
    }
    return a / b, nil
}

// 调用时用多变量接收
result, err := divide(10, 2)
if err != nil {
    fmt.Println("错误:", err)
} else {
    fmt.Println("结果:", result)
}

// 只取其中一个：用 _ 忽略
result, _ = divide(10, 0)
```

### 命名返回值

```go
// 可以在返回值列表里先定义变量名
func split(sum int) (x, y int) {
    x = sum / 2
    y = sum - x
    return  // 裸返回（直接 return，自动返回 x, y）
}
```

### 函数作为值

```go
// Go 的函数也是一等公民
fn := func(a, b int) int {
    return a + b
}
fmt.Println(fn(3, 5))  // 8

// 函数作为参数（类似回调）
func operate(a, b int, op func(int, int) int) int {
    return op(a, b)
}
```

---

## 指针与值语义

Go 默认按值传递：函数收到的是实参的一份副本。指针让函数拿到“某个值的地址”，从而可以读取或修改原值。

```go
func resetByValue(n int) {
    n = 0 // 只修改副本
}

func resetByPointer(n *int) {
    if n == nil {
        return
    }
    *n = 0 // 修改调用方的变量
}

count := 3
resetByValue(count)
fmt.Println(count) // 3
resetByPointer(&count)
fmt.Println(count) // 0
```

`&count` 取地址，`*p` 解引用，`nil` 表示没有指向有效值的指针。这个模型和 JavaScript 对象引用有相似之处，但不要直接等同：Go 的 `struct` 传参默认会复制字段，只有显式传指针或包含引用型字段时才共享底层数据。

结构体方法也要选择接收者：值接收者适合不修改对象的小值类型，指针接收者适合修改对象或避免复制大结构体。编译器会在可寻址的变量上自动补 `&`，但接口值、函数返回值等场景不能依赖这种自动转换。

```go
type Counter struct{ Value int }

func (c Counter) Snapshot() int { return c.Value }
func (c *Counter) Add(n int)    { c.Value += n }

c := Counter{}
c.Add(1) // 等价于 (&c).Add(1)
```

`new(T)` 只分配一个零值 `T` 并返回 `*T`。业务代码通常用结构体字面量或构造函数表达意图，只有确实需要“指向零值的指针”时才使用 `new`。

---

## 数组与切片

```go
// 数组：固定长度
var arr [3]int = [3]int{1, 2, 3}

// 切片：动态长度（最常用，类似 JS 的数组）
var slice1 []int
slice2 := []int{1, 2, 3}
slice3 := make([]int, 5)     // length=5，全部为 0
slice4 := make([]int, 3, 5)  // length=3, capacity=5

// 追加（类似 push）
slice2 = append(slice2, 4, 5)

// 切片操作（类似 slice）
sub := slice2[1:3]  // [2, 3]

// 长度和容量
len(slice2)  // 5
cap(slice2)  // 底层数组从起始位置到末尾的容量
```

**和 JS 的对比：**

| 操作 | JavaScript | Go |
|------|-----------|-----|
| 创建 | `[]int{1,2,3}` | `[]int{1,2,3}`（类似） |
| 追加 | `arr.push(4)` | `arr = append(arr, 4)` |
| 长度 | `arr.length` | `len(arr)` |
| 切片 | `arr.slice(1,3)` | `arr[1:3]` |
| 删除 | `arr.splice(i,1)` | 需要手动拼接 `append(arr[:i], arr[i+1:]...)` |

### Slice 的底层结构与别名

Slice 可以理解为一个小描述符：指向底层数组的指针、当前 `len` 和可继续扩容的 `cap`。复制 slice 只复制描述符，不会复制底层数组：

```go
source := []int{1, 2, 3}
view := source[:2]
view[0] = 99
fmt.Println(source) // [99 2 3]，两者共享底层数组

copyOfSource := append([]int(nil), source...)
copyOfSource[0] = 7
fmt.Println(source[0]) // 99，复制后互不影响
```

`append` 可能在容量不足时分配新的底层数组，所以调用方必须接住返回值：`items = append(items, item)`。如果一个 slice 的子切片长期存活，它也会让整个底层数组保持存活；处理大文件或大请求体时，可以用 `copy` 取出需要的部分再释放原始引用。

空 slice 和 `nil` slice 都可以 `len`、`range` 和 `append`，但它们在 JSON 编码或作为 API 字段时可能表现不同：`nil` slice 通常编码为 `null`，空 slice 编码为 `[]`。对外响应要根据契约主动选择。

---

## Map（字典）

```go
// 声明
var m1 map[string]int            // nil map，不能直接写入
m2 := map[string]int{"a": 1, "b": 2}
m3 := make(map[string]int)       // 空 map，可以写入

// 读写
m3["key"] = 100
value := m3["key"]

// 判断 key 是否存在（Go 的特色）
value, exists := m3["key"]
if exists {
    fmt.Println("存在:", value)
}

// 删除
delete(m3, "key")

// 遍历
for key, value := range m2 {
    fmt.Println(key, value)
}
```

Map 的遍历顺序没有稳定保证，不能把它当作排序后的结果。读取不存在的 key 会得到该类型的零值，因此需要用 `value, ok := m[key]` 区分“没有 key”和“key 的值恰好是零值”。Map 不是并发安全容器；并发读写必须在边界处使用锁或 `sync.Map`，细节见[并发模式与工程实践](./go-advanced-concurrency)。

---

## Struct（结构体）— 类似 TS 的 interface / class

```go
// 定义结构体（类似 TS 的 interface，但可以包含方法）
type User struct {
    ID       int
    Name     string
    Email    string
    IsActive bool
}

// 创建实例
u1 := User{ID: 1, Name: "Alice", Email: "alice@example.com", IsActive: true}
u2 := User{ID: 2, Name: "Bob"}  // 未指定字段为零值

// 访问字段
fmt.Println(u1.Name)  // Alice

// 结构体方法（类似 class 的方法）
func (u User) Greet() string {
    return "Hello, I'm " + u.Name
}

// 指针接收者（修改原对象）
func (u *User) Deactivate() {
    u.IsActive = false
}

fmt.Println(u1.Greet())  // Hello, I'm Alice
u1.Deactivate()
```

**和 TS 的对比：**

```typescript
// TypeScript
interface User {
    id: number
    name: string
    email: string
    isActive: boolean
}
```

```go
// Go
type User struct {
    ID       int
    Name     string
    Email    string
    IsActive bool
}
```

---

## Interface（接口）— 类似 TS 的 interface，但更灵活

Go 的接口是**隐式实现**——不需要显式写 `implements`：

```go
// 定义接口
type Greeter interface {
    Greet() string
}

// 定义两个类型
type User struct{ Name string }
type Robot struct{ Model string }

// User 实现了 Greeter（无需写 implements）
func (u User) Greet() string {
    return "Hi, I'm " + u.Name
}

// Robot 也实现了 Greeter
func (r Robot) Greet() string {
    return "Beep, I'm " + r.Model
}

// 任何实现了 Greeter 的类型都能传进来
func SayHello(g Greeter) {
    fmt.Println(g.Greet())
}

SayHello(User{Name: "Alice"})   // Hi, I'm Alice
SayHello(Robot{Model: "R2D2"}) // Beep, I'm R2D2
```

**空接口 `interface{}`（Go 1.18+ 可用 `any`）：**

```go
// 可以接收任何类型（类似 TS 的 unknown）
var anything any = "hello"
anything = 42
anything = true
```

---

## 错误处理

Go 没有 try/catch，错误通过返回值显式传递：

```go
import (
    "errors"
    "fmt"
)

func safeDivide(a, b float64) (float64, error) {
    if b == 0 {
        return 0, errors.New("除数不能为零")
    }
    return a / b, nil
}

// 调用者必须处理错误
result, err := safeDivide(10, 0)
if err != nil {
    fmt.Println("出错了:", err)  // 出错了: 除数不能为零
    return
}
fmt.Println(result)

// 自定义错误
type ValidationError struct {
    Field string
    Value any
    Msg   string
}

func (e ValidationError) Error() string {
    return fmt.Sprintf("字段 %s 校验失败: %s", e.Field, e.Msg)
}
```

**原则：不忽略错误。编译时不会报错，但逻辑上每个 `err` 都应该处理。**

---

## Goroutine 与 Channel（Go 的核心竞争力）

### Goroutine：轻量级线程

```go
// 用 go 关键字启动一个 goroutine
go func() {
    fmt.Println("在另一个 goroutine 中执行")
}()

// 启动多个
for i := 0; i < 10; i++ {
    go func(id int) {
        fmt.Println("worker:", id)
    }(i)
}
```

**goroutine vs 线程：**
- 一个 goroutine 初始只占几 KB 栈空间，可以轻松启动数十万个
- 线程通常占 MB 级栈空间
- goroutine 由 Go 运行时调度，不是 OS 线程

### Channel：goroutine 之间的通信

```go
// 创建 channel
ch := make(chan int)

// 发送（在 goroutine 中）
go func() {
    ch <- 42  // 发送数据到 channel
}()

// 接收
value := <-ch  // 从 channel 接收
fmt.Println(value)  // 42
```

### 实际例子：并发请求

```go
package main

import (
    "fmt"
    "net/http"
    "time"
)

func fetchURL(url string, ch chan<- string) {
    start := time.Now()
    resp, err := http.Get(url)
    if err != nil {
        ch <- fmt.Sprintf("❌ %s: %v", url, err)
        return
    }
    defer resp.Body.Close()
    ch <- fmt.Sprintf("✅ %s: %d (%v)", url, resp.StatusCode, time.Since(start))
}

func main() {
    urls := []string{
        "https://httpbin.org/delay/2",
        "https://httpbin.org/delay/1",
        "https://httpbin.org/delay/3",
    }

    ch := make(chan string, len(urls))  // 缓冲 channel

    // 同时发起 3 个请求
    for _, url := range urls {
        go fetchURL(url, ch)
    }

    // 收集结果
    for range urls {
        fmt.Println(<-ch)
    }
}
```

**输出（谁先完成先打印谁）：**

```
✅ https://httpbin.org/delay/1: 200 (1.2s)
✅ https://httpbin.org/delay/2: 200 (2.1s)
✅ https://httpbin.org/delay/3: 200 (3.0s)
```

### select：多 channel 等待

```go
// 同时等待多个 channel，哪个先来执行哪个
select {
case msg1 := <-ch1:
    fmt.Println("ch1 收到:", msg1)
case msg2 := <-ch2:
    fmt.Println("ch2 收到:", msg2)
case <-time.After(5 * time.Second):
    fmt.Println("超时了")
default:
    fmt.Println("没有 channel 准备好")
}
```

**和 JS 的对比：**

| JavaScript | Go |
|-----------|-----|
| `Promise.all([...])` | goroutine + channel |
| `Promise.race([...])` | `select { case <-ch1: ... }` |
| `async/await` | 没有直接等价物（用 channel 同步） |
| `setTimeout` | `time.After` |
| 事件循环 | goroutine 调度器 |

---

## 标准库亮点

Go 的标准库非常强大，很多功能不需要第三方依赖：

```go
import (
    "fmt"        // 格式化 I/O
    "net/http"   // HTTP 客户端和服务端
    "encoding/json"  // JSON 序列化
    "io"         // I/O 抽象
    "os"         // 文件/环境变量
    "time"       // 时间
    "strings"    // 字符串操作
    "sync"       // 并发原语（Mutex、WaitGroup）
    "database/sql"  // 数据库接口
)
```

### 一个完整的 HTTP 服务

```go
package main

import (
    "encoding/json"
    "fmt"
    "log"
    "net/http"
)

type User struct {
    ID   int    `json:"id"`
    Name string `json:"name"`
}

// 处理器函数
func handleUsers(w http.ResponseWriter, r *http.Request) {
    // 判断方法
    if r.Method != http.MethodGet {
        http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
        return
    }

    users := []User{
        {ID: 1, Name: "Alice"},
        {ID: 2, Name: "Bob"},
    }

    w.Header().Set("Content-Type", "application/json")
    json.NewEncoder(w).Encode(users)
}

func handleHealth(w http.ResponseWriter, r *http.Request) {
    w.Header().Set("Content-Type", "application/json")
    json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
}

func main() {
    http.HandleFunc("/users", handleUsers)
    http.HandleFunc("/health", handleHealth)

    fmt.Println("Server starting on :8080")
    log.Fatal(http.ListenAndServe(":8080", nil))
}
```

```bash
go run main.go &
curl http://localhost:8080/health       # {"status":"ok"}
curl http://localhost:8080/users        # [{"id":1,"name":"Alice"},...]
```

---

## 包管理（go mod）

### package、导入与可见性

目录通常对应一个 package，同一个目录下的 `.go` 文件必须属于同一个 package（测试文件可以使用 `包名` 或 `包名_test`）。标识符首字母大写表示对其他 package 可见，小写表示只在当前 package 可见：

```go
// internal/user/user.go
package user

import "strings"

type Profile struct { // 外部可用
    Name string
}

func normalizeName(name string) string { // 仅当前 package 可用
    return strings.TrimSpace(name)
}
```

这不是装饰性命名规则，而是 Go 最基础的封装边界。`internal/` 目录还会限制导入方只能来自它的父目录树，适合放业务实现，避免被其他模块直接依赖。

```bash
# 初始化模块（第一步）
go mod init github.com/yourname/my-api

# 安装依赖（类似 npm install）
go get github.com/gin-gonic/gin

# 这会自动生成 go.mod 和 go.sum
# go.mod  ≈ package.json
# go.sum  ≈ package-lock.json

# 整理依赖
go mod tidy

# 下载所有依赖
go mod download
```

**推荐 Web 框架：**
- 标准库 `net/http` — 够用就先用它
- [Gin](https://github.com/gin-gonic/gin) — 轻量高性能，最流行
- [Echo](https://github.com/labstack/echo) — 类似 Express
- [Fiber](https://github.com/gofiber/fiber) — 受 Express 启发，性能极好

---

## Go 项目结构推荐

```
my-api/
├── main.go              # 入口
├── go.mod               # 模块信息
├── go.sum               # 依赖校验
├── cmd/
│   └── server/          # 启动入口
├── internal/            # 不对外暴露的包
│   ├── handler/         # HTTP 处理器
│   ├── service/         # 业务逻辑
│   ├── repository/      # 数据访问
│   └── model/           # 数据模型
├── pkg/                 # 可对外暴露的包
└── config/              # 配置
```

---

## 面试怎么说

> Go 是一门静态类型、编译型语言，语法极简但内置 goroutine 和 channel，非常擅长并发场景。我选 Go 的场景通常是高性能 API 网关、微服务或云原生工具。Go 的错误处理方式比较特别——没有 try/catch，错误通过返回值显式传递，这样调用方不会忽略。goroutine 可以在单个进程内启动数十万个轻量级协程，通过 channel 安全通信，不需要复杂的锁机制。标准库的 net/http 和 encoding/json 足够应付大多数 Web 场景，不需要像 Node 那样找各种第三方包。
