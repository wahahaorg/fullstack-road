# Go 进阶：类型系统与泛型

> 泛型、类型断言、接口约束、结构体嵌入、反射——Go 的类型系统比你想象的更强大。

## 泛型（Generics）

Go 1.18 引入了泛型，这是 Go 语言历史上最大的语法变更。泛型允许你编写可处理多种类型的函数和数据结构，而不需要运行时反射或代码生成。

### 泛型函数

```go
// 非泛型：要为每种类型写一遍
func SumInts(vals []int) int64 {
    var s int64
    for _, v := range vals { s += int64(v) }
    return s
}

func SumFloats(vals []float64) float64 {
    var s float64
    for _, v := range vals { s += v }
    return s
}

// 泛型：一个函数处理所有数字类型
func Sum[T int | int64 | float64](vals []T) T {
    var s T
    for _, v := range vals { s += v }
    return s
}

// 使用
ints := []int{1, 2, 3}
floats := []float64{1.1, 2.2, 3.3}

fmt.Println(Sum(ints))    // 6
fmt.Println(Sum(floats))  // 6.6
```

`[T int | int64 | float64]` 是**类型参数列表**。`T` 像一个占位符，调用时由编译器推断具体类型。

### 泛型类型

不只是函数，结构体和接口也可以带类型参数：

```go
// 泛型栈
type Stack[T any] struct {
    items []T
}

func (s *Stack[T]) Push(item T) {
    s.items = append(s.items, item)
}

func (s *Stack[T]) Pop() (T, bool) {
    if len(s.items) == 0 {
        var zero T
        return zero, false
    }
    item := s.items[len(s.items)-1]
    s.items = s.items[:len(s.items)-1]
    return item, true
}

// 使用
stack := Stack[string]{}
stack.Push("hello")
stack.Push("world")

v, ok := stack.Pop()
fmt.Println(v, ok)  // world true
```

```go
// 泛型二叉搜索树
type Tree[T comparable] struct {
    Left, Right *Tree[T]
    Value       T
}

func (t *Tree[T]) Insert(v T) {
    if t.Value == v {
        return
    }
    if t.Value == *new(T) { // 零值判断
        t.Value = v
        return
    }
    if any(v) < any(t.Value) { // 需要约束支持比较
        // ...
    }
}
```

> 注意：`comparable` 是内置约束，表示可比较（`==`、`!=`）。但不能直接用 `<`、`>` 比较，那些需要 `constraints.Ordered`。

### 类型约束（Constraints）

类型约束本质上是一个**接口**，但可以包含类型集合：

```go
// 自定义约束
type Number interface {
    int | int8 | int16 | int32 | int64 |
        uint | uint8 | uint16 | uint32 | uint64 |
        float32 | float64
}

func Double[T Number](v T) T {
    return v * 2
}
```

**`any` 是 `interface{}` 的别名**，表示不限制类型：

```go
func PrintAny[T any](v T) {
    fmt.Println(v)
}
```

**类型约束中的 `~` 符号：**

```go
// ~int 表示"底层类型为 int 的所有类型"
type MyInt int

type IntLike interface {
    ~int | ~int64
}

func Add[T IntLike](a, b T) T {
    return a + b
}

var x MyInt = 5
fmt.Println(Add(x, MyInt(3)))  // 8（没有 ~ 的话会编译报错）
```

`~` 表示接受**底层类型匹配**。`MyInt` 的底层类型是 `int`，所以 `~int` 允许它通过。

### 常用内置约束

```go
// comparable — 可比较（== / !=）
// 内置，无需导入
func Find[T comparable](items []T, target T) int {
    for i, v := range items {
        if v == target {
            return i
        }
    }
    return -1
}

// golang.org/x/exp/constraints 提供额外约束
import "golang.org/x/exp/constraints"

func Max[T constraints.Ordered](a, b T) T {
    if a > b { return a }
    return b
}
```

`constraints.Ordered` 包含所有可以 `<` `>` `<=` `>=` 的类型：`int` 系、`float` 系、`string`。

### 泛型的常见误区

```go
// ❌ 泛型类型不能用于 switch 类型断言
func TypeName[T any](v T) string {
    // switch v.(type) { }  // 编译错误！
    return fmt.Sprintf("%T", v)
}

// ❌ 泛型类型不能用作方法接收者的类型参数（但结构体可以）
type Box[T any] struct{ Val T }

// 方法可以引用结构体的类型参数
func (b Box[T]) Get() T { return b.Val }

// 但方法不能再引入新的类型参数
// func (b Box[T]) Map[U any](fn func(T) U) Box[U] { }  // ❌ Go 不支持
```

---

## 类型断言（Type Assertion）

类型断言用于提取接口值的底层具体类型：

```go
var val any = "hello"

// 基础断言：如果失败会 panic
s := val.(string)
fmt.Println(s)  // hello

// 安全断言：用 comma-ok 模式
s, ok := val.(string)
if ok {
    fmt.Println("是字符串:", s)
} else {
    fmt.Println("不是字符串")
}

// 断言不同的类型会 panic（如果不检查 ok）
// n := val.(int)  // panic: interface conversion
```

**类型断言的本质：**
- 它在运行时检查接口的动态类型
- `any.(T)` 在运行时检查接口值是否持有类型 `T`
- 如果 `T` 是接口类型，它检查是否实现了该接口

```go
type Stringer interface {
    String() string
}

func Print(v any) {
    if s, ok := v.(Stringer); ok {
        fmt.Println(s.String())
    } else {
        fmt.Println(v)
    }
}
```

---

## 类型 Switch（Type Switch）

类型 switch 是类型断言的升级版，可以在一组类型中匹配：

```go
func showType(v any) {
    switch v := v.(type) {
    case nil:
        fmt.Println("nil")
    case int:
        fmt.Println("int:", v)      // v 在这里是 int
    case string:
        fmt.Println("string:", v)   // v 在这里是 string
    case bool:
        fmt.Println("bool:", v)
    case fmt.Stringer:
        fmt.Println("Stringer:", v.String())
    default:
        fmt.Printf("unknown type: %T\n", v)
    }
}

showType(42)        // int: 42
showType("hello")   // string: hello
showType(true)      // bool: true
```

**类型 switch 的执行顺序：** case 按编写顺序匹配，命中第一个就不再继续。

```go
// 结合泛型约束风格的 switch（Go 1.21+ 的 interface 风格）
func process[T int | string](v T) {
    // 但 switch v.(type) 对泛型参数有限制
    // 泛型类型参数不能直接用 .(type)
}
```

> 注意：对泛型类型参数 `T` 不能做 `.(type)` 类型 switch，因为编译器在编译时不知道具体类型。

---

## 结构体嵌入与组合

Go 没有继承，但通过**结构体嵌入**实现了强大的组合模式。

### 基本嵌入

```go
type Base struct {
    ID int
}

func (b Base) GetID() int { return b.ID }

// User 嵌入了 Base
type User struct {
    Base             // 嵌入（匿名字段）
    Name  string
    Email string
}

// 使用：User 直接"继承"了 Base 的字段和方法
u := User{
    Base:  Base{ID: 1},
    Name:  "Alice",
    Email: "alice@example.com",
}

fmt.Println(u.ID)       // 1（直接访问嵌入字段）
fmt.Println(u.GetID())  // 1（直接调用嵌入方法）
```

### 方法提升与覆盖

```go
type Logger struct{}

func (Logger) Log(msg string) {
    fmt.Println("[LOG]", msg)
}

type Service struct {
    Logger  // 嵌入
    Name string
}

// 可以覆盖嵌入的方法
func (s Service) Log(msg string) {
    fmt.Printf("[%s] %s\n", s.Name, msg)
}

svc := Service{Name: "users"}
svc.Log("started")  // [users] started
// 仍然可以访问原始方法
svc.Logger.Log("raw log")  // [LOG] raw log
```

### 多重嵌入与冲突

```go
type A struct{ Val int }
type B struct{ Val int }

type C struct {
    A
    B
}

c := C{}
// c.Val // 编译错误：ambiguous selector c.Val
c.A.Val = 1  // 显式指定
c.B.Val = 2
```

### 嵌入接口

```go
// 嵌入接口可以在新接口中组合多个接口
type Reader interface {
    Read(p []byte) (n int, err error)
}

type Writer interface {
    Write(p []byte) (n int, err error)
}

// ReadWriter 组合了 Reader 和 Writer
type ReadWriter interface {
    Reader
    Writer
}

// 嵌入还可以用于部分实现
type ReadOnly struct {
    Reader  // 嵌入接口——需要外部注入实现
}

func NewReadOnly(r Reader) *ReadOnly {
    return &ReadOnly{Reader: r}
}
```

---

## 接口进阶：类型约束与类型集合

Go 1.18 之后，接口除了定义方法集，还可以定义**类型集合**：

```go
// 传统接口：方法集
type Stringer interface {
    String() string
}

// 新接口：类型集合（可以用作约束）
type Integer interface {
    ~int | ~int8 | ~int16 | ~int32 | ~int64
}

// 混合：方法 + 类型约束
type SignedInteger interface {
    ~int | ~int8 | ~int16 | ~int32 | ~int64
    String() string  // 除了是整数，还必须实现 String()
}
```

### 接口的「近似元素」

```go
// interface{ int } 约束：严格匹配 int
// interface{ ~int } 约束：底层为 int 的类型

type MyInt int

func F1[T int](v T) T { return v }   // MyInt 不行
func F2[T ~int](v T) T { return v }  // MyInt 可以
```

### 空接口与 any

```go
// 以下完全等价
var a interface{}
var b any  // 推荐，更简洁

// any 可以接任何类型
var v any = 42
v = "hello"
v = struct{ Name string }{"alice"}
```

---

## 反射基础（reflect 包）

反射允许程序在运行时检查类型和值。**日常开发中用得少，但框架、序列化库、测试工具大量依赖它。**

```go
import "reflect"

func inspect(v any) {
    t := reflect.TypeOf(v)
    val := reflect.ValueOf(v)

    fmt.Println("类型:", t.Name())
    fmt.Println("种类:", t.Kind())
    fmt.Println("值:", val.Interface())

    // 遍历结构体字段
    if t.Kind() == reflect.Struct {
        for i := 0; i < t.NumField(); i++ {
            field := t.Field(i)
            value := val.Field(i)
            fmt.Printf("  %s (%s) = %v\n",
                field.Name, field.Type, value.Interface())
        }
    }
}

type Config struct {
    Host string
    Port int
}

inspect(Config{Host: "localhost", Port: 8080})
// 类型: Config
// 种类: struct
// 值: {localhost 8080}
//   Host (string) = localhost
//   Port (int) = 8080
```

### 通过反射修改值

```go
// 反射修改值要求传入指针
func setField(v any, name string, value any) {
    val := reflect.ValueOf(v)

    // 必须是指针，否则无法修改
    if val.Kind() != reflect.Ptr {
        panic("必须传入指针")
    }

    elem := val.Elem() // 解引用
    field := elem.FieldByName(name)

    if !field.IsValid() {
        fmt.Println("字段不存在:", name)
        return
    }

    if !field.CanSet() {
        fmt.Println("字段不可设置")
        return
    }

    // 设置值
    newVal := reflect.ValueOf(value)
    field.Set(newVal)
}

cfg := &Config{Host: "localhost", Port: 8080}
setField(cfg, "Port", 9090)
fmt.Println(cfg.Port)  // 9090
```

### 反射与标签（Tags）

```go
type User struct {
    Name  string `json:"name" validate:"required"`
    Email string `json:"email" validate:"required,email"`
    Age   int    `json:"age" validate:"gte=0,lte=150"`
}

func readTags(v any) {
    t := reflect.TypeOf(v)
    for i := 0; i < t.NumField(); i++ {
        field := t.Field(i)
        fmt.Printf("%s: json=%s validate=%s\n",
            field.Name,
            field.Tag.Get("json"),
            field.Tag.Get("validate"),
        )
    }
}

readTags(User{})
// Name: json=name validate=required
// Email: json=email validate=required,email
// Age: json=age validate=gte=0,lte=150
```

### 什么时候用 / 什么时候不用反射

**应该用：**
- 序列化/反序列化库（JSON、YAML、protobuf）
- ORM（通用 CRUD）
- 测试框架（自动 mock）
- 依赖注入容器
- 配置读取绑定

**不应该用：**
- 能用泛型解决的场景
- 热点路径（反射慢 10-100 倍）
- 可以手写代码的重复逻辑

> **规则：** 如果你在写业务代码时用到了 `reflect`，大概率是在做不该做的事情。反射是框架作者的工具，不是业务开发者的日常工具。

---

## 常见模式与实战技巧

### Functional Options（函数选项模式）

这是 Go 中最流行的构造模式之一，不用重载构造函数：

```go
type ServerOption func(*Server)

func WithHost(host string) ServerOption {
    return func(s *Server) {
        s.Host = host
    }
}

func WithPort(port int) ServerOption {
    return func(s *Server) {
        s.Port = port
    }
}

func WithTimeout(timeout time.Duration) ServerOption {
    return func(s *Server) {
        s.Timeout = timeout
    }
}

type Server struct {
    Host    string
    Port    int
    Timeout time.Duration
}

func NewServer(opts ...ServerOption) *Server {
    // 默认值
    s := &Server{
        Host:    "0.0.0.0",
        Port:    8080,
        Timeout: 30 * time.Second,
    }
    // 应用选项
    for _, opt := range opts {
        opt(s)
    }
    return s
}

// 使用
srv := NewServer(
    WithHost("localhost"),
    WithPort(9090),
    WithTimeout(10*time.Second),
)
```

### 类型集合+泛型实现统一处理

```go
type Entity interface {
    GetID() int64
    SetID(id int64)
}

type BaseEntity struct {
    ID int64
}

func (b *BaseEntity) GetID() int64  { return b.ID }
func (b *BaseEntity) SetID(id int64) { b.ID = id }

// 泛型 CRUD 基类
type Repository[T Entity] struct {
    // ...
}

func (r *Repository[T]) Save(entity T) error {
    // 通用保存逻辑
    return nil
}

// 实体类型
type User struct {
    BaseEntity
    Name  string
    Email string
}

type Product struct {
    BaseEntity
    Title string
    Price float64
}

// 使用
userRepo := &Repository[User]{}
productRepo := &Repository[Product]{}
```

---

## 面试怎么说

> Go 的泛型在 1.18 引入，采用类型参数和类型约束的设计，比 Java 的类型擦除和 C++ 的模板更简洁。实际项目中，我用泛型写过通用的集合操作库和数据访问层，但不建议过度使用——复杂的泛型签名会降低代码可读性。结构体嵌入是 Go 的组合替代继承的方式，配合接口的隐式实现，可以写出非常灵活的架构。反射我很少在业务代码中用，主要在写工具库时用到，比如基于标签的验证函数或配置绑定。一个我常用的模式是 Functional Options，它用闭包解决了 Go 没有函数重载和可选参数的问题，在开源框架中随处可见。
