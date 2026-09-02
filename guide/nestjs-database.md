# NestJS 数据库操作：TypeORM 实战

> Entity 怎么写、三种关系怎么映射、查询该用 `find` 还是 QueryBuilder 还是裸 SQL、生产为什么必须上 migration。这篇是 TypeORM 在 Nest 里的完整落地路径。

## 集成基线

```bash
npm install @nestjs/typeorm typeorm mysql2
```

`@nestjs/typeorm` 只是一层胶水：它把 TypeORM 的 `DataSource` 和每个 Entity 的 `Repository` 注册成 Provider，真正干活的 API 全是 TypeORM 自己的。

```typescript
@Module({
  imports: [
    TypeOrmModule.forRoot({
      type: 'mysql',
      host: 'localhost',
      port: 3306,
      username: 'root',
      password: '***',
      database: 'shop',
      autoLoadEntities: true,     // 让 forFeature 注册过的 Entity 自动进来，省掉 glob
      synchronize: false,         // 生产必须 false，下面单独讲
      logging: process.env.NODE_ENV !== 'production',
      poolSize: 10,
      connectorPackage: 'mysql2',
    }),
  ],
})
export class AppModule {}
```

真实项目里数据库配置来自环境变量，要用 `forRootAsync` 注入 `ConfigService`——写法和「为什么动态模块能带参数」都在[动态模块与配置管理](/guide/nestjs-dynamic-module)里，这里只给结果：`forRootAsync({ imports: [ConfigModule], inject: [ConfigService], useFactory: (c) => ({ ... }) })`。

> ⚠️ 版本基线：TypeORM 0.3 起连接对象叫 **`DataSource`**，旧的 `Connection` / `getConnection()` / `createConnection()` 已废弃。网上大量 0.2 时代的教程还在用 `Connection`，照抄会踩坑。全篇统一用 `DataSource`。

### 三种注入方式

| 注入什么 | 装饰器 | 适合 |
|---|---|---|
| `Repository<T>` | `@InjectRepository(T)` | 90% 的场景，单 Entity 的 CRUD |
| `EntityManager` | `@InjectEntityManager()` | 一次操作跨多个 Entity，每个方法要传 Entity 类作首参 |
| `DataSource` | `@InjectDataSource()` | 开事务、跑原生 SQL、拿 `QueryRunner` |

`Repository` 要先在**用它的那个模块**里注册：

```typescript
@Module({
  imports: [TypeOrmModule.forFeature([Order, OrderItem])],   // 只在本模块内可注入
  providers: [OrdersService],
})
export class OrdersModule {}

@Injectable()
export class OrdersService {
  constructor(
    @InjectRepository(Order) private readonly orderRepo: Repository<Order>,
    @InjectDataSource() private readonly dataSource: DataSource,
  ) {}
}
```

`forRoot` 注册的 `DataSource` / `EntityManager` 挂在一个 `@Global()` 模块上，所以任何地方都能直接注入；而 `forFeature` 是**模块局部**的，哪个模块要注入 `Repository<Order>`，哪个模块就得 `imports` 一次。别为了共享 Repository 到处 `forFeature([Order])`——那等于让多个模块直接读写同一张表。正确做法是让拥有这张表的模块导出 Service，其他模块调 Service。

> 两个模块互相依赖时的 `forwardRef` 用法和「大多数循环依赖是设计信号」这个判断，见[依赖注入](/guide/nestjs-di)。

---

## Entity：一张表的完整声明

```typescript
export enum OrderStatus { Pending = 'pending', Paid = 'paid', Closed = 'closed' }

@Entity('orders')
@Index(['userId', 'createdAt'])                        // 复合索引，顺序 = 最左前缀
export class Order {
  @PrimaryGeneratedColumn()
  id: number

  @Column({ name: 'order_no', length: 32, unique: true, comment: '对外单号' })
  orderNo: string

  @Column({ name: 'user_id' })
  @Index()                                             // 单列索引
  userId: number

  @Column({ type: 'decimal', precision: 12, scale: 2, default: 0 })
  amount: string                                       // decimal 映射成 string，见下方警告

  @Column({ type: 'enum', enum: OrderStatus, default: OrderStatus.Pending })
  status: OrderStatus

  @Column({ type: 'json', nullable: true })
  snapshot: Record<string, unknown> | null

  @Column({ select: false })                           // 默认查询不带出这一列
  internalNote: string

  @CreateDateColumn({ name: 'created_at' })
  createdAt: Date

  @UpdateDateColumn({ name: 'updated_at' })
  updatedAt: Date

  @DeleteDateColumn({ name: 'deleted_at' })
  deletedAt: Date | null

  @VersionColumn()
  version: number
}
```

### @Column 常用选项

| 选项 | 说明 |
|---|---|
| `type` | **数据库类型**，不是 TS 类型：`'varchar'` `'text'` `'int'` `'bigint'` `'decimal'` `'enum'` `'json'` `'timestamp'` |
| `name` | 列名。TS 用 camelCase、库里用 snake_case 时靠它映射 |
| `length` | varchar 长度；不写默认 255 |
| `nullable` | 是否 `NOT NULL`。TS 类型也要跟着写成 `| null`，否则类型在骗你 |
| `default` | 默认值，写进 DDL |
| `unique` | 建唯一索引 |
| `comment` | 列注释。表结构自解释，接手的人少问一句 |
| `precision` / `scale` | decimal 的总位数与小数位 |
| `enum` | 配 `type: 'enum'`，值取 TS 枚举 |
| `select: false` | 默认查询不返回该列，要显式 `select` 才取（大文本、内部字段） |
| `update: false` / `insert: false` | 只读列，`save` 时忽略 |
| `transformer` | 读写时做转换（加密字段、金额分↔元） |

> ⚠️ MySQL 的 `decimal` 在 TypeORM 里映射成 **`string`**，不是 `number`——因为 JS 的 `number` 存不住任意精度小数。金额字段要么接受 `string` 然后用 decimal 库运算，要么干脆用 `int` 存「分」。直接声明成 `number` 会在算钱的地方出现精度错误。


### 主键：自增还是 UUID

```typescript
@PrimaryGeneratedColumn()          // 等价于 'increment'：INT AUTO_INCREMENT
@PrimaryGeneratedColumn('uuid')    // CHAR(36)，应用层生成
@PrimaryColumn()                   // 自己给值；多个 @PrimaryColumn 构成复合主键
```

| | 自增 int | UUID |
|---|---|---|
| 存储 | 4 / 8 字节 | 36 字节字符串（或 16 字节 binary） |
| 插入性能 | 顺序写，B+ 树尾部追加 | 随机写，页分裂多、二级索引都变大 |
| 分库分表 / 多写入源 | 会撞号，要额外发号器 | 天然唯一，客户端就能生成 |
| 安全性 | 可枚举，`/orders/1001` 猜得到别人的单 | 不可枚举 |
| 调试 | 人能记住、能比大小 | 一串乱码 |

默认选自增；需要「ID 不能被枚举」或「多个源同时写」时才上 UUID。折中方案是主键仍用自增、对外再暴露一个 `orderNo`（带唯一索引），既保留写入性能又不泄露业务量。

### 时间戳与版本列

| 装饰器 | 行为 |
|---|---|
| `@CreateDateColumn()` | 插入时自动写入当前时间 |
| `@UpdateDateColumn()` | 每次 `save` 自动刷新（注意：`update()` 也会刷新，但 `query()` 不会） |
| `@DeleteDateColumn()` | 软删除标记列，有它 `softDelete` / `restore` 才能用 |
| `@VersionColumn()` | 每次 `save` 自增，用于乐观锁 |

`@VersionColumn` 是乐观锁的最省事实现：读的时候拿到 `version`，写的时候 TypeORM 自动带上 `WHERE version = ?`，被人抢先改过就抛 `OptimisticLockVersionMismatchError`。适合「用户编辑表单，提交时不想覆盖别人的修改」这类场景。悲观锁（`SELECT ... FOR UPDATE`）和隔离级别的选择见[并发与事务](/guide/concurrency-transaction)。

### 索引

```typescript
@Index()                                        // 单列，加在属性上
@Index(['userId', 'status'])                    // 复合，加在类上
@Index(['orderNo'], { unique: true })           // 唯一索引
@Index('idx_order_created', ['createdAt'])      // 显式命名，migration diff 更稳定
```

复合索引遵守最左前缀：`['userId', 'status']` 能加速 `WHERE userId = ?` 和 `WHERE userId = ? AND status = ?`，但对单独的 `WHERE status = ?` 没用。索引怎么设计、什么查询用不上索引，见 [MySQL 表设计](/guide/mysql-table-design)。

### synchronize: true 为什么是生产灾难

它的行为是：**每次应用启动，对比 Entity 和真实表结构，自动执行 DDL 把库改成和 Entity 一样**。开发期确实爽——改个属性，重启就有列。但它在生产上等于把 `ALTER TABLE` 的决策权交给了一个只看得到「当前代码」的程序：

| 你的改动 | 它执行的 DDL | 后果 |
|---|---|---|
| 删掉一个属性 | `DROP COLUMN` | 该列所有数据**立刻消失**，没有确认、没有备份 |
| 属性改名 | `DROP` 旧列 + `ADD` 新列 | 它看不出这是"改名"，数据不会搬过去 |
| 改 `type` 或 `length` | `MODIFY COLUMN` | 缩短长度会截断，类型不兼容会转换失败或丢精度 |
| 回滚代码到上个版本 | 反向再改一次表 | 表结构随部署来回抖动 |

雪上加霜的是 `start:dev` 每次保存都会重启，也就是每次保存都可能重跑一轮 DDL。**规则：`synchronize` 只在本地开发库上开，其他任何环境一律 `false`，靠 migration 改表。**


---

## 关系映射

关系映射是 ORM 最大的价值，也是坑最密的地方。先记住贯穿三种关系的一条总规则：

**外键（或中间表）落在哪一侧，那一侧就是「拥有方」（owning side）。拥有方能靠自己的外键找到对方；非拥有方没有外键，必须通过第二个参数 `(x) => x.本方属性` 告诉 TypeORM「去对面哪个属性上找那个外键」。**

| | 拥有方 | 外键在哪 | 谁写 `@JoinColumn` / `@JoinTable` | 谁需要反向函数 |
|---|---|---|---|---|
| 一对一 | 你指定的那一侧 | 拥有方的表 | 拥有方写 `@JoinColumn()` | 非拥有方 |
| 一对多 / 多对一 | 永远是「多」的一侧 | 「多」的表 | 都不用（位置没有歧义） | 「一」的一侧 |
| 多对多 | 你指定的那一侧 | 独立的中间表 | 拥有方写 `@JoinTable()` | 双向导航时两侧都要 |

### 一对一

用户和用户扩展资料：一个用户一份资料。

```typescript
@Entity('users')
export class User {
  @PrimaryGeneratedColumn() id: number
  @Column() email: string

  @OneToOne(() => Profile, (profile) => profile.user, { cascade: true })
  @JoinColumn({ name: 'profile_id' })       // 外键 profile_id 落在 users 表
  profile: Profile
}

@Entity('profiles')
export class Profile {
  @PrimaryGeneratedColumn() id: number
  @Column({ type: 'text', nullable: true }) bio: string | null

  @OneToOne(() => User, (user) => user.profile)      // 非拥有方：只声明反向，不建列
  user: User
}
```

`@JoinColumn()` 写在哪一侧，外键就落在哪张表。选择依据是**「谁离不开谁」**：`profile` 没有 `user` 就没意义，反过来 `user` 可以暂时没有 `profile`，所以把外键放在 `users` 上并允许为空，语义更顺。

保存关联数据，开了 `cascade` 之后只保存拥有方即可：

```typescript
// 有 cascade：一次 save，TypeORM 先插 profiles 再插 users（把生成的 id 填进外键）
await this.userRepo.save({ email: 'a@b.com', profile: { bio: 'hi' } })

// 无 cascade：必须自己排顺序，被引用的一方先存，因为要先拿到它的自增 id
const profile = await this.profileRepo.save({ bio: 'hi' })
await this.userRepo.save({ email: 'a@b.com', profile })
```


### 四个开关：cascade / onDelete / eager / nullable

这四个都写在关系装饰器的第三个参数里，管的却是完全不同的事：

| 开关 | 生效层 | 管什么 |
|---|---|---|
| `cascade` | **ORM 层** | 我 `save()` 这个对象时，要不要顺手把它挂着的关联对象也写库 |
| `onDelete` / `onUpdate` | **数据库层** | 生成外键约束时带上 `ON DELETE CASCADE` 之类的动作，由数据库执行 |
| `eager` | ORM 层 | `find` 时是否自动带上这个关系（不用每次写 `relations`） |
| `nullable` | 数据库层 | 外键列能不能为 `NULL`，也就是关系是否可选 |

`cascade` 和 `onDelete` 最容易被当成一回事，实际差别很大：

```typescript
@OneToOne(() => Profile, (p) => p.user, {
  cascade: ['insert', 'update'],   // ORM：save(user) 时连带 insert/update profile
  onDelete: 'CASCADE',             // DB：profiles 里那行被删时，users 这行也被删
  nullable: false,
})
```

| | `cascade` | `onDelete` |
|---|---|---|
| 谁执行 | TypeORM，在应用进程里翻译成多条 SQL | 数据库引擎，在外键约束里 |
| 写在哪 | 关系装饰器，只影响 TypeORM 的行为 | 关系装饰器，但会写进 DDL |
| 取值 | `true` 或 `['insert' \| 'update' \| 'remove' \| 'soft-remove' \| 'recover']` | `'CASCADE' \| 'SET NULL' \| 'RESTRICT' \| 'NO ACTION'` |
| 绕过它的操作 | `queryRunner.query()`、别的服务、DBA 手工 SQL 都不受影响 | 任何途径的删除都会触发，包括手工 SQL |
| 改它要不要迁移 | 不用，纯代码行为 | 要，它是表结构的一部分 |

实践建议：**引用完整性交给 `onDelete`（数据库才是最后一道防线），写入的便利性才用 `cascade`**。`cascade: true` 是把 insert/update/remove 全打开，范围过大，建议写成数组只开需要的动作。

> ⚠️ `eager: true` 慎用。它会让**所有** `find` 都带上这个 join，包括那些只想查个 id 的地方，而且无法在调用处关掉。需要预加载就在调用处显式写 `relations`，别在 Entity 上做全局决定。懒加载（把属性声明成 `Promise<Profile>`，访问时才发 SQL）同理——它会让「一次属性访问」偷偷变成一次数据库往返，在循环里就是 N+1。

### 一对多 / 多对一

订单和订单明细：一个订单多个明细。

```typescript
@Entity('orders')
export class Order {
  @PrimaryGeneratedColumn() id: number

  @OneToMany(() => OrderItem, (item) => item.order, {
    cascade: ['insert', 'update'],
    orphanedRowAction: 'delete',      // 从数组里移除的明细，直接删行
  })
  items: OrderItem[]
}

@Entity('order_items')
export class OrderItem {
  @PrimaryGeneratedColumn() id: number
  @Column() skuId: number
  @Column() quantity: number

  @ManyToOne(() => Order, (order) => order.items, { onDelete: 'CASCADE' })
  @JoinColumn({ name: 'order_id' })   // 可选，只为了指定列名
  order: Order
}
```

三条硬规则：

1. **`@OneToMany` 必须配 `@ManyToOne`。** 「一」的一侧没有外键，不写反向函数 TypeORM 就不知道该查 `order_items` 的哪一列，运行时直接报错。反过来 `@ManyToOne` 可以单独存在——它自己有外键，够用了。
2. **外键永远在「多」的一侧**，位置没有歧义，所以 `@JoinColumn` 不是必需的，写它只为改列名。
3. **`cascade` 只能配在一侧。** 两边都开会互相触发、无限递归。惯例是配在 `@OneToMany`（「保存订单时连带保存明细」符合直觉）。


关联查询有三种写法，性能和适用场景都不同：

```typescript
// ① relations 选项：底层就是 LEFT JOIN，最常用
await this.orderRepo.find({ where: { userId }, relations: { items: true } })
await this.orderRepo.find({ relations: { items: { sku: true } } })    // 支持嵌套

// ② QueryBuilder：需要给关联表加过滤条件、或只取部分字段时
await this.orderRepo.createQueryBuilder('o')
  .leftJoinAndSelect('o.items', 'i', 'i.quantity > :min', { min: 1 })
  .where('o.userId = :userId', { userId })
  .getMany()

// ③ 懒加载：属性类型声明成 Promise<T>，访问时才发 SQL
// items: Promise<OrderItem[]>   →   const items = await order.items
```

保存明细：

```typescript
// 开了 cascade：一次 save，父子一起进（TypeORM 包在一个事务里）
await this.orderRepo.save({
  userId: 1,
  items: [{ skuId: 100, quantity: 2 }, { skuId: 101, quantity: 1 }],
})

// 没开 cascade：先存父拿 id，再存子
const order = await this.orderRepo.save({ userId: 1 })
await this.itemRepo.save([{ order, skuId: 100, quantity: 2 }])
```

> ⚠️ `orphanedRowAction` 决定「从数组里被移除的子行」怎么处理：`'nullify'`（默认，把外键置空，留下一堆孤儿行）、`'delete'`（删行）、`'soft-delete'`、`'disable'`。默认值经常不是你想要的——订单明细被移除后应该删掉，而不是留一行 `order_id = NULL` 的垃圾数据。

### 多对多

文章和标签：一篇文章多个标签，一个标签多篇文章。

```typescript
@Entity('articles')
export class Article {
  @PrimaryGeneratedColumn() id: number

  @ManyToMany(() => Tag, (tag) => tag.articles)
  @JoinTable({
    name: 'article_tags',                                  // 不写会自动生成，建议显式命名
    joinColumn: { name: 'article_id', referencedColumnName: 'id' },
    inverseJoinColumn: { name: 'tag_id', referencedColumnName: 'id' },
  })
  tags: Tag[]
}

@Entity('tags')
export class Tag {
  @PrimaryGeneratedColumn() id: number
  @Column({ unique: true }) name: string

  @ManyToMany(() => Article, (article) => article.tags)    // 只声明反向，不写 @JoinTable
  articles: Article[]
}
```

`@JoinTable` **只写在一侧**，两侧都写会生成两张中间表。不指定 `name` 时中间表按「拥有方表名_属性名_对方表名」自动命名，可读性一般，而且属性改名会让表名跟着变——显式命名更稳。中间表的两个外键默认带 `ON DELETE CASCADE`，所以删掉任一侧的行，关联记录会自动清掉，不用手工维护。

更新关联的行为值得记一下：**把数组整体换掉，TypeORM 只改中间表**——先查出当前关联，再删掉数组里消失的那些配对、插入新增的那些，被解除关联的 Tag 本身不会被删。

```typescript
const article = await this.articleRepo.findOne({ where: { id }, relations: { tags: true } })
article.tags = await this.tagRepo.findBy({ id: In(newTagIds) })
await this.articleRepo.save(article)      // 只有中间表的 DELETE / INSERT
```

<!-- NEXT -->