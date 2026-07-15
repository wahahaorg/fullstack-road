# EventEmitter、Buffer 与 Stream

> Node 处理数据的三大基础抽象，从事件到字节再到流。

## EventEmitter

Node 很多核心模块都建立在事件驱动模型上，`EventEmitter` 是这个模型的基础设施。

```js
import { EventEmitter } from 'events'

const emitter = new EventEmitter()

// 注册监听器
emitter.on('data', (chunk) => {
  console.log('收到数据:', chunk)
})

// 只监听一次
emitter.once('connect', () => {
  console.log('已连接')
})

// 触发事件
emitter.emit('data', { id: 1, value: 'hello' })

// 移除监听器（防止内存泄漏）
const handler = () => {}
emitter.on('event', handler)
emitter.off('event', handler)  // 或 emitter.removeListener('event', handler)
```

**非常重要：`emit()` 触发时，监听器是同步调用的。**

```js
emitter.on('task', () => {
  // 这里的重 CPU 计算会直接拖慢当前流程
  heavyCompute()
})
emitter.emit('task')  // 同步执行监听器
```

> "事件产生是异步的"不等于"监听器执行是异步的"。很多人误以为 EventEmitter 天然是异步的。

**内存泄漏警告：**

```js
// Node 默认一个事件超过 10 个监听器会警告
emitter.setMaxListeners(20)  // 如果确实需要更多监听器
```

---

## Buffer

`Buffer` 用来表示一段二进制数据，本质上是字节序列。继承自 `Uint8Array`。

**为什么服务端必须理解 Buffer：**
- 网络传输的数据底层都是字节
- 文件不是天然字符串
- 不同编码之间要明确转换
- 大文件、流式处理、协议解析都离不开 Buffer

```js
// 创建 Buffer
const buf1 = Buffer.from('Hello, 世界', 'utf-8')
const buf2 = Buffer.alloc(10)          // 10 字节，填充 0
const buf3 = Buffer.allocUnsafe(10)    // 10 字节，不初始化（更快，但需注意旧数据）

// 转换
buf1.toString('utf-8')      // 'Hello, 世界'
buf1.toString('base64')     // base64 编码
buf1.toString('hex')        // 十六进制字符串

// 拼接
const merged = Buffer.concat([buf1, buf2])

// 读写
buf2.writeUInt32BE(123456, 0)  // 写 4 字节无符号整数（大端序）
buf2.readUInt32BE(0)            // 读回
```

**常见误区：**

```js
// ❌ 错误：把 Buffer 当字符串直接用
console.log(buf1)      // <Buffer 48 65 6c 6c 6f ...>

// ✅ 正确：先解码
console.log(buf1.toString())  // 'Hello, 世界'
```

---

## Stream（流）

Stream 是 Node 处理流式数据的抽象，适合大文件、网络传输、压缩解压、视频、日志、代理转发。

**四类流：**

| 类型 | 说明 | 例子 |
|---|---|---|
| `Readable` | 可读流 | `fs.createReadStream`、HTTP 请求体 |
| `Writable` | 可写流 | `fs.createWriteStream`、HTTP 响应 |
| `Duplex` | 可读可写 | TCP Socket |
| `Transform` | 转换流（Duplex 的特殊形式） | `zlib.createGzip()` |

**为什么 Stream 比一次性读取更重要：**

```js
// ❌ 读超大文件：可能撑爆内存
const data = fs.readFileSync('huge-file.json')  // 全部读入内存

// ✅ 流式读取：边读边处理，内存可控
const readable = fs.createReadStream('huge-file.json')
readable.on('data', (chunk) => process(chunk))
```

---

## 背压（Backpressure）

背压就是：**上游生产数据太快，下游消费不过来**，中间缓冲区越堆越多。

**常见场景：**
- 大文件读取 → 网络发送（读很快，写比较慢）
- 数据库导出 → HTTP 下载
- 上传流 → 压缩流 → 落盘

**为什么背压重要：**
没有流控，内存会不断上涨，严重时会把进程拖垮。

**手动处理背压（了解原理）：**

```js
const readable = fs.createReadStream('large.txt')
const writable = fs.createWriteStream('output.txt')

readable.on('data', (chunk) => {
  const canContinue = writable.write(chunk)
  if (!canContinue) {
    readable.pause()           // 下游满了，暂停上游
    writable.once('drain', () => {
      readable.resume()        // 下游排空了，恢复上游
    })
  }
})
```

---

## pipeline()

推荐用 `stream.pipeline()` 而不是手搓多个 `pipe()`。

**为什么 `a.pipe(b).pipe(c)` 不够：**
一旦中间某个流出错，错误与关闭逻辑容易遗漏，最终造成句柄泄漏、连接不释放、响应挂住。

```js
import { pipeline } from 'stream/promises'
import { createReadStream, createWriteStream } from 'fs'
import { createGzip } from 'zlib'

// ✅ pipeline 会自动处理：错误传递、资源关闭、流结束
await pipeline(
  createReadStream('input.txt'),
  createGzip(),
  createWriteStream('output.txt.gz')
)
console.log('压缩完成')
```

**`pipeline()` vs `pipe()`：**

| 对比 | `pipe()` | `pipeline()` |
|---|---|---|
| 错误处理 | 需手动处理每个流 | 自动传递 |
| 资源清理 | 容易遗漏 | 自动关闭 |
| Promise | ❌ | ✅（`stream/promises`） |
| 生产推荐 | 不推荐 | ✅ 推荐 |

> Demo 里直接 `pipe()` 很常见，但线上链路更推荐 `pipeline()`，因为它更强调整条流管道的生命周期管理。

---

## 自定义 Transform 流

```js
import { Transform } from 'stream'

class UpperCaseTransform extends Transform {
  _transform(chunk, encoding, callback) {
    const upper = chunk.toString().toUpperCase()
    this.push(upper)   // 推给下游
    callback()         // 告知上游可以继续发
  }
}

await pipeline(
  createReadStream('input.txt'),
  new UpperCaseTransform(),
  createWriteStream('output.txt')
)
```
