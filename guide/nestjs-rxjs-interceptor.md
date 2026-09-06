---
title: RxJS 与 Interceptor 实战
---

# RxJS 与 Interceptor 实战

> Nest 的 Interceptor 返回的是 Observable。不懂 RxJS 就只会写个 `tap` 打日志，超时熔断、缓存短路、异常转换这些活儿全做不了。这篇只教 Interceptor 里真正用得上的那一小撮 operator，然后写六个能直接抄进项目的拦截器。

Interceptor 在整条请求链里的位置、和 Middleware / Guard / Pipe 的先后关系，见[请求生命周期](/guide/nestjs-pipeline)。下面的示例省略 import：operator 都来自 `rxjs`，装饰器和接口来自 `@nestjs/common`。

## 为什么是 Observable，不是 Promise

前端最熟的类比是 axios 拦截器：请求发出前改 header，响应回来后统一解包 `res.data`。Nest 的 Interceptor 干的是同一件事，只是包住的对象从「一次 HTTP 请求」换成了「一次 handler 执行」。区别在于它用 Observable 而不是 Promise 表示这次执行：

| | Promise | Observable |
|---|---|---|
| 能产出几个值 | 一个 | 0 到 n 个（SSE、WebSocket 消息流都是多值） |
| 什么时候开始执行 | 创建即执行（eager） | 被订阅才执行（lazy） |
| 能不能取消 | 不能，`AbortController` 是外挂 | `unsubscribe()` 就是取消 |
| 怎么组合 | `then` / `await` 手写流程 | operator 拼装 |
| 超时、重试、节流 | 自己实现 | `timeout` / `retry` / `throttleTime` 现成 |

对绝大多数 HTTP 接口来说，`handle()` 返回的 Observable 只发一个值就完成了，行为和 Promise 没差别。**但正因为它是 Observable，你才能白拿 `timeout`、`catchError`、`finalize` 这些能力**，不用自己拼 `Promise.race` 和 `try/finally`。SSE、WebSocket 场景更需要它——那时 handler 返回的本来就是流。

---

## Interceptor 里的 RxJS 最小必要集

RxJS 有一百多个 operator，Interceptor 里反复用到的就这九个：

| operator | 在 Interceptor 里干什么 |
|---|---|
| `map` | 改写 handler 的返回值：统一包装、字段脱敏、结构重塑 |
| `tap` | 不碰数据只做副作用：打日志、写缓存、埋点 |
| `catchError` | 接住 handler 抛的异常，转换成语义化异常或降级返回 |
| `throwError` | 在 `catchError` 里把异常重新抛出去，必须写成 `throwError(() => err)` |
| `timeout` | 超过指定时间没返回就抛 `TimeoutError` |
| `of` | 造一个立即完成的流，用来短路（缓存命中、降级兜底） |
| `finalize` | 成功、异常、被取消都会执行的收尾逻辑 |
| `switchMap` | 后置逻辑里要做异步：拿到 handler 结果后再 await 一个 Promise |
| `mergeMap` | 同上，但不取消前一个内层流 |

> `handle()` 只发一个值时，`switchMap` 和 `mergeMap` 行为几乎一致，习惯上用 `switchMap`。只有上游连续发多个值（SSE、WebSocket）时才需要认真区分：`switchMap` 会取消上一个未完成的内层流，`mergeMap` 让它们并发跑完。

---

## `CallHandler.handle()` 到底是什么

一句话：**`handle()` 返回的 Observable 代表「路由处理函数的执行」**。围绕这句话有三条推论，记住之后 Interceptor 就没有玄学了。

```typescript
@Injectable()
export class SkeletonInterceptor implements NestInterceptor {
  intercept(context: ExecutionContext, next: CallHandler): Observable<unknown> {
    // ① handle() 之前 = 前置逻辑。此刻 Guard 已放行，handler 还没执行
    const startedAt = Date.now()

    // ② 不调用 handle() = 短路。handler 永远不执行，但外层拦截器的后置逻辑照常跑
    if (this.hitCache(context)) {
      return of({ fromCache: true })
    }

    return next
      .handle()      // ③ 惰性：Nest 订阅它的那一刻，Pipe 才跑、handler 才被调用
      .pipe(
        // ④ pipe 里 = 后置逻辑。handler 的返回值（或异常）从这里流过
        tap(() => console.log(`${Date.now() - startedAt}ms`)),
      )
  }
}
```

「惰性」这条最关键：`next.handle()` 本身不触发任何事情，必须把它 `return` 出去（或自己 `subscribe`）。写了却没返回，请求会一直挂着直到客户端或网关超时。

**前置逻辑要异步**，直接把 `intercept` 声明成 `async` 就行——它的返回类型允许 `Promise<Observable<T>>`：

```typescript
async intercept(context: ExecutionContext, next: CallHandler): Promise<Observable<unknown>> {
  const cached = await this.redis.get(key)          // 前置异步，完全合法
  return cached ? of(JSON.parse(cached)) : next.handle()
}
```

**后置逻辑要异步**就不能这么干：`.pipe(map(async (data) => ...))` 得到的是一个 Promise 对象，会被原样序列化成 `{}`。必须用 `switchMap`。

---

## 实战一：统一响应包装

前端最烦的是每个接口返回格式都不一样。统一包装应该在后端一处解决：

```typescript
export const SKIP_WRAP = 'skip_response_wrap'
/** 贴在 handler 或 controller 上，跳过包装 */
export const SkipWrap = () => SetMetadata(SKIP_WRAP, true)

export interface ApiResult<T> {
  code: number
  data: T
  message: string
  timestamp: number
}

@Injectable()
export class ResponseWrapInterceptor implements NestInterceptor {
  constructor(private readonly reflector: Reflector) {}

  intercept(context: ExecutionContext, next: CallHandler): Observable<unknown> {
    const skip = this.reflector.getAllAndOverride<boolean>(SKIP_WRAP, [
      context.getHandler(),
      context.getClass(),
    ])
    if (skip) return next.handle()

    return next.handle().pipe(
      map((data): ApiResult<unknown> => ({
        code: 0,
        data: data ?? null,
        message: 'ok',
        timestamp: Date.now(),
      })),
    )
  }
}
```

```typescript
@Get('export')
@SkipWrap()                      // 文件流不能被包一层
exportCsv(): StreamableFile {}
```

**为什么要留后门**：文件下载、SSE、第三方回调（微信、支付宝要求返回它们规定的格式）、健康检查这些接口都不能被包装。用元数据开后门比在拦截器里写 `if (url.startsWith('/export'))` 硬编码路径可维护得多——判断条件跟着接口走，改路由不用回来改拦截器。元数据的读写机制见 [Metadata 与 Reflector](/guide/nestjs-metadata-reflector)。

注意事项：

- **异常路径不走这里**。抛异常时响应由 Exception Filter 生成，所以 Filter 的输出结构必须和这里对齐，否则前端得写两套解析逻辑。见[参数校验与异常处理](/guide/nestjs-validation-filter)。
- `data ?? null`：handler 返回 `undefined`（比如 delete 接口没写 return）时 `JSON.stringify` 会把整个字段丢掉，前端拿到的对象里没有 `data` 键，容易踩空。
- 它要注入 `Reflector`，所以全局注册必须用 `APP_INTERCEPTOR` 而不是 `app.useGlobalInterceptors()`。
- 它应该在洋葱最外层，也就是在 `AppModule` 里第一个注册。

---

## 实战二：耗时日志与慢接口告警

```typescript
@Injectable()
export class TimingInterceptor implements NestInterceptor {
  private static readonly SLOW_MS = 500
  private readonly logger = new Logger('Timing')

  intercept(context: ExecutionContext, next: CallHandler): Observable<unknown> {
    const req = context.switchToHttp().getRequest<Request>()
    const target = `${context.getClass().name}.${context.getHandler().name}`
    const startedAt = process.hrtime.bigint()

    return next.handle().pipe(
      tap({
        error: (err) => this.logger.warn(`${target} 抛出异常: ${err?.message}`),
      }),
      finalize(() => {
        const ms = Number(process.hrtime.bigint() - startedAt) / 1e6
        const line = `${req.method} ${req.originalUrl} → ${target} ${ms.toFixed(1)}ms`
        ms >= TimingInterceptor.SLOW_MS
          ? this.logger.warn(`[慢接口] ${line}`)
          : this.logger.log(line)
      }),
    )
  }
}
```

`context.getClass().name` 和 `getHandler().name` 拿到的是控制器类名和方法名，比 URL 更适合做指标维度——URL 里带着 `/orders/1234` 这样的 id，直接聚合会把监控打爆。

`tap` 和 `finalize` 的区别是这节的重点：

| | `tap(fn)` | `tap({ error })` | `finalize(fn)` |
|---|---|---|---|
| 正常返回 | ✅ | ❌ | ✅ |
| handler 抛异常 | ❌ | ✅ | ✅ |
| 客户端断开导致取消订阅 | ❌ | ❌ | ✅ |
| 能拿到响应数据 | ✅ | 只能拿到 error | ❌ 什么都拿不到 |

结论：要记录响应内容用 `tap`；要「无论如何都执行」的收尾（结束计时、释放资源、并发计数减一）用 `finalize`；两个都要就都挂上，像上面这样。只用 `tap(() => ...)` 计时的话，接口一报错就没有耗时日志——恰恰是最需要耗时数据的时候。

---

## 实战三：超时熔断

```typescript
@Injectable()
export class TimeoutInterceptor implements NestInterceptor {
  constructor(private readonly ms: number = 5000) {}

  intercept(context: ExecutionContext, next: CallHandler): Observable<unknown> {
    return next.handle().pipe(
      timeout(this.ms),
      catchError((err) =>
        throwError(() =>
          err instanceof TimeoutError
            ? new RequestTimeoutException('处理超时，请稍后重试')
            : err,
        ),
      ),
    )
  }
}

// 需要不同阈值时传实例
@UseInterceptors(new TimeoutInterceptor(15_000))
```

**为什么必须把 `TimeoutError` 转成 `RequestTimeoutException`？** 因为 `TimeoutError` 是 RxJS 的普通 Error，不是 `HttpException` 的子类。Nest 内置 Filter 只认 `HttpException`，其余一律当未知错误返回 500 + `Internal server error`，前端拿不到 408 这个语义，也就没法区分「超时可以重试」和「服务器炸了别重试」。

> ⚠️ `timeout` 的含义只是「我不等了」，**它不会终止 handler 里正在跑的那条 SQL 或 HTTP 请求**，连接池占用照旧。真正的取消要靠下游支持（数据库的 statement timeout、axios 的 `signal`）。把它当成保护调用方的手段，不是保护数据库的手段。

另外，全局启用会把 SSE、长轮询、大文件下载一起掐断。这类接口要么用元数据开后门（同实战一），要么只在需要的模块里局部注册。

---

## 实战四：把底层异常转成语义化异常

ORM 和 HTTP 客户端抛出来的异常直接暴露给前端，既难看又漏信息（SQL 片段、内网地址）。在 Interceptor 里翻译一遍：

```typescript
@Injectable()
export class DomainErrorInterceptor implements NestInterceptor {
  intercept(context: ExecutionContext, next: CallHandler): Observable<unknown> {
    return next.handle().pipe(catchError((err) => throwError(() => this.translate(err))))
  }

  private translate(err: unknown): unknown {
    if (err instanceof HttpException) return err       // 已经语义化了，别二次包装

    if (err instanceof QueryFailedError) {
      const code = (err as QueryFailedError & { code?: string }).code
      // MySQL 唯一键冲突是 ER_DUP_ENTRY，PostgreSQL 是 23505
      if (code === 'ER_DUP_ENTRY' || code === '23505') {
        return new ConflictException('记录已存在')
      }
      return new InternalServerErrorException('数据库操作失败')
    }

    if (isAxiosError(err)) {
      const status = err.response?.status ?? 502
      // 上游 5xx 对我们的调用方而言是 502（网关错误），不是 500
      return new HttpException(`依赖服务不可用: ${err.config?.url}`, status >= 500 ? 502 : status)
    }

    return err
  }
}
```

这件事也可以放在全局 Exception Filter 里做，**但别两处都做**，否则线上排查要看两个地方。选择标准是作用范围：只有用 TypeORM 的模块才需要翻译 `QueryFailedError`，那就绑在那几个模块上；如果是全站统一策略，收口在 Filter 更合适（见[参数校验与异常处理](/guide/nestjs-validation-filter)）。

`throwError(() => err)` 的箭头函数不能省。RxJS 7 起直接传值的 `throwError(err)` 已废弃，因为那样异常会在流构建时就被求值。

---

## 实战五：缓存拦截器（短路的典型用法）

```typescript
export const CACHE_META = 'query_cache'
export const Cacheable = (prefix: string, ttl = 60) => SetMetadata(CACHE_META, { prefix, ttl })

@Injectable()
export class QueryCacheInterceptor implements NestInterceptor {
  constructor(
    private readonly reflector: Reflector,
    @Inject('REDIS_CLIENT') private readonly redis: RedisClientType,
  ) {}

  async intercept(context: ExecutionContext, next: CallHandler): Promise<Observable<unknown>> {
    const meta = this.reflector.get<{ prefix: string; ttl: number }>(
      CACHE_META,
      context.getHandler(),
    )
    const req = context.switchToHttp().getRequest<Request>()
    if (!meta || req.method !== 'GET') return next.handle()

    // key 要带上一切会影响结果的东西，尤其是当前用户
    const fingerprint = createHash('md5').update(req.originalUrl).digest('hex')
    const key = `${meta.prefix}:${req.user?.id ?? 'anon'}:${fingerprint}`

    const hit = await this.redis.get(key)
    if (hit) return of(JSON.parse(hit))            // ← 短路：handler 不执行

    return next.handle().pipe(
      tap((data) => {
        // 写缓存失败不能影响正常响应，所以不 await、并且吞掉错误
        this.redis.set(key, JSON.stringify(data), { EX: meta.ttl }).catch(() => void 0)
      }),
    )
  }
}
```

```typescript
@Get('ranking')
@Cacheable('ranking', 300)
getRanking(@Query() query: RankingQueryDto) {}
```

注意事项：

- **key 忘了带用户维度，就是把别人的数据发给你**。这是缓存拦截器最常见也最严重的事故，要么带上 `user.id`，要么明确只缓存与身份无关的公共数据。
- 只缓存 `GET`。写接口不但不能读缓存，还要主动失效相关 key——这部分逻辑放 service 层更合适，拦截器只管读。
- 短路时后置链照常执行：外层的响应包装、耗时日志都还在，所以监控里能看到「缓存命中的请求耗时 2ms」。
- 简单场景直接用 `@nestjs/cache-manager` 的 `CacheInterceptor` 配 `@CacheKey()` / `@CacheTTL()`；自己写是为了自定义 key 策略和多维度失效。

---

## 实战六：响应序列化与字段脱敏

`password`、`refreshToken`、手机号这些字段不能直接吐给前端。传统做法是给每个 entity 手写一个 VO 类，很啰嗦；用 class-transformer 只要在字段上标个装饰器：

```typescript
export class User {
  id: number
  username: string

  @Exclude()                                    // 永远不出现在响应里
  password: string

  @Transform(({ value }) => value?.replace(/^(\d{3})\d{4}(\d{4})$/, '$1****$2'))
  phone: string

  @Expose()                                     // 计算属性也能输出
  get displayName(): string {
    return `${this.username}#${this.id}`
  }
}
```

```typescript
@Injectable()
export class SerializeInterceptor implements NestInterceptor {
  intercept(context: ExecutionContext, next: CallHandler): Observable<unknown> {
    return next.handle().pipe(
      map((data) => (data && typeof data === 'object' ? instanceToPlain(data) : data)),
    )
  }
}
```

`instanceToPlain` 会读取对象所属 class 上的 class-transformer 装饰器，产出一个新的普通对象——**这就是 Nest 内置 `ClassSerializerInterceptor` 的全部原理**，它只是额外处理了数组、`StreamableFile`，并支持从元数据读 `@SerializeOptions()`。所以大多数项目直接开内置的即可：

```typescript
{ provide: APP_INTERCEPTOR, useClass: ClassSerializerInterceptor }
```

> ⚠️ **「脱敏没生效」最常见的原因：handler 返回的不是 class 实例。** `@Exclude()` 的信息挂在 class 的元数据上，TypeORM 的 `find()` 返回 entity 实例所以有效；而 Prisma、`getRawMany()`、`JSON.parse()` 出来的都是普通对象，装饰器完全没有落点，密码就这么发出去了。

普通对象的场景要用视图类显式挑字段：

```typescript
map((data) => plainToInstance(UserView, data, { excludeExtraneousValues: true }))
```

`excludeExtraneousValues: true` 表示「只保留 `UserView` 上用 `@Expose()` 标出来的字段」，是白名单模式——比 `@Exclude()` 的黑名单模式安全：将来新增一个敏感字段忘了标注，白名单模式默认不会泄露。

还有一点：`@Exclude()` 只作用于出站响应，`this.logger.log(JSON.stringify(user))` 照样会把密码打进日志。视图类 / DTO 的设计和 class-transformer 装饰器清单见 [DTO 与序列化](/guide/nestjs-dto)。

---

## 同一件事该放在哪层

| 需求 | 放哪 | 为什么 |
|---|---|---|
| cookie 解析、gzip、helmet、静态资源 | Middleware | 平台层现成生态，和业务无关 |
| 生成 traceId 挂到 request 上 | Middleware | 要在最外层就有，后面每层都要用 |
| 根据路由元数据决定行为 | Interceptor / Guard | Middleware 拿不到 handler 和元数据 |
| 改写正常响应体 | Interceptor | Middleware 手上没有响应数据，Filter 只管异常 |
| 超时、缓存短路、耗时统计 | Interceptor | 需要包住 handler 的执行 |
| 把底层异常翻译成语义异常 | Interceptor 的 `catchError` | 想按模块局部启用时 |
| 异常 → 最终响应结构 | Exception Filter | 全站唯一出口，连 404、参数校验失败这些没进 handler 的情况也能兜住 |
| 决定能不能访问 | Guard | 语义就是放行 / 拒绝，且它在 Interceptor 之前 |

---

## 常见坑

**1. 拦截器必须返回一条流**

```typescript
// ❌ 忘了 return：函数返回 undefined，Nest 收不到流，请求挂到网关超时
intercept(context: ExecutionContext, next: CallHandler): Observable<unknown> {
  next.handle().pipe(map((data) => this.wrap(data)))
}

// ❌ 更隐蔽：pipe 返回的是新流，这里返回的是没包装过的原始流，安静地什么都没做
intercept(context: ExecutionContext, next: CallHandler): Observable<unknown> {
  const stream = next.handle()
  stream.pipe(map((data) => this.wrap(data)))
  return stream
}
```

第一种 TypeScript 会报错（声明了返回类型），第二种不会。`pipe` 和数组的 `map` 一样返回新对象，不是原地修改。

**2. 在 `pipe` 里写 `async`**

```typescript
.pipe(map(async (data) => await this.enrich(data)))   // ❌ 响应变成 {}
.pipe(switchMap((data) => this.enrich(data)))         // ✅ 返回 Promise 也行，switchMap 会展开
```

**3. `@Res()` 之后 Interceptor 改不动响应**

handler 里一旦用 `@Res()` 拿到原生 response 自己 `res.json()`，Nest 就不再关心返回值，`map` 拿到的是 `undefined`，改也没用（响应头已发出）。既要操作 response 又想保留 Nest 流程，用 `@Res({ passthrough: true })`。

**4. 异常被悄悄吞掉**

```typescript
catchError(() => of([]))    // 降级返回空数组：Filter 收不到、监控看不到、你不知道它坏了
```

降级本身没问题，但**必须打日志或上报**，否则等于把故障藏起来，等着被用户投诉发现。

**5. 全局 Interceptor 的顺序会影响结果**

多个 `APP_INTERCEPTOR` 按声明顺序组成洋葱，先声明的在外层。「响应包装」声明在「脱敏」之前时，脱敏拿到的是原始 entity、包装拿到的是脱敏后的数据，正确；顺序反了就变成给已经包好的 `{ code, data }` 做脱敏，而那个外层对象不是 entity 实例，`@Exclude()` 直接失效。

**6. 配对逻辑要放 `finalize`**

客户端提前断开时 Nest 会取消订阅，此时 `tap` 不执行、`finalize` 会执行。所以「并发计数 +1 / -1」「获取锁 / 释放锁」这类配对操作必须放 `finalize`，否则计数只增不减，慢慢就把限流阈值占满了。

---

## 面试问答

**1. `handle()` 返回的是什么？拦截器忘了 return 会发生什么？**

- 它返回的 Observable 代表「路由处理函数的执行」，而且是惰性的：Nest 订阅它的那一刻，Pipe 才跑、handler 才被调用。
- 忘了 return，Nest 收不到流，请求会一直挂着直到客户端或网关超时；更隐蔽的是 `pipe` 返回的是新流，把没包装的原始流 return 回去等于安静地什么都没做。
- 别踩的坑：后置逻辑要异步时写成 `.pipe(map(async (data) => ...))`，得到的是一个 Promise 对象，会被原样序列化成 `{}`，必须用 `switchMap`。
- 加分：能说出 `switchMap` / `mergeMap` 只在上游发多个值（SSE、WebSocket）时才需要认真区分——前者会取消未完成的内层流，后者让它们并发跑完。

**2. `tap` 和 `finalize` 有什么区别？耗时日志该用哪个？**

- `tap` 只在正常返回时执行，`tap({ error })` 能拿到异常；`finalize` 在成功、异常、客户端断开取消订阅时都会执行，但什么都拿不到。
- 只用 `tap(() => ...)` 计时，接口一报错就没有耗时日志——恰恰是最需要耗时数据的时候。所以要 `finalize` 记时间、`tap({ error })` 记异常，两个都挂。
- 配对操作（并发计数 +1 / -1、获取锁 / 释放锁）必须放 `finalize`：客户端提前断开时 Nest 会取消订阅，`tap` 不执行，计数只增不减会慢慢把限流阈值占满。

**3. `timeout` 抛的 `TimeoutError` 为什么要转成 `RequestTimeoutException`？它真的取消了下游操作吗？**

- `TimeoutError` 是 RxJS 的普通 Error，不是 `HttpException` 的子类，Nest 内置 Filter 只认 `HttpException`，其余一律当未知错误返回 500；转成 `RequestTimeoutException` 前端才能拿到 408 语义，区分「超时可重试」和「服务器炸了别重试」。
- `timeout` 的含义只是「我不等了」，不会终止 handler 里正在跑的那条 SQL 或 HTTP 请求，连接池占用照旧；真正的取消要靠下游支持（statement timeout、axios 的 `signal`）。
- 别踩的坑：全局启用会把 SSE、长轮询、大文件下载一起掐断，这类接口要么用元数据开后门，要么只在需要的模块局部注册。

**4. 把底层异常翻译成语义化异常，该放 Interceptor 还是 Exception Filter？**

- 别两处都做，否则线上排查要看两个地方。选择看作用范围：只有用 TypeORM 的模块才需要翻译 `QueryFailedError`，就绑在那几个模块的 Interceptor 上。
- 全站统一策略收口在 Exception Filter 更合适——它是全站唯一出口，连没进 handler 的 404、参数校验失败都能兜住。
- 已经语义化的 `HttpException` 不要二次包装；上游 5xx 对我们的调用方而言是 502（网关错误），不是 500。
- 加分：知道 `throwError(() => err)` 的箭头函数不能省——RxJS 7 起直接传值的写法已废弃，那样异常会在流构建时就被求值。

**5. 缓存拦截器最严重的事故是什么？**

- key 忘了带用户维度，就是把别人的数据发给你——缓存拦截器最常见也最严重的事故。key 必须带上 `user.id`，或者明确只缓存与身份无关的公共数据。
- 只缓存 GET；写缓存失败不能影响正常响应，所以不 await、吞掉错误，但降级本身必须打日志或上报，否则等于把故障藏起来。
- 短路时外层后置链照常执行：响应包装、耗时日志都还在，监控里能看到「缓存命中的请求耗时 2ms」。
- 简单场景直接用 `@nestjs/cache-manager` 的 `CacheInterceptor` 配 `@CacheKey()` / `@CacheTTL()`；自己写是为了自定义 key 策略和多维度失效。
