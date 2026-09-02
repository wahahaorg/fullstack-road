# 日志与可观测性

> 线上出问题时，你手里只有日志。这篇讲清怎么从 `console.log` 升级到能查、能告警、能定位到某一次请求的日志体系，以及指标和健康检查该怎么做。

## console.log 为什么不能上生产

前端的 `console.log` 是给人当场看的：你在浏览器里点一下、看一眼、关掉。服务端日志是给机器事后查的：出问题可能是三天前的凌晨，请求量每分钟几万条，你要在里面找出某个用户的某一次操作。这两件事的要求完全不同。

| 缺什么 | 线上会发生什么 |
|---|---|
| 级别 | 想只看错误做不到。要么全量输出（日志量爆炸），要么删代码（下次排查又得加回来） |
| 时间戳与上下文 | 日志里躺着一行「保存失败」。哪个时间、哪个模块、哪个用户、哪一次请求，全都不知道 |
| 结构化 | 字符串拼出来的日志只能全文检索。想按 `level=error AND userId=1123` 过滤，得写正则去猜 |
| 切割与归档 | 单文件涨到几十 GB，编辑器打不开，磁盘写满连数据库都跟着写不进去 |
| 背压处理 | 见下 |

最后一条最容易被忽略。Node 的 `process.stdout` 写入行为取决于它指向哪里：指向**文件或 TTY 时是同步写**，一次 `console.log` 就是一次阻塞的系统调用，日志一多直接吃掉事件循环的时间；指向**管道时是异步写**（Docker 日志驱动、PM2、`|` 接到别的进程都属于这种），下游读得慢的时候待写数据会在进程内存里堆积。两种模式各有各的坏结果，而 `console.log` 对此毫无控制手段。

日志框架解决的正是这些：分级、结构化、可配置目的地、可控的写入策略。

---

## Nest 内置 Logger

`@nestjs/common` 导出的 `Logger` 就能替掉大部分 `console.log`：

```typescript
@Injectable()
export class OrderService {
  // 构造时传 context，后面每次调用就不用再传
  private readonly logger = new Logger(OrderService.name)

  async create(userId: number, dto: CreateOrderDto) {
    try {
      const order = await this.repo.insert(userId, dto)
      this.logger.log(`订单创建成功 orderId=${order.id}`)
      return order
    } catch (err) {
      // 第二个参数传 stack，否则堆栈会丢
      this.logger.error(`订单创建失败 userId=${userId}`, (err as Error).stack)
      throw err
    }
  }
}
```

五个常用级别从低到高是 `verbose` → `debug` → `log` → `warn` → `error`，当前版本还多一个 `fatal`（进程即将不可用时用）。`[OrderService]` 这个 context 会打在每行日志前面，是排查时最省事的字段——不看代码就知道日志是谁打的。

启动阶段的日志由 `NestFactory.create` 的 `logger` 选项控制：

```typescript
// 白名单：只输出这两个级别，Nest 那一堆路由映射日志就不刷屏了
const app = await NestFactory.create(AppModule, { logger: ['error', 'warn'] })

// 当前版本的 ConsoleLogger 能直接输出 JSON，容器环境很实用
const app = await NestFactory.create(AppModule, {
  logger: new ConsoleLogger({ json: true, timestamp: true }),
})
```

> ⚠️ `logger` 数组是**白名单**，不是最低级别。写成 `['warn']` 的话 `error` 也不会输出。传 `false` 则彻底关掉，一般只在测试里这么用。

### 自定义 Logger 并全局替换

实现 `LoggerService` 接口即可，其中 `log` / `error` / `warn` 必需，`debug` / `verbose` / `fatal` 可选：

```typescript
export class PlainLogger implements LoggerService {
  log(message: unknown, ...meta: unknown[]) { this.write('info', message, meta) }
  error(message: unknown, ...meta: unknown[]) { this.write('error', message, meta) }
  warn(message: unknown, ...meta: unknown[]) { this.write('warn', message, meta) }

  private write(level: string, message: unknown, meta: unknown[]) {
    process.stdout.write(`${JSON.stringify({ level, message, meta })}\n`)
  }
}

app.useLogger(new PlainLogger())    // 从这行之后，Nest 内部日志也走你的实现
```

只想改一两个方法就**继承 `ConsoleLogger`**（它已经处理好 context 提取、级别过滤、时间戳、颜色），在覆写里调 `super` 即可，别从头实现整个接口。

### 怎么让自定义 Logger 也能被 DI 注入

上面两种写法都是手动 `new` 的，在容器外面，注入不了任何 Provider——想在日志里带上配置里的服务名、或者把错误顺手上报给监控 Service 就做不到。矛盾在时序上：logger 要在应用创建时就生效，但容器要等应用初始化完才能取实例。`bufferLogs` 就是为这个缝隙设计的：

```typescript
const app = await NestFactory.create(AppModule, { bufferLogs: true })
// 启动期日志先进缓冲区，此刻还没有输出
app.useLogger(app.get(AppLogger))   // 指定容器里的 logger，缓冲区随即 flush

@Injectable()
export class AppLogger extends ConsoleLogger {
  constructor(private readonly config: ConfigService) {   // ← 正常注入依赖
    super(AppLogger.name, { timestamp: true })
  }

  log(message: unknown, ...rest: unknown[]) {
    super.log(`[${this.config.get('APP_NAME')}] ${message}`, ...rest)
  }
}
```

业务代码怎么拿到它？把它放进一个 `@Global()` 模块并 `exports`，各处直接注入，不用每个模块都 `imports`。这是 `@Global()` 少数正当的用途——横切基础设施、全应用只该有一个、几乎人人都要用；相关取舍见 [依赖注入](/guide/nestjs-di)。想让调用方在 `imports` 时传配置（级别、目录、服务名），就做成 `forRoot()` 动态模块，写法见 [动态模块与配置管理](/guide/nestjs-dynamic-module)。

> ⚠️ 开了 `bufferLogs` 却忘了 `useLogger`，启动日志会一直躺在缓冲区里，表现为「服务明明起来了但控制台什么都没有」。另外进程退出前要 flush，否则最后几条日志会丢——这属于优雅退出的一环，钩子见 [依赖注入](/guide/nestjs-di)。

---

## 为什么还要 Winston / Pino

内置 Logger 已经解决了级别、时间戳、context 和结构化输出，但它的目的地**只有 stdout / stderr**。真实项目通常要求：error 单独落一个文件方便交接、日志按天切割保留两周、部分日志同时发给告警服务。这些内置 Logger 一件都做不了，而且它没有子 logger、没有采样、没有背压控制。

| 维度 | 内置 Logger | Winston | Pino |
|---|---|---|---|
| 输出目的地 | 只有 stdout / stderr | transport 生态最全：文件、按天轮转、HTTP、数据库、云日志服务 | 主进程只写一个流，其余目的地交给 transport 子进程 |
| JSON 输出 | 支持（`json: true`） | `format.json()`，格式可自由编排 | 默认就是 JSON |
| 按天/按大小轮转 | ❌ | `winston-daily-rotate-file` | 交给 `pino-roll` 或系统 logrotate |
| 性能 | 一般 | 中等，format 链每条日志都要跑一遍 | 最快：序列化用预编译函数，写入走异步批量 |
| 子 logger（绑定固定字段） | ❌ | `logger.child({ module })` | `logger.child({ module })` |
| 人眼可读的开发输出 | 开箱即用 | `format.printf` 自己拼 | 要额外接 `pino-pretty` |
| Nest 集成 | 原生 | `nest-winston` | `nestjs-pino`（自带请求上下文绑定） |

一句话选型：**要「一份日志按不同格式写到多个地方」选 Winston；要「高 QPS、日志统一交给采集器」选 Pino。** 中小项目里 Winston 的灵活性通常更实用，QPS 上千、日志成为热点之后再换 Pino——`nestjs-pino` 还顺手把请求上下文绑定做了，能省掉后面自己写 `AsyncLocalStorage` 的活。

---

## 集成 Winston 实战

```bash
npm i winston nest-winston winston-daily-rotate-file
```

### 格式：开发给人看，生产给机器看

```typescript
const base = format.combine(
  format.timestamp({ format: 'YYYY-MM-DD HH:mm:ss.SSS' }),
  format.errors({ stack: true }),          // 关键，见下
)

export const jsonFormat = format.combine(base, format.json())   // 生产：一行一个 JSON

export const prettyFormat = format.combine(                     // 开发：彩色、紧凑
  base,
  format.colorize({ level: true }),
  format.printf(({ timestamp, level, context, message, traceId, stack }) =>
    `${timestamp} ${level} [${context ?? '-'}]${traceId ? ` (${traceId})` : ''} ${message}`
    + (stack ? `\n${stack}` : '')),
)
```

`format.errors({ stack: true })` 不能省。Winston 遇到 `Error` 对象时，默认只会把它的可枚举属性拿去序列化，而 `message` 和 `stack` 都不可枚举——结果日志里出现一个空的 `{}`，你知道出错了但不知道错在哪。这是集成 Winston 时最常踩的坑。

**为什么生产必须是 JSON？** 因为解析日志的不是人，是采集器（Filebeat、Fluent Bit、Loki、云日志服务）。`2026-09-02 10:00:01 error [OrderService] 保存失败 userId=1123` 这样一行，采集器只能当成一整串文本存起来，你只有全文检索；换成 JSON，`level`、`context`、`userId`、`traceId` 都是独立字段，可以精确过滤、可以按字段聚合出错误率、可以对某个字段配告警。另外多行堆栈在文本格式下会被采集器拆成好几条互不相关的记录，JSON 把 `stack` 装进一个字段就不会。

### transport：按天轮转 + 按级别分文件

```typescript
// logger.module.ts
import { WinstonModule } from 'nest-winston'
import { transports } from 'winston'
import 'winston-daily-rotate-file'

const isProd = process.env.NODE_ENV === 'production'

const rotate = (name: string, level: string, keep: string) =>
  new transports.DailyRotateFile({
    level,
    dirname: 'logs',
    filename: `${name}-%DATE%.log`,
    datePattern: 'YYYY-MM-DD',
    zippedArchive: true,
    maxSize: '100m',
    maxFiles: keep,
    format: jsonFormat,
  })

@Module({
  imports: [
    WinstonModule.forRoot({
      level: isProd ? 'info' : 'debug',
      transports: [
        new transports.Console({ format: isProd ? jsonFormat : prettyFormat }),
        rotate('app', 'info', '14d'),      // 全量日志留两周
        rotate('error', 'error', '30d'),   // 错误单独一份、留更久，出事故只看这个文件
      ],
      // 兜住没人接的异常，把进程猝死前的最后现场留下来
      exceptionHandlers: [new transports.File({ dirname: 'logs', filename: 'crash.log' })],
      rejectionHandlers: [new transports.File({ dirname: 'logs', filename: 'crash.log' })],
    }),
  ],
})
export class LoggerModule {}
```

几个容易写错的点：

| 配置 | 语义 | 写错的后果 |
|---|---|---|
| transport 的 `level` | 「这个级别**及以上**」，不是「只有这个级别」 | `level: 'info'` 的文件里同样会有 error，这是预期行为；想只要 error 就单独开一个 transport |
| `maxFiles` | 保留数量或天数（`'14d'`） | 不配就是永久保留。磁盘写满之后不只是日志停了——同一台机器上的数据库也会开始报写入失败 |
| `maxSize` | 单文件上限，超了当天内继续切 | 只按天切的话，一次异常刷日志能把单天文件顶到几十 GB |
| `zippedArchive` | 轮转后 gzip 历史文件 | 文本日志压缩比通常有十倍以上，这个开关几乎没有理由不开 |

`exceptionHandlers` / `rejectionHandlers` 分别兜 `uncaughtException` 和 `unhandledRejection`。它们的价值是**把进程猝死的最后一条现场信息留下来**——否则进程被拉起后你只能看到一个没有原因的重启记录。但要注意 Winston 默认 `exitOnError: true`，记完日志就退出，这是对的：未捕获异常之后进程状态已经不可信（可能有连接没关、有事务悬着），正确做法是记录后退出、交给 PM2 或 K8s 重启。**不要为了「服务别挂」把它设成 `false` 硬撑**，那只会把一次干净的重启换成一段行为诡异的运行期。

最后在 `main.ts` 里把它接上：

```typescript
import { WINSTON_MODULE_NEST_PROVIDER } from 'nest-winston'

const app = await NestFactory.create(AppModule, { bufferLogs: true })
app.useLogger(app.get(WINSTON_MODULE_NEST_PROVIDER))
```

`WINSTON_MODULE_NEST_PROVIDER` 取到的是一个实现了 `LoggerService` 的适配器，所以业务代码里继续用 `new Logger(XxxService.name)` 就行，不需要到处改成注入 Winston——**换底层实现不该让业务代码感知**，这也是 Nest 把 Logger 做成接口的意义。

> ⚠️ 容器里到底要不要写文件？K8s 的约定是**只写 stdout**，轮转、归档、采集都由平台负责；在容器里写文件反而要额外挂卷、还要自己清理。所以 `DailyRotateFile` 适合单机 / PM2 部署，容器化之后应该只留 Console transport。部署形态的差异见 [Docker 部署](/guide/docker-deployment)。

---

## 请求日志：Middleware 还是 Interceptor

两个都能记，但能拿到的东西不一样：

| | Middleware | Interceptor |
|---|---|---|
| 耗时的起点 | 最外层，包含 Guard、Pipe、其他中间件 | 只从 Interceptor 自己开始，前面几层的耗时看不到 |
| 响应体 | ❌ 拿不到 | ✅ `tap` 里就是 handler 的返回值 |
| 异常 | ❌ 只能从 `res.statusCode` 反推 | ✅ `tap({ error })` / `catchError` |
| 控制器与方法名 | ❌ 没有 `ExecutionContext` | ✅ `getClass()` / `getHandler()` |
| 覆盖范围 | 全部请求，包括 404 和被 Guard 拒掉的 | 只有路由命中的请求 |

**结论是两个都要，但分工不同。** Middleware 负责注入 traceId 和一条兜底的 access log（在 `res.on('finish')` 里记，此时状态码和耗时都已确定）；Interceptor 负责业务维度的细节（handler 名、异常、必要时的响应内容）。只能选一个的话选 Middleware——它不会漏掉 404、限流拒绝和鉴权失败，而这些恰恰是排查时最需要的。两者的职责边界和完整执行顺序见 [请求生命周期](/guide/nestjs-pipeline)，Interceptor 侧的耗时统计与慢接口告警在 [RxJS 与 Interceptor 实战](/guide/nestjs-rxjs-interceptor) 里有完整实现，这里不重复。

### 记哪些字段

| 字段 | 取值 | 注意 |
|---|---|---|
| `traceId` | 见下一节 | 没有它，其余字段的价值减半 |
| `method` / `route` | `req.method` / `req.route?.path` | 用**路由模板**而不是原始 URL。`/orders/1234` 这种带 id 的路径直接聚合会产生无数个维度，把日志系统和监控一起打爆 |
| `status` | `res.statusCode` | |
| `durationMs` | `process.hrtime.bigint()` 差值 | 别用 `Date.now()`，毫秒精度不够 |
| `ip` | 见下 | |
| `userId` | Guard 挂在 `request.user` 上的 | 匿名请求留空，不要填 `0` |
| `userAgent` / `query` | 截断后再记 | 爬虫 UA 能长到几 KB；完整 body 不要无条件记，见下一节 |

IP 有个必须处理的细节：经过 Nginx 之后 `req.ip` 拿到的是反向代理的地址。要拿真实客户端 IP 得读 `X-Forwarded-For` 的**第一段**，并且必须先 `app.set('trust proxy', 1)` 告诉 Express 信任最靠近自己的那一跳。

> ⚠️ `X-Forwarded-For` 是客户端可以随便伪造的请求头。只有在**确认自己前面有一层会重写它的反向代理**时才能信；直接暴露在公网的服务读这个头，等于让人任意伪造 IP，风控和限流会直接失效。

### 敏感字段脱敏

日志一旦落盘就已经泄露了，指望采集端过滤是来不及的。脱敏必须发生在写日志之前：

```typescript
const SENSITIVE = /pass(word)?|token|secret|credential|authorization|cookie|id_?card|bank_?card|cvv/i
const PHONE = /(1[3-9]\d)\d{4}(\d{4})/g
const MAX_DEPTH = 5, MAX_ITEMS = 50, MAX_STRING = 512

export function redact(value: unknown, depth = 0): unknown {
  if (typeof value === 'string') return maskString(value)
  if (value === null || typeof value !== 'object') return value
  if (Buffer.isBuffer(value)) return `[Buffer ${value.length}B]`
  if (value instanceof Date) return value.toISOString()
  if (depth >= MAX_DEPTH) return '[depth limit]'

  if (Array.isArray(value)) {
    const head = value.slice(0, MAX_ITEMS).map((v) => redact(v, depth + 1))
    return value.length > MAX_ITEMS ? [...head, `…${value.length - MAX_ITEMS} more`] : head
  }
  return Object.fromEntries(
    Object.entries(value).map(([k, v]) => [k, SENSITIVE.test(k) ? '***' : redact(v, depth + 1)]),
  )
}

function maskString(s: string): string {
  const clipped = s.length > MAX_STRING ? `${s.slice(0, MAX_STRING)}…(${s.length})` : s
  return clipped.replace(PHONE, '$1****$2')
}
```

三个上限都不是多余的：**深度**上限防住循环引用导致的栈溢出（`request.user.company.employees[0].company…` 这种关联对象很常见）；**数组**上限防住一次批量接口把一万条记录写进日志；**字符串**上限防住 base64 图片和长文本。少了任何一个，一个接口就能把当天的日志配额吃完。

更稳妥的做法是**双层防护**：业务代码里调 `redact()`，同时在 Winston 上挂一个 `format((info) => …redact(info.meta))` 兜底——因为总会有人直接 `logger.log(dto)`。

### 一定要排除的路径

```typescript
const SKIP = [/^\/health/, /^\/metrics/, /^\/favicon\.ico$/, /^\/static\//]
```

健康检查探针默认几秒一次，liveness 加 readiness 两个探针乘以三个副本，一天就是几万条内容完全一样的日志。它们既会把真实请求冲淡，又在按量计费的日志服务上直接变成账单。静态资源同理。

---

## 链路追踪：traceId

一次下单请求会在 controller、service、repository、缓存层各打几条日志，线上并发几百的时候这些日志是**交错**的。没有 traceId，你只能按时间戳猜哪几条属于同一次请求——请求一多就完全猜不出来。有了它，一次 `traceId:"…"` 查询就能把整条链路按顺序捞出来；再把 traceId 返回给客户端，用户报错时截个图，你就能直接定位到那一次请求。

### 为什么用 AsyncLocalStorage

traceId 要出现在每一条日志里，而日志是横切关注点。一路传参意味着从 controller 到 repository 沿途每个方法都要多一个参数，业务签名被日志需求污染；`Scope.REQUEST` 的 Provider 也能拿到请求上下文，但代价是整棵依赖树按请求实例化（见 [依赖注入](/guide/nestjs-di)）。

`AsyncLocalStorage` 是 Node 原生的答案：它把一份数据绑在**异步调用链**上，链路里任何深度的代码都能取到，并发请求之间互不干扰。前端类比是 React Context——组件树里任意深的子组件都能 `useContext`，中间不用一层层传 props；区别是这里的「树」是异步调用链。

```typescript
// request-context.ts
import { AsyncLocalStorage } from 'node:async_hooks'

export interface RequestStore { traceId: string; userId?: number }

export const requestContext = new AsyncLocalStorage<RequestStore>()
export const getTraceId = () => requestContext.getStore()?.traceId
```

在最外层的 Middleware 里开启上下文，顺手接受上游传来的 id：

```typescript
@Injectable()
export class TraceMiddleware implements NestMiddleware {
  use(req: Request, res: Response, next: NextFunction) {
    const incoming = req.headers['x-request-id']
    const raw = Array.isArray(incoming) ? incoming[0] : incoming
    // 只接受合法形态，避免上游把任意内容注入到日志字段里
    const traceId = raw && /^[\w-]{8,64}$/.test(raw) ? raw : randomUUID()

    res.setHeader('X-Request-Id', traceId)
    requestContext.run({ traceId }, next)   // next 必须在 run 的回调里执行
  }
}
```

> ⚠️ 写成 `requestContext.run({ traceId }, () => {}); next()` 是无效的——后续中间件和 handler 就跑在上下文之外，`getStore()` 全部返回 `undefined`。`run` 的第二个参数必须是真正往下走的那个函数。

接受上游 `X-Request-Id` 的意义是**跨服务串联**：网关生成一次，往下每一跳都带着同一个 id，这样几个服务的日志能拼成一条完整链路。前端也可以主动生成并带上，前后端日志就打通了。

### 让 traceId 自动出现在日志里

不要指望每个人在每次 `logger.log()` 时手动带上，加一个 Winston format 就行：

```typescript
const traceFormat = format((info) => Object.assign(info, requestContext.getStore() ?? {}))
// 挂在最前面：format.combine(traceFormat(), base, format.json())
```

另一半是**错误响应里也要带**，否则用户报障时你还是拿不到 id。在全局 Exception Filter 里加一个字段就行：

```typescript
res.status(status).json({
  code: status,
  message: status >= 500 ? '服务器内部错误' : exception.message,
  traceId: getTraceId(),          // ← 用户能看到、能报给你的那个 id
})
```

500 错误对外只给一句通用文案、细节只进日志，这是基本的信息暴露纪律；完整的 Filter 写法见 [参数校验与异常处理](/guide/nestjs-validation-filter)。

### 两个容易忽略的边界

**没有 HTTP 请求的地方也需要 traceId。** 定时任务和消息消费者跑在请求之外，`getStore()` 是空的，那部分日志就串不起来。做法是在入口自己开一个上下文：

```typescript
@Cron(CronExpression.EVERY_DAY_AT_4AM)
async syncViewCount() {
  await requestContext.run({ traceId: `cron-${randomUUID()}` }, () =>
    this.articleService.flushViewCount(),
  )
}
```

**异步边界会切断语义。** `AsyncLocalStorage` 的上下文跟着异步资源自动传递，所以 `await`、`setTimeout`、事件监听器里都还在，这是它好用的原因。但如果任务是从队列里取出来消费的，那次消费的上下文属于「消费者的这一轮循环」，和「当初入队的那个请求」没有关系——想串起来必须把 traceId 作为**消息体里的字段**显式传递，消费时再 `run()` 进去。定时任务与事件的入口在 [定时任务与事件驱动](/guide/nestjs-schedule-events)，跨进程投递见 [消息队列基础](/guide/message-queue)。

---

## 日志级别纪律

级别不是给「重要程度」打分，而是回答**「谁会在什么时候看它」**：

| 级别 | 语义 | 该记什么 | 不该记什么 |
|---|---|---|---|
| `error` | 系统坏了，需要人现在去看 | 未预期异常、下游连不上、数据不一致、写库失败 | 用户输错密码、参数校验失败、404 |
| `warn` | 还能跑，但不对劲 | 降级生效、重试后成功、慢查询、限流触发、配置回退到默认值 | 每一个 4xx |
| `log` | 关键业务事件，事后要能复盘 | 启动完成、订单创建、支付回调、定时任务开始与结束 | 循环体里的每条记录 |
| `debug` | 排查用的中间态 | 入参出参、分支判断、SQL 语句 | 生产默认关闭 |
| `verbose` | 极细粒度追踪 | 缓存命中与否、每一次重试 | 生产永远关闭 |

**「用户输错密码」不是 error。** 它是预期内的业务分支，一天出现几千次完全正常。一旦记成 error，「error 数量超过阈值就告警」这条规则会天天响；两周之后所有人都把这个告警静音，真正的故障来的时候没有人看。同样的道理适用于参数校验失败、404、幂等拒绝——这些都是系统**按设计工作**的证据。

判断标准就一句：**error 的定义是「需要有人现在去看」。** 做不到这一点的都不该是 error。用户维度的失败要么记 `warn`（连续失败可能是撞库，这时确实值得关注），要么根本不进日志，只进业务审计表和指标计数器。

反过来也有个纪律：`debug` 不要靠删代码来关，靠配置。级别从环境变量读，线上排查时改配置重启就能开出细节，比临时加日志再发一次版快得多。

---

## 服务器指标

日志回答「这一次请求发生了什么」，指标回答「这段时间整体怎么样」。最基础的几个指标用 Node 原生 API 就能拿。

### CPU：必须采两次样

```typescript
import os from 'node:os'
import { setTimeout as sleep } from 'node:timers/promises'

function sample() {
  return os.cpus().reduce((acc, { times: t }) => {
    acc.idle += t.idle
    acc.total += t.user + t.nice + t.sys + t.irq + t.idle
    return acc
  }, { idle: 0, total: 0 })
}

export async function cpuUsage(windowMs = 1000): Promise<number> {
  const before = sample()
  await sleep(windowMs)
  const after = sample()

  const total = after.total - before.total
  const idle = after.idle - before.idle
  return total === 0 ? 0 : +(((total - idle) / total) * 100).toFixed(2)
}
```

`os.cpus()` 里的 `times` 是**开机以来的累计毫秒数**。直接拿 `user / total` 算出来的是「开机至今的平均使用率」——机器跑了一个月，现在 CPU 打满你也看不出来，因为一个月的分母把它稀释掉了。想要瞬时值必须采两次样求差值，上面那段就是为此存在的。`os.loadavg()` 返回 1 / 5 / 15 分钟的平均负载，和使用率不是一回事：它统计的是**等待运行的任务数**，超过核数就说明有排队；注意它在 Windows 上恒为 `[0, 0, 0]`。

### 内存：rss 和 heapUsed 看的是两件事

| 字段 | 含义 | 什么时候看它 |
|---|---|---|
| `rss` | 进程实际占用的物理内存，含 V8 堆、栈、代码段、Buffer | 判断「离 OOMKilled 还有多远」，容器 limit 比对的就是它 |
| `heapTotal` | V8 已经向系统申请的堆大小 | 参考值，会随 GC 策略波动 |
| `heapUsed` | V8 堆里真正被对象占用的部分 | 判断 JS 层有没有内存泄漏，看它的**长期趋势** |
| `external` | 绑定在 V8 上的 C++ 对象内存 | 用了 native 模块时 |
| `arrayBuffers` | `Buffer` / `ArrayBuffer` 占用（`external` 的子集） | 流式处理大文件时 |

两者的组合能直接指向问题：`heapUsed` 平稳而 `rss` 一直涨，说明漏的不是 JS 对象，而是 Buffer、native 内存或内存碎片；两个一起涨才是常规的 JS 层泄漏（多半是某个 Map 只 set 不 delete）。排查手法见 [Node.js 性能与稳定性](/guide/node-perf)。

> ⚠️ 容器里 `os.totalmem()` 返回的是**宿主机**内存，不是容器的 limit；`os.cpus().length` 同理。这就是为什么容器里的进程会「明明还剩很多内存」却突然被 OOMKilled——它看到的从来不是自己的额度。真要知道自己的上限，得读 cgroup（v2 下是 `/sys/fs/cgroup/memory.max` 和 `memory.current`），或者干脆把 limit 用环境变量注进来自己比对。

### 磁盘

Node 18.15 起内置了 `fs.statfs`，不用再装第三方包：

```typescript
import { statfs } from 'node:fs/promises'

export async function diskUsage(path = '/') {
  const s = await statfs(path)
  const total = s.blocks * s.bsize
  const available = s.bavail * s.bsize      // 非特权用户可用，比 bfree 更接近真实可用量
  return { totalGB: +(total / 1024 ** 3).toFixed(2), usedPercent: +(((total - available) / total) * 100).toFixed(2) }
}
```

用 `bavail` 而不是 `bfree`：文件系统会给 root 预留一部分块，`bfree` 把这部分算进去，会让你以为还有空间。

---

## 健康检查：liveness 与 readiness

指标是给人看趋势的，健康检查是给编排系统做决策的。`@nestjs/terminus` 把它做成了标准形态：

```typescript
@Controller('health')
export class HealthController {
  constructor(
    private readonly health: HealthCheckService,
    private readonly db: TypeOrmHealthIndicator,
    private readonly disk: DiskHealthIndicator,
    private readonly memory: MemoryHealthIndicator,
    private readonly redis: RedisHealthIndicator,
  ) {}

  @Get('live') @HealthCheck()
  live() {
    return this.health.check([])          // 只回答「重启我有用吗」
  }

  @Get('ready') @HealthCheck()
  ready() {                               // 回答「现在能不能给我发流量」
    return this.health.check([
      () => this.db.pingCheck('mysql', { timeout: 1500 }),
      () => this.redis.isHealthy('redis'),
      () => this.disk.checkStorage('disk', { path: '/', thresholdPercent: 0.9 }),
      () => this.memory.checkHeap('heap', 512 * 1024 * 1024),
    ])
  }
}
```

自定义探针（Redis、下游服务、Prisma）用 `HealthIndicatorService` 拼装结果：

```typescript
@Injectable()
export class RedisHealthIndicator {
  constructor(
    @Inject(REDIS_CLIENT) private readonly redis: RedisClientType,
    private readonly indicatorService: HealthIndicatorService,
  ) {}

  async isHealthy(key: string) {
    const indicator = this.indicatorService.check(key)
    const startedAt = Date.now()
    try {
      await this.redis.ping()
      return indicator.up({ latencyMs: Date.now() - startedAt })
    } catch (err) {
      return indicator.down({ message: (err as Error).message })
    }
  }
}
```

### 为什么两个探针必须分开

| | liveness | readiness |
|---|---|---|
| 回答的问题 | 进程是不是已经死了或彻底卡死 | 现在能不能正确处理请求 |
| 失败的后果 | kubelet **杀掉容器重启** | 从 Service endpoints **摘掉，不重启** |
| 该检查什么 | 只检查自己：能不能返回 200 | 依赖是否可用：数据库、缓存、必要的下游 |
| 千万不要 | 把数据库探针放进来 | 做成永远返回 200 |

**liveness 里绝对不能查数据库。** 数据库抖动 30 秒，所有副本的 liveness 同时失败，全部被杀掉重启；重启后连接池要冷启动、本地缓存全空、请求一齐涌向刚恢复的数据库——一次可以自愈的抖动就这样被放大成一次全站故障。liveness 唯一要回答的是「重启我有用吗」，数据库挂了，重启我没用。

readiness 反过来必须查依赖，因为它的动作是**摘流量**：这个副本连不上数据库时把它摘掉，流量转给健康的副本，是完全正确的处理。它还承担优雅退出的第一步——收到 `SIGTERM` 后立刻让 readiness 返回 503，等负载均衡摘掉流量、在途请求收尾后再关连接。这套时序和对应的生命周期钩子见 [依赖注入](/guide/nestjs-di)。

启动慢的应用（要跑 migration、要预热缓存）用 startupProbe，而不是把 liveness 的 `failureThreshold` 调大——后者会让 liveness 在整个运行期都变得迟钝，失去意义。

---

## 日志、指标、追踪：先做哪一步

三件套解决的不是同一类问题，别指望其中一个覆盖全部：

| 你的问题 | 该看哪个 | 为什么不是别的 |
|---|---|---|
| 「刚才这个用户下单为什么失败」 | 日志（按 traceId 查） | 只有日志保留了具体某一次请求的上下文 |
| 「最近半小时错误率是不是变高了」 | 指标 | 用日志做聚合又慢又贵，指标就是为聚合而生的 |
| 「这个接口 900ms 花在哪一段」 | 追踪 | 需要跨服务、跨函数的耗时分解 |
| 「内存是不是在泄漏」 | 指标（`heapUsed` 长期趋势） | 单点采样看不出趋势 |
| 「这次故障影响了多少用户」 | 日志（按状态码 + userId 聚合） | 指标只有总数，没有主体 |

小项目按这个顺序推进，不要跳步：

1. **必须有**：结构化 JSON 日志、traceId、全局异常兜底、`/health` 探针。这四件加起来不到两百行代码，缺任何一件，线上出问题就只能靠猜。
2. **有用户量之后**：日志采集与检索（哪怕只是 Loki + Grafana）、错误告警（error 计数和关键接口 5xx 率）、慢接口与慢查询告警。
3. **拆成多个服务之后**：OpenTelemetry 分布式追踪。单体服务里追踪的收益远小于接入成本，Interceptor 里的耗时日志基本够用。

顺序反了会很难受：**没有 traceId 的追踪系统等于没有追踪**，没有结构化日志的告警只能告诉你「出事了」却说不出出在哪。

---

## 面试怎么说

- **为什么不用 `console.log`**：没有级别、没有结构、不能控制目的地和轮转；而且 `process.stdout` 指向文件或 TTY 时是同步写，日志一多会直接占用事件循环的时间。
- **自定义 Logger 怎么注入依赖**：`NestFactory.create` 时开 `bufferLogs: true`，启动日志先进缓冲区，等容器就绪后 `app.useLogger(app.get(AppLogger))`，缓冲区随即 flush。
- **请求日志放 Middleware 还是 Interceptor**：Middleware 能覆盖 404 和被 Guard 拒掉的请求、耗时从最外层算起，但拿不到响应体和异常；Interceptor 能拿到 handler 名、响应和异常，但只覆盖路由命中的请求。生产上两个配合用。
- **traceId 怎么传**：`AsyncLocalStorage` 绑在异步调用链上，日志格式里自动读取，不污染业务方法签名；入口接受上游 `X-Request-Id`，没有就自己生成，同时写回响应头和错误响应体。
- **liveness 和 readiness 的区别**：前者失败会重启容器，只能检查进程自身；后者失败只是摘流量，应该检查依赖。把数据库探针放进 liveness，会把一次数据库抖动放大成全副本重启。
