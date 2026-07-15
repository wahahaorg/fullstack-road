# Node.js 性能与稳定性

> 为什么 Node 服务会变慢、内存会涨、怎么排查和预防。

## 不要阻塞事件循环

这不是一句口号，而是 Node 服务设计的根约束。

**后果：**
- 所有请求一起变慢
- timer 延迟
- I/O 回调迟迟执行不到
- 高并发下吞吐明显下降

**两类阻塞：**

```js
// 1. 超长同步逻辑
function bad(data) {
  // ❌ 复杂正则、大循环、超大 JSON 处理都会阻塞
  const result = JSON.parse(hugejson)         // 100MB 的 JSON
  const match = input.match(/^(a+)+$/)        // 回溯型正则（ReDoS）
}

// 2. 同步 API
fs.readFileSync('big.txt')    // ❌ 整个事件循环等这里
execSync('ffmpeg ...')        // ❌ 外部命令慢时，进程跟着卡住
```

> Node 最怕的不是"忙"，而是"主线程一直不让别人轮到"。

---

## 为什么同步 API 在线上服务里要慎用

```js
// ❌ 线上服务不要这样做
const config = fs.readFileSync('config.json')   // 遇到慢磁盘风险很大
const output = execSync('git log --oneline')     // 外部命令慢时卡死

// ✅ 异步版本
const config = await fs.promises.readFile('config.json')
const output = await execFileAsync('git', ['log', '--oneline'])
```

**同步 API 的合理使用场景：**
- CLI 脚本、小工具
- 启动阶段一次性配置读取（服务还没开始处理请求）
- `JSON.parse` 小对象

---

## 内存问题的常见来源

```js
// 1. 意外的全局引用
const cache = {}  // 全局 Map，只进不出

// 2. 缓存没有边界
class Cache {
  store = new Map()

  set(key, value) {
    this.store.set(key, value)  // ❌ 没有大小限制，没有 TTL
  }
}

// ✅ 加限制
import LRU from 'lru-cache'
const cache = new LRU({ max: 500, ttl: 1000 * 60 * 5 })

// 3. 事件监听器泄漏
function subscribe(emitter) {
  // ❌ 每次调用都叠加一个监听器，从不移除
  emitter.on('data', handleData)
}

// ✅ 用 once 或在合适时机 off
emitter.once('data', handleData)

// 4. 流/连接没正确关闭
// ❌
const stream = fs.createReadStream('file.txt')
// 忘记处理 'end'/'error' 事件，句柄一直开着

// ✅
stream.on('error', err => stream.destroy(err))
stream.on('end', () => stream.destroy())

// 5. 大对象长期滞留
// ❌
const allUsers = await db.query('SELECT * FROM users')  // 几十万条
```

**JS 有 GC，不代表不会泄漏。只要对象还可达，就不会被回收。**

---

## 如何排查接口变慢

有层次的排查思路才是加分项：

```
1. 先分层定位
   └── 是网络慢？下游慢？主线程卡？还是内存/GC 抖动？

2. 看事件循环是否被阻塞
   └── clinic.js doctor 工具可以可视化事件循环延迟

3. 看是否有慢 SQL / 慢 RPC / 慢文件 I/O
   └── 给下游调用加超时和日志

4. 看是否误用了同步 API
   └── grep 一下 Sync 后缀

5. 看是否有大对象序列化、超大 JSON、重 CPU 逻辑
   └── 对敏感路径加耗时日志

6. 看日志、metrics、heap/CPU 快照
   └── node --prof、clinic.js flame、heapdump
```

> 重点不是工具名背多少，而是"先判断瓶颈属于哪一层"的意识。

---

## 安全意识

### 常见服务端安全问题

| 风险类型 | 说明 |
|---|---|
| 输入校验不足 | 信任用户输入，直接用于查询/命令 |
| 命令注入 | 乱用 `exec()`，用户输入拼进命令字符串 |
| 路径穿越 | `../../../etc/passwd` 类攻击 |
| 原型污染 | `__proto__` 注入，影响全局对象 |
| 敏感信息泄露 | 堆栈信息、环境变量暴露给客户端 |
| npm 供应链风险 | 依赖包含恶意代码 |

### 为什么 `exec()` 比 `spawn()` 更危险

```js
// ❌ exec 通过 shell 执行，用户输入可能注入命令
const userInput = '; rm -rf /'
exec(`ls ${userInput}`)  // 灾难性！

// ✅ spawn/execFile 传参数数组，不经过 shell
import { execFile } from 'child_process'
execFile('ls', ['-la', userDir], callback)

// ✅ 对输入做严格白名单校验
const ALLOWED_DIRS = ['/data', '/public']
if (!ALLOWED_DIRS.includes(userInput)) {
  throw new Error('Invalid directory')
}
```

### 路径穿越防护

```js
import path from 'path'

function safeFilePath(base, userInput) {
  const resolved = path.resolve(base, userInput)
  if (!resolved.startsWith(base)) {
    throw new Error('路径穿越攻击')
  }
  return resolved
}
```

### 安全响应头（推荐 helmet）

```js
import helmet from 'helmet'
app.use(helmet())
// 自动设置：X-Frame-Options、X-Content-Type-Options、
//           Strict-Transport-Security 等安全头
```

---

## 前端转全栈最容易踩的坑

1. **只会写功能，不懂服务稳定性** — 超时、重试、限流、日志、错误边界全没想
2. **把 Node 当浏览器 JS 延伸** — 忽视流、进程、内存、I/O 模型
3. **过度依赖框架，忽略底层原理** — 遇到性能问题不知从哪下手
4. **CPU/内存意识不够** — 请求里做大循环、大 JSON 操作、同步文件

> 前端转全栈最大的提升，不是学会 Express/Nest，而是开始用"服务"的角度思考响应时间、并发、资源、故障和边界。
