# NestJS 装饰器体系

> NestJS 大量使用装饰器，理解装饰器体系是读懂 NestJS 代码的第一步。

## 什么是装饰器

装饰器是以 `@` 符号开头的特殊函数，可以附加在类、方法、属性或参数上，用于添加元数据、扩展行为、描述用途。

NestJS 提供大量内置装饰器，也支持自定义。

---

## 类装饰器

```typescript
@Controller('users')        // 标记为控制器，路由前缀 /users
@Injectable()               // 标记为可注入的 Provider
@Module({ ... })            // 标记为模块
@Guard()                    // 通常不直接用，见守卫章节
```

---

## 路由方法装饰器

```typescript
@Controller('cats')
export class CatsController {
  @Get()                    // GET /cats
  findAll(): string { ... }

  @Get(':id')               // GET /cats/:id
  findOne(@Param('id') id: string) { ... }

  @Post()                   // POST /cats
  create(@Body() dto: CreateCatDto) { ... }

  @Patch(':id')             // PATCH /cats/:id
  update(@Param('id') id: string, @Body() dto: UpdateCatDto) { ... }

  @Delete(':id')            // DELETE /cats/:id
  remove(@Param('id') id: string) { ... }

  @Put(':id')               // PUT /cats/:id
  replace(@Param('id') id: string, @Body() dto: CreateCatDto) { ... }
}
```

---

## 参数装饰器

```typescript
@Controller('example')
export class ExampleController {
  @Get(':id')
  example(
    @Param('id') id: string,            // 路由参数 :id
    @Param() params: Record<string, string>, // 所有路由参数
    @Query('page') page: number,        // 查询参数 ?page=1
    @Query() query: Record<string, any>,// 所有查询参数
    @Body() body: CreateDto,            // 完整请求体
    @Body('name') name: string,         // 请求体中的某个字段
    @Headers('authorization') auth: string, // 请求头
    @Req() req: Request,                // 原始请求对象
    @Res() res: Response,               // 原始响应对象（需手动 res.send()）
    @Ip() ip: string,                   // 客户端 IP
  ) {}
}
```

> ⚠️ 使用 `@Res()` 后，NestJS 不再自动发送响应，必须手动调用 `res.json()` 或 `res.send()`。通常避免直接使用 `@Res()`，除非需要底层控制（如流式响应）。

---

## HTTP 状态码与响应控制

```typescript
@Post()
@HttpCode(201)              // 自定义响应状态码
create(@Body() dto: CreateCatDto) { ... }

@Get()
@Header('Cache-Control', 'no-cache')  // 设置响应头
findAll() { ... }

@Get(':id')
@Redirect('https://nestjs.com', 301)  // 重定向
redirect() {}
```

---

## 自定义装饰器

```typescript
// 提取当前用户（配合 Guard 使用）
import { createParamDecorator, ExecutionContext } from '@nestjs/common'

export const CurrentUser = createParamDecorator(
  (data: unknown, ctx: ExecutionContext) => {
    const request = ctx.switchToHttp().getRequest()
    return request.user  // 由 AuthGuard 注入到 request 上
  }
)

// 控制器中使用
@Get('profile')
getProfile(@CurrentUser() user: User) {
  return user
}
```

**自定义元数据装饰器（配合 Guard 做权限控制）：**

```typescript
import { SetMetadata } from '@nestjs/common'

export const Roles = (...roles: string[]) => SetMetadata('roles', roles)

// 控制器中标记所需角色
@Post()
@Roles('admin')
create(@Body() dto: CreateCatDto) { ... }

// Guard 中读取元数据
@Injectable()
export class RolesGuard implements CanActivate {
  constructor(private reflector: Reflector) {}

  canActivate(context: ExecutionContext): boolean {
    const requiredRoles = this.reflector.get<string[]>('roles', context.getHandler())
    if (!requiredRoles) return true

    const { user } = context.switchToHttp().getRequest()
    return requiredRoles.some(role => user.roles.includes(role))
  }
}
```

---

## 装饰器组合

多个装饰器可以叠加使用，执行顺序**从下到上**（距离方法最近的先执行）：

```typescript
@Controller('products')
@UseGuards(AuthGuard)           // 类级别守卫
export class ProductsController {

  @Post()
  @Roles('admin')               // 先检查角色元数据
  @UseGuards(RolesGuard)        // 再执行 RolesGuard
  @UseInterceptors(LoggingInterceptor)
  create(@Body() dto: CreateProductDto) { ... }
}
```

---

## 常用装饰器速查

| 装饰器 | 类型 | 说明 |
|---|---|---|
| `@Controller(prefix)` | 类 | 标记控制器，设置路由前缀 |
| `@Injectable()` | 类 | 标记为可注入的 Provider |
| `@Module()` | 类 | 标记为模块 |
| `@Get/Post/Put/Patch/Delete()` | 方法 | HTTP 路由方法 |
| `@HttpCode(code)` | 方法 | 自定义响应状态码 |
| `@UseGuards(guard)` | 方法/类 | 应用守卫 |
| `@UseInterceptors(interceptor)` | 方法/类 | 应用拦截器 |
| `@UsePipes(pipe)` | 方法/类 | 应用管道 |
| `@Param(key?)` | 参数 | 路由参数 |
| `@Query(key?)` | 参数 | 查询参数 |
| `@Body(key?)` | 参数 | 请求体 |
| `@Headers(key?)` | 参数 | 请求头 |
| `@Req()` | 参数 | 原始 Request 对象 |
| `@Res()` | 参数 | 原始 Response 对象 |
| `@Inject(token)` | 参数/属性 | 显式注入 |
