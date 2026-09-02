# 参数校验与异常处理

> Pipe 管「进来的数据对不对」，Exception Filter 管「出错了返回什么」。这两件事配置好，controller 里就不用再写一行 `if (!xxx) throw new BadRequestException()`。

这两类切面在请求链里的位置见[请求生命周期](/guide/nestjs-pipeline)；DTO 本身怎么设计（映射类型、class-validator 装饰器清单、Swagger 注解）见 [DTO 与序列化](/guide/nestjs-dto)。本篇只讲校验管道和异常处理机制。

## Pipe 的两种绑定形态

Pipe 实现 `PipeTransform`，返回值就是最终传给 handler 的参数值。绑定的时候可以传类，也可以传实例，区别很重要：

```typescript
// 传类：Nest 自己实例化并放进 IoC 容器 —— 这个 Pipe 能注入依赖
@Get(':id')
findOne(@Param('id', ParseIntPipe) id: number) {}

// 传实例：你自己 new 的，能传配置，但拿不到依赖注入
@Get(':id')
findOne(
  @Param('id', new ParseIntPipe({ errorHttpStatusCode: HttpStatus.UNPROCESSABLE_ENTITY }))
  id: number,
) {}
```

绑定位置从粗到细有四层，同一个参数上可以串多个 Pipe，**从左到右依次执行**：

```typescript
@UsePipes(new ValidationPipe({ whitelist: true }))     // 方法级（也可贴在 @Controller 上）
@Get()
list(
  @Query('page', new DefaultValuePipe(1), ParseIntPipe) page: number,   // 参数级，先给默认值再转整数
) {}
```

顺序反了就出错：`ParseIntPipe` 在前时，不传 `page` 会先拿到 `undefined` 直接抛 400，`DefaultValuePipe` 根本轮不到。

内置 Pipe 的报错也能定制，两个通用选项：

```typescript
new ParseUUIDPipe({
  version: '4',
  errorHttpStatusCode: HttpStatus.UNPROCESSABLE_ENTITY,       // 换状态码
})

new ParseIntPipe({
  exceptionFactory: () =>                                     // 换整个错误结构
    new BadRequestException({ code: 'INVALID_ID', message: 'id 必须是整数' }),
})
```

---

## 内置 Pipe 速查

| Pipe | 作用 | 用法 |
|---|---|---|
| `ValidationPipe` | 按 DTO 上的规则校验并转换整个对象 | `@Body() dto: CreateOrderDto`（配全局启用） |
| `ParseIntPipe` | 字符串 → 整数，转不了抛 400 | `@Param('id', ParseIntPipe)` |
| `ParseFloatPipe` | 字符串 → 浮点数 | `@Query('ratio', ParseFloatPipe)` |
| `ParseBoolPipe` | `'true'` / `'false'` / `'1'` / `'0'` → boolean | `@Query('onlyActive', ParseBoolPipe)` |
| `ParseArrayPipe` | 分隔符字符串 → 数组，可指定元素类型 | `new ParseArrayPipe({ items: Number, separator: ',', optional: true })` |
| `ParseUUIDPipe` | 校验 UUID 格式，可限定版本 | `new ParseUUIDPipe({ version: '4' })` |
| `ParseEnumPipe` | 限定取值范围，并转成枚举类型 | `new ParseEnumPipe(OrderStatus)` |
| `DefaultValuePipe` | 值为 `undefined` / `null` 时给默认值 | `new DefaultValuePipe(20), ParseIntPipe` |

```typescript
@Get()
list(
  @Query('ids', new ParseArrayPipe({ items: Number, optional: true })) ids: number[] = [],
  @Query('status', new ParseEnumPipe(OrderStatus)) status: OrderStatus,
  @Query('withDeleted', new DefaultValuePipe(false), ParseBoolPipe) withDeleted: boolean,
) {}
```

`ParseEnumPipe` 不只是取值——它顺手把「非法值」拦在了 service 之外。同理 `ParseArrayPipe` 的 `optional: true` 很关键：不加的话参数缺失会直接报错。文件上传相关的 `ParseFilePipe` / `FileValidator` 属于另一个话题，不在这里展开。

---

## 自定义 Pipe

`transform` 拿到两个参数：值和 `ArgumentMetadata`。三个元数据字段各有用处：

| 字段 | 是什么 | 什么时候有用 |
|---|---|---|
| `type` | `'body'` / `'query'` / `'param'` / `'custom'` | 一个 Pipe 全局启用时，用它只处理某一类参数（例如只给 body 做 trim） |
| `metatype` | 参数声明的 TS 类型（`Number`、`CreateOrderDto`…） | `ValidationPipe` 靠它拿到 DTO 类；没有类型标注时是 `undefined`，只能原样放过 |
| `data` | 传给 `@Query('page')` 的那个 key | 报错信息里带上字段名，前端才知道是哪个参数错了 |

> ⚠️ `metatype` 依赖 TypeScript 的 `emitDecoratorMetadata`（Nest 项目模板默认开启）。而且接口在运行时不存在，所以 DTO **必须是 class 不能是 interface**，否则 `metatype` 拿到的是 `Object`，校验直接被跳过。原理见 [Metadata 与 Reflector](/guide/nestjs-metadata-reflector)。

### 实战一：逗号分隔字符串转数组，并校验白名单

排序字段这类参数最终会拼进 SQL，必须白名单化：

```typescript
@Injectable()
export class SortFieldsPipe implements PipeTransform<string | undefined, string[]> {
  constructor(private readonly allowed: readonly string[]) {}

  transform(value: string | undefined, metadata: ArgumentMetadata): string[] {
    if (!value) return []

    const fields = value.split(',').map((f) => f.trim()).filter(Boolean)
    const invalid = fields.filter((f) => !this.allowed.includes(f))

    if (invalid.length > 0) {
      throw new BadRequestException(
        `${metadata.data} 不支持字段 ${invalid.join('、')}，可选值：${this.allowed.join('、')}`,
      )
    }
    return [...new Set(fields)]     // 顺手去重
  }
}
```

```typescript
@Get()
list(
  @Query('sort', new SortFieldsPipe(['createdAt', 'price', 'sales'])) sort: string[],
) {}
```

白名单放在构造参数里，同一个 Pipe 就能给不同接口配不同白名单——这正是「必须用实例形态绑定」的典型场景。更重要的是，非法字段在进入 service 之前就被拦住了，SQL 拼接那一层不可能被注入。

### 实战二：分页参数归一化

```typescript
export interface Pagination {
  page: number
  pageSize: number
  skip: number
}

@Injectable()
export class PaginationPipe implements PipeTransform<Record<string, unknown>, Pagination> {
  private static readonly MAX_PAGE_SIZE = 100

  transform(value: Record<string, unknown>): Pagination {
    const page = Math.max(1, this.toInt(value?.page, 1))
    const pageSize = Math.min(
      PaginationPipe.MAX_PAGE_SIZE,
      Math.max(1, this.toInt(value?.pageSize, 20)),
    )
    return { page, pageSize, skip: (page - 1) * pageSize }
  }

  private toInt(raw: unknown, fallback: number): number {
    const parsed = Number.parseInt(String(raw ?? ''), 10)
    return Number.isNaN(parsed) ? fallback : parsed
  }
}
```

```typescript
@Get()
list(@Query(PaginationPipe) pagination: Pagination) {}   // 不带 key，拿到整个 query 对象
```

`@Query()` 不传 key 时，Pipe 拿到的是整个 query 对象（`metadata.type` 为 `'query'`）。上界必须夹死：`?pageSize=100000` 是成本最低的一种慢查询攻击，同时也能防住前端手滑传错。这个 Pipe 顺带把「负数页码」「非数字」都归一化了，service 层可以放心假设参数合法。

---

## ValidationPipe 深入

`ValidationPipe` 的原理是两个库的组合：用 class-transformer 把请求里的普通对象转成 DTO 类的实例，再用 class-validator 按类上的装饰器校验这个实例。所以它只对「有 class 类型标注的参数」生效。

推荐的全局配置：

```typescript
// main.ts
app.useGlobalPipes(
  new ValidationPipe({
    whitelist: true,                    // 剥掉 DTO 里没声明的字段
    forbidNonWhitelisted: true,         // 有多余字段直接报错
    transform: true,                    // 转成 DTO 实例，并按 @Type() 做类型转换
    stopAtFirstError: true,             // 每个字段只报第一条错误
    disableErrorMessages: process.env.NODE_ENV === 'production',
  }),
)
```

| 选项 | 作用 | 建议 |
|---|---|---|
| `whitelist` | 剥掉未在 DTO 中声明的字段 | **生产必开**。否则前端多传一个 `role: 'admin'`，`Object.assign(entity, dto)` 就把它写进库了 |
| `forbidNonWhitelisted` | 有多余字段时直接 400，而不是静默剥离 | 内部接口建议开，能第一时间发现前后端字段不一致 |
| `transform` | 把 plain object 转成 DTO 实例，配合 `@Type()` 做类型转换 | 必开。不开的话拿到的还是普通对象，DTO 上的方法和 getter 都不存在 |
| `transformOptions.enableImplicitConversion` | 按 TS 类型自动转换（`'18'` → `18`） | query 场景省事，但边界值行为不直观，见下文 |
| `groups` | 只执行指定分组的校验规则 | 同一个 DTO 在创建 / 更新场景规则不同时用 |
| `stopAtFirstError` | 每个字段只返回第一条错误 | 前端只展示一条提示时开，响应干净很多 |
| `disableErrorMessages` | 不返回具体错误信息 | 对外接口的生产环境可开，避免暴露字段结构；但必须保证日志里留有细节 |
| `exceptionFactory` | 自定义抛出的异常 | 需要 `{ code, errors }` 这类结构时用 |

### 高频坑：query 参数天生是字符串

```typescript
// GET /orders?page=2&minAmount=99.5
export class ListOrdersDto {
  @Type(() => Number)      // ← 少了这行，@IsInt() 一定失败
  @IsInt()
  @Min(1)
  page = 1

  @Type(() => Number)
  @IsNumber()
  @IsOptional()
  minAmount?: number
}
```

原因很简单：HTTP 的 query string、路径参数、`multipart/form-data` 字段在协议层就只有字符串，`page` 到手是 `'2'`，`@IsInt()` 看到 string 直接判失败。两种解法：

1. 在字段上写 `@Type(() => Number)`（class-transformer 提供）。精确、可控，**推荐**。
2. 全局开 `transformOptions: { enableImplicitConversion: true }`，让它按 TS 类型隐式转。省事，但隐式转换的规则由 class-transformer 决定，空字符串、`'false'`、`'abc'` 这些边界值的结果不一定符合直觉，容易出现「校验通过但值不对」。

`@Body()` 接 JSON 时通常不需要 `@Type()`，因为 JSON 本身有类型。坑集中在 query、param 和表单。

### groups：一个 DTO 两套规则

创建时手机号必填、更新时可以不传，用分组表达：

```typescript
export class UpsertMemberDto {
  @IsString({ groups: ['create', 'update'] })
  @IsNotEmpty({ groups: ['create'] })
  @IsOptional({ groups: ['update'] })
  nickname: string

  @IsMobilePhone('zh-CN', {}, { groups: ['create'] })   // 更新接口不校验手机号
  phone: string
}
```

```typescript
@Post()
create(@Body(new ValidationPipe({ groups: ['create'], transform: true })) dto: UpsertMemberDto) {}

@Patch(':id')
update(@Body(new ValidationPipe({ groups: ['update'], transform: true })) dto: UpsertMemberDto) {}
```

> 实践中更常见的是用 `PartialType(CreateXxxDto)` 生成 Update DTO（见 [DTO 与序列化](/guide/nestjs-dto)）。`groups` 适合「同一字段在两种场景下规则本身不同」，而不只是「可选变必填」。

### exceptionFactory：自定义错误结构

默认的错误响应里 `message` 是一个字符串数组，前端拿到得自己拆。改成结构化的：

```typescript
new ValidationPipe({
  whitelist: true,
  transform: true,
  exceptionFactory: (errors: ValidationError[]) =>
    new BadRequestException({
      code: 'VALIDATION_FAILED',
      errors: errors.map((e) => ({
        field: e.property,
        message: Object.values(e.constraints ?? {})[0],
      })),
    }),
})
```

嵌套 DTO 的错误在 `error.children` 里（需要 `@ValidateNested()` + `@Type()`），要递归展开才拿得全，上面这段只处理了第一层。

---

## 异常体系

所有 HTTP 异常都继承 `HttpException`，构造函数是「响应体 + 状态码」：

```typescript
throw new NotFoundException(`订单 ${id} 不存在`)
// 等价于
throw new HttpException('订单 xxx 不存在', HttpStatus.NOT_FOUND)

// 传对象时，getResponse() 拿到的就是这个对象，可以塞业务码
throw new ConflictException({ code: 'ORDER_PAID', message: '订单已支付，不能取消' })
```

| 异常类 | 状态码 | 什么业务场景抛 |
|---|---|---|
| `BadRequestException` | 400 | 参数格式或取值不合法（`ValidationPipe` 默认抛这个） |
| `UnauthorizedException` | 401 | 没登录、token 缺失 / 无效 / 过期 |
| `ForbiddenException` | 403 | 已登录但没权限（Guard 返回 `false` 时 Nest 抛的就是它） |
| `NotFoundException` | 404 | 资源不存在。也常用来「假装不存在」以隐藏他人资源，避免被枚举探测 |
| `ConflictException` | 409 | 唯一键冲突、重复提交、状态冲突（订单已支付还要付） |
| `GoneException` | 410 | 资源已删除、分享链接已失效 |
| `PayloadTooLargeException` | 413 | 请求体 / 上传文件超限 |
| `UnsupportedMediaTypeException` | 415 | `Content-Type` 不支持 |
| `UnprocessableEntityException` | 422 | 格式没问题但业务规则不通过：余额不足、库存不够、时间冲突 |
| `RequestTimeoutException` | 408 | 处理超时（配合 Interceptor 的 `timeout`） |
| `InternalServerErrorException` | 500 | 兜底，一般不手抛——未捕获的错误自动就是 500 |
| `BadGatewayException` / `ServiceUnavailableException` / `GatewayTimeoutException` | 502 / 503 / 504 | 依赖的上游服务挂了、限流降级、上游超时 |

> 400 和 422 的分工值得约定清楚：**格式错误用 400，业务规则不通过用 422**。前端据此决定是「高亮表单字段」还是「弹一个业务提示」。限流场景 `@nestjs/common` 没有对应异常类，用 `new HttpException(msg, HttpStatus.TOO_MANY_REQUESTS)`，或者直接用 `@nestjs/throttler`（它抛的 `ThrottlerException` 就是 429）。

### 自定义业务异常

前端往往需要一个稳定的业务错误码来做分支，HTTP 状态码不够用：

```typescript
export class BusinessException extends HttpException {
  constructor(
    readonly bizCode: string,
    message: string,
    status: HttpStatus = HttpStatus.UNPROCESSABLE_ENTITY,
  ) {
    super({ code: bizCode, message }, status)
  }
}

export class InsufficientStockException extends BusinessException {
  constructor(skuId: string, remaining: number) {
    super('STOCK_INSUFFICIENT', `SKU ${skuId} 库存不足，仅剩 ${remaining} 件`)
  }
}
```

为什么要继承 `HttpException` 而不是自己造一个裸 class：继承之后内置 Filter 和你自己的 Filter 都能通过 `instanceof` 认出它，状态码语义也在。裸 class 当然也能用（下面 `@Catch()` 那节就有例子），但你必须为它专门写一个 Filter，漏了就是 500。

---

## Exception Filter

实现 `ExceptionFilter`，用 `@Catch()` 声明捕获什么：

```typescript
/** 完全自定义的异常，不继承 HttpException */
export class QuotaExceededException {
  constructor(readonly used: number, readonly limit: number) {}
}

@Catch(QuotaExceededException)
export class QuotaFilter implements ExceptionFilter<QuotaExceededException> {
  catch(exception: QuotaExceededException, host: ArgumentsHost) {
    const response = host.switchToHttp().getResponse<Response>()
    response.status(HttpStatus.PAYMENT_REQUIRED).json({
      code: 'QUOTA_EXCEEDED',
      message: `本月额度已用完（${exception.used}/${exception.limit}）`,
    })
  }
}
```

`host` 是 `ArgumentsHost`，取 response 之前先 `switchToHttp()`。Filter 同样服务 WebSocket 和微服务，所以跨上下文的写法要判断 `host.getType()`，细节见[请求生命周期](/guide/nestjs-pipeline)里的 ExecutionContext 一节。

### 三个层级与捕获优先级

| 绑定方式 | 作用范围 |
|---|---|
| `@UseFilters(F)` 在方法上 | 只这一个 handler |
| `@UseFilters(F)` 在 controller 上 | 该 controller 下全部 handler |
| `APP_FILTER` 或 `app.useGlobalFilters(new F())` | 整个应用 |

匹配规则：Nest 按「方法 → 控制器 → 全局」的顺序找第一个 `@Catch()` 类型能 `instanceof` 匹配上的 Filter，**命中即停**。由此推出三条实用结论：

- 越近的层级越先匹配。想让某个接口的错误格式和别人不一样，在方法上贴一个专用 Filter 就行。
- 类型越具体的应该绑在越近的层级。`@Catch(HttpException)` 会把 `BadRequestException` 一并吃掉，所以更具体的 Filter 要么绑得更近，要么在同一层级里写在前面。
- `@Catch()` 不传参数 = 捕获一切，包括不继承 `HttpException` 的原生 `Error`。全局兜底 Filter 就是这么写的。

> ⚠️ **一个异常只会被一个 Filter 处理**。别设计成「先让日志 Filter 记一笔，再让格式化 Filter 输出」——第二个永远不会执行。要么在一个 Filter 里做完两件事，要么把异常日志 / 上报放到 Interceptor 的 `catchError` 里（见 [RxJS 与 Interceptor 实战](/guide/nestjs-rxjs-interceptor)）。

### 用 BaseExceptionFilter 做兜底转发

只想在异常路径上加个副作用（上报监控），响应格式仍用 Nest 默认的：

```typescript
@Catch()
export class SentryFilter extends BaseExceptionFilter {
  catch(exception: unknown, host: ArgumentsHost) {
    if (!(exception instanceof HttpException)) {
      Sentry.captureException(exception)    // 只上报非预期错误
    }
    super.catch(exception, host)            // 其余交回 Nest 的默认实现
  }
}
```

注意：`BaseExceptionFilter` 需要 HTTP adapter。用 `APP_FILTER` 注册时 Nest 会自动注入；用 `useGlobalFilters` 就得手动传：

```typescript
const { httpAdapter } = app.get(HttpAdapterHost)
app.useGlobalFilters(new SentryFilter(httpAdapter))
```

---

## 全局异常 Filter：完整实现

区分三类异常，统一输出格式，未知错误在生产环境不外泄细节但一定落日志。这段可以直接抄进项目：

```typescript
import {
  ArgumentsHost, Catch, ExceptionFilter, HttpException, HttpStatus, Logger,
} from '@nestjs/common'
import { QueryFailedError } from 'typeorm'
import type { Request, Response } from 'express'

interface ErrorPayload {
  code: string
  message: string
  path: string
  timestamp: string
  traceId?: string
}

@Catch()
export class AllExceptionsFilter implements ExceptionFilter {
  private readonly logger = new Logger('Exception')

  catch(exception: unknown, host: ArgumentsHost) {
    const http = host.switchToHttp()
    const req = http.getRequest<Request>()
    const res = http.getResponse<Response>()

    const { status, code, message } = this.normalize(exception)
    const payload: ErrorPayload = {
      code,
      message,
      path: req.originalUrl,
      timestamp: new Date().toISOString(),
      traceId: req.headers['x-request-id'] as string | undefined,
    }

    // 5xx 才打 error 和堆栈，4xx 打 warn —— 否则告警会被参数错误刷爆
    if (status >= 500) {
      this.logger.error(
        `${req.method} ${payload.path} → ${status} traceId=${payload.traceId ?? '-'}`,
        exception instanceof Error ? exception.stack : String(exception),
      )
    } else {
      this.logger.warn(`${req.method} ${payload.path} → ${status} ${message}`)
    }

    // 流式响应可能已经开始写出，这时候再 status().json() 会抛 ERR_HTTP_HEADERS_SENT
    if (res.headersSent) return
    res.status(status).json(payload)
  }

  private normalize(exception: unknown): { status: number; code: string; message: string } {
    // ① HttpException：内置异常、ValidationPipe 的错误、自定义业务异常都走这里
    if (exception instanceof HttpException) {
      const status = exception.getStatus()
      const body = exception.getResponse()

      if (typeof body === 'string') {
        return { status, code: String(status), message: body }
      }
      const { code, message } = body as { code?: string; message?: string | string[] }
      return {
        status,
        code: code ?? String(status),
        // ValidationPipe 的 message 是数组，不 join 的话前端拿到 [object Object]
        message: Array.isArray(message) ? message.join('; ') : message ?? exception.message,
      }
    }

    // ② 数据库异常：只暴露语义，绝不把 SQL 和表结构吐出去
    if (exception instanceof QueryFailedError) {
      const driverCode = (exception as QueryFailedError & { code?: string }).code
      if (driverCode === 'ER_DUP_ENTRY' || driverCode === '23505') {
        return { status: HttpStatus.CONFLICT, code: 'DUPLICATE', message: '记录已存在' }
      }
      return {
        status: HttpStatus.INTERNAL_SERVER_ERROR,
        code: 'DB_ERROR',
        message: '数据库操作失败',
      }
    }

    // ③ 未知错误：生产环境给用户一句人话，细节只进日志
    const detail = exception instanceof Error ? exception.message : String(exception)
    return {
      status: HttpStatus.INTERNAL_SERVER_ERROR,
      code: 'INTERNAL_ERROR',
      message: process.env.NODE_ENV === 'production' ? '服务器繁忙，请稍后重试' : detail,
    }
  }
}
```

几处设计说明：

- `@Catch()` 必须不传参数。第三类分支要接住的是原生 `Error`、被 reject 的字符串、甚至第三方库抛出的普通对象，`@Catch(HttpException)` 拦不到它们。
- **`ValidationPipe` 的 `message` 是数组**，这是自定义全局 Filter 最常见的 bug：加了 Filter 之后参数校验的错误提示全变成 `undefined`，就是因为没处理数组分支。
- `traceId` 由最外层的 Middleware 生成并挂在请求头上（见[请求生命周期](/guide/nestjs-pipeline)的 Middleware 一节）。有了它，用户截图报错 → 直接搜日志。
- 这里的输出结构要和响应包装 Interceptor 的 `{ code, data, message }` 对齐，否则前端得写两套解析。
- 别在这里做重试、补偿、发消息。Filter 的职责就是「翻译成响应」，副作用放这里很难测。

---

## 全局注册的两种方式

这是 Nest 里最容易踩的一个坑：**在 `main.ts` 里手动 new 的全局切面，不在 IoC 容器里，注入不了任何依赖。**

```typescript
// main.ts —— 手动 new：构造函数里想注入 ConfigService、Repository？没门
app.useGlobalFilters(new AllExceptionsFilter())

// app.module.ts —— 用 token 注册：由容器创建，依赖照常注入
@Module({
  providers: [
    { provide: APP_FILTER, useClass: AllExceptionsFilter },
  ],
})
export class AppModule {}
```

| | `app.useGlobalFilters(new X())` | `{ provide: APP_FILTER, useClass: X }` |
|---|---|---|
| 谁创建实例 | 你自己 `new` | Nest 的 IoC 容器 |
| 能否注入依赖 | ❌ 只能构造函数手动传 | ✅ 想注入什么注入什么 |
| 能否注册多个 | ✅ | ✅ 多个同 token 的 provider 都会生效 |
| 适合什么 | 没有依赖的简单切面、快速验证 | 几乎所有真实项目 |

`APP_GUARD`、`APP_PIPE`、`APP_INTERCEPTOR` 同理，都从 `@nestjs/core` 导入：

```typescript
@Module({
  providers: [
    { provide: APP_GUARD, useClass: JwtAuthGuard },              // 全局鉴权，能注入 JwtService
    { provide: APP_INTERCEPTOR, useClass: ResponseWrapInterceptor },
    { provide: APP_FILTER, useClass: AllExceptionsFilter },
    {
      provide: APP_PIPE,
      // ValidationPipe 的配置只能通过构造参数传，所以这里用 useValue
      useValue: new ValidationPipe({ whitelist: true, transform: true }),
    },
  ],
})
export class AppModule {}
```

几个补充：

- `useClass` 才有依赖注入；`useValue: new ValidationPipe({...})` 是「要传配置但不需要注入」时的折中写法。如果全局 Pipe 既要配置又要注入依赖，就自己写一个 Pipe 类，在里面 `new ValidationPipe(options)` 或直接继承它。
- 注册顺序对 Filter 没意义（只按 `@Catch()` 类型就近匹配），但对 Interceptor 有意义（决定洋葱层次）、对 Guard 有意义（决定短路顺序）。
- 全局切面默认是**单例**。想拿请求级数据就从 `ArgumentsHost` / `ExecutionContext` 里取，不要往实例字段上存——并发请求会互相覆盖。确实需要请求级实例时才声明 `Scope.REQUEST`，代价是每个请求都要重新构造依赖树（见[依赖注入](/guide/nestjs-di)）。
- 用 `APP_GUARD` 注册全局鉴权后，公开接口要用元数据开后门（`@Public()`），不要在 Guard 里维护路径白名单。
