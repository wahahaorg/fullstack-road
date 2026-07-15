# Node.js 综合场景与实战练习

> 面试加分项：把知识点连成场景，再动手做一遍比背答案强很多。

## 高频面试场景题

### 大文件上传服务

**至少要答到这几个点：**

1. **流式处理**：不要整文件读入内存
2. **背压控制**：上传速度和写盘速度不一致时要能兜住
3. **异常处理**：断连、超时、部分上传、清理临时文件
4. **安全性**：文件类型、大小、路径、恶意内容校验
5. **可扩展性**：分片上传、断点续传、对象存储对接

```js
import { pipeline } from 'stream/promises'
import { createWriteStream } from 'fs'
import { unlink } from 'fs/promises'
import path from 'path'

const MAX_SIZE = 100 * 1024 * 1024  // 100MB
const ALLOWED_TYPES = ['image/jpeg', 'image/png', 'application/pdf']

async function handleUpload(req, res) {
  const contentType = req.headers['content-type']
  const contentLength = parseInt(req.headers['content-length'], 10)

  // 安全校验
  if (!ALLOWED_TYPES.includes(contentType)) {
    return res.status(415).json({ error: '不支持的文件类型' })
  }
  if (contentLength > MAX_SIZE) {
    return res.status(413).json({ error: '文件太大' })
  }

  const tmpPath = path.join('/tmp', `upload-${Date.now()}.bin`)

  try {
    await pipeline(req, createWriteStream(tmpPath))
    // TODO: 移动到最终位置、记录数据库...
    res.json({ ok: true, path: tmpPath })
  } catch (err) {
    // 清理临时文件
    await unlink(tmpPath).catch(() => {})
    res.status(500).json({ error: '上传失败' })
  }
}
```

> 这类场景里 Node 的价值主要在接入、编排、流处理，不在于做复杂文件计算本身；如果要做重转码，可能要下沉到 worker 或独立服务。

---

### BFF 接口：并发聚合 + 超时控制

```js
async function withTimeout(promise, ms) {
  const timeout = new Promise((_, reject) =>
    setTimeout(() => reject(new Error(`Timeout after ${ms}ms`)), ms)
  )
  return Promise.race([promise, timeout])
}

async function getProductPage(productId) {
  const [product, reviews, inventory] = await Promise.allSettled([
    withTimeout(productService.getById(productId), 2000),
    withTimeout(reviewService.getByProductId(productId), 1500),
    withTimeout(inventoryService.getStock(productId), 1000),
  ])

  return {
    product: product.status === 'fulfilled' ? product.value : null,
    reviews: reviews.status === 'fulfilled' ? reviews.value : [],
    inStock: inventory.status === 'fulfilled' ? inventory.value.quantity > 0 : null,
  }
}
```

**要点：**
- `Promise.allSettled` 让某个下游超时不影响其他
- 每个下游有独立超时控制
- 返回降级数据而不是直接 500

---

### 接口变慢排查思路

```
第一步：分层定位
  ├── curl 直测接口 → 响应时间多少？
  ├── 有没有超时日志？
  ├── 是所有接口慢还是某个接口慢？
  └── 是固定慢还是偶发慢？

第二步：看主线程是否被阻塞
  ├── clinic.js doctor（可视化事件循环延迟）
  └── 看同步 API 使用情况（grep Sync）

第三步：看下游
  ├── 给所有下游调用加耗时日志
  ├── 看 SQL 执行计划（EXPLAIN ANALYZE）
  └── 看 RPC 耗时分布

第四步：看内存/GC
  ├── 进程内存监控（process.memoryUsage()）
  └── 触发 GC 暂停时接口会抖动

第五步：采集 profiling
  ├── node --prof + node --prof-process
  └── clinic.js flame（火焰图）
```

---

## 7 个动手练习

> 对应 `node-interview-code/` 目录下的实战项目

### 练习 1：静态文件服务器

```bash
cd node-interview-code/01-static-file-server
```

**目标：** 不借助框架，用 `http` + `fs` 实现：
- 根据 URL 读取文件并返回
- 正确设置 `Content-Type`
- 处理 404（文件不存在）
- 路径穿越防护

**核心知识点：** `http.createServer`、`path.resolve`、`fs.createReadStream`

---

### 练习 2：大文件下载对比

```bash
cd node-interview-code/02-download-compare
```

**目标：** 对比两种实现的内存占用差异：
- `readFile` 版本：一次性读入内存再发送
- Stream 版本：`createReadStream` 直接 pipe 到响应

**核心知识点：** 流式 vs 全量，`process.memoryUsage()` 对比

---

### 练习 3：pipeline + gzip 压缩

```bash
cd node-interview-code/03-pipeline-gzip
```

**目标：** 实现文件压缩下载接口：
- 读文件 → gzip 压缩 → HTTP 响应
- 使用 `stream.pipeline()`
- 处理中间环节失败的清理

**核心知识点：** `zlib.createGzip()`、`pipeline()`、错误传递

---

### 练习 4：BFF 超时控制

```bash
cd node-interview-code/04-bff-timeout
```

**目标：** 实现 BFF 聚合接口：
- 同时请求两个下游（模拟不同延迟）
- 每个下游独立超时控制
- 某个超时时返回降级数据

**核心知识点：** `Promise.race`、`Promise.allSettled`、降级策略

---

### 练习 5：事件循环阻塞演示

```bash
cd node-interview-code/05-event-loop-blocking
```

**目标：** 直观感受主线程阻塞的影响：
- 版本 A：同步大循环，期间其他请求无响应
- 版本 B：拆分到 `setImmediate`，保持响应
- 版本 C：移到 Worker Thread，完全不影响主线程

**核心知识点：** 事件循环阻塞、`worker_threads`、`setImmediate` 拆分

---

### 练习 6：CJS 与 ESM 互操作

```bash
cd node-interview-code/06-cjs-esm-interop
```

**目标：** 理解两种模块系统的边界：
- ESM import CJS 模块
- CJS 用 `import()` 加载 ESM 模块
- `package.json` 的 `type` 字段影响

**核心知识点：** 模块系统互操作、条件导出、动态 import

---

### 练习 7：优雅退出

```bash
cd node-interview-code/07-graceful-shutdown
```

**目标：** 实现 HTTP 服务的优雅退出：
- 收到 `SIGTERM` 停止接受新请求
- 等待已有请求处理完（最多 10 秒）
- 关闭数据库连接
- 强制超时退出兜底

**核心知识点：** `process.on('SIGTERM')`、`server.close()`、`keepAliveTimeout`

---

## 优先掌握的 10 个高频题

1. Node 是什么，适合什么场景
2. 事件循环和非阻塞 I/O
3. `process.nextTick` / Promise 微任务 / `setImmediate` / `setTimeout`
4. CommonJS 与 ESM 的区别
5. `package.json` 的 `type` 和 `exports`
6. `async/await` 的并发与错误边界
7. `unhandledRejection` / `uncaughtException`
8. `Buffer`、Stream、背压
9. 为什么不要阻塞事件循环
10. 大文件上传 / BFF / 网关类综合场景

> 如果这 10 个题你都能讲到"定义 + 原理 + 场景 + 坑点"，Node 基础面试基本就有内容可说了。
