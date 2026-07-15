# Go 进阶：工程化实战

> 测试、错误包装、优雅关闭、中间件模式、性能分析、模块管理——把 Go 用到生产级别。

## 测试（testing 包）

Go 有内置的测试工具链，不需要第三方框架。测试文件的命名规则：`xxx_test.go`，测试函数签名：`func TestXxx(t *testing.T)`。

### Table-Driven Tests（表格驱动测试）

这是 Go 中最主流的测试风格：

```go
// calc.go
func Add(a, b int) int { return a + b }
func IsEven(n int) bool { return n%2 == 0 }

// calc_test.go
func TestAdd(t *testing.T) {
    tests := []struct {
        name string
        a, b int
        want int
    }{
        {"正数相加", 1, 2, 3},
        {"负数相加", -1, -2, -3},
        {"零值", 0, 0, 0},
        {"正负混合", 5, -3, 2},
    }

    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            got := Add(tt.a, tt.b)
            if got != tt.want {
                t.Errorf("Add(%d, %d) = %d; want %d",
                    tt.a, tt.b, got, tt.want)
            }
        })
    }
}
```

### Subtests（子测试）

```go
func TestIsEven(t *testing.T) {
    t.Run("偶数", func(t *testing.T) {
        if !IsEven(4) {
            t.Error("4 应该是偶数")
        }
    })

    t.Run("奇数", func(t *testing.T) {
        if IsEven(7) {
            t.Error("7 应该是奇数")
        }
    })

    t.Run("零", func(t *testing.T) {
        if !IsEven(0) {
            t.Error("0 应该是偶数")
        }
    })
}
```

子测试的好处：
- 可以单独运行某个 case：`go test -run TestIsEven/偶数`
- 失败时清晰定位到哪个子测试
- 可以共享 setup/teardown

### Setup 与 Teardown

```go
func TestDatabase(t *testing.T) {
    // Setup
    db := setupTestDB(t)
    defer db.Close()

    t.Run("插入", func(t *testing.T) {
        // ...
    })

    t.Run("查询", func(t *testing.T) {
        // ...
    })

    // 每个 test 函数结束后自动清理
    // 可以用 t.Cleanup 注册清理函数
    t.Cleanup(func() {
        db.Exec("TRUNCATE TABLE users")
    })
}
```

### Test Main（整个包的 setup/teardown）

```go
func TestMain(m *testing.M) {
    // 包级 setup
    fmt.Println("=== 开始测试包 ===")
    setup()

    // 运行所有测试
    code := m.Run()

    // 包级 teardown
    teardown()
    fmt.Println("=== 测试包结束 ===")

    os.Exit(code)
}
```

### 覆盖率

```bash
# 运行测试并生成覆盖率报告
go test -cover ./...
go test -coverprofile=coverage.out ./...

# 查看哪些行被覆盖
go tool cover -html=coverage.out -o coverage.html

# 在终端中查看
go tool cover -func=coverage.out
```

**覆盖率目标：** 核心逻辑 80%+，但不要追求 100%——100% 的覆盖率不代表没有 bug。

### Mock 与接口测试

```go
// 定义接口，方便 mock
type UserRepository interface {
    GetByID(id int64) (*User, error)
    Save(user *User) error
}

// 真实实现
type dbUserRepo struct {
    db *sql.DB
}

// Mock 实现（测试用）
type mockUserRepo struct {
    users map[int64]*User
}

func (m *mockUserRepo) GetByID(id int64) (*User, error) {
    if user, ok := m.users[id]; ok {
        return user, nil
    }
    return nil, ErrNotFound
}

func (m *mockUserRepo) Save(user *User) error {
    m.users[user.ID] = user
    return nil
}

// 测试业务逻辑
func TestUserService_GetProfile(t *testing.T) {
    mock := &mockUserRepo{
        users: map[int64]*User{
            1: {ID: 1, Name: "Alice"},
        },
    }
    svc := NewUserService(mock)

    user, err := svc.GetProfile(1)
    if err != nil {
        t.Fatal(err)
    }
    if user.Name != "Alice" {
        t.Errorf("want Alice, got %s", user.Name)
    }
}
```

### 基准测试（Benchmark）

```go
func BenchmarkSum(b *testing.B) {
    nums := make([]int, 1000)
    for i := range nums {
        nums[i] = i
    }

    b.ResetTimer() // 忽略初始化时间

    for i := 0; i < b.N; i++ {
        Sum(nums)
    }
}

// 跳过某些分配
func BenchmarkWithAllocs(b *testing.B) {
    b.ReportAllocs() // 报告内存分配次数
    // ...
}
```

```bash
go test -bench=. -benchmem ./...
# 输出：
# BenchmarkSum-8    1000000    1024 ns/op    0 B/op    0 allocs/op
```

**关键指标：** `ns/op`（每次操作耗时）、`B/op`（每次分配字节数）、`allocs/op`（每次分配次数）。减少分配次数通常比减少分配大小更重要。

### Fuzzing（模糊测试，Go 1.18+）

```go
func FuzzReverse(f *testing.F) {
    // 种子语料
    f.Add("hello")
    f.Add("世界")

    f.Fuzz(func(t *testing.T, s string) {
        reversed := Reverse(s)
        doubleReversed := Reverse(reversed)
        if s != doubleReversed {
            t.Errorf("两次反转后不相等: %q -> %q -> %q", s, reversed, doubleReversed)
        }
    })
}
```

```bash
go test -fuzz=. -fuzztime=10s
```

---

## 错误处理进阶

Go 1.13 引入了 errors 包的新功能，让错误处理更灵活。

### 错误包装（%w）

```go
import (
    "errors"
    "fmt"
)

// 用 %w 创建包装错误
func ReadConfig(path string) (Config, error) {
    data, err := os.ReadFile(path)
    if err != nil {
        return Config{}, fmt.Errorf("读取配置文件 %s 失败: %w", path, err)
    }

    cfg, err := parseConfig(data)
    if err != nil {
        return Config{}, fmt.Errorf("解析配置失败: %w", err)
    }

    return cfg, nil
}
```

### errors.Is：检查错误链

```go
var ErrNotFound = errors.New("item not found")
var ErrPermission = errors.New("permission denied")

func GetItem(id int) (Item, error) {
    return Item{}, ErrNotFound
}

// 调用方
item, err := GetItem(42)
if errors.Is(err, ErrNotFound) {
    fmt.Println("没找到，显示空状态")
} else if errors.Is(err, ErrPermission) {
    fmt.Println("无权限")
} else if err != nil {
    fmt.Println("其他错误:", err)
}
```

`errors.Is` 会沿错误链（通过 `%w` 包装的链）逐层检查，直到找到匹配的错误或链结束。

### errors.As：获取错误链中的特定类型

```go
type HTTPError struct {
    StatusCode int
    Message    string
}

func (e *HTTPError) Error() string {
    return fmt.Sprintf("HTTP %d: %s", e.StatusCode, e.Message)
}

func fetchURL(url string) error {
    return &HTTPError{StatusCode: 404, Message: "Not Found"}
}

// 调用方
err := fetchURL("/api/users")
var httpErr *HTTPError
if errors.As(err, &httpErr) {
    fmt.Printf("HTTP 错误 %d: %s\n", httpErr.StatusCode, httpErr.Message)
    // 可以根据状态码做不同处理
    if httpErr.StatusCode == 404 {
        // 处理 404
    }
}
```

### Sentinel Errors + 自定义行为

```go
// 带行为的 sentinel error
type ValidationError struct {
    Field string
    Rule  string
    Value any
}

func (e *ValidationError) Error() string {
    return fmt.Sprintf("字段 %s 验证失败[%s]: %v", e.Field, e.Rule, e.Value)
}

// 实现 Is 方法，让 errors.Is 可以匹配
func (e *ValidationError) Is(target error) bool {
    t, ok := target.(*ValidationError)
    if !ok {
        return false
    }
    return e.Field == t.Field && e.Rule == t.Rule
}

// 使用
var ErrRequired = &ValidationError{Rule: "required"}

func ValidateUser(u User) error {
    if u.Name == "" {
        return &ValidationError{Field: "Name", Rule: "required"}
    }
    return nil
}

err := ValidateUser(User{})
if errors.Is(err, ErrRequired) {
    fmt.Println("必填字段缺失")
}
```

### 最佳实践

```go
// ✅ 好：用 %w 保留错误链
return fmt.Errorf("查询用户失败: %w", err)

// ❌ 不好：丢失原始错误信息
return fmt.Errorf("查询用户失败: %v", err)

// ❌ 不好：吞掉错误
return errors.New("内部错误")

// ✅ 好：包装时加额外上下文
return fmt.Errorf("查询用户 #%d 失败: %w", userID, err)
```

**原则：** 在中间层包装错误时加上下文，在顶层（HTTP handler、CLI main）统一处理/打印。

---

## 优雅关闭（Graceful Shutdown）

生产级的 HTTP 服务必须支持优雅关闭：

```go
package main

import (
    "context"
    "fmt"
    "log"
    "net/http"
    "os"
    "os/signal"
    "syscall"
    "time"
)

func main() {
    mux := http.NewServeMux()
    mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
        // 模拟长时间处理
        time.Sleep(2 * time.Second)
        fmt.Fprintln(w, "完成")
    })

    srv := &http.Server{
        Addr:    ":8080",
        Handler: mux,
    }

    // 在独立 goroutine 中启动
    go func() {
        fmt.Println("Server starting on :8080")
        if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
            log.Fatalf("启动失败: %v", err)
        }
    }()

    // 等待退出信号
    quit := make(chan os.Signal, 1)
    signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
    <-quit
    fmt.Println("\n收到退出信号，开始优雅关闭...")

    // 给正在处理的请求最多 10 秒完成
    ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
    defer cancel()

    if err := srv.Shutdown(ctx); err != nil {
        log.Fatalf("强制关闭: %v", err)
    }

    fmt.Println("服务已安全关闭")
}
```

```go
// 带数据库连接的版本
type Server struct {
    httpServer *http.Server
    db         *sql.DB
    cache      *redis.Client
}

func (s *Server) Shutdown(ctx context.Context) error {
    // 1. 先停止接收新请求
    if err := s.httpServer.Shutdown(ctx); err != nil {
        return fmt.Errorf("HTTP 服务关闭失败: %w", err)
    }

    // 2. 关闭数据库连接
    if err := s.db.Close(); err != nil {
        return fmt.Errorf("数据库关闭失败: %w", err)
    }

    // 3. 关闭缓存连接
    if err := s.cache.Close(); err != nil {
        return fmt.Errorf("缓存关闭失败: %w", err)
    }

    return nil
}
```

---

## HTTP 中间件模式

Go 的 `net/http` 通过 `http.Handler` 接口天然支持中间件：

```go
// 中间件是一个接收 Handler 返回 Handler 的函数
type Middleware func(http.Handler) http.Handler

// 日志中间件
func Logger(next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        start := time.Now()
        next.ServeHTTP(w, r)
        fmt.Printf("[%s] %s %s (%v)\n",
            r.Method, r.URL.Path, r.RemoteAddr, time.Since(start))
    })
}

// 恢复（panic 保护）中间件
func Recovery(next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        defer func() {
            if err := recover(); err != nil {
                log.Printf("panic recovered: %v", err)
                http.Error(w, "Internal Server Error", http.StatusInternalServerError)
            }
        }()
        next.ServeHTTP(w, r)
    })
}

// CORS 中间件
func CORS(next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        w.Header().Set("Access-Control-Allow-Origin", "*")
        w.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE")
        w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization")

        if r.Method == http.MethodOptions {
            w.WriteHeader(http.StatusNoContent)
            return
        }

        next.ServeHTTP(w, r)
    })
}

// 链式组合
func Chain(h http.Handler, middlewares ...Middleware) http.Handler {
    for i := len(middlewares) - 1; i >= 0; i-- {
        h = middlewares[i](h)
    }
    return h
}

// 使用
mux := http.NewServeMux()
mux.HandleFunc("/api/users", handleUsers)

handler := Chain(mux, Logger, Recovery, CORS)
http.ListenAndServe(":8080", handler)
```

### 带状态的中间件（认证）

```go
// 中间件可以往 context 写数据
type contextKey string

const UserIDKey contextKey = "user_id"

func Auth(next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        token := r.Header.Get("Authorization")
        if token == "" {
            http.Error(w, "Unauthorized", http.StatusUnauthorized)
            return
        }

        userID, err := validateToken(token)
        if err != nil {
            http.Error(w, "Invalid token", http.StatusUnauthorized)
            return
        }

        // 把用户 ID 写入 context
        ctx := context.WithValue(r.Context(), UserIDKey, userID)
        next.ServeHTTP(w, r.WithContext(ctx))
    })
}

// 在 handler 中获取
func handleProfile(w http.ResponseWriter, r *http.Request) {
    userID := r.Context().Value(UserIDKey).(string)
    // 使用 userID...
}
```

---

## pprof 性能分析

Go 内置了 `pprof` 性能分析工具：

```go
import (
    "net/http"
    _ "net/http/pprof"  // 通过 import 注册 pprof 路由
)

func main() {
    // pprof 路由注册在 /debug/pprof/ 下
    go func() {
        log.Println(http.ListenAndServe(":6060", nil))
    }()

    // 业务服务正常启动
    http.ListenAndServe(":8080", mux)
}
```

### 常用分析命令

```bash
# CPU 分析（采样 30 秒）
go tool pprof http://localhost:6060/debug/pprof/profile?seconds=30

# 堆内存分析（当前）
go tool pprof http://localhost:6060/debug/pprof/heap

# goroutine 分析
go tool pprof http://localhost:6060/debug/pprof/goroutine

# 查看所有 goroutine 堆栈
wget http://localhost:6060/debug/pprof/goroutine?debug=2 -O goroutines.txt
```

### 交互式分析

```bash
# 进入 pprof 交互模式
go tool pprof -http=:8081 ~/pprof/pprof.samples.cpu.001.pb.gz

# 常用交互命令（终端模式）
top10     # 查看最耗时的 10 个函数
list funcName  # 查看具体函数的耗时分布
web       # 生成调用图
traces    # 查看调用栈
```

### 代码级 CPU 分析

```go
func expensiveFunction() {
    // 用 runtime/pprof 做自定义分析
    f, _ := os.Create("cpu.prof")
    pprof.StartCPUProfile(f)
    defer pprof.StopCPUProfile()

    // 你的业务代码...
}
```

### 内存分析

```go
// 在代码中触发堆转储
f, _ := os.Create("heap.prof")
pprof.WriteHeapProfile(f)
f.Close()
```

### 常见性能问题

| 问题 | 现象 | 分析方式 |
|------|------|----------|
| goroutine 泄漏 | 内存持续增长 | `pprof goroutine` 查看数量 |
| 内存分配过多 | GC 频繁、STW 时间长 | `pprof heap` + `go test -benchmem` |
| CPU 热点 | QPS 上不去 | `pprof profile` 看 top |
| 锁竞争 | 并发吞吐上不去 | `pprof mutex`（需要先开启） |
| 阻塞操作 | 延迟高 | `pprof block`（需要先开启） |

```go
// 开启 mutex 和 block 分析
import "runtime"

func init() {
    runtime.SetMutexProfileFraction(1) // 记录所有 mutex 事件
    runtime.SetBlockProfileRate(1)      // 记录所有阻塞事件
}
```

---

## Go Modules 进阶

### replace 指令

当你需要替换依赖（比如修复 bug、本地调试）时用 `replace`：

```go
// go.mod
module my-api

go 1.22

require (
    github.com/gin-gonic/gin v1.9.1
)

// 替换为本地路径（开发用）
replace github.com/gin-gonic/gin => ../local-gin

// 或替换为 fork
replace github.com/gin-gonic/gin => github.com/yourname/gin v1.9.1-fixed
```

**注意：** `replace` 不会提交到上游——CI 环境要确保路径或版本可访问。

### Go Workspace（多模块开发，Go 1.18+）

当你在本地同时开发多个模块时，workspace 比 `replace` 更优雅：

```bash
# 项目结构
my-project/
├── go.work         # workspace 文件
├── service-a/
│   └── go.mod
├── service-b/
│   └── go.mod
└── shared-lib/
    └── go.mod
```

```go
// go.work
go 1.22

// 把本地的模块加入 workspace
use (
    ./service-a
    ./service-b
    ./shared-lib
)

// 仍然可以使用 replace
replace example.com/old => ./new
```

```bash
# 初始化 workspace
go work init ./service-a ./shared-lib

# 添加更多模块
go work use ./service-b

# 查看当前 workspace
go work sync
```

### Build Tags（条件编译）

```go
// 文件：dev.go
//go:build dev

package main

func init() {
    log.Println("开发模式：开启调试日志")
}
```

```go
// 文件：prod.go
//go:build !dev

package main

func init() {
    log.Println("生产模式：关闭调试日志")
}
```

```bash
# 开发模式运行
go run -tags dev main.go

# 默认生产模式
go build -o app
```

**常见用途：** 条件包含 mock 实现、平台特定代码（`//go:build linux`）、特性开关。

### ldflags（编译时注入变量）

```go
var (
    Version   = "unknown"
    CommitSHA = "unknown"
    BuildTime = "unknown"
)
```

```bash
go build -ldflags="\
    -X main.Version=v1.2.3 \
    -X main.CommitSHA=$(git rev-parse HEAD) \
    -X main.BuildTime=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    -o my-app
```

```go
// 运行时可以打印版本信息
func main() {
    fmt.Printf("Version: %s\nCommit: %s\nBuild: %s\n",
        Version, CommitSHA, BuildTime)
}
```

---

## 面试怎么说

> Go 的测试文化很特别——标准库的 testing 包就够用，社区的主流风格是 table-driven tests。我经常用 `t.Run` 做子测试分组，配合 `go test -run` 可以精确定位失败的 case。错误处理方面，我习惯用 `fmt.Errorf` 的 `%w` 包装每一层错误，上层用 `errors.Is` 和 `errors.As` 判断错误类型，不丢失调用链。优雅关闭是生产服务的基本功——监听 SIGINT/SIGTERM，给正在处理的请求一个宽限期，再关闭 DB 连接和缓存。pprof 是排查 Go 服务性能问题的利器——内存泄漏看 heap，CPU 问题看 profile，goroutine 泄漏看 goroutine 的数量和状态。Go 1.18 的 workspace 让多模块本地开发不再需要写一堆 replace 指令，我现在的项目都改成 workspace 了。
