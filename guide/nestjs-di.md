# NestJS 依赖注入

> DI 是 NestJS 架构的核心，理解它才能真正理解 NestJS 的模块化和可测试性。

## 依赖注入（DI）是什么？

依赖注入是一种设计模式：**一个类不自己创建依赖，而是由外部把依赖提供给它**。

NestJS 有自己的 IoC 容器，负责管理依赖的创建与注入：

```typescript
// ❌ 不用 DI：紧耦合，难测试
class UsersController {
  private usersService = new UsersService()  // 自己创建依赖
}

// ✅ 用 DI：松耦合，易测试
class UsersController {
  constructor(private usersService: UsersService) {}  // 容器注入依赖
}
```

---

## @Injectable() vs @Inject()

### `@Injectable()`

把一个类标记为**可由 NestJS DI 系统管理的 Provider**。

```typescript
@Injectable()
export class CatsService {
  private cats: Cat[] = []

  findAll(): Cat[] {
    return this.cats
  }
}
```

### `@Inject()`

在类内部**显式注入某个依赖**，通常写在构造函数参数上。

```typescript
// 注入类 Provider：TypeScript 能自动推断，通常不需要 @Inject()
constructor(private catsService: CatsService) {}

// 注入非类 Provider（值/工厂）：必须用 @Inject() + token
constructor(
  @Inject('DATABASE_URL') private dbUrl: string,
  @Inject('CONFIG') private config: AppConfig,
) {}
```

**总结：**
- `@Injectable()`：标记"我可以被注入"
- `@Inject(token)`：标记"注入这个 token 对应的依赖"

---

## Provider vs Service

**Service** 是 Provider 的一种具体形式，两者关系：

```
Provider（宽泛）
  ├── Service（@Injectable() 的类）  ← 最常见
  ├── 值 Provider（useValue）
  ├── 工厂 Provider（useFactory）
  └── 类别名（useExisting）
```

---

## 标准 Provider

```typescript
@Injectable()
export class CatsService {
  constructor(private readonly catsRepository: CatsRepository) {}
}
```

在模块中注册：

```typescript
@Module({
  providers: [CatsService],  // 简写，等价于 { provide: CatsService, useClass: CatsService }
})
```

---

## 自定义 Provider

### 值 Provider

```typescript
@Module({
  providers: [
    {
      provide: 'CONFIG',
      useValue: { apiUrl: 'https://api.example.com', timeout: 5000 },
    },
  ],
})

// 注入时
constructor(@Inject('CONFIG') private config: AppConfig) {}
```

### 工厂 Provider

```typescript
@Module({
  providers: [
    {
      provide: 'DATABASE_CONNECTION',
      useFactory: async (configService: ConfigService) => {
        return createConnection(configService.get('DATABASE_URL'))
      },
      inject: [ConfigService],  // 工厂函数的依赖
    },
  ],
})
```

### 异步工厂 Provider

```typescript
{
  provide: 'REDIS_CLIENT',
  useFactory: async () => {
    const client = createClient({ url: process.env.REDIS_URL })
    await client.connect()
    return client
  },
}
```

### 类别名 Provider

```typescript
// 用 MockCatsService 替代 CatsService（测试中很有用）
{
  provide: CatsService,
  useExisting: MockCatsService,
}
```

---

## IoC vs DI

| 概念 | 说明 |
|---|---|
| **IoC（控制反转）** | 更宽泛的原则：控制流程不再由开发者手动驱动，而是交由框架管理 |
| **DI（依赖注入）** | IoC 的具体落地方式之一：把依赖的创建和绑定交给容器 |

**关系：IoC 是设计原则，DI 是实现该原则的其中一种方式。**

Angular、Spring、NestJS 都采用这种 IoC 实现方式。

---

## 依赖倒置原则（DIP）

SOLID 五大原则之一：**依赖抽象，而不是具体实现**。

```typescript
// ❌ 高层模块直接依赖低层实现
@Injectable()
export class OrderService {
  constructor(private mysqlRepo: MysqlOrderRepository) {}  // 直接依赖 MySQL 实现
}

// ✅ 依赖抽象（接口）
export interface IOrderRepository {
  findById(id: number): Promise<Order | null>
  save(order: Order): Promise<Order>
}

@Injectable()
export class OrderService {
  constructor(
    @Inject('ORDER_REPO') private orderRepo: IOrderRepository,  // 依赖接口
  ) {}
}

// 模块中绑定具体实现
{
  provide: 'ORDER_REPO',
  useClass: MysqlOrderRepository,  // 切换实现只需改这里
}
```

**好处：**
- 单元测试可以注入 Mock 实现
- 切换数据库/外部服务不需要修改业务逻辑
- 更容易演进和重构

---

## 作用域（Scope）

默认情况下，NestJS 的 Provider 是**单例**（整个应用共享一个实例）。

```typescript
@Injectable({ scope: Scope.DEFAULT })    // 单例（默认）
export class CatsService {}

@Injectable({ scope: Scope.REQUEST })    // 每个请求创建新实例
export class RequestScopedService {}

@Injectable({ scope: Scope.TRANSIENT })  // 每次注入都创建新实例
export class TransientService {}
```

> 通常不需要改变作用域。REQUEST scope 会影响性能；只在需要隔离请求级状态时使用。

---

## 单元测试中的 DI

DI 让测试变得非常容易：

```typescript
describe('CatsService', () => {
  let service: CatsService

  beforeEach(async () => {
    const module = await Test.createTestingModule({
      providers: [
        CatsService,
        {
          provide: CatsRepository,
          useValue: {
            findAll: jest.fn().mockResolvedValue([{ id: 1, name: 'Tom' }]),
            save: jest.fn(),
          },
        },
      ],
    }).compile()

    service = module.get<CatsService>(CatsService)
  })

  it('应该返回所有猫', async () => {
    const cats = await service.findAll()
    expect(cats).toHaveLength(1)
  })
})
```
