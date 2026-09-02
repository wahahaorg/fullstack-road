# NestJS 生产环境清单：测试、版本控制与安全加固

> 这三件事有个共同点：都不挂在某一个模块底下。没有「测试模块」，没有「版本模块」，没有「安全模块」，但少任何一件都不该上线。开头一张表说明原来那些「进阶特性」都搬到哪儿去了。

## 原来的小节去哪了

这篇原本是「进阶特性」大杂烩：缓存讲十行、日志讲十行、WebSocket 讲十行，读完知道有这些东西，但一个都落不了地。现在这些话题各有专篇，本篇只留三块——**测试**（测的是所有模块，不属于任何模块，写法还和 DI 深度绑定）、**API 版本控制**（实现只有一个开关，难点全在判断上）、**安全加固与 CORS**（一串互不相干的小配置，散进各篇一定会漏）。

从搜索或旧书签进来找别的话题的话，下表是完整去向，每行带着那篇的核心结论，不点进去也能拿到判断。表末一行不是原小节，是常和本篇一起被问到的相邻话题。

| 话题 | 现在看 | 一句话结论 |
|---|---|---|
| Logger | [日志与可观测性](/guide/nestjs-logging) | 内置 Logger 够用到测试环境，生产要换 Winston / Pino 输出 JSON，并给每条日志带上 traceId 才查得动 |
| 缓存 | [Redis 实战](/guide/redis-practice)、[Interceptor 与 RxJS](/guide/nestjs-rxjs-interceptor) | Nest 侧装配就是 `CacheModule.register({ isGlobal: true, ttl })` 一行，`cache-manager` 只够「按 key 存一段 JSON」，要 ZSET、Lua 就直接上 ioredis；开箱的 `CacheInterceptor` 默认只按 URL 生成 key，多用户系统会串号 |
| 任务调度 | [定时任务与事件驱动](/guide/nestjs-schedule-events) | `@Cron` / `@Interval` / `@Timeout` 三件套很好写，真正的坑是多副本部署时每个实例都会各跑一遍 |
| SSE | [实时通信](/guide/nestjs-realtime) | AI 流式回复的默认答案：走 HTTP、浏览器自带重连 |
| 环境变量与配置管理 | [动态模块与配置管理](/guide/nestjs-dynamic-module) | `ConfigModule` 是动态模块最典型的样例；配置要在启动时校验，缺 key 当场崩掉比运行到一半才报好 |
| 错误处理 | [参数校验与异常处理](/guide/nestjs-validation-filter) | 内置异常类 + 一个全局 Exception Filter，controller 里一行 `try/catch` 都不用写 |
| 模块类型 | [动态模块](/guide/nestjs-dynamic-module)、[依赖注入](/guide/nestjs-di) | 静态 / 动态 / 全局 / 共享四种形态的区别，以及 `@Global()` 省下的 import 是拿「依赖变隐式」换的 |
| 文件上传 | [文件上传与大文件处理](/guide/nestjs-file-upload) | 从 multer 到分片上传到对象存储直传，按文件大小换方案 |
| WebSocket Gateway | [实时通信](/guide/nestjs-realtime) | Gateway 本身十行写完，难点是握手阶段怎么鉴权、多实例怎么广播 |
| 循环依赖 | [依赖注入](/guide/nestjs-di) | `forwardRef` 能救急，但它出现的地方通常说明模块边界划错了 |
| 软删除 | [TypeORM 实战](/guide/nestjs-database) | `@DeleteDateColumn` + `softDelete` / `restore`，代价是从此每个查询都要想一下要不要 `withDeleted` |
| 微服务基础（TCP） | [微服务与跨语言通信](/guide/nestjs-microservice) | TCP 传输只是入门形态，跨语言调用（Node 网关调 Python 服务）看 gRPC |
| compodoc（项目结构文档） | [DTO、序列化与 Swagger](/guide/nestjs-dto) | 两种文档给两拨人看：**Swagger 给接口消费者**，写清参数和响应；**compodoc 给维护代码的人**，画模块依赖图和 Provider 关系图。接手陌生项目时后者比读十个文件快 |

---

## 测试：这一节值得花最多时间

前端的 Jest 你已经写过了，Nest 侧只多出一件事：**被测对象的依赖是容器注入进来的，所以测试的第一步是搭一个只装了必要 Provider 的迷你容器**。`Test.createTestingModule` 就干这个，作用相当于前端测试里给组件套一层只放 mock 的 Provider wrapper。

### 三层测试各自抓什么 bug

| 层次 | 装什么 | 数据库 | 单用例耗时 | 抓什么 |
|---|---|---|---|---|
| 单元 | 被测类 + 依赖全换成 mock | 不连 | 毫秒 | 业务分支写反、边界条件、异常该抛没抛 |
| 集成 | 一个真实模块（Service + Repository） | 真连 | 几十到几百毫秒 | SQL 写错、关系映射错、事务边界错、唯一约束冲突 |
| E2E | 真实 `AppModule` + HTTP | 真连 | 百毫秒级 | 全局管道没装、路由拼错、鉴权配错、序列化把敏感字段漏出去 |

健康的比例是「单元测试覆盖业务分支 + 十几个 E2E 守住关键链路 + 集成测试只给复杂查询和事务写」。**倒过来做（几乎没有单测、堆一大堆 E2E）的项目，CI 一次十几分钟，最后没人愿意跑，测试就死了。**

### 单元测试：把依赖换掉

```typescript
describe('OrderService', () => {
  let service: OrderService
  const repo = { findOneBy: jest.fn(), save: jest.fn() }
  const mailer = { send: jest.fn() }

  beforeEach(async () => {
    jest.resetAllMocks()
    const moduleRef = await Test.createTestingModule({
      providers: [
        OrderService,
        { provide: getRepositoryToken(Order), useValue: repo },   // Repository 的 token
        { provide: MAIL_SENDER, useValue: mailer },
      ],
    }).compile()
    service = moduleRef.get(OrderService)
  })

  it('库存不足时抛 ConflictException，并且不发通知邮件', async () => {
    repo.findOneBy.mockResolvedValue({ id: 1, stock: 0 })

    await expect(service.place(1, 2)).rejects.toThrow(ConflictException)
    expect(mailer.send).not.toHaveBeenCalled()      // 断言「没有发生」常比断言返回值更有价值
  })
})
```

`providers` 里只列被测类和它的**直接**依赖，别图省事写 `imports: [AppModule]`——那会把整个应用连数据库一起拉起来，单测就变集成测试了。取 REQUEST / TRANSIENT 作用域的实例要用 `await moduleRef.resolve(X)`，`get(X)` 会抛错。手写 mock 类型不全，社区常用 `jest-mock-extended` 的 `mockDeep<T>()` 补类型。

依赖链一深，手写 mock 要写十几个，这时反过来做——导入真实模块，只替换外部副作用：

```typescript
const moduleRef = await Test.createTestingModule({ imports: [OrderModule] })
  .overrideProvider(MAIL_SENDER).useValue({ send: jest.fn() })       // 别真发邮件
  .overrideProvider(PAYMENT_GATEWAY).useClass(FakePaymentGateway)    // 别真扣钱
  .compile()
```

`.useValue()` / `.useClass()` / `.useFactory({ factory })` 和 Provider 定义一致。判断标准：**会产生进程外副作用的依赖（发邮件短信、调三方、写对象存储、推消息队列）必须换掉**，纯计算的依赖留着真实实现反而更有价值。换的位置有讲究——**在自己的边界上 mock，不要在别人的库内部 mock**：

| 外部依赖 | 怎么换 | 别这么做 |
|---|---|---|
| HTTP 调三方 | 自己包一层 `PaymentGateway` / `HttpService` 再 override；或用 `nock` / `msw` 在网络层拦 | 直接 mock `axios` 的内部方法，将来换个客户端库测试全废 |
| Redis | 单测把自己的 `CacheService` 换成一个 Map；集成测试起真容器 | 逐个 mock `ioredis` 命令，Lua 和过期行为根本测不出来 |
| 消息队列 | mock 生产者，断言「发出了哪条消息」；消费者当普通方法直接调 | 真连 MQ 再等消息落地，用例会变成随机失败的定时炸弹 |

> ⚠️ 反常识的一条：**很多单测其实不需要 `createTestingModule`**，`new OrderService(repo as any, mailer as any)` 更快也更直白。真正需要容器的是这几种：被测类依赖 `Reflector` / `ModuleRef` 这类框架对象、依赖生命周期钩子（`onModuleInit` 里预热了东西）、或者你要验证的正是「模块装配对不对」。为了「看起来像 Nest 的测试」套一层容器，只是多十行样板。

### 集成测试：连真库验模块协作

单测把数据库 mock 掉了，所以「SQL 写错、关系映射错、唯一约束没生效、事务边界不对」这几类 bug 它一个都抓不到。集成测试补的正是这一段：装真实模块、连真实数据库、不碰 HTTP。

```typescript
let moduleRef: TestingModule
let dataSource: DataSource
let service: OrderService

beforeAll(async () => {
  moduleRef = await Test.createTestingModule({
    imports: [
      TypeOrmModule.forRoot({ ...testDbConfig, entities: [Order, Sku], synchronize: true }),
      OrderModule,
    ],
  })
    .overrideProvider(MAIL_SENDER).useValue({ send: jest.fn() })     // 外部副作用照样换掉
    .compile()

  service = moduleRef.get(OrderService)
  dataSource = moduleRef.get(DataSource)
})

afterEach(() => dataSource.query('TRUNCATE TABLE orders'))           // 用例间清表，见下一小节
afterAll(() => moduleRef.close())                                   // 关连接池，否则 Jest 不退出

it('并发下单同一个 SKU 只成功一次（靠唯一索引，不靠代码里的先查后插）', async () => {
  const r = await Promise.allSettled([service.place(1, 1), service.place(1, 1)])
  expect(r.filter((x) => x.status === 'fulfilled')).toHaveLength(1)
  expect(await dataSource.getRepository(Order).count()).toBe(1)
})
```

`synchronize: true` 只允许出现在测试配置里，生产开它等于让 ORM 随手改表结构（见文末清单）。更贴近生产的做法是测试库也跑 migration，代价是每次准备库多几秒。集成测试要挑着写：只给复杂查询、事务和约束写，每个 Service 方法都来一遍的话 CI 时间必然失控。

### E2E：supertest 打真实应用

```typescript
let app: INestApplication

beforeAll(async () => {
  const moduleRef = await Test.createTestingModule({ imports: [AppModule] })
    .overrideProvider(MAIL_SENDER).useValue({ send: jest.fn() })
    .compile()

  app = moduleRef.createNestApplication()
  setupApp(app)                    // ← 关键，见下
  await app.init()
})

afterAll(() => app.close())        // 不关会残留数据库连接，Jest 报「did not exit」

it('POST /orders 缺字段返回 400，错误体里点明哪个字段', async () => {
  const res = await request(app.getHttpServer()).post('/orders').send({}).expect(400)
  expect(res.body.message).toEqual(expect.arrayContaining([expect.stringContaining('skuId')]))
})
```

`app.getHttpServer()` 拿到的是底层 http server，supertest 自己挑临时端口，所以 **E2E 不需要 `app.listen()`**，`init()` 就够。只有测 WebSocket 和微服务传输层才要真的 listen（见 [实时通信](/guide/nestjs-realtime)）。

### 假绿灯之王：全局切面在 E2E 里消失了

`main.ts` 里那些 `app.useGlobalPipes(...)`、`useGlobalFilters(...)`、`useGlobalInterceptors(...)` 在 E2E 里**一行都不会执行**——E2E 是自己 `createNestApplication()` 起的应用，`bootstrap()` 根本没被调用。后果是本地全绿、上线后同一个请求行为完全不同：校验没生效、错误格式不一样、响应没被包装。两种解法，选一个：

- **抽出 `setupApp(app)`**：把 `main.ts` 里所有 `useGlobalXxx`、`enableCors`、`enableVersioning` 收进一个函数，`main.ts` 和测试都调它。改动最小。
- **全局切面改成 Provider**：用 `APP_PIPE` / `APP_FILTER` / `APP_GUARD` / `APP_INTERCEPTOR` 在 `AppModule` 里注册。新项目首选——切面自己能注入依赖，测试 `imports: [AppModule]` 自动带上，还能被 override 换掉。两种注册方式的完整差异见 [参数校验与异常处理](/guide/nestjs-validation-filter)。

### 测试数据库怎么隔离

用例之间互相污染是集成测试最大的时间黑洞：单跑绿、一起跑红，或者今天绿、明天红。五种方案：

| 方案 | 做法 | 隔离性 | 速度 | 代价 |
|---|---|---|---|---|
| 用例后清表 | `afterEach` 按外键逆序 `DELETE` / `TRUNCATE` | 中 | 中 | 并行跑会互相踩，要 `--runInBand` 或每个 worker 一个库 |
| 用例内开事务再回滚 | `beforeEach` 开事务，`afterEach` `rollback` | 强 | 快 | 被测代码必须用上测试开的那条连接，见下 |
| 每个 Jest worker 一个库 / schema | 用 `JEST_WORKER_ID` 拼库名，各跑一次 migration | 强 | 中 | 建库和迁移成本 × N，CI 里要留意权限 |
| testcontainers | 一次性 Docker 容器，起来后跑 migration + seed | 最强，连数据库版本都是真的 | 慢（启动数秒到数十秒） | 依赖 Docker，CI 要能起容器 |
| 换 SQLite 内存库 | 改 driver 就完事 | 强 | 最快 | ⚠️ 方言不一样：JSON 列、时间函数、外键行为、`ON DUPLICATE KEY` 全对不上，测过的 SQL 上线照样报错 |

推荐组合：**整个 suite 起一次 testcontainers 容器（或复用一个专用测试库），用例之间靠清表隔离；等项目里已经有事务上下文机制了再上事务回滚。**

事务回滚快，但在 Nest 里有个前置条件常被忽略：**被测代码必须和测试用同一条连接**，否则测试事务里写的数据，被测代码那条连接根本看不见。满足它有三种方式——Service 方法签名本来就接受 `manager?: EntityManager`（最干净，测试直接传事务 manager 进去）；有 `AsyncLocalStorage` 事务上下文，Repository 从 ALS 取当前 manager（`typeorm-transactional` 这类库就是这么做的）；或者把 `getRepositoryToken(Entity)` 覆盖成 `queryRunner.manager.getRepository(Entity)`，但 QueryRunner 要在 `compile()` 之前准备好，装配顺序会变绕。

还有个躲不开的问题：**被测代码内部自己 `dataSource.transaction()` 会形成嵌套事务**，要靠 SAVEPOINT 才正确。项目里没有现成的事务上下文机制时，别硬上事务回滚，清表更省事。

### Guard 和 Interceptor：绕过还是留着

E2E 里每个用例都先登录拿 token 很啰嗦，`overrideGuard` 能把鉴权换成永远放行的假 Guard，顺手把用户塞进 request：

```typescript
const moduleRef = await Test.createTestingModule({ imports: [AppModule] })
  .overrideGuard(JwtAuthGuard)
  .useValue({
    canActivate: (ctx: ExecutionContext) => {
      ctx.switchToHttp().getRequest().user = { id: 1, roles: ['admin'] }
      return true                                   // 同族还有 overrideInterceptor / overrideFilter / overridePipe
    },
  })
  .compile()
```

> ⚠️ 这些 override 只对**类形式注册**的切面生效——`@UseGuards(JwtAuthGuard)` 或 `APP_GUARD`。`app.useGlobalGuards(new JwtAuthGuard(...))` 手动 new 出来的实例压根不在容器里，override 静默失效，测试照样 401。这是「全局切面改成 Provider」的又一个理由。

但**不要全绕过**：至少留一两个用例走完整鉴权链——调登录接口拿真 token，带着它请求业务接口。否则「Guard 顺序写反」、「JWT 校验配错」这类线上最容易出的事故，测试完全看不见。权限矩阵这种要跑很多遍的场景，写个 `loginAs('admin' | 'member' | 'guest')` helper 缓存 token 复用，比每个用例 override 更接近真实行为。

### 异步、定时任务和假时钟

```typescript
jest.useFakeTimers()
service.scheduleRetry()              // 内部 setTimeout 30s 后重试
await jest.advanceTimersByTimeAsync(30_000)
expect(gateway.call).toHaveBeenCalledTimes(2)
```

`advanceTimersByTimeAsync` 推进时钟的同时会把微任务队列冲干净，比同步版更适合测 `async` 逻辑。定时任务本身别硬测：

- **把 `@Cron()` 方法体的逻辑抽成普通方法**，测那个普通方法。装饰器只是触发器，验它注册没注册用 `SchedulerRegistry.getCronJob('name')` 拿得到就行。Cron 表达式对不对，用解析出的下一次触发时间来断言，比推快时钟稳定。
- 假时钟只用在纯逻辑上（退避重试、缓存过期、防抖窗口）。**混着真实 I/O 会死等**：假时钟不推进真实数据库的响应，你 `await` 的 Promise 永远不 resolve，用例超时。
- 事件监听器（`@OnEvent`）同理：直接调监听器方法测逻辑，「事件发出去了没有」用 mock 掉的 `EventEmitter2` 断言 `emit` 参数。等异步副作用落地用轮询断言，别写 `setTimeout(500)`。相关设计见 [定时任务与事件驱动](/guide/nestjs-schedule-events)。

### 测什么，不测什么

新手写测试最常见的浪费不是「测得少」，是「把测试写在没有信息量的地方」。

| 值得测 | 理由 |
|---|---|
| Service 的业务分支 | 库存不足、余额不够、状态机非法跃迁——分支多、改得频繁、错了直接影响钱和数据 |
| DTO 的校验规则 | 它就是 API 契约。用 `plainToInstance` + `validate` 直接测，一条规则三行，性价比最高 |
| Guard / 权限判断 | 布尔表达式写反的代价极高，而这类逻辑最容易在加需求时改错 |
| 纯函数工具 | 金额计算、分页参数解析、时间窗口切分——便宜，回归价值高 |
| 关键路径 E2E | 注册登录、下单支付、权限矩阵。防的是「上线即挂」，单测防不住 |

| 不值得测 | 理由 |
|---|---|
| 只做转发的 Controller | `return this.service.create(dto)` 的单测等于把实现抄一遍改成断言，它的价值由 E2E 覆盖 |
| 框架自身行为 | `@Body()` 能不能解析、`repo.save()` 会不会写库——测的是框架不是你的代码 |
| 私有方法、getter、简单 mapper | 测公开行为。私有方法随重构消失，测它等于给重构上锁；mapper 里有脱敏或计算逻辑时另说，那已经算业务了 |
| 真调三方 API | 会把 CI 变成随机失败机器。换成 mock，另外单独放一组可选执行的契约测试 |

### 覆盖率：一张地图，不是一个分数

- 覆盖率回答的是「哪里一次都没跑到」，**不回答「测得好不好」**。一个只有 `expect(true).toBe(true)` 的用例照样能把覆盖率拉满。
- 看**分支覆盖（branch）**，别看行覆盖。行覆盖 90% 而分支覆盖 40% 是常态，说明 `if` 的另一半从没进去过。`collectCoverageFrom` 要排掉 `main.ts`、`*.module.ts`、DTO 和生成的代码，否则数字被样板文件稀释。
- 门槛设在**新增代码**上（diff coverage）比设全局 80% 有用得多——全局阈值的典型后果是有人给 getter 补测试凑数。
- 覆盖率上不去，多数时候是设计问题不是勤奋问题：一个方法里塞了 IO、分支和副作用，怎么 mock 都难受。**这时候该拆方法，不是写更多 mock。**

---

## API 版本控制

接口上线后要改，老客户端还在调旧的——尤其是 App，用户不升级你就得一直伺候。Nest 内置了多版本共存：同一个路由，按版本号分发到不同 handler。

### 四种版本号载体

```typescript
// main.ts
app.enableVersioning({
  type: VersioningType.URI,      // /v1/orders，前缀默认是 v，可以 prefix: 'api/v' 或 prefix: false
  defaultVersion: '1',           // 不带版本号时按 v1 处理；也接受数组或 VERSION_NEUTRAL
})
```

另外三种只是换个载体，开关同样是一行：

```typescript
app.enableVersioning({ type: VersioningType.HEADER, header: 'X-API-Version' })
app.enableVersioning({ type: VersioningType.MEDIA_TYPE, key: 'v=' })   // Accept: application/json;v=2
app.enableVersioning({
  type: VersioningType.CUSTOM,
  // 返回版本号字符串（或数组，按优先级从高到低）；返回空字符串等于谁都匹配不上
  extractor: (req: Request) => (req.headers['x-app-build'] as string) ?? '1',
})
```

| 类型 | 客户端怎么带 | 优点 | 代价 |
|---|---|---|---|
| `URI` | `GET /v1/orders` | 日志、浏览器地址栏、CDN 缓存 key 里都能直接看见版本，排查最省事 | URL 里混进了非资源信息；**不支持 `VERSION_NEUTRAL`** |
| `HEADER` | `GET /orders` + 自定义头 | URL 干净 | 抓包和日志里看不见版本，CDN 要配 `Vary` 否则缓存串版本 |
| `MEDIA_TYPE` | `Accept: application/json;v=1` | 最符合 HTTP 语义 | 客户端最难写，前端同学第一次接都要问一遍 |
| `CUSTOM` | 自己实现 `extractor(request)` 返回版本号 | 能做灰度：按用户 ID 尾号、按 App 版本号分流 | 规则藏在一个函数里，别人看路由看不出行为 |

对外的公开 API 用 `URI`，判断依据很实际：**出问题时能不能从一行访问日志里看出调的是哪个版本。** `CUSTOM` 的 extractor 返回空字符串就匹配不上任何版本，等于 404，可以拿来做「灰度名单外的人不给用」。

### 版本标在哪

```typescript
@Controller({ path: 'orders', version: '2' })      // 控制器级：整个 controller 都是 v2
export class OrdersV2Controller {}

@Version('2') @Get('summary') summaryV2() {}       // 方法级：个别接口升级
@Version(['1', '2']) @Get(':id') findOne() {}      // 数组：两个版本共用一个实现

@Controller({ path: 'health', version: VERSION_NEUTRAL })   // 与版本无关：健康检查、webhook
export class HealthController {}
```

> ⚠️ 路由**按注册顺序从上往下匹配**。一个 `VERSION_NEUTRAL` 的 controller 排在版本化 controller 前面，会把后面所有版本的同名路由全吃掉，表现为「v2 怎么改都不生效」。把 NEUTRAL 的放最后，或者各版本一个独立 controller。另外 `URI` 类型不支持 `VERSION_NEUTRAL`，用它就必须显式给版本号。

推荐的落地形态：**DTO 分版本、Controller 分版本、Service 共享一份**。`CreateOrderV1Dto` / `CreateOrderV2Dto` 各自声明自己的字段和校验规则，两个 controller 各自把入参转成 Service 的内部模型，业务逻辑只有一处。

不要在一个方法里写 `if (version === '2')`。它的问题不是丑，是**两个版本会互相污染**：改 v2 的默认值时顺手改坏 v1，而 v1 的用例未必跑得到那条分支；半年后这种 if 会散落十几处，谁都不敢删。反过来说，如果共享的 Service 真的必须为某个版本分叉，那是「该拆成两个方法」的信号，不是「该加个分支」的信号。DTO 拆分的写法见 [DTO、序列化与 Swagger](/guide/nestjs-dto)。

### 该升版本，还是兼容改造

这是本节唯一真正需要判断力的地方。判断标准一句话：**只加不删不改语义的，兼容；其余的，升版本。**

| 改动 | 兼容？ | 做法 |
|---|---|---|
| 响应加一个字段 | 兼容 | 直接加。除非客户端做了严格白名单校验（少见，但 gRPC / 强类型客户端会） |
| 请求加一个可选字段 | 兼容 | 直接加，服务端给默认值 |
| 请求加一个必填字段 | 不兼容 | 先加成可选 + 默认值，监控到调用方都传了再收紧 |
| 删字段、改字段名 | 不兼容 | 升版本。老版本继续返回旧字段，文档标 deprecated |
| 改字段类型（`number` → `string`、ID 换成雪花） | 不兼容 | 升版本。这类最容易被当成小改动然后炸掉客户端 |
| **改语义**（`status` 加了新枚举值、金额从元变分） | 最危险 | 结构没变，客户端不报错，行为悄悄错到没人发现。必须升版本，或者换个新字段名 |
| 改分页协议、改错误码体系、收紧校验 | 不兼容 | 这些是全局契约，升版本。收紧校验前先在日志里统计有多少请求会被新规则拒掉 |

移动端要额外保守：**Web 发一次版全世界就都是新的，App 不行。** 老版本要活到「还在用它的用户少到可以接受」为止，这个时间由用户升级曲线决定，不由你决定。

还有一层成本要认：开一个 v2 的真实代价不在 `@Version('2')` 那一行，而在 Service 要长出两条路径、DTO 要维护两套、测试要跑两遍、迁移要同时满足两个版本的读写。**版本数是乘法不是加法**，所以多数团队的实际做法是：日常改动死守向后兼容（只加字段 + feature flag 控制新行为），只在整体重构时才开新版本，并且**同时在线的版本数控制在两个**。

### 老版本怎么下线

下线是六步，顺序不能换——前两步不做，后面每一步都是在赌：

1. **先有数据再谈下线。** 把版本号打进访问日志和指标标签（见 [日志与可观测性](/guide/nestjs-logging)），没有调用量曲线的下线通知只是许愿。
2. **公告给到具体日期**，对内两周量级，对外三到六个月，移动端按升级曲线定。
3. **响应头告知**：`Sunset` 头（RFC 8594）给下线时间，`Deprecation` 头 + `Link` 指向迁移文档，写成 Interceptor 挂在老版本 controller 上。
4. **盯残余调用量**，按 API key / UA / 用户 ID 定位到还在调的那几家主动去推。剩下的通常是「没人维护的老服务」和「一个忘了升级的定时脚本」。
5. **停服演练**：低峰期返回 410 十分钟再恢复，让沉默的调用方浮出水面，比直接下线安全得多。正式下线要返回 **`410 Gone` 而不是 404**——404 是「没有这个东西」，410 是「以前有，现在没了」，调用方看错误码就知道去查迁移文档。
6. **删代码。** 路由删了但 Service 里的 `if (isV1Shape)` 分支留着，是技术债最主要的来源。下线任务不包含这一步就等于没做完。

```typescript
@Injectable()
export class SunsetInterceptor implements NestInterceptor {
  intercept(ctx: ExecutionContext, next: CallHandler) {
    const res = ctx.switchToHttp().getResponse<Response>()
    res.setHeader('Deprecation', 'true')
    res.setHeader('Sunset', 'Tue, 30 Jun 2026 23:59:59 GMT')
    res.setHeader('Link', '<https://docs.example.com/migrate-v2>; rel="deprecation"')
    return next.handle()
  }
}
```

---

## 安全加固与 CORS

这一节是清单式的：单独哪一条都不难，漏一条就可能是一次事故。

### helmet：每个响应头分别防什么

```typescript
import helmet from 'helmet'      // npm i helmet

app.use(helmet())                // main.ts 里，要在注册路由之前
```

| 响应头 | 防什么 | 注意 |
|---|---|---|
| `Content-Security-Policy` | XSS：限制脚本、样式、图片能从哪儿加载 | 纯 JSON API 收益有限，但它会挡掉 Swagger UI 的内联脚本——Swagger 打开空白先怀疑这个 |
| `Strict-Transport-Security` | 降级攻击：浏览器记住这个域名只走 HTTPS | 必须全站 HTTPS 才能开，`includeSubDomains` 想清楚再加，回滚要等浏览器缓存过期 |
| `X-Content-Type-Options: nosniff` | 浏览器猜 MIME 把上传的文本当 HTML / JS 执行 | 和下面「上传目录」那条是同一件事的两端 |
| `X-Frame-Options` / CSP `frame-ancestors` | 点击劫持：你的页面被别人 iframe 套壳 | 自己有嵌入需求时改成 `SAMEORIGIN` 或白名单 |
| `Referrer-Policy` | URL 里的 token、订单号顺着 Referer 泄漏给第三方 | |
| 移除 `X-Powered-By` | 少暴露一层技术栈指纹 | 防御力很弱，但免费 |
| `X-XSS-Protection: 0` | 现代浏览器已移除这个过滤器，它本身还能被利用 | helmet 显式设 0 是**对的**，不是漏配 |

前后端分离时最需要这些头的其实是**前端站点那台服务器**（nginx / CDN），因为 XSS 和点击劫持攻击的是 HTML 页面。Nest 这边配了不亏——Swagger、SSR 页面、直接返回 HTML 的回调页都吃这套。nginx 侧怎么配见 [nginx 核心配置](/guide/nginx-core)。

### CORS：它到底管住了什么

必须先纠正的误解：**CORS 不拦请求，它只决定「浏览器要不要把响应交给 JS」。** 跨域的简单请求（GET、表单 POST）照样会到达服务端并执行副作用，只是响应被浏览器扣下了。所以 CORS **不是**权限控制，真正的门是 Guard 里的鉴权；CSRF 也是另一件事，见下一小节。服务端到服务端的调用（curl、后端互调）完全不受同源策略约束，因为没有浏览器。

```typescript
const WHITELIST = config.get<string>('ALLOWED_ORIGINS').split(',')

app.enableCors({
  // 固定域名用数组就够；要放行 PR 预览环境这类动态子域，就得用函数
  origin: (origin, cb) => {
    if (!origin) return cb(null, true)          // 同源请求、curl、服务端调用不带 Origin
    const ok = WHITELIST.includes(origin) || /^https:\/\/pr-\d+\.preview\.example\.com$/.test(origin)
    cb(ok ? null : new Error(`Origin not allowed: ${origin}`), ok)
  },
  methods: ['GET', 'POST', 'PATCH', 'DELETE'],
  allowedHeaders: ['Content-Type', 'Authorization'],
  exposedHeaders: ['X-Request-Id'],     // 不写在这里，前端 JS 读不到自定义响应头
  credentials: true,
  maxAge: 86400,                        // 预检结果缓存一天
})
```

> ⚠️ 函数形式最容易出的两个错：图省事写成 `cb(null, true)` 无条件放行，效果等于 `*` 却还带着凭证；正则不加锚点、不转义点号，`/preview\.example\.com/` 少了 `^$` 就会把 `https://preview.example.com.evil.io` 一起放进来。白名单永远要整串精确比对。

**为什么 `origin: '*'` 和 `credentials: true` 不能一起用**：规范禁止携带凭证的请求配通配符——浏览器拿到 `Access-Control-Allow-Origin: *` 而请求带了 cookie 时直接判失败，控制台报 CORS 错误。`Allow-Headers` / `Allow-Methods` 同理不能用 `*`。这个限制不多余：`*` 加凭证等于「任意网站都能带着用户的 cookie 读你的接口」。正确做法永远是白名单 + 回显具体 Origin。

**预检（OPTIONS）**是浏览器发现请求「不简单」时先发一个问句。触发条件包括自定义头（`Authorization` 就算）、`Content-Type: application/json`、`PUT` / `PATCH` / `DELETE`——也就是说**你写的绝大多数接口都会先来一次预检**。三个相关的坑：

- 预检**不带业务身份**（没有 cookie、没有 `Authorization`）。在 nginx 或全局中间件里做鉴权时必须放行 OPTIONS，否则前端看到的是「CORS 错误」而不是 401，能查半天。Nest 的 `enableCors` 在路由之前处理，正常用不会踩。
- `maxAge` 不配，每个请求都多一次往返，跨洋链路上体感直接慢一倍。跨域带 cookie 时，cookie 本身还要 `SameSite=None; Secure`，少一个都不发。

### CSRF：token 放在哪，决定了要不要防

CSRF 成立的前提是**浏览器会自动带上凭证**。凭证放哪，直接决定要不要额外做防护：

| 凭证放在哪 | 跨站请求会自动携带吗 | 要不要 CSRF token |
|---|---|---|
| `Authorization: Bearer <jwt>` | 不会。这个头必须由 JS 显式加，而攻击者页面上的 JS 读不到你域名下的存储 | **不需要** |
| Session cookie，或把 JWT 写进 cookie | 会。攻击者页面里一个自动提交的表单就带上了 | **需要**，至少要配 `SameSite` |

所以「用了 JWT 就不用管 CSRF」只在 JWT 走 header 时成立。一旦为了 `httpOnly` 把 JWT 塞进 cookie，就同时继承了 cookie 的 CSRF 风险，防护是三件套：`SameSite=Lax`（挡住大部分跨站表单，但真跨站的前端就用不了）、双提交 cookie 或服务端下发 CSRF token、以及对写操作校验 `Origin` / `Referer`。header 方案换来的代价是 XSS 风险——脚本能读到 token。两种存法的完整取舍见 [认证与登录状态](/guide/nestjs-auth)。

再强调一次上一小节的结论：**CORS 不防 CSRF。** 跨站表单 POST 是简单请求，压根不触发预检，请求到达服务端时副作用已经发生了，浏览器只是没把响应交给 JS。

### 限流：按什么维度限，比限多少更重要

限流分三层，各管一段，不能互相替代：

| 层 | 挡什么 | 为什么别的层挡不了 |
|---|---|---|
| 网关（nginx / 云 WAF） | IP 级洪水、慢连接、扫描流量 | 这些流量根本不该进 Node 进程，见 [nginx 核心配置](/guide/nginx-core) |
| 应用（`@nestjs/throttler`） | 按用户、按接口的业务配额：「每人每分钟一条短信」「免费用户每天 20 次对话」 | 需要用户身份和套餐信息，网关拿不到 |
| 数据库 / 下游 | 连接池上限、下游并发上限 | 兜底，防止一个慢查询拖垮全站 |

```typescript
// app.module.ts，npm i @nestjs/throttler
ThrottlerModule.forRoot([
  { name: 'default', ttl: 60_000, limit: 100 },                       // 兜底：每分钟 100
  { name: 'login', ttl: 60_000, limit: 5, blockDuration: 300_000 },   // 登录：每分钟 5 次，超了锁 5 分钟
])

@UseGuards(ThrottlerGuard)
@Controller('auth')
export class AuthController {
  @Throttle({ login: { limit: 5, ttl: 60_000 } })   // 命名限流器必须在装饰器里点名
  @Post('login')
  login(@Body() dto: LoginDto) {}

  @SkipThrottle({ default: true })                  // 不点名等于不生效，这是最常见的误用
  @Get('captcha')
  captcha() {}
}
```

| 维度 | 适合 | 缺陷 |
|---|---|---|
| IP | 未登录接口：登录、注册、发验证码、忘记密码 | NAT 出口会连坐（一个公司共用配额）；攻击者换 IP 成本很低 |
| 用户 ID / API key | 登录后的业务配额 | 攻击者批量注册账号就绕过了，所以注册接口本身必须按 IP 限 |
| 账号 + IP 组合 | 登录接口的正确答案 | 只按 IP 挡不住分布式撞库；只按账号会被人拿来锁死别人的账号 |

三条必须知道的：

- **默认按 IP 识别，反代后面必须开 `trust proxy`**，否则 `req.ip` 拿到的全是网关地址，整站共用一个配额，一个人触发全站 429。Express 侧 `app.set('trust proxy', 1)`，Fastify 侧配 `trustProxy`，再继承 `ThrottlerGuard` 覆盖 `getTracker()` 取真实客户端 IP——改成按用户限流也是覆盖这个方法。
- **默认存储是单进程内存**，多实例部署时每个实例各算一份，实际额度放大成 N 倍，必须换 Redis 存储适配器。
- 登录接口别用「失败 N 次硬锁账号」，那会变成拒绝服务工具（我锁死你的账号）。**递增延迟 + 超阈值强制验证码**是更好的形态，配合 `blockDuration` 用。`ThrottlerGuard` 抛的 `ThrottlerException` 就是 429，前端按这个状态码做退避重试。

### 输入这一侧：whitelist 和 SQL 注入

`ValidationPipe` 的 `whitelist` 不只是清洁工，它是**越权写入的最后一道防线**：

```typescript
app.useGlobalPipes(new ValidationPipe({
  whitelist: true,              // DTO 上没声明的字段直接剥掉
  forbidNonWhitelisted: true,   // 更严：出现未声明字段直接 400
  transform: true,              // 按 DTO 类型转换，配合 @Type() 用
}))
```

防的是这个场景：注册接口的 DTO 只声明了 `email` / `password`，攻击者多传一个 `role: 'admin'` 或 `balance: 999999`，而你的 Service 写的是 `repo.save({ ...dto })`——字段就这么进库了。这类漏洞叫 mass assignment，是权限提升最省力的路径。两道防线一起上：**开 `whitelist`，并且不要 `save({ ...dto })` 铺开整个 body，显式挑字段。** 校验细节见 [参数校验与异常处理](/guide/nestjs-validation-filter)、[DTO 与序列化](/guide/nestjs-dto)。

SQL 注入方面，用 ORM 基本免疫，原因是**参数化**：`find({ where: { name } })` 和 QueryBuilder 的 `:name` 占位符会把 SQL 文本和参数值分开发给驱动，值永远不会被当语法解析，引号怎么拼都只是字符串内容。仍然会出事的只有三个地方：

```typescript
qb.where(`u.name = '${keyword}'`)             // ❌ 拼进条件字符串，参数化被绕过
qb.where('u.name = :keyword', { keyword })    // ✅ 占位符

// ❌ 列名和排序方向不能参数化，拼进去就是注入口：qb.orderBy(`u.${sortField}`, sortOrder)
const ALLOWED = { createdAt: 'u.created_at', price: 'u.price' } as const     // ✅ 只能白名单枚举
qb.orderBy(ALLOWED[sortField] ?? ALLOWED.createdAt, sortOrder === 'ASC' ? 'ASC' : 'DESC')

dataSource.query(`SELECT * FROM orders WHERE id = ${id}`)     // ❌ 裸 SQL 拼变量
dataSource.query('SELECT * FROM orders WHERE id = ?', [id])   // ✅ 裸 SQL 也支持参数
```

**排序字段和分页参数是实战中最常见的注入口**，因为它们「看起来只是个字符串」。查询写法见 [TypeORM 实战](/guide/nestjs-database)。

### 密码存储：慢才是特性

```typescript
import * as bcrypt from 'bcrypt'

const COST = Number(config.get('BCRYPT_COST') ?? 12)        // 从配置读，方便随硬件往上调
const passwordHash = await bcrypt.hash(plain, COST)         // salt 自动生成，并编码进结果串里
const ok = await bcrypt.compare(plain, user.passwordHash)   // 恒定时间比较，不要自己写 ===
```

- **为什么不用 MD5 / SHA-256**：它们是为「快」设计的，GPU 一秒能算几十亿次，常见密码用彩虹表直接反查。密码需要的恰恰相反——**慢，而且每人一个 salt**，这就是 bcrypt / scrypt / argon2 这类 KDF 存在的理由。「SHA-256 加个 salt」也不够：salt 只挡彩虹表，挡不住针对单个哈希的暴力枚举，因为单次计算还是太快。
- **cost（salt rounds）怎么选**：cost 每加 1，耗时翻一倍。选法不是背一个数字，而是**在目标机器上压一遍，取单次 hash 落在 100–250ms 的那个值**，当前硬件上通常是 12～13。太低挡不住离线爆破；太高会让登录接口变成最省力的 CPU 打击面，所以它必须和限流一起配。
- **cost 是可以往上升的**：用户登录成功那一刻你手里正好有明文，检查存量哈希的 cost 低于当前配置就重新 hash 存回去，无感迁移。
- 两个细节：bcrypt **只取前 72 字节**，更长的部分不参与计算，要支持长口令就先 SHA-256 再 bcrypt，或者直接用 `argon2id`；`bcrypt` 是原生模块，Alpine 镜像里要么装编译链要么换 `bcryptjs`（见 [Dockerfile 实践](/guide/dockerfile-practice)）。
- 明文和哈希都**不许进日志**，包括异常上下文和 ORM 的 SQL 日志（对应文末清单里的 `logging: true`）。密码强度规则写在 DTO 里，别散在 Service（见 [参数校验与异常处理](/guide/nestjs-validation-filter)）。

### 文件与依赖：两个容易漏的口子

上传是最容易被打穿的入口——你在别人的控制下往自己的磁盘写文件：

- **重命名，不要用原始文件名。** 原名里可能带 `../../`（路径穿越）、超长名、控制字符、和系统文件同名。用 UUID + 白名单扩展名。
- **别信 `mimetype` 和扩展名**，都是客户端说了算的。按文件头字节判断真实类型（`file-type` 这类库），见 [文件上传与大文件处理](/guide/nestjs-file-upload)。
- **上传目录不能落在会被解释器执行的路径下。** nginx 里给那个 `location` 明确关掉脚本处理，只做静态返回。能上传 + 目录能执行 = 直接拿 shell。
- **下载带 `Content-Disposition: attachment` 和 `nosniff`。** 关键在 HTML 和 SVG——SVG 里可以写 `<script>`，浏览器直接渲染它就是一次同源 XSS。最稳的是放对象存储 + 独立域名，和主站不同源，XSS 也偷不到主站 cookie。

依赖漏洞这侧，`npm audit --omit=dev --audit-level=high` 放进 CI 只卡生产依赖的高危：

- `npm audit fix` 只在 semver 兼容范围内升；`--force` 会跨 major，**别放进 CI**，它能一次性把项目搞挂。
- lockfile 必须提交，CI 用 `npm ci` 而不是 `npm install`——后者按 semver 范围拉新版本，等于每次构建的依赖树都可能不一样。
- 报告要人读：`audit` 不区分「漏洞在你真正走到的代码路径上」还是「在某个构建工具的深层依赖里」，高危也可能完全打不到你。当分级信号用，别当必须清零的指标。自动化交给 Dependabot / Renovate 定期开 PR。
- 加新依赖时警惕**投毒和仿名包**（`node-fetch` vs `node--fetch` 这种）：看下载量、看最后提交时间、看有没有 `postinstall` 脚本。

### 上线前要关掉的东西

生产环境事故里有相当一部分不是「没做防护」，而是「开发期的方便配置忘了关」。

| 项 | 不关会怎样 | 怎么做 |
|---|---|---|
| Swagger UI | 白送攻击者一份完整接口地图，含参数结构和校验规则 | 生产不 `SwaggerModule.setup()`，或者挂内网 + Basic Auth |
| 详细错误堆栈 | 泄漏文件路径、依赖版本、有时连 SQL 语句都带出来 | 全局 Filter 里生产只返回 code + message，堆栈只进日志 |
| `synchronize: true` | TypeORM 按 Entity 直接改表结构，改错一个字段名就是丢一列数据 | 永远 `false`，结构变更走 migration |
| ORM `logging: true` | 日志量爆炸，参数里的手机号、密码明文一起进日志文件 | 只留慢查询日志 |
| `.env` 进镜像或进仓库 | 密钥泄漏，而且 git 历史删不干净 | 环境变量 / 密钥管理服务注入，`.env*` 一律 gitignore |
| 弱 JWT secret、默认密码 | token 可以被伪造 | 从配置读 + 启动时校验长度，缺失就崩（[动态模块与配置管理](/guide/nestjs-dynamic-module)） |
| CORS 图省事配成 `*` | 任意站点的 JS 都能读你的接口响应 | 白名单，从配置读 |
| `--inspect` 调试端口、REPL | 暴露在公网等于给 shell | 生产启动命令里不能有 `--inspect`；容器只暴露业务端口 |
| 健康检查返回内部细节 | 泄漏依赖拓扑、组件版本 | liveness 只返回存活，详细信息走内网（[日志与可观测性](/guide/nestjs-logging)） |
| 未鉴权的管理接口 | 最直接的一类事故 | 全局 `APP_GUARD` 默认拒绝，公开接口用 `@Public()` 显式开洞 |

最后一条值得单独强调：**默认拒绝比默认放行安全**。全局挂鉴权 Guard、公开接口靠装饰器白名单开洞，这样「新加的接口忘了加鉴权」的默认结果是 401 而不是全世界可访问。做法见 [认证与登录状态](/guide/nestjs-auth)。

---

## 三块内容的优先级

版本控制和安全加固基本是**一次性配置**：配完之后只要别退化就行，所以它们最适合做成 checklist 挨着过一遍。测试不一样，它是**每加一个功能都要跟着长**的东西，也是这三块里唯一需要持续投入的——所以真要排优先级，先把 `setupApp()` 或 `APP_PIPE` 那套全局切面的注册方式定下来（否则 E2E 从第一天起就是假绿灯），再补关键路径的 E2E，最后才追单测覆盖。

Nest 板块的完整篇目和建议阅读顺序见左侧导航：[简介与架构概览](/guide/nestjs-intro) 是入口和概念地图，[项目架构蓝图](/guide/nestjs-project-blueprint) 把这些能力组装成完整系统。配套的基础设施篇目在其他板块：[Redis 实战](/guide/redis-practice)、[nginx 核心配置](/guide/nginx-core)、[Dockerfile 实践](/guide/dockerfile-practice)、[MySQL 进阶](/guide/mysql-advanced)、[MongoDB 与 Mongoose](/guide/mongodb-mongoose)。

---

## 面试怎么说

**被问测试**：Nest 的测试分三层。单元测试用 `Test.createTestingModule` 把依赖换成 mock，只测 Service 的业务分支；集成测试连真库，验 SQL 和事务；E2E 用 supertest 打真实 `AppModule`，守注册登录下单这些关键链路。有两个坑我会主动提：**`main.ts` 里的全局管道在 E2E 里不会执行**，所以全局切面我用 `APP_PIPE` 这类 Provider 形式注册，测试才和线上一致；**测试数据隔离**优先「一次性容器 + 用例后清表」，事务回滚更快但要求被测代码和测试共用一条连接。至于覆盖率，我把它当「哪里没测到」的地图看，只盯分支覆盖和新增代码的覆盖率，不追全局百分比。

**被问版本控制**：`app.enableVersioning()` 有 URI / Header / Media Type / Custom 四种，对外 API 我选 URI——访问日志里一眼能看出调的是哪个版本；`VERSION_NEUTRAL` 匹配所有版本，但 URI 类型不支持它，而且路由按注册顺序匹配，NEUTRAL 放前面会把版本化路由吃掉。更重要的是**什么时候才该升版本**：加字段是兼容的，删字段、改类型、改语义必须升版本，其中「改语义」最危险，因为客户端不会报错只会悄悄错。下线老版本走「按版本埋点 → 公告 → 打 `Deprecation` / `Sunset` 响应头 → 盯残余调用量 → 演练停服 → 正式返回 410 并删掉兼容代码」。

**被问安全**：helmet 管响应头，CSP 防 XSS、HSTS 防降级、`nosniff` 防 MIME 嗅探；CORS 只决定浏览器要不要把响应交给 JS，**不是权限控制**，而且带 `credentials` 时 `origin` 不能配 `*`，规范直接禁止。限流分网关和应用两层，未登录接口按 IP、登录后按用户，登录接口单独更严并配 `blockDuration`，注意反代后面要开 `trust proxy`、多实例要换 Redis 存储。参数侧靠 `ValidationPipe` 的 `whitelist` 挡 mass assignment，SQL 注入因为 ORM 参数化基本免疫，例外是排序字段和列名这类不能参数化的位置，只能白名单。最后是上线前的清单：关 Swagger、关详细堆栈、`synchronize` 永远 `false`、`.env` 不进仓库、全局 Guard 默认拒绝。
