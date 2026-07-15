# NestJS 认证与授权

> JWT、Passport、Token 刷新机制——生产级认证方案的完整实现。

## 认证 vs 授权

| 概念 | 说明 | 例子 |
|---|---|---|
| **Authentication（认证）** | 确认你是谁 | 验证用户名+密码，颁发 Token |
| **Authorization（授权）** | 确认你能做什么 | 检查 Token，判断是否有权访问该接口 |

典型流程：
```
① 用户提交 username + password → 认证
② 服务端验证，生成 Access Token + Refresh Token 返回
③ 用户后续请求带上 Access Token → 授权校验
④ Access Token 过期 → 用 Refresh Token 换新 Token
```

---

## @nestjs/jwt 基础用法

```bash
npm install @nestjs/jwt @nestjs/passport passport passport-jwt bcryptjs
```

```typescript
// auth.module.ts
@Module({
  imports: [
    JwtModule.registerAsync({
      imports: [ConfigModule],
      useFactory: (configService: ConfigService) => ({
        secret: configService.get('JWT_SECRET'),
        signOptions: { expiresIn: '15m' },  // Access Token 15 分钟
      }),
      inject: [ConfigService],
    }),
  ],
  providers: [AuthService, LocalStrategy, JwtStrategy],
  exports: [AuthService],
})
export class AuthModule {}
```

---

## AuthService：登录与 Token 生成

```typescript
@Injectable()
export class AuthService {
  constructor(
    private usersService: UsersService,
    private jwtService: JwtService,
  ) {}

  async validateUser(email: string, password: string): Promise<User | null> {
    const user = await this.usersService.findByEmail(email)
    if (user && await bcrypt.compare(password, user.passwordHash)) {
      return user
    }
    return null
  }

  async login(user: User) {
    const payload = { sub: user.id, email: user.email, roles: user.roles }

    return {
      accessToken: this.jwtService.sign(payload, { expiresIn: '15m' }),
      refreshToken: this.jwtService.sign(
        { sub: user.id, type: 'refresh' },
        { expiresIn: '7d' }
      ),
    }
  }

  async refreshTokens(refreshToken: string) {
    try {
      const payload = this.jwtService.verify(refreshToken)
      if (payload.type !== 'refresh') throw new Error()

      const user = await this.usersService.findById(payload.sub)
      return this.login(user)
    } catch {
      throw new UnauthorizedException('Refresh token 无效或已过期')
    }
  }
}
```

---

## JWT 策略（Passport）

```typescript
import { PassportStrategy } from '@nestjs/passport'
import { Strategy, ExtractJwt } from 'passport-jwt'

@Injectable()
export class JwtStrategy extends PassportStrategy(Strategy) {
  constructor(configService: ConfigService) {
    super({
      jwtFromRequest: ExtractJwt.fromAuthHeaderAsBearerToken(),
      ignoreExpiration: false,
      secretOrKey: configService.get('JWT_SECRET'),
    })
  }

  // 验证通过后，此方法的返回值会被挂到 request.user 上
  async validate(payload: JwtPayload) {
    return {
      id: payload.sub,
      email: payload.email,
      roles: payload.roles,
    }
  }
}
```

---

## AuthGuard：保护路由

```typescript
// 使用内置 AuthGuard
@Get('profile')
@UseGuards(AuthGuard('jwt'))
getProfile(@Request() req) {
  return req.user
}

// 自定义封装（推荐）
@Injectable()
export class JwtAuthGuard extends AuthGuard('jwt') {
  canActivate(context: ExecutionContext) {
    return super.canActivate(context)
  }

  handleRequest(err: any, user: any) {
    if (err || !user) {
      throw new UnauthorizedException('Token 无效或已过期')
    }
    return user
  }
}

// 配合 @CurrentUser() 装饰器使用
@Get('profile')
@UseGuards(JwtAuthGuard)
getProfile(@CurrentUser() user: User) {
  return user
}
```

---

## 角色权限控制（RBAC）

```typescript
// 定义角色装饰器
export const Roles = (...roles: string[]) => SetMetadata('roles', roles)

// 角色守卫
@Injectable()
export class RolesGuard implements CanActivate {
  constructor(private reflector: Reflector) {}

  canActivate(context: ExecutionContext): boolean {
    const requiredRoles = this.reflector.getAllAndOverride<string[]>('roles', [
      context.getHandler(),
      context.getClass(),
    ])

    if (!requiredRoles?.length) return true

    const { user } = context.switchToHttp().getRequest()
    return requiredRoles.some(role => user.roles?.includes(role))
  }
}

// 控制器中使用
@Post('admin/products')
@UseGuards(JwtAuthGuard, RolesGuard)
@Roles('admin')
createProduct(@Body() dto: CreateProductDto) {}
```

---

## Token 为什么要设置过期时间？

**安全角度：** Token 被窃取后，攻击者的利用窗口有限。过期越短，风险越小。

**建议配置：**

| Token 类型 | 建议过期时间 | 存储位置 |
|---|---|---|
| Access Token | 15 分钟 ～ 2 小时 | 内存或 localStorage |
| Refresh Token | 7 ～ 30 天 | HttpOnly Cookie（更安全） |

---

## Refresh Token 机制

```typescript
// refresh 接口
@Post('auth/refresh')
async refresh(@Body('refreshToken') refreshToken: string) {
  return this.authService.refreshTokens(refreshToken)
}

// 前端自动刷新（axios 拦截器示例）
axios.interceptors.response.use(
  response => response,
  async error => {
    if (error.response?.status === 401 && !error.config._retry) {
      error.config._retry = true
      const { accessToken } = await axios.post('/auth/refresh', {
        refreshToken: localStorage.getItem('refreshToken')
      })
      localStorage.setItem('accessToken', accessToken)
      error.config.headers['Authorization'] = `Bearer ${accessToken}`
      return axios(error.config)
    }
    return Promise.reject(error)
  }
)
```

---

## 完整认证控制器

```typescript
@Controller('auth')
export class AuthController {
  constructor(private authService: AuthService) {}

  @Post('login')
  async login(@Body() dto: LoginDto) {
    const user = await this.authService.validateUser(dto.email, dto.password)
    if (!user) throw new UnauthorizedException('邮箱或密码错误')
    return this.authService.login(user)
  }

  @Post('refresh')
  refresh(@Body('refreshToken') token: string) {
    return this.authService.refreshTokens(token)
  }

  @Post('logout')
  @UseGuards(JwtAuthGuard)
  async logout(@CurrentUser() user: User) {
    // 如果 Refresh Token 存在数据库中，这里应该让它失效
    await this.authService.invalidateRefreshToken(user.id)
    return { message: '已退出登录' }
  }
}
```
