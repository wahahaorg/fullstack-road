# NestJS 进阶特性

> 缓存、任务调度、版本控制、SSE、Logger、测试、安全等生产级能力。

## Logger：结构化日志

NestJS 内置 Logger 比 `console.log()` 提供更多能力：

```typescript
import { Logger, Injectable } from '@nestjs/common'

@Injectable()
export class UsersService {
  private readonly logger = new Logger(UsersService.name)

  async findOne(id: number) {
    this.logger.log(`查询用户 #${id}`)
    try {
      const user = await this.userRepo.findOneBy({ id })
      if (!user) {
        this.logger.warn(`用户 #${id} 不存在`)
        throw new NotFoundException()
      }
      return user
    } catch (err) {
      this.logger.error(`查询用户失败`, err.stack)
      throw err
    }
  }
}
```

**日志级别：** `log` > `warn` > `error` > `debug` > `verbose`

**生产环境推荐：** 使用 `winston` 或 `pino` 替换内置 Logger，支持 JSON 格式、日志文件、日志聚合。

---

## 缓存

```bash
npm install @nestjs/cache-manager cache-manager
# Redis 后端
npm install cache-manager-ioredis-yet ioredis
```

```typescript
// 模块配置（Redis）
CacheModule.registerAsync({
  isGlobal: true,
  useFactory: () => ({
    store: redisStore,
    host: 'localhost',
    port: 6379,
    ttl: 60 * 1000,  // 毫秒
  }),
})
```

**手动操作缓存：**

```typescript
@Injectable()
export class ProductsService {
  constructor(
    @Inject(CACHE_MANAGER) private cacheManager: Cache,
  ) {}

  async findOne(id: number): Promise<Product> {
    const cacheKey = `product:${id}`
    const cached = await this.cacheManager.get<Product>(cacheKey)
    if (cached) return cached

    const product = await this.productRepo.findOneBy({ id })
    await this.cacheManager.set(cacheKey, product, 5 * 60 * 1000)  // 5 分钟
    return product
  }

  async update(id: number, dto: UpdateProductDto) {
    const product = await this.productRepo.save({ id, ...dto })
    await this.cacheManager.del(`product:${id}`)  // 清除缓存
    return product
  }
}
```

**路由级自动缓存：**

```typescript
@UseInterceptors(CacheInterceptor)
@CacheKey('all-products')
@CacheTTL(30 * 1000)  // 30 秒
@Get()
findAll() {
  return this.productsService.findAll()
}
```

---

## 任务调度

```bash
npm install @nestjs/schedule
```

```typescript
@Module({
  imports: [ScheduleModule.forRoot()],
})

@Injectable()
export class TasksService {
  private readonly logger = new Logger(TasksService.name)

  // Cron 表达式
  @Cron('0 0 * * *')                       // 每天 0 点
  @Cron(CronExpression.EVERY_HOUR)          // 每小时
  async dailyCleanup() {
    this.logger.log('执行每日清理任务')
    await this.cleanExpiredSessions()
  }

  // 固定间隔（毫秒）
  @Interval(30000)  // 每 30 秒
  async syncData() {
    await this.syncFromExternalService()
  }

  // 延迟执行一次
  @Timeout(5000)  // 应用启动后 5 秒执行一次
  async initCache() {
    await this.warmUpCache()
  }
}
```

---

## API 版本控制

NestJS 支持 4 种方式：

```typescript
// URI 版本控制（推荐，最常见）
app.enableVersioning({ type: VersioningType.URI })
// 访问：GET /v1/users，GET /v2/users

// Header 版本控制
app.enableVersioning({
  type: VersioningType.HEADER,
  header: 'API-Version',
})
// 访问：GET /users + Header: API-Version: 1

// 媒体类型版本控制
app.enableVersioning({ type: VersioningType.MEDIA_TYPE, key: 'v=' })
// 访问：GET /users + Accept: application/json;v=1
```

```typescript
// 控制器版本
@Controller({ path: 'users', version: '1' })
export class UsersV1Controller {}

@Controller({ path: 'users', version: '2' })
export class UsersV2Controller {}

// 路由级别版本
@Version('1')
@Get()
findAllV1() {}

@Version(['1', '2'])  // 多版本共用
@Get(':id')
findOne() {}
```

---

## SSE（Server-Sent Events）

适合 AI 流式输出、实时通知等单向推送场景：

```typescript
import { Sse, MessageEvent } from '@nestjs/common'
import { Observable, interval } from 'rxjs'
import { map } from 'rxjs/operators'

@Controller('events')
export class EventsController {
  // 简单示例：每秒推送一次
  @Sse('heartbeat')
  heartbeat(): Observable<MessageEvent> {
    return interval(1000).pipe(
      map(() => ({ data: { timestamp: Date.now() } }))
    )
  }

  // AI 流式输出示例
  @Sse('chat')
  @UseGuards(JwtAuthGuard)
  async chatStream(@Query('prompt') prompt: string): Promise<Observable<MessageEvent>> {
    const stream = await this.aiService.stream(prompt)

    return new Observable(subscriber => {
      stream.on('data', (token: string) => {
        subscriber.next({ data: { token } })
      })
      stream.on('end', () => {
        subscriber.next({ data: { done: true } })
        subscriber.complete()
      })
      stream.on('error', (err) => subscriber.error(err))
    })
  }
}
```

**客户端（浏览器）：**

```typescript
const source = new EventSource('/events/chat?prompt=hello')
source.onmessage = (event) => {
  const { token, done } = JSON.parse(event.data)
  if (done) source.close()
  else appendToOutput(token)
}
```

**SSE vs WebSocket：**

| 对比 | SSE | WebSocket |
|---|---|---|
| 方向 | 服务端 → 客户端（单向） | 双向 |
| 协议 | HTTP | ws:// |
| 自动重连 | ✅ 浏览器内置 | ❌ 需手动实现 |
| 适合场景 | AI 输出、通知推送 | 实时聊天、游戏 |

---

## 环境变量与配置管理

```bash
npm install @nestjs/config
```

```typescript
// 全局配置模块
@Module({
  imports: [
    ConfigModule.forRoot({
      isGlobal: true,
      envFilePath: ['.env.local', '.env'],
      validationSchema: Joi.object({
        NODE_ENV: Joi.string().valid('development', 'production', 'test').required(),
        DB_HOST: Joi.string().required(),
        JWT_SECRET: Joi.string().min(32).required(),
      }),
    }),
  ],
})

// 注入使用
@Injectable()
export class AppService {
  constructor(private configService: ConfigService) {}

  getDbConfig() {
    return {
      host: this.configService.get<string>('DB_HOST'),
      port: this.configService.get<number>('DB_PORT', 3306),  // 带默认值
    }
  }
}
```

---

## 错误处理

NestJS 使用异常过滤器统一处理错误：

```typescript
// 内置 HTTP 异常
throw new NotFoundException('用户不存在')
throw new BadRequestException('请求参数错误')
throw new UnauthorizedException('未登录')
throw new ForbiddenException('无权访问')
throw new ConflictException('数据已存在')

// 自定义异常过滤器
@Catch()
export class GlobalExceptionFilter implements ExceptionFilter {
  private readonly logger = new Logger(GlobalExceptionFilter.name)

  catch(exception: unknown, host: ArgumentsHost) {
    const ctx = host.switchToHttp()
    const response = ctx.getResponse<Response>()

    if (exception instanceof HttpException) {
      const status = exception.getStatus()
      const message = exception.getResponse()
      response.status(status).json({
        statusCode: status,
        message,
        timestamp: new Date().toISOString(),
      })
    } else {
      this.logger.error('未处理的异常', exception)
      response.status(500).json({
        statusCode: 500,
        message: 'Internal Server Error',
      })
    }
  }
}

// 注册全局过滤器
app.useGlobalFilters(new GlobalExceptionFilter())
```

---

## CORS

```typescript
// 简单启用
app.enableCors()

// 精细配置
app.enableCors({
  origin: ['https://app.example.com', 'https://admin.example.com'],
  methods: ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'],
  allowedHeaders: ['Content-Type', 'Authorization'],
  credentials: true,
})
```

---

## 安全加固

```bash
npm install helmet
```

```typescript
import helmet from 'helmet'

app.use(helmet())        // 安全响应头（XSS、clickjacking 等）

// 限流
npm install @nestjs/throttler

ThrottlerModule.forRoot([{
  ttl: 60000,   // 时间窗口（毫秒）
  limit: 100,   // 窗口内最大请求数
}])

@UseGuards(ThrottlerGuard)
@Controller('auth')
export class AuthController {}
```

---

## 测试框架

NestJS 推荐 Jest，内置 `@nestjs/testing`：

```typescript
// 单元测试
describe('UsersService', () => {
  let service: UsersService

  beforeEach(async () => {
    const module = await Test.createTestingModule({
      providers: [
        UsersService,
        { provide: getRepositoryToken(User), useValue: mockRepo },
      ],
    }).compile()
    service = module.get(UsersService)
  })

  it('findOne：用户不存在时抛出 NotFoundException', async () => {
    mockRepo.findOneBy.mockResolvedValue(null)
    await expect(service.findOne(999)).rejects.toThrow(NotFoundException)
  })
})

// E2E 测试
describe('UsersController (e2e)', () => {
  let app: INestApplication

  beforeAll(async () => {
    const module = await Test.createTestingModule({
      imports: [AppModule],
    }).compile()
    app = module.createNestApplication()
    await app.init()
  })

  it('GET /users → 200', () => {
    return request(app.getHttpServer())
      .get('/users')
      .expect(200)
      .expect(res => expect(Array.isArray(res.body)).toBe(true))
  })
})
```

---

## 模块类型

| 模块类型 | 说明 | 示例 |
|---|---|---|
| 功能模块 | 按业务功能划分 | `UsersModule`、`ProductsModule` |
| 全局模块 | `@Global()` 标记，无需导入即可注入 | `ConfigModule`、`LoggerModule` |
| 动态模块 | 带配置参数的模块工厂 | `TypeOrmModule.forRoot()`、`JwtModule.register()` |
| 共享模块 | `exports` 公开的模块 | `AuthModule` 导出 `AuthService` |

```typescript
// 全局模块
@Global()
@Module({
  providers: [LoggerService],
  exports: [LoggerService],
})
export class LoggerModule {}
```

---

## 文件上传

NestJS 通过 `FileInterceptor` 处理文件上传：

```bash
npm install @types/multer
```

```typescript
import {
  Controller, Post, UseInterceptors, UploadedFile,
  UploadedFiles, BadRequestException,
} from '@nestjs/common'
import { FileInterceptor, FilesInterceptor } from '@nestjs/platform-express'
import { diskStorage } from 'multer'
import { extname } from 'path'

@Controller('upload')
export class UploadController {
  // 单文件上传
  @Post('file')
  @UseInterceptors(
    FileInterceptor('file', {
      storage: diskStorage({
        destination: './uploads',
        filename: (req, file, cb) => {
          const name = Date.now() + extname(file.originalname)
          cb(null, name)
        },
      }),
      limits: { fileSize: 10 * 1024 * 1024 },  // 10MB
      fileFilter: (req, file, cb) => {
        if (!file.mimetype.match(/\/(jpg|jpeg|png|gif|pdf)$/)) {
          cb(new BadRequestException('不支持的文件类型'), false)
        }
        cb(null, true)
      },
    }),
  )
  uploadFile(@UploadedFile() file: Express.Multer.File) {
    return { filename: file.filename, path: file.path, size: file.size }
  }

  // 多文件上传
  @Post('files')
  @UseInterceptors(FilesInterceptor('files', 5))  // 最多 5 个
  uploadFiles(@UploadedFiles() files: Express.Multer.File[]) {
    return files.map(f => ({ filename: f.filename, size: f.size }))
  }
}
```

---

## WebSocket Gateway

```bash
npm install @nestjs/websockets @nestjs/platform-socket.io
```

```typescript
import {
  WebSocketGateway, WebSocketServer, SubscribeMessage,
  OnGatewayConnection, OnGatewayDisconnect,
} from '@nestjs/websockets'
import { Server, Socket } from 'socket.io'

@WebSocketGateway({
  cors: { origin: '*' },
  namespace: '/chat',
})
export class ChatGateway implements OnGatewayConnection, OnGatewayDisconnect {
  @WebSocketServer()
  server: Server

  handleConnection(client: Socket) {
    console.log(`客户端连接: ${client.id}`)
  }

  handleDisconnect(client: Socket) {
    console.log(`客户端断开: ${client.id}`)
  }

  @SubscribeMessage('message')
  handleMessage(client: Socket, payload: { room: string; text: string }) {
    this.server.to(payload.room).emit('message', {
      from: client.id,
      text: payload.text,
    })
  }

  @SubscribeMessage('join')
  handleJoin(client: Socket, room: string) {
    client.join(room)
  }
}
```

**前端连接：**

```typescript
import { io } from 'socket.io-client'

const socket = io('http://localhost:3000/chat')
socket.emit('join', 'room-1')
socket.emit('message', { room: 'room-1', text: 'Hello' })
socket.on('message', (data) => console.log(data))
```

---

## 循环依赖

当两个服务互相依赖时：

```typescript
// ❌ 直接互相 import 会报错
@Injectable()
export class CatsService {
  constructor(private commonService: CommonService) {}  // Error!
}
```

```typescript
// ✅ 用 forwardRef 解决
import { forwardRef, Inject } from '@nestjs/common'

@Injectable()
export class CatsService {
  constructor(
    @Inject(forwardRef(() => CommonService))
    private commonService: CommonService,
  ) {}
}

// 另一侧也要加
@Injectable()
export class CommonService {
  constructor(
    @Inject(forwardRef(() => CatsService))
    private catsService: CatsService,
  ) {}
}
```

---

## 软删除（TypeORM）

```typescript
import { Entity, Column, DeleteDateColumn } from 'typeorm'

@Entity()
export class User {
  @Column()
  name: string

  @DeleteDateColumn()
  deletedAt?: Date  // 被删除时自动设置为当前时间
}

// Service
@Injectable()
export class UsersService {
  constructor(
    @InjectRepository(User)
    private userRepo: Repository<User>,
  ) {}

  // 软删除
  async softRemove(id: number) {
    await this.userRepo.softDelete(id)
  }

  // 恢复
  async restore(id: number) {
    await this.userRepo.restore(id)
  }

  // 普通查询不包含软删除的
  async findAll(): Promise<User[]> {
    return this.userRepo.find()  // 自动过滤 deletedAt IS NULL
  }

  // 包含已删除的
  async findAllWithDeleted(): Promise<User[]> {
    return this.userRepo.find({ withDeleted: true })
  }
}
```

**为什么用软删除：**
- 数据可恢复
- 保留审计跟踪
- 不破坏外键关系

---

## 微服务基础（TCP 传输）

```bash
npm install @nestjs/microservices
```

```typescript
// main.ts — 混合 HTTP + TCP 微服务
import { NestFactory } from '@nestjs/core'
import { Transport, MicroserviceOptions } from '@nestjs/microservices'

async function bootstrap() {
  const app = await NestFactory.create(AppModule)

  // 微服务（TCP）
  app.connectMicroservice<MicroserviceOptions>({
    transport: Transport.TCP,
    options: { port: 3001 },
  })

  await app.startAllMicroservices()
  await app.listen(3000)
}

// document.controller.ts — 微服务控制器
import { Controller } from '@nestjs/common'
import { MessagePattern } from '@nestjs/microservices'

@Controller()
export class DocumentController {
  @MessagePattern({ cmd: 'parse_document' })
  async parseDocument(data: { documentId: number }) {
    // 在微服务中解析文档
    return { status: 'parsed' }
  }
}

// 客户端调用
@Injectable()
export class AppService {
  constructor(
    @Inject('DOCUMENT_SERVICE') private client: ClientProxy,
  ) {}

  async parseDoc(id: number) {
    return this.client.send({ cmd: 'parse_document' }, { documentId: id }).toPromise()
  }
}
```

---

## 面试怎么说

> NestJS 的进阶能力包括缓存管理（@nestjs/cache-manager + Redis）、任务调度（@nestjs/schedule）、SSE 实时推送、文件上传、WebSocket Gateway、API 版本控制、循环依赖处理、软删除和微服务。生产环境会用 Helmet 安全头、Throttler 限流、ConfigModule 管理环境变量，再用 Jest + @nestjs/testing 覆盖单元和 E2E 测试。
