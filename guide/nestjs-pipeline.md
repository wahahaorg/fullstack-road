# NestJS 请求管道

> 一个请求从进入到返回，经历 Middleware → Guard → Interceptor → Pipe → Handler 的完整流程。

## 请求处理流程

```
Client Request
     ↓
Middleware          ← 最先执行，偏 HTTP 层通用处理
     ↓
Guard               ← 决定请求能不能继续（认证/授权）
     ↓
Interceptor（前置）  ← 记录日志、开始计时、调用前准备
     ↓
Pipe                ← 参数转换与校验
     ↓
Controller Handler  ← 执行业务逻辑
     ↓
Interceptor（后置）  ← 统一包装响应、记录耗时
     ↓
Client Response
```

---

## Middleware（中间件）

类似 Express 中间件，最早执行，可以访问 `request` / `response` 对象：

```typescript
import { Injectable, NestMiddleware } from '@nestjs/common'
import { Request, Response, NextFunction } from 'express'

@Injectable()
export class LoggerMiddleware implements NestMiddleware {
  use(req: Request, res: Response, next: NextFunction) {
    const start = Date.now()
    console.log(`→ [${req.method}] ${req.originalUrl}`)

    res.on('finish', () => {
      const duration = Date.now() - start
      console.log(`← [${res.statusCode}] ${req.originalUrl} ${duration}ms`)
    })

    next()  // 必须调用，否则请求挂起
  }
}
```

注册中间件：

```typescript
@Module({})
export class AppModule implements NestModule {
  configure(consumer: MiddlewareConsumer) {
    consumer
      .apply(LoggerMiddleware)
      .forRoutes('*')                     // 所有路由

    consumer
      .apply(AuthMiddleware)
      .exclude({ path: 'auth', method: RequestMethod.POST })
      .forRoutes(UsersController)         // 特定控制器
  }
}
```

**适合用 Middleware 做：**
- 请求日志
- 给 request 挂载通用字段（如请求 ID）
- 限流（rate limiting）
- CORS 预处理

---

## Guard（守卫）

决定请求**能不能继续**，返回 `true` 放行，`false` 拒绝：

```typescript
import { Injectable, CanActivate, ExecutionContext } from '@nestjs/common'
import { JwtService } from '@nestjs/jwt'

@Injectable()
export class AuthGuard implements CanActivate {
  constructor(private jwtService: JwtService) {}

  canActivate(context: ExecutionContext): boolean {
    const request = context.switchToHttp().getRequest()
    const token = request.headers.authorization?.replace('Bearer ', '')

    if (!token) return false

    try {
      const payload = this.jwtService.verify(token)
      request.user = payload  // 把用户信息挂到 request 上
      return true
    } catch {
      return false
    }
  }
}
```

使用守卫：

```typescript
// 方法级别
@Get('profile')
@UseGuards(AuthGuard)
getProfile(@CurrentUser() user: User) {}

// 控制器级别（所有路由都需要认证）
@Controller('products')
@UseGuards(AuthGuard)
export class ProductsController {}

// 全局（main.ts）
app.useGlobalGuards(new AuthGuard(jwtService))
```

**适合用 Guard 做：**
- JWT 认证校验
- 角色权限控制（RBAC）
- API Key 验证
- 订阅/配额检查

---

## Interceptor（拦截器）

包住整个调用过程，基于 RxJS Observable：

```typescript
import {
  Injectable, NestInterceptor, ExecutionContext, CallHandler
} from '@nestjs/common'
import { Observable } from 'rxjs'
import { tap, map } from 'rxjs/operators'

// 记录耗时
@Injectable()
export class TimingInterceptor implements NestInterceptor {
  intercept(context: ExecutionContext, next: CallHandler): Observable<any> {
    const start = Date.now()

    return next.handle().pipe(
      tap(() => {
        const duration = Date.now() - start
        console.log(`请求耗时: ${duration}ms`)
      })
    )
  }
}

// 统一包装响应格式
@Injectable()
export class ResponseWrapInterceptor implements NestInterceptor {
  intercept(context: ExecutionContext, next: CallHandler): Observable<any> {
    return next.handle().pipe(
      map(data => ({
        code: 0,
        data,
        timestamp: new Date().toISOString(),
      }))
    )
  }
}

// 缓存（简单示例）
@Injectable()
export class CacheInterceptor implements NestInterceptor {
  private cache = new Map<string, any>()

  intercept(context: ExecutionContext, next: CallHandler): Observable<any> {
    const request = context.switchToHttp().getRequest()
    const key = request.url

    if (this.cache.has(key)) {
      return of(this.cache.get(key))  // 命中缓存，不走 Handler
    }

    return next.handle().pipe(
      tap(data => this.cache.set(key, data))
    )
  }
}
```

---

## Pipe（管道）

在数据传给 Handler 之前做**转换和校验**：

```typescript
// 内置：ParseIntPipe 把字符串转为整数
@Get(':id')
findOne(@Param('id', ParseIntPipe) id: number) {
  return this.service.findOne(id)
}

// 内置：ValidationPipe 校验 DTO
@Post()
create(@Body(new ValidationPipe()) dto: CreateCatDto) {}
```

**内置 9 种 Pipe：**

| Pipe | 作用 |
|---|---|
| `ValidationPipe` | 校验 DTO（配合 class-validator） |
| `ParseIntPipe` | 字符串 → 整数 |
| `ParseFloatPipe` | 字符串 → 浮点数 |
| `ParseBoolPipe` | 字符串 → 布尔值 |
| `ParseArrayPipe` | 逗号分隔字符串 → 数组 |
| `ParseUUIDPipe` | 校验 UUID 格式 |
| `ParseEnumPipe` | 校验枚举值 |
| `DefaultValuePipe` | 提供默认值 |
| `ParseFilePipe` | 文件上传校验 |

**自定义 Pipe：**

```typescript
@Injectable()
export class TrimPipe implements PipeTransform {
  transform(value: any): any {
    if (typeof value === 'string') {
      return value.trim()
    }
    if (typeof value === 'object') {
      return Object.fromEntries(
        Object.entries(value).map(([k, v]) =>
          [k, typeof v === 'string' ? v.trim() : v]
        )
      )
    }
    return value
  }
}
```

---

## 四者职责对比

| | Middleware | Guard | Pipe | Interceptor |
|---|---|---|---|---|
| **执行时机** | 最早 | Guard 阶段 | 参数处理时 | 包住 Handler |
| **访问 Response** | ✅ | ❌ | ❌ | ✅（后置） |
| **能否拦截响应** | ❌ | ❌ | ❌ | ✅ |
| **能否阻止继续** | ✅（不调用 next） | ✅（返回 false） | ✅（抛出异常） | ✅（不调用 handle） |
| **支持 WebSocket/微服务** | ❌（仅 HTTP） | ✅ | ✅ | ✅ |
| **适合场景** | 日志/限流/CORS | 认证/授权 | 校验/转换 | 响应包装/耗时 |

---

## ExecutionContext

Guard、Interceptor、Pipe 都可以访问 `ExecutionContext`，它提供了获取请求上下文的统一接口：

```typescript
canActivate(context: ExecutionContext) {
  // HTTP 上下文
  const request = context.switchToHttp().getRequest<Request>()
  const response = context.switchToHttp().getResponse<Response>()

  // WebSocket 上下文
  const client = context.switchToWs().getClient()
  const data = context.switchToWs().getData()

  // gRPC 上下文
  const grpcCtx = context.switchToRpc().getContext()

  // 获取处理函数元数据
  const roles = this.reflector.get<string[]>('roles', context.getHandler())
}
```
