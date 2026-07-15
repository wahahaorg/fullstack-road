# Node.js HTTP 与文件操作

> 从文件 I/O 到 HTTP 服务，理解 Node 作为 BFF / 网关层的优势。

## fs.readFile vs createReadStream

根据数据规模和处理方式选择：

### 用 `readFile()` 的场景

```js
import { readFile } from 'fs/promises'

// 文件小、一次性读取配置/模板/小文本
const config = JSON.parse(await readFile('config.json', 'utf-8'))
const template = await readFile('template.html', 'utf-8')
```

### 用 `createReadStream()` 的场景

```js
import { createReadStream } from 'fs'
import { pipeline } from 'stream/promises'
import { createGzip } from 'zlib'

// 大文件、要边读边传、要和压缩/网络/加密流串起来
await pipeline(
  createReadStream('large-video.mp4'),
  createGzip(),
  response          // HTTP 响应流
)
```

**权衡：**

| 对比 | `readFile` | `createReadStream` |
|---|---|---|
| 开发便利性 | ✅ 简单 | 稍复杂 |
| 内存占用 | 文件大小 | 固定缓冲区（KB 级） |
| 适合文件大小 | 小（< 几十 MB） | 任意大小 |
| 适合长期运行服务 | 不推荐大文件 | ✅ 推荐 |

---

## HTTP 服务的本质

```js
import http from 'http'

const server = http.createServer((req, res) => {
  // req 是 IncomingMessage（Readable 流）
  // res 是 ServerResponse（Writable 流）

  console.log(req.method, req.url)

  // 读取请求体（流式）
  let body = ''
  req.on('data', chunk => { body += chunk })
  req.on('end', () => {
    const data = JSON.parse(body)

    res.writeHead(200, { 'Content-Type': 'application/json' })
    res.end(JSON.stringify({ received: data }))
  })
})

server.listen(3000, () => console.log('Server running on :3000'))
```

**理解要点：**
- 请求本质是字节流，不是天然 JSON
- 请求头、方法、URL、body 都要分别处理
- 响应必须显式结束（`res.end()`）
- 请求体很大时，应该按流处理，而不是默认一次性拼到内存

> 把 HTTP 理解成"协议 + 流 + 连接管理"，而不是"框架帮我拿个 req/res"。

---

## 为什么 Node 适合做 BFF / 网关 / 中间层

这些场景通常不是超重 CPU，而是：
- 聚合多个接口
- 协议转换（REST → gRPC、GraphQL → REST）
- 转发请求
- 拼装/裁剪数据
- 控制缓存
- 管理登录态和鉴权

这些都偏 **I/O 密集、编排型逻辑**，正好符合 Node 的优势。

```js
// BFF 典型模式：并发聚合多个下游接口
async function getProductDetail(id) {
  const [product, reviews, inventory] = await Promise.all([
    productService.getById(id),
    reviewService.getByProductId(id),
    inventoryService.getStock(id),
  ])

  return {
    ...product,
    reviews: reviews.slice(0, 5),
    inStock: inventory.quantity > 0,
  }
}
```

> Node 适合做"离用户近、离 I/O 近、离前端协议近"的一层，尤其适合前端团队向服务端延伸时做 BFF。

---

## 流式处理：上传、代理、下载

```js
// 文件上传：流式落盘（不缓存到内存）
app.post('/upload', (req, res) => {
  const dest = fs.createWriteStream('./uploads/file.bin')
  pipeline(req, dest)
    .then(() => res.json({ ok: true }))
    .catch(err => res.status(500).json({ error: err.message }))
})

// 代理转发：不缓存，直接透传
app.get('/proxy/:path', async (req, res) => {
  const upstream = await fetch(`https://api.upstream.com/${req.params.path}`)
  upstream.body.pipe(res)
})

// 大文件下载：带 Range 支持
app.get('/download/:file', (req, res) => {
  const filePath = path.join('./files', req.params.file)
  const stat = fs.statSync(filePath)

  const range = req.headers.range
  if (range) {
    const [start, end] = range.replace('bytes=', '').split('-').map(Number)
    const chunk = end - start + 1
    res.writeHead(206, {
      'Content-Range': `bytes ${start}-${end}/${stat.size}`,
      'Content-Length': chunk,
      'Content-Type': 'application/octet-stream',
    })
    fs.createReadStream(filePath, { start, end }).pipe(res)
  } else {
    res.writeHead(200, { 'Content-Length': stat.size })
    fs.createReadStream(filePath).pipe(res)
  }
})
```

**为什么大数据量场景流式处理几乎是必选项：**

如果总想"先全部收齐，再一次性处理"，很容易带来：
- 内存暴涨
- 首字节延迟变长
- 错误恢复差
- 进程不稳定

网络和磁盘本来就是分段到达、分段写入的，流式处理更符合底层设备的工作方式。

---

## path 模块常用 API

```js
import path from 'path'

path.join('/usr', 'local', 'bin')    // '/usr/local/bin'
path.resolve('./config.json')        // 绝对路径
path.basename('/home/user/file.txt') // 'file.txt'
path.extname('index.html')           // '.html'
path.dirname('/home/user/file.txt')  // '/home/user'

// 解构路径
path.parse('/home/user/file.txt')
// { root: '/', dir: '/home/user', base: 'file.txt', ext: '.txt', name: 'file' }
```

---

## 优雅退出

```js
// HTTP server + 数据库连接的优雅退出
async function shutdown(signal) {
  console.log(`收到 ${signal}，开始优雅退出...`)

  server.close(async () => {
    console.log('HTTP 服务已停止接受新请求')
    await db.pool.end()
    console.log('数据库连接已关闭')
    process.exit(0)
  })

  // 强制超时退出
  setTimeout(() => {
    console.error('优雅退出超时，强制退出')
    process.exit(1)
  }, 10_000)
}

process.on('SIGTERM', () => shutdown('SIGTERM'))
process.on('SIGINT', () => shutdown('SIGINT'))
```
