---
title: 微服务与跨语言通信
---

# 微服务与跨语言通信

> 什么时候不该拆微服务，拆了之后消息怎么走、契约怎么定、异常怎么传。重点在 gRPC——它是 Node 网关调用 Python 侧 Agent / embedding 服务的标准答案。

## 先劝退：大多数项目不需要微服务

微服务解决的是**组织和部署**问题，不是代码整洁问题。代码乱是因为模块边界没划清，把它拆成服务只会让函数调用变成网络调用——边界还是那个边界，只是原本编译期就能发现的错误挪到了运行时。

三个前提，**全部满足**才值得考虑拆：

1. **负载特征差异大，需要独立扩容。** 一个模块 QPS 是另一个的百倍，或者一个吃 CPU 一个吃内存，混在一个进程里只能整体扩。
2. **需要独立发布节奏。** 不同团队维护、发布频率差一个数量级，合在一起意味着每次上线都要互相等。
3. **边界已经稳定。** 在单体里它已经是一个清晰的模块，很少发生跨模块的改动。边界没摸清就拆，等于把重构成本从改代码升级成改协议。

还有一个独立于以上三条的理由：**技术栈不同**。Node 网关 + Python 推理服务这种组合，「拆」不是选择题，是既定事实——这也是本篇最后重点写 gRPC 的原因。

拆分要付的代价，每一项都是长期成本：

| 你付出的 | 具体表现 |
|---|---|
| 网络成为常态 | 本地方法调用变成可能超时、重试、半失败的远程调用，每个调用点都要想清楚失败怎么办 |
| 事务消失 | 跨服务没有 ACID，要上 saga、最终一致、幂等键，业务代码复杂度显著上升 |
| 调试链路变长 | 一个 500 要跨三个服务的日志才能拼出来，必须先有 traceId 和链路追踪 |
| 查询变难 | 每个服务一个库，一个列表页可能要聚合多次调用，或者做数据冗余再解决同步问题 |
| 部署与本地开发 | 本地要起五个进程加 MQ、注册中心；CI 从一条流水线变成 N 条 |
| 版本兼容 | 契约一改就要考虑灰度期间新旧并存，不能再「一起发」 |

**单体 + 模块化能撑很久。** Nest 的 Module 本身就是编译期的边界，配上一条纪律——「一张表只由拥有它的模块直接读写，别的模块调它的 Service」——边界就已经立住了。真到该拆的那天，工作量接近于搬目录。反过来，边界烂的单体拆出来的只会是分布式单体：所有缺点，没有优点。

---

## Nest 微服务的形态

`@nestjs/microservices` 提供的不是一个新框架，而是**另一个入口 + 另一套路由装饰器**。Module、Provider、DI、Guard、Interceptor、Pipe、Filter 全部照用。

```typescript
// ① 纯微服务：不监听 HTTP，只监听传输层
const app = await NestFactory.createMicroservice<MicroserviceOptions>(AppModule, {
  transport: Transport.TCP,
  options: { host: '0.0.0.0', port: 8877 },
})
await app.listen()

// ② 混合应用：一个进程同时对外提供 HTTP、对内监听消息
const app = await NestFactory.create(AppModule)
app.connectMicroservice<MicroserviceOptions>(
  { transport: Transport.TCP, options: { port: 8877 } },
  { inheritAppConfig: true },   // 让全局 Pipe / Filter / Interceptor 也作用到消息处理器上
)
await app.startAllMicroservices()
await app.listen(3000)
```

| | `create` | `createMicroservice` |
|---|---|---|
| 对外协议 | HTTP | 传输层协议（TCP / AMQP / gRPC / …） |
| 路由装饰器 | `@Get()` `@Post()` | `@MessagePattern()` `@EventPattern()` `@GrpcMethod()` |
| Middleware | 可用（HTTP 平台层的能力） | **不可用**，它只存在于 HTTP 平台 |
| Guard / Interceptor / Pipe / Filter | 可用 | 可用，但上下文是 `rpc` 不是 `http` |
| 参数装饰器 | `@Body()` `@Query()` `@Param()` | `@Payload()` 取数据、`@Ctx()` 取传输层上下文 |
| 健康检查 | HTTP 探针 | 没有 HTTP 端口，K8s 要用 `tcpSocket` 或 `exec` 探针 |

切面在两种上下文里怎么写成通用的（`context.getType()` 分支、`switchToRpc()`），见[请求生命周期](/guide/nestjs-pipeline)里 `ExecutionContext` 那节。

> 混合应用是实践中最常用的形态：一个服务对内用消息被别人调用，同时留一个 HTTP 端口给 `/health`、给 Swagger、给运维排查。纯微服务在 K8s 上第一次部署最常见的问题就是探针配不上——因为它根本没有 HTTP 端口。

---

## 传输层怎么选

| 传输 | 投递保证 | 是否持久化 | 吞吐 | 适用场景 |
|---|---|---|---|---|
| TCP（Nest 内置） | 无确认无重试，连接断了消息就丢 | 无 | 中 | 内网点对点、开发调试、只有两三个服务的项目 |
| Redis（Pub/Sub） | 至多一次，订阅者不在线就丢 | 无 | 高 | 无关紧要的广播：缓存失效、配置刷新 |
| RabbitMQ | 至少一次（ack + 重投 + 死信） | 队列和消息都可持久化 | 中高 | 任务分发、流量削峰、需要重试和补偿的异步流程 |
| Kafka | 至少一次，可按 offset 重放 | 磁盘日志，可保留数天 | 极高 | 日志 / 埋点 / 事件流，多个消费组各读一份 |
| NATS | 核心版至多一次，JetStream 至少一次 | 核心无，JetStream 有 | 极高 | 低延迟内部通信，运维负担小 |
| gRPC | 单次调用级别，失败要自己重试 | 无 | 高（二进制 + HTTP/2） | 跨语言同步调用、强契约、流式 |

**Nest 的 TCP 传输要单独说清楚**：它是一个私有的「JSON over TCP」协议，一个消息一个 JSON 帧。没有 broker、没有确认、没有重试、没有负载均衡，客户端里写死一个 `host:port`。它很适合理解微服务通信的形状，但两件事绝对不要用它做——**生产骨架**（一次网络抖动就丢消息）和**跨语言**（协议是 Nest 私有的，别的语言没有现成客户端）。

选型口径压缩成三句：**要保证不丢就走 broker；要低延迟同步拿返回值就用 gRPC；要跨语言就用 gRPC 或 broker。**

---

## 两种通信模式

```typescript
// ── 服务端
@MessagePattern('doc.count')                          // 请求响应，要返回值
countDocs(@Payload() data: { spaceId: number }) {
  return this.docService.count(data.spaceId)
}

@EventPattern('doc.published')                        // 发布订阅，不返回
async onPublished(@Payload() data: { docId: number }) {
  await this.searchService.index(data.docId)
}

// ── 客户端
const total = await firstValueFrom(this.client.send<number>('doc.count', { spaceId: 1 }))
this.client.emit('doc.published', { docId: 7 })
```

| | `send` + `@MessagePattern` | `emit` + `@EventPattern` |
|---|---|---|
| 语义 | 我要一个答案 | 我通知一件已经发生的事 |
| 返回值 | `Observable`，用 `firstValueFrom` 转 Promise | 不关心结果 |
| Observable 冷热 | **冷**：不订阅就根本不发出去 | **热**：立刻发出，不需要订阅 |
| 调用方是否等待 | 等，对端失败会传播过来 | 不等，失败通常只进日志 |
| 订阅者数量 | 一个 pattern 只该有一个处理器 | 可以多个服务各自订阅 |
| 耦合方向 | 调用方知道被调方存在 | 发布方不知道谁在听 |
| 失败处理 | 调用方负责超时、重试、降级 | broker 负责 ack、重投、死信 |

**默认原则：查询用 `send`，通知用 `emit`。** 命名跟着语义走——`send` 的 pattern 用动词（`doc.count`），`emit` 的 pattern 用过去式事件名（`doc.published`）。看到 `emit('doc.count')` 就知道有人写错了。

> ⚠️ 冷热的区别会咬人。`send()` 返回的 Observable 不订阅就什么都不会发生，所以 controller 里必须 `return` 它或者 `firstValueFrom` 一下；反过来 `emit()` 是热的，忘了 `await` 消息照样发出去，但你也拿不到 broker 的确认——要确认就得 `await lastValueFrom(...)`。

---

## ClientsModule：调用方这一侧

`ClientsModule` 是个标准动态模块，`register` / `registerAsync` 的命名约定和 `JwtModule`、`TypeOrmModule` 一致（为什么是这套命名，见[动态模块与配置管理](/guide/nestjs-dynamic-module)）。

```typescript
// 静态：地址写死，只适合本地
ClientsModule.register([
  { name: DOC_SERVICE, transport: Transport.TCP, options: { host: 'doc-svc', port: 8877 } },
])

// 异步：配置从 ConfigService 来，生产必须这样
ClientsModule.registerAsync([{
  name: DOC_SERVICE,
  imports: [ConfigModule],
  inject: [ConfigService],
  useFactory: (c: ConfigService) => ({
    transport: Transport.TCP,
    options: { host: c.getOrThrow('DOC_HOST'), port: c.getOrThrow<number>('DOC_PORT') },
  }),
}])
```

注入进来的是 `ClientProxy`：

```typescript
constructor(@Inject(DOC_SERVICE) private readonly docClient: ClientProxy) {}
```

`DOC_SERVICE` 用导出的常量而不是裸字符串 `'DOC_SERVICE'`——理由和[依赖注入](/guide/nestjs-di)里讲 token 类型时一样，拼错要能在编译期发现。

### $connect() 的时机

Nest 默认**懒连接**：第一次 `send` 时才建连。想在启动期就发现「对端不可达」，在 `onModuleInit` 里 `await this.docClient.connect()`。

代价是启动顺序被耦合了：对端没起来，本服务也起不来。在 K8s 里通常**不这么做**——Pod 启动顺序本来就不保证，宁可让首次调用失败并重试，也不要让一个依赖拖着整个部署起不来。把「对端可达」放到 readiness 探针里判断，比放到启动流程里更合适。

### 超时与重试

传输层的重连参数（TCP 的 `retryAttempts` / `retryDelay`）管的是**连接重建**，和「这次调用要不要重试」是两件事。调用级别的控制用 RxJS operator，因为 `send()` 本来就返回 Observable：

```typescript
await firstValueFrom(
  this.docClient.send<CountResult>('doc.count', dto).pipe(
    timeout({ each: 2000, with: () => throwError(() => new RequestTimeoutException('doc 服务超时')) }),
    retry({ count: 2, delay: 200 }),   // 只对读操作重试
    catchError(() => of({ total: 0, degraded: true })),   // 拿不到就降级，不要连带把自己拖死
  ),
)
```

三条纪律：**超时必须设**（不设就是无限等，一个慢下游能把上游的连接池占满）；**重试只给读操作**，写操作要重试就先有幂等键；**重试要有上限和退避**，否则下游抖动时你会亲手把它打死。RxJS operator 的选择见 [RxJS 与 Interceptor 实战](/guide/nestjs-rxjs-interceptor)。

---

## Monorepo 与 Library

服务一拆多，第一个现实问题是仓库怎么放。N 个服务 N 个仓库，公共的 DTO 和常量就得走 npm 私服：改一个字段要发版、要在三个仓库里升版本号，忘了升就是运行时才炸的契约不一致。Nest 的答案是 monorepo——一个仓库、一份 `node_modules`、多个能独立启动和部署的 app。

触发方式很隐蔽：**第一次执行 `nest g app` 时，CLI 会把项目从 standard 模式改造成 monorepo 模式**。

```bash
nest new doc-platform        # standard 模式，代码在 src/
cd doc-platform
nest g app search-svc        # ← 这一步做了改造
nest g library contracts     # 提示输入前缀，默认 @app
```

改造后根目录的 `src/` 和 `test/` 消失，原项目被平移进 `apps/` 下，和新 app 平级：

```bash
doc-platform/
├── apps/
│   ├── doc-platform/     # 原项目，现在当网关，对外 HTTP
│   └── search-svc/       # 新 app，可以是纯微服务
├── libs/
│   └── contracts/src/    # 共享代码，靠路径别名引用
├── nest-cli.json         # projects 字段是这套机制的索引
└── tsconfig.json         # paths 别名在这里
```

每个 app / lib 自带一份 `tsconfig.app.json`（`outDir` 写在里面），`node_modules` 全仓库只有一份。`nest-cli.json` 里多出 `monorepo: true` 和一个 `projects` 索引，每条记录该 project 的 `root` / `sourceRoot` / `entryFile` / `tsConfigPath`：

```json
{
  "monorepo": true,
  "sourceRoot": "apps/doc-platform/src",
  "projects": {
    "doc-platform": { "type": "application", "root": "apps/doc-platform", "entryFile": "main",
      "compilerOptions": { "tsConfigPath": "apps/doc-platform/tsconfig.app.json" } },
    "contracts": { "type": "library", "root": "libs/contracts" }
  }
}
```

> ⚠️ 顶层的 `sourceRoot` 指向**默认 project**。改造完之后 `npm run start:dev` 不带参数跑的还是原来那个 app，新建的 app 一行日志都不打——这是第一次用 monorepo 必卡一次的地方。跑别的要带名字：`nest start --watch search-svc`。

根 `tsconfig.json` 的 `paths` 由 `nest g library` 自动写入，两条别名都要有——不带 `/*` 的 `"@app/contracts": ["libs/contracts/src"]` 让 `from '@app/contracts'` 命中 barrel 文件，带 `/*` 的 `"@app/contracts/*": ["libs/contracts/src/*"]` 让你能深引用子路径。

CLI 命令都接一个 project 名：`nest start --watch search-svc` 跑指定 app，`nest build search-svc` 只构建它并产出 `dist/apps/search-svc/main.js`，不带名字则作用于默认 project，lib 也能单独 `nest build contracts`。

monorepo 模式下编译器从 tsc 换成 webpack，产物是打包后的单个 `main.js`。好处是部署镜像里不需要 `libs/` 目录；坏处是非 TS 资源（`.proto`、邮件模板、SQL 文件）不会自动进 `dist`，要在 `nest-cli.json` 的 `compilerOptions` 里显式声明 `"assets": ["**/*.proto"]` 和 `"watchAssets": true`。漏了这条的典型表现是 `start:dev` 看着正常、`build` 之后启动就报「proto 文件不存在」——因为 `join(__dirname, 'agent.proto')` 解析到的是 `dist` 里的路径。

### 什么该抽进 library

| 抽进 lib | 留在 app |
|---|---|
| 跨服务 DTO、消息 pattern 常量、`.proto` 文件 | 业务 Service |
| 公共 Guard / Interceptor / Filter（鉴权、traceId、响应包装） | Entity / Prisma schema：一张表只由拥有它的服务读写 |
| 基础设施封装（Redis client、对象存储、邮件） | 只有一个使用者的东西，等第二个出现再抽 |
| 错误码枚举、纯工具函数 | 改得最勤的模块 |

**判断标准一句话：抽进 lib 的东西，改它的时候你必须同时考虑所有 app。** 共享 Entity 是最常见的错误——它看起来只是复用类型，实际上把「每个服务一个库」的边界拆了，所有服务都能直接写别人的表。

一份 `node_modules` 的收益比省磁盘大得多：所有服务的 Nest、TypeScript、`class-validator` 版本天然一致，不会出现同一个 DTO 在两个服务里行为不同；升级依赖是一次 PR；本地一次 `npm i` 就能跑全部服务。代价是失去隔离——两个 app 需要同一个包的不同大版本时只能靠 npm alias 硬扛。

部署时**一个 app 一个镜像**：builder 阶段跑 `npm ci` + `nest build search-svc`，runtime 阶段只拷 `dist/apps/search-svc` 和生产依赖，入口是 `node dist/apps/search-svc/main.js`。`npm ci` 那一层对所有 app 都一样，构建缓存能复用；但运行进程必须独立，否则「独立扩容」这个拆分的首要理由就没了。多阶段构建见 [Dockerfile 实践](/guide/dockerfile-practice)。

---

## 服务发现与配置中心

前面 `ClientsModule` 那段代码有个隐藏假设：`DOC_HOST` 是一个固定地址。这个假设一上生产就破——doc 服务从 1 个实例扩到 3 个，调用方的配置里写什么？写第一个等于其余两个白扩，写一个列表则每次扩缩容都要改所有调用方的配置并重启。换机器、换端口、灰度一个新版本，同样都要改配置重启。限流阈值、功能开关这类要临时调的参数，改一次还得发一次版。

注册中心和配置中心解决的就是这两类问题，它们通常是同一个中间件的两种用法。

| 组件 | 职责 | 拆开就是这几件事 |
|---|---|---|
| 注册中心 | 谁在线、在哪 | **注册**（启动时写入 `服务名 → 实例地址`）、**心跳续约**（定期证明活着，停了就被摘掉）、**发现**（按服务名查当前实例列表，且变化时能收到通知） |
| 配置中心 | 参数放哪 | **集中存储**（一处修改、所有实例可见）、**变更推送**（改完主动通知，不用重启） |

### 用 Etcd 实现

Etcd 是带 watch 能力的分布式 KV 存储，K8s 自己的状态就存在里面。Node 侧用 `etcd3`，客户端是 `new Etcd3({ hosts: 'http://127.0.0.1:2379', auth: { username, password } })`。

**注册**靠 lease（租约）。lease 带 TTL，绑在 lease 上的 key 会随 lease 过期一起消失——「进程挂了自动摘掉」是存储层免费给的，不需要额外写健康检查：

```typescript
@Injectable()
export class RegistryService implements OnApplicationBootstrap, OnApplicationShutdown {
  private lease?: Lease
  private readonly key = `/services/doc-svc/${process.env.POD_NAME ?? randomUUID()}`

  async onApplicationBootstrap() {
    this.lease = client.lease(10)          // TTL 10s，etcd3 的 Lease 会在后台自动续约
    await this.lease.put(this.key).value(JSON.stringify({ host: HOST, port: PORT, version: VERSION }))
    this.lease.on('lost', () => this.onApplicationBootstrap())  // 续约彻底失败：重建并重注册
  }

  touch = () => this.lease?.keepaliveOnce()   // 健康探针里主动催一次，确认自己还挂在注册中心上
  onApplicationShutdown = () => this.lease?.revoke()  // 优雅下线：立刻摘掉，不等 TTL 过期
}
```

**发现**是按前缀读一把，**上下线自动感知**是对同一个前缀 watch。两个容易漏的点：watch 事件只说明「变了」，实例列表要重新读一遍；订阅之后要先主动读一次全量，别只等事件。

```typescript
async function watchInstances(service: string, onChange: (list: Instance[]) => void) {
  const prefix = `/services/${service}/`
  const refresh = async () => {
    const map = await client.getAll().prefix(prefix).strings()
    onChange(Object.values(map).map((v) => JSON.parse(v) as Instance))
  }
  const watcher = await client.watch().prefix(prefix).create()
  watcher.on('put', refresh).on('delete', refresh)
  await refresh()
}
```

**配置热更新**是同一套机制换个前缀，watch 到变化就替换内存里的值：`client.watch().prefix('/config/doc-svc/').create()`，然后 `watcher.on('put', (kv) => cache.set(kv.key.toString(), kv.value.toString()))`。

> ⚠️ 别用 Redis 顶替配置中心。Redis 的 keyspace notification 只能通知**已存在** key 上发生的事件，而配置项和实例 key 常常是动态创建的——「等一个还不存在的 key 出现」这件事 Redis 做不到，etcd 的前缀 watch 天生支持。

两个反直觉的点：**不是所有配置都适合热更新**——数据库连接串、连接池大小热更的意义很小（连接池要重建，风险比重启还高），真正值得热更的是开关、限流阈值、模型名、采样率；**发现之后还要负载均衡**——拿到三个实例，选哪个是调用方自己的事（轮询、随机、按响应时间加权），注册中心不管这一步。

### Etcd / Nacos / Consul 怎么选

| | Etcd | Nacos | Consul |
|---|---|---|---|
| 一致性协议 | Raft，CP | Raft，AP / CP 可切换 | Raft，CP |
| 数据模型 | 通用 KV，服务模型要自己用 key 约定拼出来 | 内建 service / instance，配置按 `dataId + group` 寻址 | 内建 service，KV 是另一套 |
| 自带配置中心 | 没有，它就是个 KV | 有，带控制台和灰度发布 | 有 KV，能力偏弱 |
| 生态 | 与 K8s 同源，云原生栈的默认选择 | Java / Spring Cloud Alibaba 生态，中文资料多 | HashiCorp 栈，配套服务网格 |
| 运维成本 | 低，单个二进制，但只有 `etcdctl` 没有 UI | 中，JVM 进程吃内存，但控制台让非开发也能改配置 | 中，有 UI |

粗口径：**Java 团队、或者需要非开发人员改配置，选 Nacos；纯 Node / 云原生栈选 Etcd；已经在用 HashiCorp 全家桶选 Consul。** 但更重要的结论是：**如果你已经在 K8s 上，这三个都不必自建。** Service 的 ClusterIP 加内部 DNS 就是注册与发现（Pod 增减由 Endpoints 自动维护，比自己写的心跳靠谱），ConfigMap / Secret 挂成文件或环境变量就是配置中心，改完 rollout 一次即可。自建注册中心只在两种情况下划算：**不在 K8s 上**，或者**需要客户端侧负载均衡、按版本灰度路由**这类 L4 轮询给不了的能力。不要为了「架构图上该有一个注册中心」引入一个自己不会运维的中间件。

---

## gRPC 跨语言通信

前面的传输层全是「Node 和 Node 说话」。真实项目里更常见的是 Node 网关要调 Python 写的推理服务、Go 写的高并发组件、Java 写的老系统。这时候需要一个**语言中立的契约**加一个**语言中立的传输协议**，这就是 gRPC：契约用 protobuf 写在 `.proto` 文件里，各语言用同一个文件生成自己的代码，传输走 HTTP/2 上的二进制帧。

### protobuf：契约先行

protobuf 是一种 IDL（接口描述语言）加二进制序列化格式。它和 JSON 的关键差别是**字段名不上线**——线上传的是「字段编号 + 值」，编解码双方靠同一份 `.proto` 知道 3 号字段叫什么、是什么类型。所以它比 JSON 小、比 JSON 快，代价是没有 `.proto` 就完全读不懂报文。

```protobuf
syntax = "proto3";

package agent;                        // 命名空间，Nest 侧的 options.package 要和它一致

service AgentService {                // 一个 service = 一组可远程调用的方法
  rpc Chat (ChatRequest) returns (ChatReply) {}
  rpc StreamChat (ChatRequest) returns (stream ChatChunk) {}   // 响应是流
}

message ChatRequest {
  string session_id = 1;              // = 1 是字段编号，不是默认值
  string prompt = 2;
  repeated string doc_ids = 3;        // repeated = 数组
  optional int32 max_tokens = 4;      // optional 让「没传」和「传了 0」能区分开
}
message ChatReply { string content = 1; int32 prompt_tokens = 2; int32 completion_tokens = 3; }
message ChatChunk { string delta = 1; bool done = 2; }
```

`stream` 关键字加在请求侧、响应侧或两侧，组合出四种模式：

| 模式 | proto 写法 | 典型场景 | Nest 侧形态 |
|---|---|---|---|
| unary | `rpc F (Req) returns (Rep)` | 普通 RPC 调用 | 返回值或 `Promise` |
| server-stream | `returns (stream Rep)` | LLM 逐 token 输出、日志跟随、进度推送 | 返回 `Observable` |
| client-stream | `(stream Req) returns (Rep)` | 上传音频分片、批量埋点后汇总 | `@GrpcStreamMethod()`，参数是 `Observable` |
| bidi | `(stream Req) returns (stream Rep)` | 实时语音转写、双向对话 | `@GrpcStreamMethod()`，进出都是 `Observable` |

### Nest 两侧的写法

服务端把 `.proto` 交给 `GrpcOptions`：`package` 对应 proto 里的 `package`，`protoPath` 是文件路径，`url` 是监听地址，`loader` 透传给 `@grpc/proto-loader`。

```typescript
const app = await NestFactory.createMicroservice<MicroserviceOptions>(AgentModule, {
  transport: Transport.GRPC,
  options: {
    package: 'agent',
    protoPath: join(__dirname, 'proto/agent.proto'),
    url: '0.0.0.0:50051',
    loader: { keepCase: false },   // 默认 false：proto 的 snake_case 转成 JS 的 camelCase
  },
})
await app.listen()
```

路由装饰器的两个参数是 proto 里的原始名字（大驼峰），方法名随你：

```typescript
@Controller()
export class AgentGrpcController {
  @GrpcMethod('AgentService', 'Chat')
  chat(data: ChatRequest): Promise<ChatReply> {
    return this.agent.answer(data)
  }

  // 服务端流：请求 unary、响应 stream，仍用 @GrpcMethod 但返回 Observable，
  // Nest 会订阅它、每次 emit 写一帧、complete 时关闭流
  @GrpcMethod('AgentService', 'StreamChat')
  streamChat(data: ChatRequest): Observable<ChatChunk> {
    return this.agent.stream(data)
  }
}
```

客户端流和双向流换成 `@GrpcStreamMethod('AgentService', 'Transcribe')`，此时参数本身就是一条 `Observable`，返回值也是 `Observable`；想拿原始 gRPC call 对象自己 `write` / `end`，用 `@GrpcStreamCall()` 这个逃生舱。

调用方注册照样走 `ClientsModule`，但注入进来的是 `ClientGrpc` 而不是 `ClientProxy`，要再调一次 `getService` 拿强类型 stub：

```typescript
// libs/contracts 里手写一份 TS 接口：方法名首字母小写、字段名转驼峰
export interface AgentServiceClient {
  chat(req: ChatRequest): Observable<ChatReply>
  streamChat(req: ChatRequest): Observable<ChatChunk>
}

@Injectable()
export class AgentClient implements OnModuleInit {
  svc!: AgentServiceClient
  constructor(@Inject(AGENT_PACKAGE) private readonly client: ClientGrpc) {}
  onModuleInit() { this.svc = this.client.getService<AgentServiceClient>('AgentService') }
}
```

> ⚠️ 三处命名不一致，全是踩过的坑：proto 里是 `StreamChat`，`@GrpcMethod()` 的第二个参数必须写 `'StreamChat'`（原名），而 `getService()` 返回的 stub 方法是 `streamChat`（首字母小写）；字段 `session_id` 到 TS 里是 `sessionId`。想保持 snake_case 就把两侧都配上 `loader: { keepCase: true }`，配一边就是永远收到 `undefined`。

### 重点场景：Node 网关调用 Python Agent 服务

这是 gRPC 在 AI 应用里最实际的用法：Nest 做网关，负责鉴权、限流、会话管理、对浏览器说 HTTP；Python 做 Agent，负责模型调用、检索、工具执行。两边共用上面那份 `agent.proto`。

Python 侧先用 `grpcio-tools` 生成 stub，产物是 `agent_pb2.py`（消息类）、`agent_pb2_grpc.py`（servicer 基类和 stub）、`agent_pb2.pyi`（类型提示）：

```bash
pip install grpcio grpcio-tools
python -m grpc_tools.protoc -I ./proto --python_out=./gen --grpc_python_out=./gen --pyi_out=./gen ./proto/agent.proto
```

> ⚠️ 生成的 `agent_pb2_grpc.py` 里是 `import agent_pb2` 这种绝对导入，放进包目录后会 `ModuleNotFoundError`。两个解法：把 `gen/` 加进 `sys.path`，或者生成后把导入改成相对导入。这是所有人用 Python gRPC 的第一个坎。

实现 servicer。方法名和 proto 里完全一致（大驼峰），server-stream 就是一个 `async` 生成器：

```python
import asyncio, grpc
from gen import agent_pb2, agent_pb2_grpc

class AgentServicer(agent_pb2_grpc.AgentServiceServicer):
    async def Chat(self, request, context):
        r = await run_agent(request.prompt, list(request.doc_ids))
        return agent_pb2.ChatReply(content=r.text, prompt_tokens=r.pt, completion_tokens=r.ct)

    async def StreamChat(self, request, context):
        async for delta in stream_agent(request.prompt):
            if context.cancelled():   # 浏览器断开会一路传到这里，及时停掉模型调用省钱
                return
            yield agent_pb2.ChatChunk(delta=delta, done=False)
        yield agent_pb2.ChatChunk(delta="", done=True)

async def serve():
    server = grpc.aio.server()                   # 用 aio 版，别用同步版的线程池 server
    agent_pb2_grpc.add_AgentServiceServicer_to_server(AgentServicer(), server)
    server.add_insecure_port("0.0.0.0:50051")    # 内网明文；跨网段要上 TLS
    await server.start()
    await server.wait_for_termination()

asyncio.run(serve())
```

Nest 侧把这条 gRPC 流直接转成 SSE 吐给浏览器。**这一段是 Nest 里最顺的一段管道**：`streamChat()` 返回的是 `Observable<ChatChunk>`，`@Sse()` 要的也是一条 `Observable`，中间只要 `map` 换个形状，不需要手写 pump、不需要处理背压。

```typescript
@Sse('chat/stream')
stream(@Query() dto: AskDto): Observable<MessageEvent> {
  return this.agentClient.svc
    .streamChat({ sessionId: dto.sessionId, prompt: dto.prompt, docIds: dto.docIds ?? [] })
    .pipe(
      takeWhile((chunk) => !chunk.done),            // done 那帧只是终止信号，不下发
      map((chunk) => ({ data: { delta: chunk.delta } }) as MessageEvent),
      timeout({ first: 15_000, each: 30_000 }),      // 首帧超时和帧间超时分开设
      catchError(() => of({ type: 'error', data: { message: '生成失败，请重试' } } as MessageEvent)),
    )
}
```

两个衔接细节：**浏览器断开 SSE 时 Nest 会 unsubscribe，unsubscribe 会取消底层的 gRPC 调用**，Python 侧的 `context.cancelled()` 因此会变 true——这条取消链路是 Observable 语义免费给的，用回调或裸 stream 都要自己拼。另外 SSE 只能 `GET`，长 prompt 塞不进 query，通常先 `POST` 建一个会话拿 `sessionId`，再用它开流。SSE 的重连、`retry`、Nginx 缓冲坑见[实时通信](/guide/nestjs-realtime)，RxJS operator 的选择见 [RxJS 与 Interceptor 实战](/guide/nestjs-rxjs-interceptor)。

### gRPC vs HTTP/JSON vs 消息队列

| | gRPC | HTTP + JSON | 消息队列 |
|---|---|---|---|
| 性能 | 高：二进制 + HTTP/2 多路复用 + 长连接 | 中：文本编解码、header 开销 | 看 broker，吞吐高但单条延迟不低 |
| 契约管理 | `.proto` 是唯一真相，编译期就能发现不匹配 | 靠 OpenAPI 文档和自觉，容易和实现漂移 | 靠约定，最弱 |
| 调试难度 | 高：curl 看不了，要 `grpcurl` 或反射 | 最低：浏览器、Postman、curl 都行 | 中：要进 broker 控制台看队列 |
| 浏览器可达 | 不可直连，要 grpc-web 或网关转 | 原生 | 不可达 |
| 流式支持 | 四种模式原生支持 | 只有 SSE / chunked 这种单向流 | 天然是流，但没有请求响应语义 |
| 跨语言成本 | 低：一份 proto 生成各语言代码 | 低但重复：每种语言各写一遍 client | 低：各语言都有成熟客户端 |

建议很明确：**对外一律 HTTP（浏览器和第三方只认它）；内部服务间同步调用用 gRPC；异步解耦、削峰、重试用队列。** 这不是三选一，是同一个系统里的三层。判断口径：调用方需要立刻拿到结果吗？需要 → gRPC；不需要且允许延迟 → 队列（见[消息队列](/guide/message-queue)）。

### 工程坑

| 坑 | 后果 | 怎么办 |
|---|---|---|
| proto 复制粘贴到各仓库 | 两边不同步，报文解析错位且不报错 | 单独一个 proto repo（git submodule 或发成包），或者上 buf 做集中管理和破坏性变更检查 |
| 改了字段编号 | 编号是线上格式的一部分，改编号等于换协议，老客户端读到错位的值 | 编号只增不改；删字段要 `reserved 3;` 占位，防止后人复用 |
| proto3 标量的默认值陷阱 | 不加 `optional` 时，`0` / `""` / `false` 在线上根本不传，接收端分不清「没传」和「传了零值」 | 需要区分就加 `optional`（proto 3.15+ 恢复了 field presence），或用 `google.protobuf.Int32Value` 包装类型。`temperature = 0`、`top_k = 0` 这类合法零值必须这么处理 |
| 让浏览器直连 gRPC | 浏览器 fetch 拿不到 HTTP/2 trailer，跑不通 | grpc-web + 代理，或者就按本篇的做法用网关转 REST / SSE |
| 默认 4MB 消息上限 | 传 embedding 大数组、长文档直接报 `RESOURCE_EXHAUSTED` | 调 `grpc.max_receive_message_length`，或者改成流式分片传 |
| 在 K8s 上用 ClusterIP 调 gRPC | Service 是 L4 轮询，HTTP/2 长连接建好就粘在一个 Pod 上，扩容后流量不均 | headless Service + 客户端 `round_robin` 负载均衡策略，或者交给 service mesh |

---

## 微服务的横切问题

### 异常怎么跨进程

在 rpc 上下文里 `throw new NotFoundException()` 不会变成 404——微服务没有 HTTP 状态码这个概念，调用方拿到的是一个被序列化过的对象，形状和你预期的不一样。跨进程要抛 `RpcException`：

```typescript
// 被调方：抛语义化的错误码 + 消息
throw new RpcException({ code: status.NOT_FOUND, message: '文档不存在' })

// 被调方：把内部抛的 HttpException 统一翻译成 RpcException，别让它原样漏出去
@Catch(HttpException)
export class HttpToRpcFilter implements RpcExceptionFilter {
  catch(e: HttpException) {
    return throwError(() => new RpcException({ code: toGrpcCode(e.getStatus()), message: e.message }))
  }
}

// 调用方：把 gRPC code 翻译回 HTTP 语义，别一律 500
catchError((e: { code?: number }) => {
  if (e.code === status.NOT_FOUND) throw new NotFoundException()
  if (e.code === status.INVALID_ARGUMENT) throw new BadRequestException()
  throw new ServiceUnavailableException('下游服务暂时不可用')
})
```

**下游的错误码不要原样透给前端。** 下游返回 `UNAVAILABLE`（没起来）对前端来说是 503 或者一份降级数据，不是「未找到」。翻译表写在网关一处，别每个 controller 各抄一遍。

### 熔断、追踪、事务

超时与重试的三条纪律在上一节讲过，不重复，这里补三件事。

**熔断**是重试的补充：错误率超过阈值就直接快速失败（open），过一段时间放一个请求探测（half-open），成功再恢复（closed）。Node 侧可以用 `opossum`，也可以自己维护一个滑动窗口加开关。关键认知是**熔断保护的是自己而不是下游**——下游已经挂了，继续打过去只是让自己的连接池和事件循环被慢请求占满，最后一个服务故障拖垮整条链路。

**traceId 透传**：HTTP 用 header，gRPC 用 `Metadata`（stub 方法的第二个参数就收它），消息队列放进消息头。Nest 侧用 `AsyncLocalStorage` 存当前 traceId，一个全局 Interceptor 负责「进来时读、出去时带上」，业务代码完全不用感知。生成、落日志、串联的完整做法见[日志与监控](/guide/nestjs-logging)。要标准化就直接上 W3C `traceparent` 和 OpenTelemetry，别自己造格式。

**分布式事务尽量不要做。** 2PC 在 Node 生态里几乎没有可用实现，而且它要求协调者在整个业务逻辑期间持有锁——跨网络持有锁是最容易演变成雪崩的设计。可行的组合是「本地事务 + 事件 + 幂等 + 对账」：业务写自己的库时，在**同一个事务里**插一条待发消息（outbox 表），后台任务把它投进队列，下游幂等消费；再加一个定时对账任务扫出两边不一致的数据。语义从「要么都成功要么都失败」退化成「最终一致、中间态可见」，大多数业务能接受这个退化。能接受就别上 saga——saga 的补偿动作往往根本写不出来（邮件发出去了收不回来）。幂等消费的实现见[消息队列](/guide/message-queue)。

---

## 什么时候真该拆

| 维度 | 不用拆 | 可以考虑 | 该拆 |
|---|---|---|---|
| 团队规模 | 一个团队，review 能覆盖全部模块 | 两三个小组，偶尔冲突 | 多团队各管一块，PR 互相阻塞 |
| 部署频率 | 一起发，一周一次 | 某个模块想单独热修 | 不同模块的发布频率差一个数量级 |
| 故障隔离 | 挂了一起挂可以接受 | 有一个模块特别不稳定 | 某个模块的故障绝对不能影响主流程（支付、登录） |
| 技术栈异构 | 全是 Node | 有一个小脚本用 Python | 核心算力在 Python / Go，不可能重写 |

四个维度里**技术栈异构是唯一一条能单独成立的理由**——Node 网关调 Python Agent 不是「要不要拆」的问题，是已经拆了，你只需要选对通信方式。其余三条要凑够两条以上再动手。

渐进路线，每一步都能停下来：

```mermaid
flowchart LR
    A[单体] --> B[模块化单体] --> C[Monorepo 多 app] --> D[真微服务]
```

| 阶段 | 长什么样 | 什么信号推你走下一步 | 这一步的代价 |
|---|---|---|---|
| 单体 | 一个 app、一个库 | 模块之间互相 import 到没人敢改 | 无 |
| 模块化单体 | 清晰的 Module 边界，一张表只由拥有它的模块读写，跨模块只调 Service | 某个模块需要独立扩容或独立发版 | 只是纪律成本 |
| Monorepo 多 app | `apps/` 下多进程、`libs/` 共享契约，通信从函数调用变成 TCP / gRPC | 需要独立仓库权限、独立 CI、独立技术栈 | 网络失败、部署复杂度、本地要起多进程 |
| 真微服务 | 独立仓库、独立库、独立发布，注册中心与链路追踪齐备 | —— | 开篇那张表里的六项长期成本全部到齐 |

回到开篇那句话：**边界先在单体里立住，再谈拆。** 从模块化单体走到 Monorepo 多 app 的工作量接近于搬目录；而边界没立住就拆出来的只会是分布式单体——所有缺点，没有优点。

四类典型系统各自该落在这条路线的哪一段，见[项目架构蓝图](/guide/nestjs-project-blueprint)。

---

## 面试问答

**1. 什么时候才值得把单体拆成微服务？**

- 三个前提**全部满足**才考虑：负载特征差异大需要独立扩容、发布节奏差一个数量级、边界已经在单体里稳定。技术栈不同（Node 网关 + Python 推理服务）是唯一能单独成立的理由。
- 微服务解决的是组织和部署问题，不是代码整洁问题。代码乱是模块边界没立住，拆开只会得到分布式单体——所有缺点，没有优点。
- 加分：能说出渐进路线——模块化单体 → Monorepo 多 app → 真微服务，每一步都能停下来，前一步的工作量接近于搬目录。

**2. Nest 内置的 TCP 传输为什么不能当生产骨架？**

- 它是一个私有的「JSON over TCP」协议：没有 broker、没有确认、没有重试、没有负载均衡，客户端写死一个 `host:port`，一次网络抖动就丢消息。
- 协议是 Nest 私有的，别的语言没有现成客户端，跨语言也不行。
- 选型三句话：要保证不丢就走 broker；要低延迟同步拿返回值就用 gRPC；要跨语言就用 gRPC 或 broker。

**3. `send` 和 `emit` 的区别？冷热 Observable 会怎么咬人？**

- `send` + `@MessagePattern` 是「我要一个答案」，返回的 Observable 是冷的——不订阅就根本不会发出去，必须 `return` 它或 `firstValueFrom` 一下。
- `emit` + `@EventPattern` 是「我通知一件已经发生的事」，是热的，忘了 `await` 消息照样发出去，但拿不到 broker 的确认，要确认就得 `await lastValueFrom(...)`。
- 命名跟着语义走：`send` 的 pattern 用动词（`doc.count`），`emit` 的用过去式事件名（`doc.published`），看到 `emit('doc.count')` 就知道写错了。
- 别踩的坑：传输层的 `retryAttempts` 管的是连接重建，不是这次调用的重试；调用级别必须自己上 RxJS operator——超时必须设、重试只给读操作、要有上限和退避。

**4. 微服务里抛 `NotFoundException` 为什么不行？异常怎么跨进程？**

- rpc 上下文没有 HTTP 状态码这个概念，`NotFoundException` 序列化到调用方只是一个形状不可预期的对象。跨进程要抛 `RpcException`（gRPC 是 code + message）。
- 被调方用 Filter 把内部抛的 `HttpException` 统一翻译成 `RpcException`，别让它原样漏出去；调用方把 gRPC code 翻回 HTTP 语义：`NOT_FOUND` → 404、`INVALID_ARGUMENT` → 400、`UNAVAILABLE` → 503。
- 下游的错误码不要原样透给前端，翻译表收口在网关一处，别每个 controller 各抄一遍。

**5. gRPC 上生产有哪些必踩的坑？**

- 字段编号是线上格式的一部分：只增不改，删字段用 `reserved` 占位防复用；proto3 标量不加 `optional` 分不清「没传」和「传了零值」，`temperature = 0` 这类合法零值必须加 `optional`。
- 三处命名不一致：`@GrpcMethod` 的第二个参数写 proto 原名 `StreamChat`，`getService()` 返回的 stub 方法是 `streamChat`（首字母小写），字段 `session_id` 到 TS 里变 `sessionId`——配一边 `keepCase: true` 一边不配，就是永远收到 `undefined`。
- K8s 的 ClusterIP 是 L4 轮询，HTTP/2 长连接建好就粘在一个 Pod 上，扩容后流量不均；用 headless Service + 客户端 `round_robin` 负载均衡，或交给 service mesh。
- 加分：proto 复制粘贴到各仓库会两边不同步且解析错位不报错，要单独 proto repo 或上 buf 集中管理；默认 4MB 消息上限传 embedding 大数组会报 `RESOURCE_EXHAUSTED`。
