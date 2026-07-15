# Node.js 异步编程与错误处理

> 从 callback 到 async/await，以及生产环境的错误边界设计。

## error-first callback（历史背景）

Node 早期大量使用的模式：

```js
fs.readFile('a.txt', (err, data) => {
  if (err) return handleError(err)
  console.log(data)
})
```

**为什么这样设计：**
- 异步结果统一出口
- 错误和成功路径都明确
- 避免同步 `try/catch` 误以为能接住异步错误（在函数调用时，异步结果还没有回来）

**今天怎么看它：**
- 容易回调嵌套（callback hell）
- 现代项目更常用 Promise / `async/await`
- 但理解这个历史包袱能帮你看懂大量老代码

---

## Promise

```js
// 创建
const p = new Promise((resolve, reject) => {
  setTimeout(() => resolve('done'), 1000)
})

// 消费
p.then(result => console.log(result))
 .catch(err => console.error(err))
 .finally(() => console.log('cleanup'))

// 并发
const [a, b] = await Promise.all([fetchA(), fetchB()])

// 竞速
const result = await Promise.race([fast(), slow()])

// 全部结果（不论成败）
const results = await Promise.allSettled([p1, p2, p3])
```

---

## async / await

让异步代码更像同步代码：

```js
async function getUser(id) {
  try {
    const user = await userRepo.findById(id)
    if (!user) throw new NotFoundError(id)
    return user
  } catch (err) {
    logger.error(err)
    throw err
  }
}
```

---

## async/await 常见误区

### 误区 1：串行化了本可并发的操作

```js
// ❌ 慢：串行，总耗时 = A + B
const a = await fetchA()
const b = await fetchB()

// ✅ 快：并发，总耗时 = max(A, B)
const [a, b] = await Promise.all([fetchA(), fetchB()])
```

### 误区 2：以为 try/catch 能兜住所有异步错误

```js
async function bad() {
  try {
    // 没有 await，Promise 被"丢弃"，catch 接不住
    someAsyncOp()
  } catch (err) {
    // 这里不会执行
  }
}
```

### 误区 3：await 不会阻塞

更准确地说：await **不会阻塞整个线程去等 I/O**，但当前函数的后续逻辑确实要等。若 `await` 的是 CPU 重活（如大量计算），主线程照样可能卡住。

### 误区 4：在循环里 await 导致串行

```js
// ❌ 每次都等上一次完成
for (const id of ids) {
  await processItem(id)
}

// ✅ 并发处理所有
await Promise.all(ids.map(id => processItem(id)))

// ✅ 限制并发数（用 p-limit 库）
import pLimit from 'p-limit'
const limit = pLimit(5)
await Promise.all(ids.map(id => limit(() => processItem(id))))
```

---

## unhandledRejection 与 uncaughtException

### unhandledRejection

Promise 被 reject，但在一个事件循环轮次内没有被处理：

```js
process.on('unhandledRejection', (reason, promise) => {
  logger.error('未处理的 Promise rejection:', reason)
  // 记录日志后通常应该退出进程
  process.exit(1)
})
```

### uncaughtException

同步异常一路冒泡，最终没人接住：

```js
process.on('uncaughtException', (err) => {
  logger.error('未捕获的异常:', err)
  // 清理资源，然后退出
  process.exit(1)
})
```

**关键原则：**

它们用于**记录日志、告警、兜底清理**，但**不应该**被当成"继续正常运行"的常规手段。

原因：一旦走到 `uncaughtException`，程序状态往往已经不可信了。

**更工程化的答法：**
- 局部错误在业务边界内处理
- 进程级错误做日志和资源清理
- 然后让进程退出，由 PM2 / K8s 等外部工具拉起

> 它们是最后一道警报，不是业务层异常处理主通道。

---

## process 对象常用 API

```js
// 读取环境变量
const env = process.env.NODE_ENV  // 'development' | 'production'

// 命令行参数（node script.js --port 3000）
const args = process.argv.slice(2)

// 当前工作目录
process.cwd()

// 设置退出码
process.exitCode = 1

// 监听进程信号（优雅退出）
process.on('SIGTERM', async () => {
  logger.info('收到 SIGTERM，开始优雅退出...')
  await server.close()
  await db.disconnect()
  process.exit(0)
})

// 监听 SIGINT（Ctrl+C）
process.on('SIGINT', () => {
  process.exit(0)
})
```

**注意事项：**

- 不要随手 `process.exit()`，尤其在服务端应用里，粗暴退出可能导致正在处理的请求、日志、连接来不及收尾
- 用 `process.env` 区分开发、测试、生产环境
- CLI 工具通过 `argv` 读取参数

---

## 错误分层处理

分层处理是生产级 Node 服务的必要设计：

```
参数层          → 输入校验错误，尽早返回 400
    ↓
业务层          → 可预期异常，返回明确业务码
    ↓
基础设施层      → 数据库/缓存/RPC 异常，做重试/熔断/降级
    ↓
进程层          → 兜底日志、告警、优雅退出
```

```js
// 示例：Express 风格的错误中间件
app.use((err, req, res, next) => {
  if (err instanceof ValidationError) {
    return res.status(400).json({ error: err.message })
  }
  if (err instanceof NotFoundError) {
    return res.status(404).json({ error: err.message })
  }
  // 未预期错误
  logger.error(err)
  res.status(500).json({ error: 'Internal Server Error' })
})
```

> 把所有错误都扔到最外层统一处理，短期看简单，长期看会丢语义，最终很难定位和恢复。
