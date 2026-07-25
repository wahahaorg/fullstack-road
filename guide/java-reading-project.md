# 第十部分：阅读陌生项目的方法

## 10.1 本章目标

读完本章后，你应该能：

1. 拿到一个陌生 Java 项目，知道从哪里开始看
2. 从接口 URL 追踪到数据库查询
3. 定位异常来源
4. 安全地进行最小范围修改

---

## 10.2 阅读顺序：先看什么

### 第一步：看 pom.xml（1 分钟）

```bash
# 快速了解项目用什么技术
grep -E '<artifactId>' pom.xml | head -20
```

你能知道：
- 用 Spring Boot 哪个版本
- 用 MyBatis 还是 JPA
- 有没有用 Redis、MQ
- 用什么数据库

### 第二步：看 application.yml（2 分钟）

```bash
cat src/main/resources/application.yml
```

你能知道：
- 端口号
- 数据库连接信息
- 第三方服务地址
- 自定义配置项

### 第三步：看启动类（1 分钟）

```java
// 找 @SpringBootApplication 注解的类
@SpringBootApplication
public class XxxApplication {
    public static void main(String[] args) {
        SpringApplication.run(XxxApplication.class, args);
    }
}
```

### 第四步：看 Controller 目录（5 分钟）

```bash
ls src/main/java/com/xxx/xxx/controller/
```

浏览所有 Controller 类，了解项目提供了哪些接口。每个 Controller 上的 `@RequestMapping` 告诉你接口路径前缀。

---

## 10.3 如何找到某个接口

假设你看到前端调用了 `POST /api/order/create`：

**方法一：搜索路径**

```bash
grep -r "order/create" src/main/java/
```

**方法二：搜索注解**

```bash
grep -r "@PostMapping.*order" src/main/java/
grep -r "@RequestMapping.*order" src/main/java/
```

**方法三：在 IDEA 中**

`Ctrl+Shift+F`（全局搜索）→ 输入 `"order/create"` → 找到 Controller 方法

---

## 10.4 从 Controller 追到数据库

假设找到了 Controller：

```java
@PostMapping("/order/create")
public Result<OrderVO> createOrder(@RequestBody CreateOrderRequest request) {
    return Result.success(orderService.createOrder(request));
}
```

**追踪路径：**

```
Controller: createOrder(request)
    ↓
Service 接口: OrderService.createOrder(request)
    ↓
Service 实现: OrderServiceImpl.createOrder(request)
    ↓
Mapper: orderMapper.insert(entity) 或 orderMapper.selectById(id)
    ↓
Entity: Order.java（对应数据库表 orders）
    ↓
SQL: 看 Mapper 的 @Select 注解或 XML 文件
```

**在 IDEA 中：** `Ctrl+点击` 方法名，一层层跟进去。

---

## 10.5 如何找到请求参数定义

```java
// Controller 方法参数
public Result<OrderVO> createOrder(@RequestBody CreateOrderRequest request)

// Ctrl+点击 CreateOrderRequest 进入 DTO 类
@Data
public class CreateOrderRequest {
    @NotNull
    private Long productId;
    @Min(1)
    private Integer quantity;
    private String remark;
}
```

**DTO 类通常在：**
- `dto/` 目录
- `model/request/` 目录
- `vo/` 目录（如果命名不规范）

---

## 10.6 如何判断是否有鉴权

**方法一：看 WebConfig 中的拦截器**

```java
@Configuration
public class WebConfig implements WebMvcConfigurer {
    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(authInterceptor)
            .addPathPatterns("/api/**")        // 拦截这些路径
            .excludePathPatterns("/api/auth/**"); // 不拦截这些路径
    }
}
```

**方法二：看 Controller 方法上的注解**

```java
// 如果有 Spring Security
@PreAuthorize("hasRole('ADMIN')")
public Result<?> deleteUser() { }
```

**方法三：搜索关键字**

```bash
grep -r "Authorization" src/main/java/
grep -r "Token" src/main/java/
grep -r "Interceptor" src/main/java/
```

---

## 10.7 如何查看数据库配置

```yaml
# application.yml
spring:
  datasource:
    url: jdbc:mysql://localhost:3306/mydb?...
    username: root
    password: ${DB_PASSWORD}
```

如果用了环境变量，在启动脚本或 Docker Compose 中找：

```bash
grep -r "DB_PASSWORD" .
```

---

## 10.8 如何查看外部服务调用

```bash
# 搜索 HTTP 调用相关代码
grep -r "RestTemplate" src/main/java/
grep -r "WebClient" src/main/java/
grep -r "FeignClient" src/main/java/  # Spring Cloud
```

---

## 10.9 如何定位异常

### 场景：前端报 500

**排查步骤：**

1. **看后端控制台日志**

```
ERROR 12345 --- [nio-8080-exec-1] c.e.c.OrderController  : 创建订单失败
java.lang.NullPointerException: ...
    at com.example.service.OrderService.createOrder(OrderService.java:45)
```

定位到 `OrderService.java` 第 45 行。

2. **看全局异常处理器**

```java
@RestControllerAdvice
public class GlobalExceptionHandler {
    @ExceptionHandler(Exception.class)
    public Result<Void> handleException(Exception e) {
        // 如果是 500 且没有业务异常信息，看看这里是不是吞掉了异常信息
    }
}
```

3. **加日志**

```java
// 在可疑位置加日志
log.info("订单参数: {}", request);
log.info("查询结果: {}", order);
```

### 场景：前端报 404

```bash
# 1. 确认接口路径是否正确
grep -r "GetMapping.*health" src/main/java/

# 2. 确认 Controller 是否被扫描到
# Controller 必须在启动类所在包或其子包下

# 3. 确认拦截器是否误拦截了
```

### 场景：返回的数据不对

```bash
# 从 Controller 开始，逐层加日志
# Controller → Service → Mapper → SQL
```

---

## 10.10 如何进行最小范围修改

**原则：** 只改你需要的，不动其他代码。

**修改一个接口的返回字段：**

1. 找到对应的 VO 类
2. 添加需要的字段
3. 在 Service 的 `toVO()` 方法中设置新字段值

**修改一个业务逻辑：**

1. 只改 Service 实现类中的方法
2. 不改接口签名（除非必要）
3. 改完后运行相关测试

**修改数据库查询：**

1. 修改 Mapper 中的 SQL（`@Select` 注解或 XML）
2. 如果返回字段变了，同步修改 Entity 或 VO

---

## 10.11 案例：前端请求返回 500，如何排查

**场景：** 前端调用 `POST /api/order/create`，返回：

```json
{"code":500,"message":"服务器内部错误","data":null}
```

**排查步骤：**

```bash
# 1. 看后端日志
# 找到最近的 ERROR 日志

# 2. 找到 Controller
grep -r "order/create" src/main/java/

# 定位到 OrderController.java 第 30 行：
@PostMapping("/order/create")
public Result<OrderVO> createOrder(@RequestBody CreateOrderRequest request) {
    return Result.success(orderService.createOrder(request));
}

# 3. Ctrl+点击 createOrder 进入 Service
# 定位到 OrderServiceImpl.java 第 45 行：
public OrderVO createOrder(CreateOrderRequest request) {
    Product product = productMapper.selectById(request.getProductId());
    // 如果 product 是 null，下面这行 NPE：
    if (product.getStock() < request.getQuantity()) {  // ← NPE!
        throw new BusinessException("库存不足");
    }
}

# 4. 修复：加空判断
public OrderVO createOrder(CreateOrderRequest request) {
    Product product = productMapper.selectById(request.getProductId());
    if (product == null) {
        throw new BusinessException("商品不存在");
    }
    if (product.getStock() < request.getQuantity()) {
        throw new BusinessException("库存不足");
    }
    // ...
}
```

---

## 10.12 本章速查表

| 想看什么 | 查看哪里 |
|----------|----------|
| 项目技术栈 | pom.xml |
| 配置信息 | application.yml |
| 接口列表 | controller/ 目录 |
| 数据库表结构 | entity/ 目录 + 建表 SQL |
| 鉴权方式 | WebConfig + Interceptor |
| SQL 查询 | Mapper 接口的 @Select 或 XML |
| 异常处理 | GlobalExceptionHandler |
| 外部调用 | RestTemplate / WebClient |

---

## 10.13 是否需要深入学习

本章标记为"看懂即可"。掌握阅读项目的方法论，具体操作在实践中积累。

**准备好了吗？** 继续阅读 [第十一章：Java 招聘要求判断 →](./java-job-requirements)