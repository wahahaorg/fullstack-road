---
title: NestJS 装饰器体系
---

# NestJS 装饰器体系

> Nest 的功能几乎全部通过装饰器暴露。这篇把内置装饰器按用途分类理清，再讲怎么造自己的、以及它们到底在什么时候执行。

## 装饰器在 Nest 里做什么

装饰器是以 `@` 开头的函数，可以贴在类、方法、属性、参数上。在 Nest 里它只做一件事：**把声明信息写进元数据，等框架启动时来读**。

```typescript
@Controller('orders')     // 写入「路由前缀是 orders」
export class OrdersController {
  @Get(':id')             // 写入「GET 方法 + 路径 :id」
  findOne(@Param('id') id: string) {}   // 写入「第 0 个参数从 path param 取」
}
```

装饰器本身不存储任何东西，也不改变方法的逻辑。真正存东西的是 `reflect-metadata`，而 DI 能靠类型自动注入靠的是 TS 的 `emitDecoratorMetadata` 编译选项 —— 这套底层机制见 [元数据与 Reflector](/guide/nestjs-metadata-reflector)，本篇只讲怎么用。

---

## 装饰器全景分类

### 模块与 Provider

| 装饰器 | 用途 | 示例 |
|---|---|---|
| `@Module()` | 声明模块，登记 imports / controllers / providers / exports | `@Module({ providers: [OrdersService] })` |
| `@Global()` | 把模块标记为全局，exports 的 Provider 各处可注入 | `@Global() @Module({...})` |
| `@Injectable()` | 声明这个类可以被容器管理和注入 | `@Injectable() export class OrdersService {}` |
| `@Inject(token)` | 显式指定注入哪个 token（非 class 的 Provider 必须用） | `@Inject('REDIS') private redis: Redis` |
| `@Optional()` | 该依赖找不到时不报错，注入 `undefined` | `@Optional() @Inject('CACHE') cache?: Cache` |

`@Global()` 要省着用：它让依赖关系从「显式声明」退化成「隐式可用」，只适合 Config、Logger 这类真正全局的东西。详见 [依赖注入](/guide/nestjs-di)。

### 控制器与路由方法

| 装饰器 | 用途 | 示例 |
|---|---|---|
| `@Controller()` | 声明控制器，可设路由前缀，也能限定 host | `@Controller({ path: 'orders', host: 'api.example.com' })` |
| `@Get` `@Post` `@Put` `@Patch` `@Delete` `@Head` `@Options` | 对应 HTTP 方法 | `@Patch(':id')` |
| `@All()` | 匹配该路径的所有方法 | `@All('webhook')` |
| `@HttpCode(code)` | 改成功响应的状态码 | `@Post() @HttpCode(202)` |
| `@Header(k, v)` | 追加响应头 | `@Header('Cache-Control', 'no-store')` |
| `@Redirect(url, code)` | 重定向，也可以在返回值里给 `{ url, statusCode }` | `@Redirect('/login', 302)` |
| `@Render(view)` | 用模板引擎渲染，返回值作为模板数据 | `@Render('order-detail')` |
| `@Sse(path)` | 声明 Server-Sent Events 端点，返回 Observable | `@Sse('progress')` |
| `@Version(v)` | 接口版本，配合 `app.enableVersioning()` | `@Version('2')` |

`@Post()` 默认返回 201，其他方法默认 200。只有需要偏离这个默认时才写 `@HttpCode()`。

### 参数装饰器

| 装饰器 | 取什么 | 示例 |
|---|---|---|
| `@Param(key?)` | 路径参数 | `@Param('id', ParseIntPipe) id: number` |
| `@Query(key?)` | query 参数 | `@Query('page') page: string` |
| `@Body(key?)` | 请求体，或体内某个字段 | `@Body() dto: CreateOrderDto` |
| `@Headers(key?)` | 请求头（key 大小写不敏感） | `@Headers('user-agent') ua: string` |
| `@Ip()` | 客户端 IP | `@Ip() ip: string` |
| `@Session()` | session 对象，需先启用 session 中间件 | `@Session() session: Record<string, any>` |
| `@HostParam(key?)` | host 里的参数（配合 `@Controller({ host })`） | `@HostParam('tenant') tenant: string` |
| `@UploadedFile()` / `@UploadedFiles()` | 已解析的上传文件 | `@UploadedFile() file: Express.Multer.File` |
| `@Req()` / `@Request()` | 原始请求对象（同一个东西） | `@Req() req: Request` |
| `@Res()` / `@Response()` | 原始响应对象，会关掉自动响应 | 见下方 passthrough |
| `@Next()` | Express 的 `next`，同样会关掉自动响应 | `@Next() next: NextFunction` |

参数装饰器都支持在第二个参数位置挂 Pipe：`@Query('page', new DefaultValuePipe(1), ParseIntPipe)`。

### 增强器绑定与元数据

| 装饰器 | 用途 | 示例 |
|---|---|---|
| `@UseGuards()` | 绑定 Guard，可用在类或方法上 | `@UseGuards(JwtAuthGuard, RolesGuard)` |
| `@UseInterceptors()` | 绑定 Interceptor | `@UseInterceptors(TimeoutInterceptor)` |
| `@UsePipes()` | 绑定 Pipe（更常见的是直接写在参数位置） | `@UsePipes(new ValidationPipe())` |
| `@UseFilters()` | 绑定 Exception Filter | `@UseFilters(HttpExceptionFilter)` |
| `@Catch()` | 声明这个 Filter 处理哪些异常类型 | `@Catch(HttpException, QueryFailedError)` |
| `@SetMetadata(key, value)` | 往类或方法上挂自定义元数据 | `@SetMetadata('roles', ['admin'])` |

`@SetMetadata` 一般不直接用在业务代码里，而是包一层语义化的自定义装饰器，然后在 Guard 里用 `Reflector` 读回来 —— 完整的读取策略（覆盖还是合并）见 [元数据与 Reflector](/guide/nestjs-metadata-reflector)。

### 微服务与 WebSocket

同一套 Guard / Interceptor / Pipe 在这两种传输层同样生效，只是入口装饰器不同。

| 装饰器 | 用途 | 示例 |
|---|---|---|
| `@MessagePattern()` | 处理请求-响应式消息，有返回值 | `@MessagePattern({ cmd: 'sum' })` |
| `@EventPattern()` | 处理事件式消息，不返回 | `@EventPattern('order.created')` |
| `@Payload(key?)` | 取消息体 | `@Payload() data: CreateOrderDto` |
| `@Ctx()` | 取传输层上下文（如 RabbitMQ 的 channel） | `@Ctx() ctx: RmqContext` |
| `@GrpcMethod()` | 声明 gRPC 方法 | `@GrpcMethod('OrderService', 'FindOne')` |
| `@WebSocketGateway()` | 声明一个 WebSocket 网关类 | `@WebSocketGateway({ cors: true })` |
| `@SubscribeMessage()` | 处理某个事件名 | `@SubscribeMessage('chat')` |
| `@MessageBody()` | 取消息体 | `@MessageBody() text: string` |
| `@ConnectedSocket()` | 取当前连接的 socket | `@ConnectedSocket() client: Socket` |
| `@WebSocketServer()` | 属性装饰器，注入 server 实例用于广播 | `@WebSocketServer() server: Server` |

细节见 [微服务](/guide/nestjs-microservice) 与 [WebSocket 与实时通信](/guide/nestjs-realtime)。

### Swagger（`@nestjs/swagger`）

| 装饰器 | 用途 | 示例 |
|---|---|---|
| `@ApiTags()` | 给控制器分组 | `@ApiTags('订单')` |
| `@ApiOperation()` | 接口标题与说明 | `@ApiOperation({ summary: '创建订单' })` |
| `@ApiProperty()` | DTO / 实体字段的文档与示例 | `@ApiProperty({ example: 2 })` |
| `@ApiBearerAuth()` | 标记该接口需要 Bearer token | `@ApiBearerAuth()` |
| `@ApiOkResponse()` / `@ApiCreatedResponse()` | 声明成功响应结构 | `@ApiOkResponse({ type: OrderVo })` |
| `@ApiConsumes()` | 声明请求 Content-Type | `@ApiConsumes('multipart/form-data')` |
| `@ApiExcludeEndpoint()` | 从文档里隐藏 | `@ApiExcludeEndpoint()` |

装了 `@nestjs/swagger` 的 CLI 插件后，`@ApiProperty()` 大部分可以省掉 —— 插件在编译期从 TS 类型和 class-validator 装饰器推断文档。用法见 [DTO 与 Swagger](/guide/nestjs-dto)。

---

## 装饰器什么时候执行

这是最容易误解的一点：**类装饰器、方法装饰器、参数装饰器都在「类定义被求值」时执行一次，也就是模块被 import 的那一刻，不是每次请求。**

```typescript
function Log(tag: string): MethodDecorator {
  console.log('工厂被调用:', tag)
  return () => {
    console.log('装饰器被应用:', tag)
  }
}

class Demo {
  @Log('A')
  @Log('B')
  handle() {}
}
// 工厂被调用: A
// 工厂被调用: B
// 装饰器被应用: B
// 装饰器被应用: A
```

两条规则：**装饰器表达式（工厂调用）自上而下求值，返回的装饰器函数自下而上应用**。所以「距离方法最近的先生效」说的是第二步。

这解释了一个高频困惑：**为什么装饰器里拿不到 request？** 因为那时候进程刚启动，一个请求都还没来。想在请求期做事只有两条路：

| 需求 | 做法 |
|---|---|
| 请求期读取声明信息 | 装饰器阶段用 `@SetMetadata` 写入，Guard / Interceptor 里用 `Reflector` 读出 |
| 请求期计算参数值 | 用 `createParamDecorator`，传进去的工厂函数每次请求都会执行，参数是 `ExecutionContext` |

---

## `@Res()` 与 passthrough 模式

一旦注入了响应对象，Nest 就**放弃自动响应**：handler 的返回值被忽略，你不自己发响应，请求就挂到超时。

```typescript
@Get('legacy')
download(@Res() res: Response) {
  res.setHeader('Content-Type', 'text/csv')
  res.send('id,total\n1024,99')   // 必须自己发
}
```

这个设计是为了避免「你发了一次，Nest 又发一次」的冲突。但大多数时候我们只是想设个 header 或 cookie，不想接管整个响应流程 —— 这时用 `passthrough`：

```typescript
@Get('export')
async export(@Res({ passthrough: true }) res: Response) {
  res.setHeader('Content-Disposition', 'attachment; filename="orders.csv"')
  res.cookie('last_export_at', Date.now().toString(), { httpOnly: true })

  return this.ordersService.toCsv()   // 返回值照旧由 Nest 序列化并发送
}
```

| 写法 | 谁负责发响应 | 适用场景 |
|---|---|---|
| 不注入 `@Res()` | Nest | 绝大多数接口 |
| `@Res()` | 你自己 | 手动控制流式写入、代理转发、直接 `pipe` 一个 stream |
| `@Res({ passthrough: true })` | Nest | 只是要设 header / cookie / 状态码 |

> ⚠️ `passthrough: true` 下**不要**再调 `res.send()` / `res.json()`，那会变成双重响应。同时注意：注入了 `@Res()` 的 handler，Interceptor 里对返回值的改写（比如统一响应包装）会失效，因为压根没有返回值流过去。

---

## 自定义参数装饰器

`createParamDecorator` 的工厂函数每次请求都会执行，**返回值就是那个参数的值**。第一个参数 `data` 是调用时传进去的东西，靠它可以做「只取某个字段」：

```typescript
import { createParamDecorator, ExecutionContext } from '@nestjs/common'

export interface AuthUser {
  id: string
  email: string
  roles: string[]
}

export const CurrentUser = createParamDecorator(
  (field: keyof AuthUser | undefined, ctx: ExecutionContext) => {
    // user 由 AuthGuard 在校验 token 后挂到 request 上
    const user = ctx.switchToHttp().getRequest<{ user?: AuthUser }>().user
    return field ? user?.[field] : user
  },
)
```

```typescript
@Get('profile')
getProfile(@CurrentUser() user: AuthUser) { return user }

@Get('orders')
myOrders(@CurrentUser('id') userId: string) {
  return this.ordersService.findByUser(userId)
}
```

内置的 `@Query` / `@Headers` / `@Ip` 本质就是这样实现的，所以自定义参数装饰器和内置的完全平级 —— 一样可以在后面挂 Pipe：`@CurrentUser('id', ParseUUIDPipe)`。

### 保持类型安全

`createParamDecorator` 返回的装饰器签名里参数值是 `any`，也就是说 `@CurrentUser('id') userId: number` 这种明显写错的类型标注**编译期不会报错**。要真正被检查，自己包一层带重载的工厂：

```typescript
const extractUser = createParamDecorator(
  (field: keyof AuthUser | undefined, ctx: ExecutionContext) => {
    const user = ctx.switchToHttp().getRequest<{ user?: AuthUser }>().user
    return field ? user?.[field] : user
  },
)

export function CurrentUser(): ParameterDecorator
export function CurrentUser<K extends keyof AuthUser>(field: K): ParameterDecorator
export function CurrentUser(field?: keyof AuthUser): ParameterDecorator {
  return extractUser(field)
}
```

这样传了不存在的字段名会直接编译报错。这层包装值不值得，看这个装饰器被多少人用 —— 团队公共装饰器建议做，一次性的不用。

---

## 用 applyDecorators 打包复合装饰器

一个需要鉴权的接口通常要写四行装饰器，而且**少写一行不会报错，只会静默出问题**（比如忘了 `@ApiBearerAuth()`，Swagger 上就没有锁图标，前端以为不用带 token）。`applyDecorators` 把它们收成一个：

```typescript
// auth.decorator.ts
import { applyDecorators, SetMetadata, UseGuards } from '@nestjs/common'
import { ApiBearerAuth, ApiUnauthorizedResponse } from '@nestjs/swagger'
import { JwtAuthGuard } from './jwt-auth.guard'
import { RolesGuard } from './roles.guard'

export const ROLES_KEY = 'roles'
export type Role = 'admin' | 'operator' | 'viewer'

export function Auth(...roles: Role[]) {
  return applyDecorators(
    SetMetadata(ROLES_KEY, roles),
    UseGuards(JwtAuthGuard, RolesGuard),
    ApiBearerAuth(),
    ApiUnauthorizedResponse({ description: '未登录或 token 已过期' }),
  )
}
```

```typescript
@Controller('orders')
export class OrdersController {
  @Delete(':id')
  @Auth('admin')                      // 一行顶四行，而且不可能只写一半
  remove(@Param('id') id: string) {
    return this.ordersService.remove(id)
  }
}
```

`RolesGuard` 里用 `Reflector` 把 `ROLES_KEY` 读回来做判断，写法见 [授权](/guide/nestjs-authorization)。

两个限制：

- `applyDecorators` 只能组合**类 / 方法 / 属性**装饰器，参数装饰器组合不了。
- 把 `@Get(path)` 也塞进复合装饰器（例如 `Auth()` 顺手把路由声明了）技术上可行，但会让路由表散落在自定义装饰器里，搜不到路径。**路由声明留在原处**，复合装饰器只打包横切关注点。

---

## 绑定层级与生效顺序

Guard / Interceptor / Pipe / Filter 都能绑在三个层级上，同时存在时**全局 → 类 → 方法**依次执行：

```typescript
// main.ts —— 全局
app.useGlobalGuards(new ThrottleGuard())

@Controller('orders')
@UseGuards(JwtAuthGuard)        // 类级：本控制器所有路由都要登录
export class OrdersController {
  @Delete(':id')
  @Auth('admin')                // 方法级：再叠一层角色校验
  @UseInterceptors(AuditInterceptor)
  remove(@Param('id') id: string) {}
}
```

| 层级 | 绑定方式 | 能否注入依赖 |
|---|---|---|
| 全局 | `app.useGlobalGuards(new X())` | ❌ 手动 `new` 拿不到容器里的东西 |
| 全局（可注入） | 在 Module 里注册 `{ provide: APP_GUARD, useClass: X }` | ✅ 推荐这种写法 |
| 类 / 方法 | `@UseGuards(X)` 传**类**而不是实例 | ✅ 由容器实例化 |

> ⚠️ `@UseGuards(new RolesGuard())` 这样传实例，Guard 里的 `constructor(private reflector: Reflector)` 就注入不进来了。传类名让 Nest 自己实例化。

同一个 key 的元数据在类和方法上都存在时，是覆盖还是合并由你读的时候决定（`reflector.getAllAndOverride` / `getAllAndMerge`），这块见 [元数据与 Reflector](/guide/nestjs-metadata-reflector)。

---

## 小结

| 想做的事 | 用什么 |
|---|---|
| 声明路由、取参数 | 内置路由与参数装饰器 |
| 只设 header / cookie，其余交给 Nest | `@Res({ passthrough: true })` |
| 请求期算出一个参数值 | `createParamDecorator` |
| 给 handler 贴上供 Guard 判断的标记 | 包一层 `@SetMetadata` |
| 把一组固定搭配的装饰器收成一个 | `applyDecorators` |
| 理解上面这些为什么能生效 | [元数据与 Reflector](/guide/nestjs-metadata-reflector) |

---

## 面试问答

**1. 装饰器是什么时候执行的？为什么装饰器里拿不到 request？**

- 类 / 方法 / 参数装饰器都在「类定义被求值」时执行一次，也就是模块被 import 的那一刻，不是每次请求——那时进程刚启动，一个请求都还没来。
- 请求期做事只有两条路：装饰器阶段用 `@SetMetadata` 写元数据，Guard / Interceptor 里用 `Reflector` 读；或者用 `createParamDecorator`，传进去的工厂函数每次请求都会执行。
- 加分：求值和应用是两步——装饰器表达式（工厂调用）自上而下求值，返回的装饰器函数自下而上应用，「距离方法最近的先生效」说的是第二步。

**2. 注入 `@Res()` 之后会发生什么？**

- Nest 放弃自动响应：handler 的返回值被忽略，不自己发响应请求就挂到超时。只是想设 header / cookie 用 `@Res({ passthrough: true })`，返回值照旧由 Nest 序列化并发送。
- 别踩的坑：passthrough 下不要再调 `res.send()` / `res.json()`，那是双重响应；注入了 `@Res()` 的 handler，Interceptor 对返回值的改写（比如统一响应包装）会失效，因为压根没有返回值流过去。

**3. 全局 Guard 用 `useGlobalGuards` 还是 `APP_GUARD` 注册？**

- `app.useGlobalGuards(new X())` 是手动 new 的实例，不在 IoC 容器里，Guard 构造函数里的 `Reflector` 注入不进来；`{ provide: APP_GUARD, useClass: X }` 由容器实例化，推荐这种写法。
- 同理 `@UseGuards(X)` 要传类而不是实例，`@UseGuards(new RolesGuard())` 的依赖注入会静默失效。

**4. `applyDecorators` 打包复合装饰器有什么限制？**

- 只能组合类 / 方法 / 属性装饰器，参数装饰器组合不了。
- 路由声明留在原处：把 `@Get(path)` 塞进复合装饰器会让路由表散落在自定义装饰器里，搜不到路径。
- 加分：动机是「少写一行不会报错，只会静默出问题」——忘了 `@ApiBearerAuth()`，Swagger 上没有锁图标，前端以为不用带 token。

**5. 自定义参数装饰器和内置的 `@Query` 是什么关系？**

- 内置的 `@Query` / `@Headers` / `@Ip` 本质就是 `createParamDecorator` 实现的，所以自定义参数装饰器和内置的完全平级——一样可以在后面挂 Pipe：`@CurrentUser('id', ParseUUIDPipe)`。
- `createParamDecorator` 返回的签名里参数值是 `any`，`@CurrentUser('id') userId: number` 这种明显写错的类型标注编译期不会报错；团队公共装饰器值得自己包一层带重载的工厂让字段名有编译期检查，一次性的不用。

