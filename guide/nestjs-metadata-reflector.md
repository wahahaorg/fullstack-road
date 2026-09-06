---
title: 元数据与 Reflector：Nest 魔法的底层
---

# 元数据与 Reflector：Nest 魔法的底层

> 为什么加一个 `@Injectable()` 就能被注入？为什么构造函数里写个类型，实例就自动来了？这篇把装饰器背后的元数据机制讲透，最后手写一个能跑的迷你 IoC 容器。

## TS 装饰器只是语法糖

装饰器不是什么运行时黑魔法。它编译后就是**普通函数调用**：

```typescript
@Injectable()
export class OrdersService {
  constructor(private readonly repo: OrderRepository) {}
}
```

tsc 输出的东西大致长这样（省略了 helper 实现）：

```javascript
let OrdersService = class OrdersService {
  constructor(repo) { this.repo = repo }
}

OrdersService = __decorate([
  (0, common_1.Injectable)(),
  __metadata('design:paramtypes', [order_repository_1.OrderRepository]),
], OrdersService)

exports.OrdersService = OrdersService
```

三个观察：

- `__decorate` 做的事只是「按顺序把装饰器套在目标上，把最后的返回值赋回原变量」。没有任何存储行为。
- `@Injectable()` 返回的那个函数内部才真正存了东西 —— 它调用了 `Reflect.defineMetadata`。**装饰器本身不存储任何信息，它只是一次副作用调用的时机。**
- `__metadata('design:paramtypes', [...])` 这一行**源码里根本没写**。它是编译器加的，后面会讲为什么。

---

## reflect-metadata 是什么

`Reflect.get` / `Reflect.has` / `Reflect.construct` 这些是 ES 标准。但 metadata 相关的 API **不是标准**，还停在提案阶段，所以要靠 `reflect-metadata` 这个 polyfill 往全局 `Reflect` 上打补丁。

```typescript
import 'reflect-metadata'

class Order {}

Reflect.defineMetadata('table', 'orders', Order)              // 挂在类上
Reflect.defineMetadata('column', 'total_fee', Order, 'total') // 挂在类的某个属性上

Reflect.getMetadata('table', Order)            // 'orders'
Reflect.getMetadata('column', Order, 'total')  // 'total_fee'
Reflect.hasMetadata('table', Order)            // true
Reflect.getMetadataKeys(Order)                 // ['table']
Reflect.deleteMetadata('table', Order)
```

| API | 说明 |
|---|---|
| `defineMetadata(key, value, target[, propertyKey])` | 写入 |
| `getMetadata(key, target[, propertyKey])` | 读取，**会沿原型链往上找** |
| `getOwnMetadata(...)` | 只看自己，不看父类 |
| `hasMetadata` / `hasOwnMetadata` | 存在性判断 |
| `getMetadataKeys(target[, propertyKey])` | 列出所有 key，调试时很有用 |
| `Reflect.metadata(key, value)` | 装饰器形式，等价于 `defineMetadata` |

**本质是一个以 target 为 key 的 WeakMap**，值是「propertyKey → (metadataKey → value)」的两层 Map：

```typescript
WeakMap<object, Map<PropertyKey | undefined, Map<any, any>>>
```

两个直接后果：元数据挂在**类对象**上而不是实例上，同一个类的所有实例共享一份；`getMetadata` 会走原型链，所以子类 Controller 能自动继承基类上声明的元数据。

### 为什么要 import 它

它是**副作用 import**：不导出任何东西，只给全局 `Reflect` 加方法。没有它，`Reflect.defineMetadata` 就是 `undefined`。

Nest 的入口包内部已经 import 过一次，所以业务项目的 `main.ts` 里通常看不到这行。但自己写脚本、写库、或搭编译测试环境时必须显式 import，且要保证它在**任何用到元数据的模块之前**执行。重复 import 无害。

---

## emitDecoratorMetadata：DI 能靠类型工作的唯一原因

TS 有个编译选项 `emitDecoratorMetadata`。开启后，只要一个目标上**至少有一个装饰器**，tsc 就会额外写入三条类型元数据：

```json
{
  "compilerOptions": {
    "experimentalDecorators": true,
    "emitDecoratorMetadata": true
  }
}
```

| key | 存的是 | 什么时候写入 |
|---|---|---|
| `design:type` | 被装饰目标本身的类型（属性的类型；方法则是 `Function`） | 装饰属性或方法 |
| `design:paramtypes` | 参数类型对应的构造函数数组 | 装饰类（取构造器参数）或方法 |
| `design:returntype` | 返回值类型 | 装饰方法 |

看一个具体例子：

```typescript
@Injectable()
export class OrdersService {
  constructor(
    private readonly repo: OrderRepository,
    private readonly mailer: MailerService,
  ) {}
}
```

```typescript
Reflect.getMetadata('design:paramtypes', OrdersService)
// [ [class OrderRepository], [class MailerService] ]
```

**这就是 DI 的全部秘密。** Nest 拿到这个数组，把每一项当 token 去容器里查实例，然后 `new OrdersService(repo, mailer)`。所谓「按类型自动注入」，就是读一行编译器帮你写的元数据。

::: warning 为什么 @Injectable() 不能省
tsc 只在目标**有装饰器**时才 emit 这些元数据。一个有构造器依赖的类如果不写 `@Injectable()`，它的 `design:paramtypes` 压根不存在，Nest 只能拿到空数组 —— 于是报 `Nest can't resolve dependencies of the XxxService`。这是新手最高频的一个错误。
:::

### 为什么 interface 不能当注入 token

```typescript
export interface OrderRepository {
  find(): Promise<Order[]>
}

@Injectable()
export class OrdersService {
  constructor(private readonly repo: OrderRepository) {}  // ❌ 跑不起来
}
```

`interface` 是纯类型，编译后**一点痕迹都不剩**。`design:paramtypes` 里那一位会退化成 `Object`，Nest 拿 `Object` 当 token 去容器里找，当然找不到。同样的原因，`type` 别名、联合类型、泛型参数都不能当 token。

两种解法：

```typescript
// 1. 用 string / Symbol 当 token，配 @Inject()
constructor(@Inject('ORDER_REPO') private readonly repo: OrderRepository) {}

// 2. 用抽象类当 token —— 抽象类编译后还在，既是类型又是值
export abstract class OrderRepository {
  abstract find(): Promise<Order[]>
}
constructor(private readonly repo: OrderRepository) {}   // ✅ 不用 @Inject
```

第二种更优雅：一个符号同时充当契约和 token，还能被 IDE 跳转。面向接口编程的完整讨论见 [依赖注入](/guide/nestjs-di)。

> ⚠️ 同一套机制也解释了另一件事：**DTO 上不写 class-validator 装饰器就没有任何校验**。`dto: CreateOrderDto` 这个类型标注在运行时不存在，校验规则必须由 `@IsEmail()` 这类装饰器实打实写进元数据里。

### 一个容易踩的工程坑

`emitDecoratorMetadata` 是 **TS 编译器特性**，不是所有构建工具都支持：

| 工具 | 支持情况 |
|---|---|
| `tsc` / `ts-node` | ✅ 原生支持 |
| SWC（`@swc/core`、Nest CLI 的 `--builder swc`） | ✅ 需显式开 `legacyDecorator` + `decoratorMetadata` |
| esbuild / `tsx` | ❌ 不支持，DI 会直接失效 |
| TS 5 的标准装饰器（去掉 `experimentalDecorators`） | ❌ 标准装饰器没有这个特性 |

最后一条是 Nest 至今仍用 legacy 装饰器的原因：整个 DI 依赖 `emitDecoratorMetadata`，而它只在 `experimentalDecorators: true` 下可用。所以别自作聪明去掉这个选项，也别为了「构建更快」把 Nest 项目直接换成 esbuild 跑。

---

## SetMetadata 与 Reflector

上面讲的都是框架自己读元数据。Nest 还把这套能力开放给了业务代码：用 `@SetMetadata` 写，用 `Reflector` 读。

写入端 —— 永远包一层语义化的装饰器，不要在业务代码里裸用 `@SetMetadata`：

```typescript
// roles.decorator.ts
import { SetMetadata } from '@nestjs/common'

export const ROLES_KEY = 'roles'
export type Role = 'admin' | 'operator' | 'viewer'

export const Roles = (...roles: Role[]) => SetMetadata(ROLES_KEY, roles)
```

读取端 —— 注入 `Reflector`，从 `ExecutionContext` 拿目标：

```typescript
// roles.guard.ts
import { CanActivate, ExecutionContext, Injectable } from '@nestjs/common'
import { Reflector } from '@nestjs/core'
import { ROLES_KEY, Role } from './roles.decorator'

@Injectable()
export class RolesGuard implements CanActivate {
  constructor(private readonly reflector: Reflector) {}

  canActivate(ctx: ExecutionContext): boolean {
    const required = this.reflector.getAllAndOverride<Role[]>(ROLES_KEY, [
      ctx.getHandler(),   // 方法级优先
      ctx.getClass(),     // 没有就退回类级
    ])

    if (!required?.length) return true   // 没标注 = 不限制

    const { user } = ctx.switchToHttp().getRequest()
    return required.some((role) => user?.roles?.includes(role))
  }
}
```

```typescript
@Controller('orders')
@Roles('operator')            // 整个控制器至少是 operator
export class OrdersController {
  @Delete(':id')
  @Roles('admin')             // 删除单独收紧到 admin
  remove(@Param('id') id: string) {}
}
```

### 四个读取方法的区别

| 方法 | 行为 | 适用场景 |
|---|---|---|
| `get(key, target)` | 从单个 target 读，等价于 `Reflect.getMetadata` | 只关心一个位置 |
| `getAll(key, [t1, t2])` | 返回一一对应的数组，不做任何处理 | 想自己决定怎么合 |
| `getAllAndOverride(key, [t1, t2])` | 返回**第一个非空**值 | 覆盖语义：方法级压过类级 |
| `getAllAndMerge(key, [t1, t2])` | 数组拼接、对象浅合并 | 叠加语义：类级和方法级都算 |

同样是类上 `@Roles('operator')`、方法上 `@Roles('admin')`，两个方法结果完全不同：

```typescript
this.reflector.getAllAndOverride(ROLES_KEY, [ctx.getHandler(), ctx.getClass()])
// ['admin']              ← 方法级说了算

this.reflector.getAllAndMerge(ROLES_KEY, [ctx.getHandler(), ctx.getClass()])
// ['admin', 'operator']  ← 两级相加
```

选哪个是**语义问题，不是偏好问题**：**权限收窄用 Override**（上面那个删除接口的意图是「只有 admin 能删」，用 Merge 会变成 `['admin', 'operator']`，配上 `some()` 判断 operator 也能删了，这是个安全漏洞）；**能力叠加用 Merge**（缓存标签、审计分类、Swagger 分组这类「类上写共性、方法上加特性」的场景）。`getAll` 很少直接用，除非合并规则比拼接更复杂，比如取最小 TTL。

---

## 手写一个迷你 IoC 容器

理解 DI 最快的方式是自己实现一遍。下面这个容器支持 `@Injectable`、`@Inject`、值 Provider、递归解析、单例缓存、循环依赖检测，一百行左右，能直接跑。

先准备环境：

```json
// tsconfig.json
{
  "compilerOptions": {
    "target": "ES2021",
    "module": "commonjs",
    "strict": true,
    "experimentalDecorators": true,
    "emitDecoratorMetadata": true
  }
}
```

```bash
npm i reflect-metadata
npm i -D typescript ts-node @types/node
npx ts-node mini-ioc.ts        # 注意：不能用 tsx / esbuild，它们不 emit 元数据
```

### 两个装饰器

```typescript
// mini-ioc.ts
import 'reflect-metadata'

type Constructor<T = any> = new (...args: any[]) => T
type Token = string | symbol | Constructor

const INJECTABLE = Symbol('mini:injectable')
const PARAM_TOKENS = Symbol('mini:param-tokens')

/** 标记这个类允许被容器创建 */
export function Injectable(): ClassDecorator {
  return (target) => {
    Reflect.defineMetadata(INJECTABLE, true, target)
  }
}

/** 给第 index 个构造器参数指定自定义 token，覆盖类型推断 */
export function Inject(token: Token) {
  return (target: object, _key: string | symbol | undefined, index: number) => {
    const tokens: Record<number, Token> =
      Reflect.getOwnMetadata(PARAM_TOKENS, target) ?? {}
    tokens[index] = token
    Reflect.defineMetadata(PARAM_TOKENS, tokens, target)
  }
}
```

`@Injectable()` 只写了一个布尔标记 —— 它真正的作用是**触发 tsc 去 emit `design:paramtypes`**。这也印证了前面那句话：装饰器本身几乎不存东西，重要的是它的存在本身。

### 容器

```typescript
interface ValueProvider { value: unknown }

export class Container {
  private providers = new Map<Token, Constructor | ValueProvider>()
  private instances = new Map<Token, unknown>()

  registerClass(token: Token, cls: Constructor) {
    this.providers.set(token, cls)
    return this
  }

  registerValue(token: Token, value: unknown) {
    this.providers.set(token, { value })
    return this
  }

  resolve<T>(token: Token, chain: Token[] = []): T {
    // 1. 单例缓存
    if (this.instances.has(token)) return this.instances.get(token) as T

    // 2. 循环依赖检测
    if (chain.includes(token)) {
      const path = [...chain, token].map(label).join(' -> ')
      throw new Error(`检测到循环依赖：${path}`)
    }

    // 3. 找 provider：显式注册优先，否则 token 本身就是类
    const provider =
      this.providers.get(token) ?? (typeof token === 'function' ? token : undefined)
    if (!provider) throw new Error(`找不到 ${label(token)} 对应的 provider`)

    // 4. 值 provider 直接返回
    if (typeof provider === 'object') {
      this.instances.set(token, provider.value)
      return provider.value as T
    }

    if (!Reflect.getMetadata(INJECTABLE, provider)) {
      throw new Error(`${label(provider)} 没有加 @Injectable()`)
    }

    // 5. 关键一步：读编译器写入的构造器参数类型
    const paramTypes: Constructor[] =
      Reflect.getMetadata('design:paramtypes', provider) ?? []
    const custom: Record<number, Token> =
      Reflect.getOwnMetadata(PARAM_TOKENS, provider) ?? {}

    // 6. 递归解析每个依赖，@Inject 的 token 优先于类型推断
    const args = paramTypes.map((paramType, i) =>
      this.resolve(custom[i] ?? paramType, [...chain, token]),
    )

    const instance = new provider(...args)
    this.instances.set(token, instance)
    return instance as T
  }
}

function label(token: Token | Constructor) {
  return typeof token === 'function' ? token.name : String(token)
}
```

### 跑起来

```typescript
@Injectable()
class Logger {
  log(msg: string) { console.log('[log]', msg) }
}

@Injectable()
class OrderRepository {
  constructor(
    private readonly logger: Logger,
    @Inject('DB_URL') private readonly dbUrl: string,
  ) {}

  find() {
    this.logger.log(`查库 ${this.dbUrl}`)
    return [{ id: 1024, total: 99 }]
  }
}

@Injectable()
class OrderService {
  constructor(private readonly repo: OrderRepository) {}
  list() { return this.repo.find() }
}

const container = new Container()
container.registerValue('DB_URL', 'postgres://localhost/shop')

console.log(container.resolve<OrderService>(OrderService).list())
// [log] 查库 postgres://localhost/shop
// [ { id: 1024, total: 99 } ]
```

`Logger` 和 `OrderRepository` 一次都没注册过 —— 因为类本身就可以当 token，容器沿着 `design:paramtypes` 一路递归下去，把整棵依赖树建好了。这就是 Nest 启动时干的事，只是它还要处理 Module 边界、作用域、异步工厂、生命周期钩子。

三处值得留意的设计：

| 实现细节 | 对应 Nest 的行为 |
|---|---|
| `instances` 缓存 | Provider 默认单例（`Scope.DEFAULT`） |
| `chain` 记录解析路径 | Nest 的循环依赖报错会打印完整依赖链，同一个思路 |
| `custom[i] ?? paramType` | `@Inject(token)` 优先于类型推断，非 class 的 Provider 必须靠它 |

把 `@Inject('DB_URL')` 去掉试试：`design:paramtypes` 里那一位变成 `String`，容器把 `String` 当 token 拿去解析，最后抛出「String 没有加 @Injectable()」—— 和真实 Nest 里那句 `Nest can't resolve dependencies` 的成因一模一样：**类型信息不够，容器不知道该给你什么**。

---

## 什么时候你会真的需要写元数据

元数据的适用条件很好判断：**这条信息属于「某个接口的声明」，而处理它的逻辑要在别处统一实现**。满足这两点就该用元数据，而不是在 handler 里写 if。

| 场景 | 元数据里存什么 | 谁来读 |
|---|---|---|
| 自定义权限 | 需要的角色、权限点 | Guard |
| 跳过全局逻辑 | 一个 `@Public()` 标记 | 全局 Guard |
| 审计日志 | 操作名、资源类型 | Interceptor |
| 响应缓存 | cache key 模板、TTL | Interceptor |
| 幂等控制 | 幂等 key 取哪个字段、窗口时长 | Interceptor |
| 事务边界 | 是否开事务、隔离级别 | Interceptor |
| 限流 | 每个接口独立的阈值 | Guard |

最实用的是 `@Public()`：全局挂一个 `JwtAuthGuard` 之后，登录和注册接口得放行 —— 用元数据开个口子，比维护一份路径白名单可靠得多。

```typescript
export const IS_PUBLIC_KEY = 'isPublic'
export const Public = () => SetMetadata(IS_PUBLIC_KEY, true)

// 全局 Guard 里第一句
const isPublic = this.reflector.getAllAndOverride<boolean>(IS_PUBLIC_KEY, [
  ctx.getHandler(),
  ctx.getClass(),
])
if (isPublic) return true
```

路径白名单会随重构失效（改了 `@Controller` 前缀就漏了），而 `@Public()` 贴在 handler 上，跟着代码走。

---

## Nest 内部哪些能力依赖元数据

几乎全部。这张表可以当成「Nest 到底是怎么运转的」的索引：

| 能力 | 依赖的元数据 | 谁写入 |
|---|---|---|
| Module 装配 | imports / controllers / providers / exports | `@Module()` |
| 路由注册 | 路径前缀、HTTP method、子路径 | `@Controller()` / `@Get()` 等 |
| 构造器注入 | `design:paramtypes` | **tsc 自动写** |
| 显式 token 注入 | 参数位置到 token 的映射 | `@Inject()` |
| 参数解析 | 第几个参数从哪取、挂了哪些 Pipe | `@Param()` / `@Body()` 等 |
| 增强器绑定 | Guard / Interceptor / Pipe / Filter 列表 | `@UseGuards()` 等 |
| 异常匹配 | Filter 处理哪些异常类型 | `@Catch()` |
| 响应控制 | 状态码、header、重定向目标 | `@HttpCode()` / `@Header()` |
| 业务侧自定义标记 | 任意值 | `@SetMetadata()` |
| Swagger 文档 | schema、示例、安全要求 | `@ApiProperty()` 等 |
| DTO 校验 | 每个字段的校验规则 | class-validator |
| 序列化 | 字段暴露 / 排除策略 | class-transformer |

注意最后三行：它们是**独立的库**，各自维护自己的元数据 key。之所以能和 Nest 无缝配合，是因为大家都往同一个 `Reflect` 上写。

搞清这一层之后，Nest 就没有魔法了：装饰器在启动时执行一次把声明写进元数据；框架递归遍历 Module 树，读元数据装配对象、注册路由；请求进来时 Guard / Interceptor 再用 `Reflector` 读回这些声明，决定怎么处理。

装饰器怎么用见 [装饰器体系](/guide/nestjs-decorators)，容器怎么装配见 [依赖注入](/guide/nestjs-di)，切面怎么消费元数据见 [请求管道](/guide/nestjs-pipeline)。

---

## 面试问答

**1. 为什么不写 `@Injectable()` 会报 `Nest can't resolve dependencies`？DI 按类型注入的原理是什么？**

- DI 的全部秘密是 `design:paramtypes` 这条元数据：tsc 开启 `emitDecoratorMetadata` 后，给有装饰器的类写入构造器参数类型数组，Nest 把每一项当 token 去容器里查实例，然后 `new`。
- tsc 只在目标**有装饰器**时才 emit 这些元数据。不写 `@Injectable()`，`design:paramtypes` 压根不存在，Nest 只能拿到空数组，于是报 can't resolve——这是新手最高频的错误。
- 加分：能说出装饰器本身不存数据，它只是一次调用 `Reflect.defineMetadata` 的时机；元数据本质是一个以 target 为 key 的 WeakMap，挂在类上而不是实例上。

**2. 为什么 interface 不能当注入 token？怎么解决？**

- `interface` 是纯类型，编译后一点痕迹都不剩，`design:paramtypes` 里那一位退化成 `Object`，Nest 拿 `Object` 当 token 去容器里找，当然找不到。
- 解法一：string / Symbol 当 token 配 `@Inject()`；解法二更优雅：抽象类当 token——编译后还在，既是类型又是值，还能被 IDE 跳转。
- 别踩的坑：同一套机制决定了 DTO 上不写 class-validator 装饰器就没有任何校验——类型标注在运行时不存在，规则必须由装饰器实打实写进元数据。

**3. `getAllAndOverride` 和 `getAllAndMerge` 用错了会怎样？**

- Override 返回第一个非空值（方法级压过类级），Merge 是数组拼接、对象浅合并。
- 权限收窄必须用 Override：类上 `@Roles('operator')`、方法上 `@Roles('admin')`，用 Merge 会得到 `['admin', 'operator']`，配上 `some()` 判断 operator 也能删了——这是个安全漏洞。
- 能力叠加才用 Merge（缓存标签、审计分类这类「类上写共性、方法上加特性」的场景）。选哪个是语义问题，不是偏好问题。
- 加分：知道 `getMetadata` 会沿原型链往上找，所以子类 Controller 能自动继承基类上声明的元数据。

**4. 把 Nest 项目换成 esbuild 构建、或升级到 TS 5 标准装饰器，会发生什么？**

- `emitDecoratorMetadata` 是 tsc 编译器特性，esbuild / tsx 不支持，DI 直接失效；SWC 要显式开 `legacyDecorator` + `decoratorMetadata` 才行。
- TS 5 的标准装饰器没有这个特性，这正是 Nest 至今仍用 legacy 装饰器的原因——整个 DI 依赖它。
- 别踩的坑：别为了「构建更快」去掉 `experimentalDecorators` 选项，或把 Nest 项目直接换成 esbuild 跑。

**5. 什么情况下该用元数据，而不是在 handler 里写 if？**

- 判断标准：这条信息属于「某个接口的声明」，而处理它的逻辑要在别处统一实现。
- 最实用的是 `@Public()`：全局 Guard 里第一句读它放行登录注册接口，比维护路径白名单可靠得多——白名单会随重构失效（改了 `@Controller` 前缀就漏了），元数据贴在 handler 上跟着代码走。
- 其余典型场景：审计日志、响应缓存的 key 和 TTL、幂等控制、限流阈值，都是「声明写进元数据、Interceptor / Guard 用 Reflector 统一读」这一个形状。
