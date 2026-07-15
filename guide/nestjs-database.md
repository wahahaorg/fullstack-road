# NestJS 数据库操作

> TypeORM + NestJS 的完整实践：Repository 注入、事务、软删除、迁移。

## TypeORM 集成

```bash
npm install @nestjs/typeorm typeorm mysql2
```

```typescript
// app.module.ts
TypeOrmModule.forRootAsync({
  imports: [ConfigModule],
  useFactory: (configService: ConfigService) => ({
    type: 'mysql',
    host: configService.get('DB_HOST'),
    port: configService.get<number>('DB_PORT'),
    username: configService.get('DB_USER'),
    password: configService.get('DB_PASSWORD'),
    database: configService.get('DB_NAME'),
    entities: [__dirname + '/**/*.entity{.ts,.js}'],
    synchronize: false,  // ❌ 生产环境禁用，用 migration
    logging: configService.get('NODE_ENV') !== 'production',
  }),
  inject: [ConfigService],
})
```

---

## 实体（Entity）

```typescript
import {
  Entity, PrimaryGeneratedColumn, Column,
  CreateDateColumn, UpdateDateColumn, DeleteDateColumn,
  ManyToOne, OneToMany, JoinColumn
} from 'typeorm'

@Entity('users')
export class User {
  @PrimaryGeneratedColumn()
  id: number

  @Column({ unique: true })
  email: string

  @Column({ name: 'password_hash' })
  passwordHash: string

  @Column({ nullable: true })
  nickname: string | null

  @Column({ default: true })
  isActive: boolean

  @CreateDateColumn({ name: 'created_at' })
  createdAt: Date

  @UpdateDateColumn({ name: 'updated_at' })
  updatedAt: Date

  @DeleteDateColumn({ name: 'deleted_at' })
  deletedAt: Date | null  // 软删除时间戳

  @OneToMany(() => Order, order => order.user)
  orders: Order[]
}
```

---

## @InjectRepository() 注入

```typescript
// users.module.ts
@Module({
  imports: [TypeOrmModule.forFeature([User])],
  providers: [UsersService],
})
export class UsersModule {}

// users.service.ts
@Injectable()
export class UsersService {
  constructor(
    @InjectRepository(User)
    private readonly userRepo: Repository<User>,
  ) {}

  findAll(): Promise<User[]> {
    return this.userRepo.find({ where: { isActive: true } })
  }

  findByEmail(email: string): Promise<User | null> {
    return this.userRepo.findOneBy({ email })
  }

  async create(dto: CreateUserDto): Promise<User> {
    const user = this.userRepo.create({
      ...dto,
      passwordHash: await bcrypt.hash(dto.password, 10),
    })
    return this.userRepo.save(user)
  }

  async update(id: number, dto: UpdateUserDto): Promise<User> {
    await this.userRepo.update(id, dto)
    return this.findOne(id)
  }
}
```

---

## 常用查询

```typescript
// 基础查询
await userRepo.findOne({ where: { id }, relations: ['orders'] })
await userRepo.find({ where: { isActive: true }, order: { createdAt: 'DESC' } })

// 分页
const [users, total] = await userRepo.findAndCount({
  skip: (page - 1) * pageSize,
  take: pageSize,
  order: { createdAt: 'DESC' },
})

// QueryBuilder（复杂查询）
const users = await userRepo
  .createQueryBuilder('user')
  .leftJoinAndSelect('user.orders', 'order')
  .where('user.isActive = :isActive', { isActive: true })
  .andWhere('order.total > :minTotal', { minTotal: 100 })
  .orderBy('user.createdAt', 'DESC')
  .take(10)
  .getMany()
```

---

## 软删除

软删除不会真正删除数据库记录，而是设置 `deletedAt` 时间戳。需要在实体上配置 `@DeleteDateColumn`。

```typescript
// 软删除（设置 deletedAt）
await userRepo.softDelete(id)
// 等价于
await userRepo.softRemove(user)

// 恢复
await userRepo.restore(id)

// 正常 find 自动过滤已删软除的记录
const users = await userRepo.find()  // 不包含 deletedAt 不为 null 的

// 查询包含软删除的记录
const allUsers = await userRepo.find({ withDeleted: true })

// 只查已软删除的
const deletedUsers = await userRepo.find({
  withDeleted: true,
  where: { deletedAt: Not(IsNull()) },
})
```

**为什么某些场景首选软删除：**
- 数据审计：保留删除历史
- 可恢复性：用户可以"撤销删除"
- 外键完整性：关联数据不会因硬删除而断链
- 合规要求：某些行业要求保留数据一定时间

---

## 事务

```typescript
// 方式一：QueryRunner（最灵活）
@Injectable()
export class TransferService {
  constructor(private dataSource: DataSource) {}

  async transfer(fromId: number, toId: number, amount: number) {
    const queryRunner = this.dataSource.createQueryRunner()
    await queryRunner.connect()
    await queryRunner.startTransaction()

    try {
      const fromAccount = await queryRunner.manager.findOneBy(Account, { id: fromId })
      const toAccount = await queryRunner.manager.findOneBy(Account, { id: toId })

      if (fromAccount.balance < amount) {
        throw new BadRequestException('余额不足')
      }

      fromAccount.balance -= amount
      toAccount.balance += amount

      await queryRunner.manager.save(fromAccount)
      await queryRunner.manager.save(toAccount)

      await queryRunner.commitTransaction()
    } catch (err) {
      await queryRunner.rollbackTransaction()
      throw err
    } finally {
      await queryRunner.release()
    }
  }
}

// 方式二：DataSource.transaction（简洁）
await this.dataSource.transaction(async (manager) => {
  const from = await manager.findOneBy(Account, { id: fromId })
  const to = await manager.findOneBy(Account, { id: toId })

  from.balance -= amount
  to.balance += amount

  await manager.save([from, to])
})
```

**什么场景必须用事务：**
- 转账：扣款和入账必须同时成功
- 订单创建：库存扣减 + 订单记录 + 支付记录
- 批量操作：部分失败需要全部回滚

---

## Migration（数据库迁移）

**为什么不用 `synchronize: true`：**
- 生产环境可能自动删除字段、改变列类型，导致数据丢失
- 无法追踪数据库变更历史
- 多人协作时容易冲突

```bash
# 生成迁移（根据实体变化自动生成 SQL）
npx typeorm migration:generate ./src/migrations/AddUserNickname -d src/data-source.ts

# 执行迁移
npx typeorm migration:run -d src/data-source.ts

# 回滚最后一次迁移
npx typeorm migration:revert -d src/data-source.ts
```

```typescript
// 迁移文件示例
export class AddUserNickname1704000000000 implements MigrationInterface {
  async up(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.addColumn('users', new TableColumn({
      name: 'nickname',
      type: 'varchar',
      length: '50',
      isNullable: true,
    }))
  }

  async down(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.dropColumn('users', 'nickname')
  }
}
```

---

## 循环依赖

当两个模块互相依赖时，NestJS 会报错。解决方式：

```typescript
// ❌ 循环依赖
// UsersModule 依赖 OrdersModule
// OrdersModule 依赖 UsersModule

// ✅ 方式一：forwardRef 解决循环依赖
@Module({
  imports: [forwardRef(() => OrdersModule)],
})
export class UsersModule {}

@Injectable()
export class UsersService {
  constructor(
    @Inject(forwardRef(() => OrdersService))
    private ordersService: OrdersService,
  ) {}
}

// ✅ 方式二（更推荐）：重新设计，抽出共享模块
// 把公共逻辑提取到 SharedModule，两者都依赖 SharedModule
```

---

## NestJS 支持的数据库方案

| 方案 | 说明 |
|---|---|
| TypeORM | NestJS 官方推荐，支持 MySQL/PostgreSQL/SQLite 等 |
| Prisma | 现代 ORM，类型安全极好，社区增长快 |
| Mongoose | MongoDB 的 ODM，NestJS 有官方集成 |
| MikroORM | 另一个活跃的 TypeScript ORM |
| 原生 SQL | 配合 `DataSource.query()` 执行原生 SQL |
