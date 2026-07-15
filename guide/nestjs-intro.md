# NestJS 简介与架构概览

> 一个面向企业级应用的 Node.js 框架，把 Angular 的工程化思想带到了服务端。

## NestJS 是什么？

Nest（NestJS）是一个用于构建高效、可扩展 Node.js 服务端应用的框架。它基于 TypeScript 构建，底层默认使用 Express（也可以切换为 Fastify）。

**设计哲学：**
- 借鉴 Angular 的模块化、装饰器、依赖注入思想
- 解决 Node.js 应用缺乏统一工程结构的问题
- 天然支持 TypeScript，提供完整类型安全

**与 Express 的区别：**

| 对比 | Express | NestJS |
|---|---|---|
| 类型 | 极简框架 | 意见性全栈框架 |
| 结构约束 | 无 | 强约束（模块/控制器/服务） |
| 适合场景 | 小应用、API 网关 | 中大型企业级应用 |
| 学习曲线 | 低 | 较高 |
| TypeScript | 可选 | 原生支持 |

---

## 应用入口

```typescript
// main.ts
import { NestFactory } from '@nestjs/core'
import { AppModule } from './app.module'
import { ValidationPipe } from '@nestjs/common'

async function bootstrap() {
  const app = await NestFactory.create(AppModule)

  // 全局启用请求校验
  app.useGlobalPipes(new ValidationPipe({ whitelist: true }))

  // 全局路由前缀
  app.setGlobalPrefix('api/v1')

  // 启用 CORS
  app.enableCors({ origin: process.env.ALLOWED_ORIGINS?.split(',') })

  await app.listen(3000)
  console.log('Application is running on: http://localhost:3000')
}

bootstrap()
```

---

## 三大核心组成

### Module（模块）

把相关组件组织到一起，是应用结构化的基础：

```typescript
import { Module } from '@nestjs/common'
import { UsersController } from './users.controller'
import { UsersService } from './users.service'
import { TypeOrmModule } from '@nestjs/typeorm'
import { User } from './user.entity'

@Module({
  imports: [TypeOrmModule.forFeature([User])],  // 导入其他模块
  controllers: [UsersController],               // 本模块的控制器
  providers: [UsersService],                    // 本模块的服务
  exports: [UsersService],                      // 对外暴露，其他模块可注入
})
export class UsersModule {}
```

**根模块（AppModule）：**

```typescript
@Module({
  imports: [
    ConfigModule.forRoot({ isGlobal: true }),
    TypeOrmModule.forRoot(typeOrmConfig),
    UsersModule,
    AuthModule,
    ProductsModule,
  ],
})
export class AppModule {}
```

### Controller（控制器）

接收传入请求，返回响应，不包含业务逻辑：

```typescript
import { Controller, Get, Post, Body, Param, Delete, HttpCode } from '@nestjs/common'
import { UsersService } from './users.service'
import { CreateUserDto } from './dto/create-user.dto'

@Controller('users')
export class UsersController {
  constructor(private readonly usersService: UsersService) {}

  @Get()
  findAll() {
    return this.usersService.findAll()
  }

  @Get(':id')
  findOne(@Param('id') id: string) {
    return this.usersService.findOne(+id)
  }

  @Post()
  create(@Body() createUserDto: CreateUserDto) {
    return this.usersService.create(createUserDto)
  }

  @Delete(':id')
  @HttpCode(204)
  remove(@Param('id') id: string) {
    return this.usersService.remove(+id)
  }
}
```

### Service（服务）

承载业务逻辑，可以被注入到控制器或其他服务中：

```typescript
import { Injectable, NotFoundException } from '@nestjs/common'
import { InjectRepository } from '@nestjs/typeorm'
import { Repository } from 'typeorm'
import { User } from './user.entity'
import { CreateUserDto } from './dto/create-user.dto'

@Injectable()
export class UsersService {
  constructor(
    @InjectRepository(User)
    private readonly userRepo: Repository<User>,
  ) {}

  async findAll(): Promise<User[]> {
    return this.userRepo.find()
  }

  async findOne(id: number): Promise<User> {
    const user = await this.userRepo.findOneBy({ id })
    if (!user) throw new NotFoundException(`User #${id} not found`)
    return user
  }

  async create(dto: CreateUserDto): Promise<User> {
    const user = this.userRepo.create(dto)
    return this.userRepo.save(user)
  }

  async remove(id: number): Promise<void> {
    await this.userRepo.delete(id)
  }
}
```

---

## 与 Angular 的对比

NestJS 深受 Angular 影响，很多概念是对应的：

| NestJS | Angular | 说明 |
|---|---|---|
| `@Module()` | `@NgModule()` | 组织应用结构 |
| `@Injectable()` | `@Injectable()` | 可注入服务 |
| `@Controller()` | `@Component()` | 处理请求/视图 |
| DI Container | DI Container | 依赖注入容器 |
| Interceptor | HTTP Interceptor | 拦截请求/响应 |
| Guard | Route Guard | 访问控制 |
| Pipe | Pipe | 数据转换 |

---

## 与其他语言/服务集成

NestJS 本身只运行 JavaScript（TypeScript），不能直接运行 Python/Ruby。

**常见集成方式：**

1. **HTTP/REST**：NestJS 作为 API 网关调用 Python FastAPI 微服务
2. **gRPC**：NestJS 支持 gRPC 客户端/服务端
3. **消息队列**：通过 RabbitMQ/Kafka 与 Python worker 通信
4. **子进程**：`child_process.spawn` 调用 Python 脚本（小规模任务）

```typescript
// 调用 Python 微服务示例
@Injectable()
export class AiService {
  async embed(text: string): Promise<number[]> {
    const response = await fetch('http://python-service:8000/embed', {
      method: 'POST',
      body: JSON.stringify({ text }),
    })
    return response.json()
  }
}
```
