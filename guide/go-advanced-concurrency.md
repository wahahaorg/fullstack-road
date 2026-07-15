# Go 进阶：并发模式与工程实践

> Context 传递链路、sync 包同步原语、select 调度模式、Worker Pool、并发陷阱——用好 goroutine 只是开始。

## Context 包

`context.Context` 是 Go 并发编程的核心接口，用于传递**取消信号**、**超时控制**和**请求级元数据**。几乎所有的 Go Web 框架和数据库驱动都依赖它。

### 基本用法

```go
import "context"

type Context interface {
    Deadline() (deadline time.Time, ok bool)
    Done() <-chan struct{}  // 返回一个只读 channel，取消时关闭
    Err() error             // context 取消的原因
    Value(key any) any      // 获取绑定的值
}
```

### 创建 Context

```go
// 根 Context——通常在 main 函数或请求入口创建
ctx := context.Background()

// TODO——当你还不确定用什么 context 时暂时替代
ctx := context.TODO()
```

### 派生 Context

```go
// 手动取消
ctx, cancel := context.WithCancel(context.Background())

// 启动一个 goroutine
go func() {
    for {
        select {
        case <-ctx.Done():
            fmt.Println("收到取消信号，清理退出")
            return
        default:
            // 继续工作
        }
    }
}()

// 在某个条件触发时取消
cancel()
```

```go
// 超时控制（自动取消）
ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
defer cancel()  // 重要！防止资源泄漏

// 也可以指定 deadline
// ctx, cancel := context.WithDeadline(context.Background(), time.Now().Add(3*time.Second))
// defer cancel()
```

```go
// 传递值（推荐仅用于请求级追踪 ID、认证信息等）
ctx := context.WithValue(context.Background(), "request_id", "req-123")

// 获取值
rid := ctx.Value("request_id")
```

### 为什么几乎每个函数第一个参数都是 ctx

```go
// 典型的 Go 函数签名
func QueryDatabase(ctx context.Context, query string) (Result, error) {
    // 检查是否被取消
    if err := ctx.Err(); err != nil {
        return Result{}, err
    }

    // 执行查询（数据库驱动会自动监听 ctx.Done()）
    rows, err := db.QueryContext(ctx, query)
    if err != nil {
        return Result{}, err
    }
    defer rows.Close()
    // ...
}
```

**规则：** `ctx` 应该作为函数第一个参数传递，不要存在结构体里。

### 实际案例：三级超时链

```go
func handleRequest(ctx context.Context, req Request) (Response, error) {
    // 第一层：整体请求超时 5 秒
    ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
    defer cancel()

    // 第二步：调用下游服务 A（自身超时 2 秒）
    resultA, err := callServiceA(ctx, req)
    if err != nil {
        return Response{}, err
    }

    // 第三步：调用下游服务 B（自身超时 3 秒，但受父 context 约束）
    resultB, err := callServiceB(ctx, req, resultA)
    if err != nil {
        return Response{}, err
    }

    return buildResponse(resultA, resultB)
}

func callServiceA(ctx context.Context, req Request) (Result, error) {
    // 子超时：服务 A 最多等 2 秒
    ctx, cancel := context.WithTimeout(ctx, 2*time.Second)
    defer cancel()

    return doHTTPCall(ctx, "https://service-a/api", req)
}

func callServiceB(ctx context.Context, req Request, aResult Result) (Result, error) {
    // 子超时：服务 B 最多等 3 秒
    ctx, cancel := context.WithTimeout(ctx, 3*time.Second)
    defer cancel()

    return doHTTPCall(ctx, "https://service-b/api", req)
}
```

父 context 超时 5s，A 最多 2s，B 最多 3s。但如果父 context 在第 1 秒就被取消了，A 和 B 也会立即收到信号。

### Context 的三个原则

1. **永远不要将 `nil` 作为 context 传入**——不确定时用 `context.TODO()`
2. **`defer cancel()` 一定要调用**——否则 context 直到父 context 取消才释放
3. **不要用 context 传可选参数**——它只适合请求级元数据（trace ID、认证信息等）

---

## sync 包：并发同步原语

### WaitGroup：等待一组 goroutine 完成

```go
var wg sync.WaitGroup

for i := 0; i < 5; i++ {
    wg.Add(1)  // 计数器 +1
    go func(id int) {
        defer wg.Done()  // 计数器 -1
        fmt.Println("worker:", id)
    }(i)
}

wg.Wait()  // 等待所有 worker 完成
fmt.Println("全部完成")
```

**常见错误：**

```go
// ❌ 在 goroutine 内部调用 Add 可能导致 Wait 提前退出
go func() {
    wg.Add(1)  // 如果还没执行到这里 Wait 就开始了
    defer wg.Done()
}()

// ✅ 在启动 goroutine 前就 Add
wg.Add(1)
go func() {
    defer wg.Done()
}()
```

### Mutex / RWMutex：保护共享数据

```go
type Counter struct {
    mu    sync.Mutex
    value int
}

func (c *Counter) Increment() {
    c.mu.Lock()
    defer c.mu.Unlock()
    c.value++
}

func (c *Counter) Value() int {
    c.mu.Lock()
    defer c.mu.Unlock()
    return c.value
}
```

**读写锁（RWMutex）：** 读多写少场景优化

```go
type Cache struct {
    mu    sync.RWMutex
    data  map[string]string
}

func (c *Cache) Get(key string) (string, bool) {
    c.mu.RLock()        // 读锁：多个 goroutine 可以同时读
    defer c.mu.RUnlock()
    v, ok := c.data[key]
    return v, ok
}

func (c *Cache) Set(key, value string) {
    c.mu.Lock()         // 写锁：独占
    defer c.mu.Unlock()
    c.data[key] = value
}
```

**对比：**
- `Mutex`：任意时刻只有一个 goroutine 能访问
- `RWMutex`：读锁可以共享，写锁独占。写锁等待时，新读锁也会被阻塞（防止写饥饿）

### Once：只执行一次

```go
var once sync.Once
var config *Config

func GetConfig() *Config {
    once.Do(func() {
        fmt.Println("初始化配置...")
        config = loadConfig()
    })
    return config
}

// 无论调用多少次，初始化函数只执行一次
GetConfig()  // 初始化配置...
GetConfig()  // (不输出)
GetConfig()  // (不输出)
```

**典型场景：** 懒加载单例、只初始化一次的资源（连接池、缓存预热）。

### Pool：对象池复用

```go
var bufPool = sync.Pool{
    New: func() any {
        return new(bytes.Buffer)
    },
}

func processRequest(data []byte) string {
    buf := bufPool.Get().(*bytes.Buffer)
    buf.Reset()
    defer bufPool.Put(buf)

    buf.Write(data)
    // 处理...
    return buf.String()
}
```

**什么时候用 Pool：**
- 对象创建开销大（如 buffer、数据库连接）
- 对象会被频繁创建和销毁
- 对象是无状态的或可重置的

**注意：** Pool 中的对象可能被 GC 回收，不要假设 Get 一定返回之前 Put 的对象。

### Map：并发安全的 map

标准 map 并发读写会 panic。有三种选择：

```go
// 1. map + Mutex（最通用，性能好）
type SafeMap struct {
    mu   sync.Mutex
    data map[string]int
}

// 2. sync.Map（读多写少、不同 key 高并发场景优化）
var sm sync.Map
sm.Store("key", "value")
v, ok := sm.Load("key")
sm.Delete("key")

// Range 遍历（回调返回 false 停止）
sm.Range(func(key, value any) bool {
    fmt.Println(key, value)
    return true
})
```

**选择建议：**
- 常规场景：`map + Mutex`
- 读多写少 + key 集稳定：`sync.Map`
- 有明确的热点 key：`sync.Map`

---

## Select：多 channel 调度

`select` 是 Go 并发编程的调度核心，同时等待多个 channel：

### 基础模式

```go
select {
case msg := <-ch1:
    fmt.Println("ch1:", msg)
case msg := <-ch2:
    fmt.Println("ch2:", msg)
case <-time.After(1 * time.Second):
    fmt.Println("超时")
default:
    fmt.Println("没有 channel 准备好")
}
```

**关键行为：**
- 同时等待所有 case
- 多个 case 同时就绪时**随机选一个**执行
- 没有任何 case 就绪时执行 `default`（没有 default 则阻塞）

### 超时控制

```go
ch := make(chan Result)

go func() {
    ch <- fetchData()
}()

select {
case res := <-ch:
    fmt.Println("结果:", res)
case <-time.After(5 * time.Second):
    fmt.Println("请求超时")
}
```

### Fan-In：合并多个 channel

```go
func fanIn(chs ...<-chan int) <-chan int {
    out := make(chan int)
    var wg sync.WaitGroup

    for _, ch := range chs {
        wg.Add(1)
        go func(c <-chan int) {
            defer wg.Done()
            for v := range c {
                out <- v
            }
        }(ch)
    }

    go func() {
        wg.Wait()
        close(out)
    }()

    return out
}

// 使用
ch1 := produce(1, 100)
ch2 := produce(2, 100)
ch3 := produce(3, 100)

merged := fanIn(ch1, ch2, ch3)
for v := range merged {
    fmt.Println(v)  // 三个 channel 的结果交织输出
}
```

### Fan-Out：分发到多个 worker

```go
func fanOut(in <-chan int, workers int) []<-chan int {
    channels := make([]<-chan int, workers)

    for i := 0; i < workers; i++ {
        ch := make(chan int, 10)  // 带缓冲
        channels[i] = ch

        go func(out chan int, id int) {
            for v := range in {
                fmt.Printf("worker %d 处理: %d\n", id, v)
                out <- v * 2
            }
            close(out)
        }(ch, i)
    }

    return channels
}
```

### 退出信号

```go
func main() {
    quit := make(chan os.Signal, 1)
    signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)

    <-quit  // 阻塞直到收到信号
    fmt.Println("优雅退出...")
}
```

```go
// 结合 context 和 select 的退出模式
func runWorker(ctx context.Context) {
    for {
        select {
        case <-ctx.Done():
            fmt.Println("worker 退出:", ctx.Err())
            return
        default:
            // 正常工作
            work()
        }
    }
}
```

---

## Worker Pool 模式

Go 中实现 worker pool 非常简单，不需要第三方库：

```go
type Job struct {
    ID   int
    Data string
}

type Result struct {
    JobID int
    Output string
}

func worker(id int, jobs <-chan Job, results chan<- Result) {
    for job := range jobs {
        fmt.Printf("worker %d 开始任务 %d\n", id, job.ID)

        // 模拟处理
        time.Sleep(time.Second)
        result := Result{
            JobID:  job.ID,
            Output: fmt.Sprintf("处理完成: %s", job.Data),
        }

        results <- result
    }
}

func main() {
    const numJobs = 10
    const numWorkers = 3

    jobs := make(chan Job, numJobs)
    results := make(chan Result, numJobs)

    // 启动 workers
    for w := 1; w <= numWorkers; w++ {
        go worker(w, jobs, results)
    }

    // 发送任务
    for j := 1; j <= numJobs; j++ {
        jobs <- Job{ID: j, Data: fmt.Sprintf("data-%d", j)}
    }
    close(jobs)  // 通知 workers 没有更多任务了

    // 收集结果
    for r := 1; r <= numJobs; r++ {
        result := <-results
        fmt.Println(result.Output)
    }
}
```

**工作流程：**
1. 创建带缓冲的 jobs channel
2. 启动固定数量的 worker goroutine（每个从 jobs channel 读取）
3. 主 goroutine 发送任务
4. 发送完毕后 close(jobs)——workers 通过 range 自然退出
5. 从 results channel 收集结果

### 带取消的 Worker Pool

```go
func workerPool(ctx context.Context, numWorkers int, jobs []Job) []Result {
    jobCh := make(chan Job, len(jobs))
    resultCh := make(chan Result, len(jobs))

    // 启动 workers
    var wg sync.WaitGroup
    for i := 0; i < numWorkers; i++ {
        wg.Add(1)
        go func(id int) {
            defer wg.Done()
            for {
                select {
                case job, ok := <-jobCh:
                    if !ok {
                        return  // channel 关闭
                    }
                    // 处理每个任务时检查 context
                    if ctx.Err() != nil {
                        return
                    }
                    resultCh <- processJob(id, job)
                case <-ctx.Done():
                    return  // context 取消
                }
            }
        }(i)
    }

    // 发送任务
    for _, job := range jobs {
        jobCh <- job
    }
    close(jobCh)

    // 等待所有 worker 完成
    wg.Wait()
    close(resultCh)

    // 收集结果
    var results []Result
    for r := range resultCh {
        results = append(results, r)
    }
    return results
}
```

---

## Atomic 操作

当只需要对单个变量做加减或比较交换时，用 `sync/atomic` 比 Mutex 轻量得多：

```go
import "sync/atomic"

var counter atomic.Int64  // Go 1.19+ 类型化 atomic

// 无需加锁
counter.Add(1)
counter.Load()
counter.Store(100)
counter.Swap(200)
counter.CompareAndSwap(200, 300)  // CAS：当前=200 时设为 300

// 旧版本用法（Go < 1.19）
var oldCounter int64
atomic.AddInt64(&oldCounter, 1)
```

**适用场景：**
- 简单计数器（QPS 统计、请求计数）
- 状态标志（无锁开关）
- CompareAndSwap（无锁更新）

**不适用：** 多变量一致性、复杂数据结构——这时用 Mutex。

---

## 常见并发陷阱

### 1. Goroutine 泄漏

```go
// ❌ 泄漏：goroutine 永远阻塞在发送上
ch := make(chan int)
go func() {
    ch <- 42  // 没有人接收，永远阻塞
}()

// ✅ 修复：带缓冲 channel，或确保有接收方
ch := make(chan int, 1)
ch <- 42

// 或者保证接收
go func() {
    fmt.Println(<-ch)
}()
ch <- 42
```

```go
// ❌ 泄漏：select 没有 default 且一直阻塞
go func() {
    select {
    case <-someCh:
        // 如果 someCh 永远不发送数据，这个 goroutine 不会退出
    }
}()

// ✅ 修复：增加超时或退出机制
go func() {
    select {
    case <-someCh:
    case <-ctx.Done():
    case <-time.After(5 * time.Second):
    }
}()
```

### 2. 闭包捕获循环变量

```go
// ❌ 所有 goroutine 共享同一个 i
for i := 0; i < 5; i++ {
    go func() {
        fmt.Println(i)  // 可能全部打印 5
    }()
}

// ✅ 正确：传参复制
for i := 0; i < 5; i++ {
    go func(id int) {
        fmt.Println(id)
    }(i)
}

// ✅ Go 1.22+ 修复：循环变量每次迭代重新创建
// for i := 0; i < 5; i++ {  // 不需要传参了
//     go func() {
//         fmt.Println(i)
//     }()
// }
```

### 3. 往已关闭的 channel 发送数据

```go
ch := make(chan int)
close(ch)
ch <- 1  // panic: send on closed channel

// 正确做法：发送方负责关闭 channel，且只关闭一次
```

### 4. 并发读写 map

```go
// ❌ fatal error: concurrent map writes
m := make(map[string]int)
go func() { for { m["a"] = 1 } }()
go func() { for { m["b"] = 2 } }()

// ✅ 用 sync.Map 或 Mutex 保护
```

### 5. 竞态检测

Go 内置竞态检测器，测试时一定要开：

```bash
go test -race ./...
go run -race main.go
```

竞态检测器会在运行时检测数据竞争，发现时打印警告并终止。

### 6. 不懂得用 `-race`

```go
// 一个经典竞态例子
var counter int

func main() {
    for i := 0; i < 1000; i++ {
        go func() {
            counter++  // 非原子操作
        }()
    }
    time.Sleep(time.Second)
    fmt.Println(counter)  // 结果不确定，经常 < 1000
}
```

```bash
go run -race main.go
# 可以检测出 data race
```

---

## 面试怎么说

> Go 的并发模型基于 CSP（通信顺序进程）——不要通过共享内存来通信，而是通过通信来共享内存。实际工作中，我用 `context.WithTimeout` 做服务调用的超时控制，每一层都传递 context，这样上游取消时下游能立即感知。`sync.WaitGroup` 是等一批 goroutine 完成的标准做法，但要注意在启动 goroutine **之前** `Add`。Mutex 保护共享数据时，我会尽量缩小锁的粒度——只锁需要保护的几行代码，而不是锁整个函数。Worker Pool 模式在日常开发中很常见，用 channel 做任务队列，固定数量 goroutine 消费，既控制了并发度又不会资源耗尽。最后也是最重要的：生产代码一定要开 `-race` 检测，很多诡异的线上问题都是 data race 导致的。
