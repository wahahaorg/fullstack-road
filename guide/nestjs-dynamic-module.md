# 动态模块与配置管理

> `TypeOrmModule.forRoot({ ... })` 能带参数，自己写的 `UsersModule` 却不能——差别不在框架给了谁特权，而在前者是动态模块。这篇讲清动态模块怎么写，以及每个真实项目都躲不开的配置管理。

## 静态模块的局限

`@Module({})` 装饰器的参数写死在源码里，装饰器在类定义时就执行完、元数据当场写进类上。所以 `imports: [UsersModule]` 无论出现在哪个模块里，拿到的内容都一样：

```typescript
@Module({
  controllers: [UsersController],
  providers: [UsersService],
  exports: [UsersService],
})
export class UsersModule {}
```

业务模块这样没问题，基础设施模块就卡住了：一个 `RedisModule` 要同时连缓存实例和消息实例（两套地址）；一个 `DatabaseModule` 要区分主库读写和从库只读；一个 `JwtModule`，access token 两小时、refresh token 三十天。

静态模块给不出"同一份代码 + 不同配置"。前端有一模一样的分界：写死的组件只能长一个样，想复用就得能传 props，或者用工厂 `createChart(options)` 造出不同实例。动态模块就是模块层面的那个工厂。

---

## 动态模块的本质

一个动态模块就是**返回 `DynamicModule` 对象的静态方法**，没有任何魔法：

```typescript
@Module({})
export class HttpClientModule {
  static register(options: HttpClientOptions): DynamicModule {
    return {
      module: HttpClientModule,
      providers: [
        { provide: HTTP_CLIENT_OPTIONS, useValue: options },   // 把配置变成 Provider
        HttpClientService,
      ],
      exports: [HttpClientService],
    }
  }
}
```

关键点：**`DynamicModule` 的字段和 `@Module()` 装饰器的参数是同一套东西**，只多了一个指回自己的 `module`，外加可选的 `global`（等价于给模块加 `@Global()`）。想通这一点就没有魔法了。

`imports` 数组既接受模块类，也接受 `DynamicModule` 对象，两种可以混用：

```typescript
@Module({
  imports: [
    UsersModule,                                                        // 静态模块：一个类
    HttpClientModule.register({ baseURL: 'https://api.example.com' }),  // 动态模块：一个对象
  ],
})
export class AppModule {}
```

传进来的 options 被包成 Provider，模块内部就能注入它——这是动态模块"按配置改变行为"的唯一机制：

```typescript
constructor(@Inject(HTTP_CLIENT_OPTIONS) options: HttpClientOptions) {
  this.http = axios.create({ baseURL: options.baseURL, timeout: options.timeout ?? 5000 })
}
```

官方模块也就这么点事：`TypeOrmModule.forRoot` 把连接配置包成 `useValue` Provider，再用 `useFactory` 根据它建出 `DataSource`，最后返回模块定义。

> token 为什么用 `Symbol` 而不是裸字符串、`useValue` 和 `useFactory` 的区别，见 [依赖注入](/guide/nestjs-di)。

---

## 命名约定：register / forRoot / forFeature

方法名叫什么框架都不管，但社区约定了明确语义，照着写别人一眼能看懂：

| 方法名 | 语义 | 调用次数 | 通常写在 |
|---|---|---|---|
| `register()` | 用一次配一次，多次调用互不相干 | 多次 | 用到它的业务模块 |
| `forRoot()` | 全局配一次，全应用共用 | 一次 | `AppModule` |
| `forFeature()` | 在 `forRoot` 之上补局部配置 | 多次 | 各业务模块 |
| `xxxAsync()` | 上面三者的异步版，options 由 `useFactory` 等产出 | 同上 | 同上 |

`TypeOrmModule` 的双层设计是这个约定最好的例子：

```typescript
// AppModule：forRoot 建立唯一的数据库连接
@Module({ imports: [TypeOrmModule.forRoot({ /* host / port / 账号密码 */ })] })
export class AppModule {}

// OrderModule：forFeature 只声明"我这个模块要用哪些实体的 Repository"
@Module({ imports: [TypeOrmModule.forFeature([Order, OrderItem])] })
export class OrderModule {}
```

连接池、事务管理器这类昂贵资源全应用只需要一份，归 `forRoot`；"哪个模块能注入哪些 `Repository<T>`"是局部信息，归 `forFeature`。`JwtModule` 反过来用 `register`，因为不同使用方的 secret 和有效期本就该不一样，不存在"全局唯一的 JWT 配置"。

---

## 手写一个动态模块

上面的 `register` 只接收编译期已知的配置，而真实项目里配置常要从 `ConfigService` 或远端取，于是需要 `registerAsync`。先补类型：

```typescript
export const HTTP_CLIENT_OPTIONS = Symbol('HTTP_CLIENT_OPTIONS')

export interface HttpClientOptions { baseURL: string; timeout?: number }

// 供 useClass / useExisting 用：实现这个接口的类负责产出 options
export interface HttpClientOptionsFactory {
  createHttpClientOptions(): Promise<HttpClientOptions> | HttpClientOptions
}

// 异步 options 的类型 @nestjs/common 有现成的，自带 imports / useFactory / inject / useClass / useExisting
type HttpClientAsyncOptions = ConfigurableModuleAsyncOptions<HttpClientOptions, 'createHttpClientOptions'>
```

`registerAsync` 的本体，核心是把三种形态归一成"产出 options 的那个 Provider"：

```typescript
@Module({})
export class HttpClientModule {
  static registerAsync(options: HttpClientAsyncOptions): DynamicModule {
    return {
      module: HttpClientModule,
      imports: options.imports ?? [],
      providers: [...this.createOptionsProviders(options), HttpClientService],
      exports: [HttpClientService],
    }
  }

  private static createOptionsProviders(options: HttpClientAsyncOptions): Provider[] {
    // 形态一：useFactory，最常用，inject 数组声明它自己的依赖
    if (options.useFactory) {
      return [{ provide: HTTP_CLIENT_OPTIONS, useFactory: options.useFactory, inject: options.inject ?? [] }]
    }
    // 形态二 useClass：容器负责实例化；形态三 useExisting：复用已注册的实例
    const cls = options.useClass ?? options.useExisting!
    const providers: Provider[] = [{
      provide: HTTP_CLIENT_OPTIONS,
      useFactory: (f: HttpClientOptionsFactory) => f.createHttpClientOptions(),
      inject: [cls],
    }]
    if (options.useClass) providers.push({ provide: cls, useClass: cls })
    return providers
  }
}
```

三种形态的调用方式：

```typescript
HttpClientModule.registerAsync({                                        // 从 ConfigService 读
  imports: [ConfigModule],
  inject: [ConfigService],
  useFactory: (c: ConfigService) => ({ baseURL: c.getOrThrow('UPSTREAM_URL') }),
})
HttpClientModule.registerAsync({ useClass: HttpClientConfigFactory })   // 配置逻辑收进一个类
HttpClientModule.registerAsync({ useExisting: SharedConfigFactory })    // 复用已有实例
```

---

## 用 ConfigurableModuleBuilder 省掉样板

上面那段有八成是模板代码，每个动态模块都要抄一遍。Nest 内置的 `ConfigurableModuleBuilder` 就是来消掉它的：

```typescript
// http-client.module-definition.ts
export const {
  ConfigurableModuleClass, MODULE_OPTIONS_TOKEN, OPTIONS_TYPE, ASYNC_OPTIONS_TYPE,
} = new ConfigurableModuleBuilder<HttpClientOptions>()
  .setClassMethodName('register')                    // 默认 register，可改成 forRoot
  .setFactoryMethodName('createHttpClientOptions')   // useClass 走哪个方法，默认 create
  .setExtras({ isGlobal: false }, (definition, extras) => ({
    ...definition,
    global: extras.isGlobal,                         // 额外 option 如何改写模块定义
  }))
  .build()

// http-client.module.ts
@Module({ providers: [HttpClientService], exports: [HttpClientService] })
export class HttpClientModule extends ConfigurableModuleClass {}
```

继承之后，`register` / `registerAsync`（含三种异步形态）、options Provider、`isGlobal` 全都有了。注入 options 用 builder 返回的 token：`@Inject(MODULE_OPTIONS_TOKEN)`。

| | 手写 | ConfigurableModuleBuilder |
|---|---|---|
| 样板代码 | 每个模块 40 行左右 | 一次 `build()` + `extends` |
| 三种异步形态 | 自己分支处理 | 自带 |
| options 类型 | 自己维护接口 | `typeof OPTIONS_TYPE`，`setExtras` 加的字段自动带上 |

需要在生成的方法上再加东西就覆写它：

```typescript
@Module({})
export class HttpClientModule extends ConfigurableModuleClass {
  static register(options: typeof OPTIONS_TYPE): DynamicModule {
    return { ...super.register(options), providers: [HttpClientService, HttpMetrics] }
  }
}
```

> 参数类型写 `typeof OPTIONS_TYPE` 而不是自己的 `HttpClientOptions`，`setExtras` 里加的 `isGlobal` 才会出现在类型提示里。

---

## 配置管理：@nestjs/config

`@nestjs/config` 自己就是个动态模块：`forRoot` 读环境变量，`forFeature` 注册局部配置。

```typescript
// npm install @nestjs/config
@Module({
  imports: [
    ConfigModule.forRoot({
      isGlobal: true,        // 免掉每个模块的 imports，取舍见「依赖注入」的全局模块一节
      cache: true,           // 缓存读取结果，热路径上少走 process.env
      envFilePath: [`.env.${process.env.NODE_ENV ?? 'development'}`, '.env'],
    }),
  ],
})
export class AppModule {}
```

### 多环境文件的优先级

`envFilePath` 传数组时**靠前的文件优先**，同名 key 后面的不会覆盖前面的，环境专属配置于是盖过公共配置：

```bash
.env.production   DB_HOST=prod-db.internal   # 生产环境命中这条
.env              DB_HOST=localhost          # 被上面盖掉；这里独有的 key 仍然生效
```

还有一层更高的优先级：**真实的进程环境变量永远赢**。`.env` 不会覆盖已存在的 `process.env`，所以容器 `-e DB_HOST=...` 或 K8s 的 `env` 字段能直接盖掉镜像里的默认值。

> ⚠️ 仓库里只提交 `.env.example`，真实的 `.env*` 必须进 `.gitignore`，生产密钥走部署平台的 secret 机制。

### yaml 做嵌套配置

`.env` 是扁平的 key=value，层级一深就难看（`DB_MASTER_POOL_MAX=10`）。嵌套配置改用 yaml + 自定义 load 函数：

```yaml
# config/config.development.yaml
server: { port: 3000 }
database:
  master:
    host: localhost
    pool: { min: 2, max: 10 }
```

```typescript
// config/yaml.loader.ts —— ConfigModule.forRoot({ isGlobal: true, load: [yamlLoader] })
export default () => {
  const env = process.env.NODE_ENV ?? 'development'
  const file = join(process.cwd(), 'config', `config.${env}.yaml`)
  return yaml.load(readFileSync(file, 'utf8')) as Record<string, unknown>
}
// 读取用点号路径：this.config.get<number>('database.master.pool.max')
```

`load` 数组里的函数可以是 async 的，所以从配置中心（Nacos、etcd）拉配置也走这里。

### registerAs：命名空间 + 类型安全

到处 `get('DB_HOST')` 拼错了只有运行时才知道。用 `registerAs` 把一组配置收成命名空间，再用 `ConfigType` 拿到类型：

```typescript
// config/database.config.ts
export default registerAs('database', () => ({
  host: process.env.DB_HOST!,
  port: parseInt(process.env.DB_PORT ?? '3306', 10),
}))

// AppModule: ConfigModule.forRoot({ isGlobal: true, load: [databaseConfig] })

@Injectable()
export class OrderRepository {
  constructor(
    @Inject(databaseConfig.KEY)                              // registerAs 自动挂上的 token
    private readonly db: ConfigType<typeof databaseConfig>,  // 字段有类型，拼错是编译期错误
  ) {}
}
```

只用 `ConfigService` 时也可以给它一个环境变量接口来收紧类型，`get('PORT', { infer: true })` 连 key 名都会被校验：

```typescript
interface EnvVars { PORT: number; DATABASE_URL: string }
constructor(private readonly config: ConfigService<EnvVars, true>) {}
```

`get()` 取不到返回 `undefined`，`getOrThrow()` 取不到直接抛错——必需项一律用后者。

---

## 启动即校验：fail fast

配置少一个 key 而服务照样起来，等冷门接口被调用才炸——这是最难查的线上问题之一。校验就是把它提前到启动时：

```typescript
ConfigModule.forRoot({
  isGlobal: true,
  validationSchema: Joi.object({
    NODE_ENV: Joi.string().valid('development', 'test', 'production').default('development'),
    PORT: Joi.number().port().default(3000),
    DATABASE_URL: Joi.string().uri().required(),
    JWT_SECRET: Joi.string().min(32).required(),      // 顺手把弱密钥挡在门外
  }),
  validationOptions: { allowUnknown: true, abortEarly: false },   // 一次报全所有缺失项
})
```

不想引入 Joi 也可以给 `forRoot` 传一个 `validate` 函数，里面用 class-validator 校验一个 `EnvVars` 类（`plainToInstance` + `validateSync`，写法见 [DTO 与 Swagger](/guide/nestjs-dto)），好处是和 DTO 校验共用一套心智模型。

工程价值就一句话：**配置错误应该让容器起不来，而不是让接口在半夜返回 500。** 启动失败会让 K8s 停止滚动更新，坏配置根本进不了生产。

---

## 把配置注入 forRootAsync

前面的内容拼起来就是真实项目的标准开头：配置模块先就绪，数据库连接从配置里取。

```typescript
@Module({
  imports: [
    ConfigModule.forRoot({ isGlobal: true, envFilePath: ['.env'], validationSchema: envSchema }),
    TypeOrmModule.forRootAsync({
      imports: [ConfigModule],       // ConfigModule 已 isGlobal 时可省，写上更明确
      inject: [ConfigService],
      useFactory: (config: ConfigService) => ({
        type: 'mysql' as const,
        host: config.getOrThrow<string>('DB_HOST'),
        port: config.get<number>('DB_PORT', 3306),
        username: config.getOrThrow<string>('DB_USER'),
        password: config.getOrThrow<string>('DB_PASSWORD'),
        database: config.getOrThrow<string>('DB_NAME'),
        autoLoadEntities: true,
        synchronize: false,          // 生产必须 false，表结构变更走 migration
      }),
    }),
  ],
})
export class AppModule {}
```

两个要点：`forRootAsync` 的 `useFactory` 和普通 Provider 的 `useFactory` 是同一个东西，`inject` 数组顺序对应参数顺序；Nest 会等它的 Promise 落地才继续启动，所以连不上数据库表现为启动失败而不是运行时报错（`synchronize` 与迁移见 [数据库操作](/guide/nestjs-database)）。

同一套写法适用于所有官方模块：

```typescript
JwtModule.registerAsync({
  inject: [ConfigService],
  useFactory: (config: ConfigService) => ({
    secret: config.getOrThrow<string>('JWT_SECRET'),
    signOptions: { expiresIn: config.get('JWT_EXPIRES_IN', '2h') },
  }),
})
```

---

## 官方模块形态速查

| 模块 | 提供的方法 | 为什么是这个形态 |
|---|---|---|
| `ConfigModule` | `forRoot` / `forFeature` | 全局配一次，`forFeature` 补局部命名空间 |
| `TypeOrmModule` | `forRoot(Async)` / `forFeature` | 连接全局唯一，Repository 按模块注册（`MongooseModule` 同理） |
| `JwtModule` | `register(Async)` | 不同场景的 secret 和有效期本就不同 |
| `CacheModule` | `register(Async)` | 一次性指定 store，常配 `isGlobal: true` |
| `BullModule` | `forRoot(Async)` / `registerQueue` | Redis 连接全局，队列按名字逐个注册 |
| `ClientsModule` | `register(Async)` | 一次声明一组微服务客户端 |

规律：**昂贵的共享资源用 `forRoot`，局部声明用 `forFeature`，天然多份的配置用 `register`。** 自己写模块时照这个规律挑方法名。
