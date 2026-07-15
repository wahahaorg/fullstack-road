# NestJS DTO、序列化与 Swagger

> 数据传输对象是 NestJS 类型安全和自动文档的核心。

## DTO 的作用

DTO（Data Transfer Object）用于定义应用不同层之间传递数据的结构：

| 价值 | 说明 |
|---|---|
| **校验** | 配合 class-validator，自动校验请求数据 |
| **类型安全** | TypeScript 编译阶段提前发现问题 |
| **文档** | 配合 Swagger 自动生成 API 文档 |
| **安全** | 防止敏感字段意外暴露到响应 |

---

## 安装依赖

```bash
npm install class-validator class-transformer
```

在 `main.ts` 启用全局 ValidationPipe：

```typescript
app.useGlobalPipes(new ValidationPipe({
  whitelist: true,        // 剔除 DTO 中未定义的字段
  forbidNonWhitelisted: true,  // 出现未知字段直接报错
  transform: true,        // 自动转换类型（如字符串 "1" → 数字 1）
}))
```

---

## 创建 DTO

```typescript
import { IsEmail, IsString, MinLength, IsOptional, IsInt, Min, Max } from 'class-validator'
import { Transform } from 'class-transformer'

export class CreateUserDto {
  @IsEmail({}, { message: '邮箱格式不正确' })
  email: string

  @IsString()
  @MinLength(8, { message: '密码至少 8 位' })
  password: string

  @IsOptional()
  @IsString()
  @Transform(({ value }) => value?.trim())  // 自动去空格
  nickname?: string
}

export class UpdateUserDto {
  @IsOptional()
  @IsString()
  nickname?: string

  @IsOptional()
  @IsInt()
  @Min(1)
  @Max(150)
  age?: number
}
```

**常用 class-validator 装饰器：**

| 装饰器 | 说明 |
|---|---|
| `@IsString()` | 字符串类型 |
| `@IsInt()` | 整数 |
| `@IsEmail()` | 邮箱格式 |
| `@IsUrl()` | URL 格式 |
| `@IsUUID()` | UUID 格式 |
| `@IsBoolean()` | 布尔值 |
| `@IsArray()` | 数组 |
| `@IsEnum(E)` | 枚举值 |
| `@IsOptional()` | 可选（不传则跳过其他校验） |
| `@IsNotEmpty()` | 不允许空字符串 |
| `@MinLength(n)` | 最小长度 |
| `@MaxLength(n)` | 最大长度 |
| `@Min(n)` | 最小值 |
| `@Max(n)` | 最大值 |
| `@ValidateNested()` | 嵌套对象校验 |

---

## 序列化：过滤响应字段

使用 `@Exclude()` 防止敏感字段返回：

```typescript
import { Exclude, Expose, Transform } from 'class-transformer'

export class UserResponseDto {
  id: number
  email: string
  nickname: string | null

  @Exclude()
  passwordHash: string  // 不会出现在响应中

  @Expose()
  @Transform(({ value }) => value?.toUpperCase())
  role: string

  constructor(partial: Partial<UserResponseDto>) {
    Object.assign(this, partial)
  }
}
```

在控制器中启用序列化：

```typescript
// 方式一：使用 @SerializeOptions 和 ClassSerializerInterceptor
@UseInterceptors(ClassSerializerInterceptor)
@Get(':id')
findOne(@Param('id', ParseIntPipe) id: number) {
  return this.usersService.findOne(id)  // 返回 UserResponseDto 实例
}

// 方式二：全局启用
app.useGlobalInterceptors(new ClassSerializerInterceptor(app.get(Reflector)))
```

---

## Swagger 文档

```bash
npm install @nestjs/swagger
```

在 `main.ts` 配置：

```typescript
import { SwaggerModule, DocumentBuilder } from '@nestjs/swagger'

const config = new DocumentBuilder()
  .setTitle('My API')
  .setDescription('API 文档')
  .setVersion('1.0')
  .addBearerAuth()          // JWT 认证
  .build()

const document = SwaggerModule.createDocument(app, config)
SwaggerModule.setup('api/docs', app, document)
```

访问 `http://localhost:3000/api/docs` 查看 Swagger UI。

---

## Swagger 装饰器

### DTO 字段说明

```typescript
import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger'

export class CreateUserDto {
  @ApiProperty({
    description: '用户邮箱',
    example: 'user@example.com',
  })
  @IsEmail()
  email: string

  @ApiProperty({
    description: '密码',
    minimum: 8,
    example: 'password123',
  })
  @MinLength(8)
  password: string

  @ApiPropertyOptional({
    description: '昵称（可选）',
    example: 'Tom',
  })
  @IsOptional()
  @IsString()
  nickname?: string
}
```

### 接口说明

```typescript
import { ApiOperation, ApiResponse, ApiTags, ApiBearerAuth } from '@nestjs/swagger'

@ApiTags('users')       // 分组标签
@ApiBearerAuth()        // 需要 JWT 认证
@Controller('users')
export class UsersController {

  @Post()
  @ApiOperation({ summary: '创建用户', description: '注册一个新用户账号' })
  @ApiResponse({ status: 201, description: '创建成功', type: UserResponseDto })
  @ApiResponse({ status: 409, description: '邮箱已存在' })
  @ApiResponse({ status: 422, description: '请求参数校验失败' })
  create(@Body() dto: CreateUserDto): Promise<UserResponseDto> {
    return this.usersService.create(dto)
  }

  @Get(':id')
  @ApiOperation({ summary: '获取用户信息' })
  @ApiResponse({ status: 200, type: UserResponseDto })
  @ApiResponse({ status: 404, description: '用户不存在' })
  findOne(@Param('id', ParseIntPipe) id: number) {
    return this.usersService.findOne(id)
  }
}
```

---

## 嵌套 DTO 校验

```typescript
import { Type } from 'class-transformer'
import { ValidateNested, IsArray } from 'class-validator'

export class AddressDto {
  @IsString()
  street: string

  @IsString()
  city: string
}

export class CreateOrderDto {
  @ValidateNested()
  @Type(() => AddressDto)    // class-transformer 需要 Type 注解
  shippingAddress: AddressDto

  @IsArray()
  @ValidateNested({ each: true })
  @Type(() => OrderItemDto)
  items: OrderItemDto[]
}
```

---

## DTO 最佳实践

```typescript
// ✅ 为每个操作创建独立 DTO
class CreateProductDto { ... }    // POST
class UpdateProductDto { ... }    // PATCH（所有字段可选）
class ProductResponseDto { ... }  // GET 响应（过滤敏感字段）
class ProductListQueryDto { ... } // 查询参数（分页、排序、过滤）

// ✅ 利用继承减少重复
class UpdateProductDto extends PartialType(CreateProductDto) {}

// ✅ 分页 DTO 复用
class PaginationDto {
  @IsOptional()
  @IsInt()
  @Min(1)
  @Transform(({ value }) => parseInt(value))
  page?: number = 1

  @IsOptional()
  @IsInt()
  @Min(1)
  @Max(100)
  @Transform(({ value }) => parseInt(value))
  pageSize?: number = 20
}
```
