# Node.js 运行时与底层模型

> 理解 Node 的本质，是所有 Node 面试题的基础。

## Node.js 是什么？

Node.js 不是一门语言，而是一个 **JavaScript 运行时**。它把 V8 引擎、libuv、以及核心模块（`fs`、`http`、`stream`、`events`）组合起来，让 JavaScript 能跑在服务端。

**Node 的核心优势：**

- 浏览器 JS 主要处理页面与交互；Node JS 主要处理文件、网络、进程、流
- Node 的强项不是"计算特别快"，而是 **I/O 密集型场景下的高并发处理能力**
- 真正让 Node 擅长高并发的，是 **事件循环 + 非阻塞 I/O + 合理的异步模型**

**常见误区：**

- ❌ "Node 就是单线程" → 更准确：**执行 JS 代码的主线程是单线程**，但 Node 运行时不止一个线程
- ❌ "Node 适合所有后端业务" → Node 更适合 I/O 密集场景；纯 CPU 密集型不一定占优

---

## 为什么单线程却能高并发？

Node 默认只有一个主线程执行 JavaScript，但很多 I/O 操作并不是主线程硬做完的。

**原理：**

- **JS 主线程**：执行同步代码、回调、Promise 后续逻辑
- **操作系统 / libuv**：负责监听网络、文件、定时器等异步事件
- **事件循环**：持续取出"已经准备好"的任务，交给 JS 主线程执行

本质是：**主线程尽量不阻塞；大量等待 I/O 的时间不浪费在"卡住线程"上**。

> Node 不是靠"同时算很多事"取胜，而是靠"自己少等、少阻塞、把等待交给系统"。

---

## 事件循环（Event Loop）

事件循环是 Node 的任务调度器，不断检查异步任务是否完成，按阶段把对应回调取出来执行。

**关键阶段（面试最常讲）：**

| 阶段 | 说明 |
|---|---|
| `timers` | `setTimeout` / `setInterval` 到期的回调 |
| `pending callbacks` | 上一轮延迟的 I/O 回调 |
| `poll` | 大多数 I/O 回调在这里执行 |
| `check` | `setImmediate` 的回调 |
| `close callbacks` | 关闭事件（如 socket 关闭） |

**重要理解：**

- 定时器不是"到了时间立刻执行"，而是"**最早可以在那个时间之后执行**"
- 如果前面有耗时同步代码，后面的 timer 一样会被拖延
- 背阶段顺序不等于理解事件循环；**真正重要的是：同步代码会阻塞后续调度**

---

## nextTick / Promise / setImmediate / setTimeout 优先级

它们都能"延后执行"，但优先级和队列不同：

```
当前同步代码
  ↓
process.nextTick() 队列全部清空
  ↓
Promise 微任务队列全部清空
  ↓
事件循环后续阶段（poll → check...）
  ↓
setImmediate() / setTimeout()
```

**要点：**

- `process.nextTick()` 优先级最高，不属于普通事件循环阶段
- 递归塞太多 `process.nextTick()` 会导致 **I/O 饥饿**
- `setImmediate()` 适合"本轮 I/O 之后尽快执行"
- `setTimeout(fn, 0)` 不是"马上执行"，只是最短等待时间到了后参与调度

**追问：为什么有时 `setImmediate` 比 `setTimeout(...,0)` 先？**

因为它们不在一个阶段。在 I/O 回调里注册时，`setImmediate()` 往往先于 `setTimeout(fn, 0)` 执行。

---

## 异步 I/O 与线程池

不是所有异步操作都走线程池，要分两类：

**1. 操作系统本身支持的异步（不依赖线程池）：**
- 大多数网络 I/O：事件通知模型，OS 直接监听

**2. 需要 libuv 线程池的操作：**
- 很多文件系统 API（`fs.readFile` 等）
- 部分 `crypto`、`zlib`
- `dns.lookup()`

> 异步不等于多线程；异步是调用方式，多线程只是某些底层实现手段。

---

## Worker Threads

让 Node 能真正**并行执行 JavaScript 代码**，适合 CPU 密集型任务。

```js
import { Worker, isMainThread, parentPort } from 'worker_threads'

if (isMainThread) {
  const worker = new Worker('./worker.js')
  worker.on('message', result => console.log('结果:', result))
  worker.postMessage({ data: [1, 2, 3, 4, 5] })
} else {
  parentPort.on('message', ({ data }) => {
    const result = data.reduce((a, b) => a + b, 0)
    parentPort.postMessage(result)
  })
}
```

**适合用 Worker Threads 的场景：**
- 大 JSON 解析/转换
- 图片缩放、加密、压缩
- 服务端代码编译
- CPU 算法任务

**不适合用 Worker Threads 的场景：**
- 普通数据库查询、HTTP 请求、读文件 → 这些用 Node 的异步 I/O 就够了

> Worker Threads 主要解决"CPU 把主线程卡死"的问题，不是拿来替代普通异步 I/O 的。

---

## child_process vs worker_threads

|  | `worker_threads` | `child_process` |
|---|---|---|
| 隔离级别 | 同进程内的线程 | 独立子进程 |
| 内存共享 | ✅ 支持 `SharedArrayBuffer` | ❌ 进程间独立 |
| 适合场景 | CPU 密集型 JS 逻辑 | 系统命令、其他语言程序 |
| 创建成本 | 较低 | 较高 |

**`child_process` 四个方法的区别：**

| 方法 | 特点 |
|---|---|
| `spawn` | 流式拿输出，适合长任务、大输出 |
| `exec` | shell 执行，输出缓冲到内存，适合短命令 |
| `execFile` | 直接执行文件，不经过 shell，更安全 |
| `fork` | 拉起新的 Node 进程，自带 IPC 通道 |
