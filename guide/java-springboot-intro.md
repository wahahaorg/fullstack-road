# 第五部分：Spring Boot 入门

## 5.1 本章目标

读完本章后，你应该能：

1. 理解 Spring 和 Spring Boot 的关系
2. 看懂 Spring Boot 项目的标准结构
3. 理解 Bean、IOC、依赖注入，并和 NestJS 的 DI 做对比
4. 理解注解（Annotation）和 NestJS 装饰器（Decorator）的异同
5. 独立编写 Controller、Service、Entity、DTO
6. 开发一个完整的 REST API 接口
7. 处理 JSON 序列化、参数校验、异常处理、统一返回结构

---

## 5.2 为什么需要学习这一章

这是整本教程最核心的一章。前几章学的 Java 语法、数据结构、工程化，都是为了这一章做准备。

学完本章，你能写一个真实的 Spring Boot 接口，而不是停留在"Hello World"。

---

## 5.3 Spring 和 Spring Boot 的关系

### 5.3.1 一句话

- **Spring** 是一个巨大的框架生态系统，提供 IOC、AOP、数据访问、事务管理等功能
- **Spring Boot** 是 Spring 的"快速启动器"，帮你自动配置、减少样板代码

**类比：**

| 概念 | Java | Node.js |
|------|------|---------|
| Spring Framework | Express 底层的 Node.js HTTP 模块 | 提供了基础能力，但需要大量配置 |
| Spring Boot | NestJS | 约定大于配置，开箱即用 |

### 5.3.2 为什么需要 Spring Boot

没有 Spring Boot 时，配置一个 Spring 项目需要大量 XML：

```xml
<!-- 传统 Spring：需要大量 XML 配置 -->
<bean id="userService" class="com.example.UserService">
    <property name="userRepository" ref="userRepository"/>
</bean>
```

有了 Spring Boot，自动配置 + 注解，零 XML：

```java
@Service
public class UserService {
    private final UserRepository userRepository;
    
    public UserService(UserRepository userRepository) {  // 自动注入
        this.userRepository = userRepository;
    }
}
```

---

## 5.4 Spring Boot 项目结构

### 5.4.1 标准目录

```
study-tracker/
├── pom.xml
├── src/
│   ├── main/
│   │   ├── java/com/example/studytracker/
│   │   │   ├── StudyTrackerApplication.java    ← 启动类
│   │   │   ├── controller/                      ← 控制器层
│   │   │   │   ├── StudyController.java
│   │   │   │   └── AuthController.java
│   │   │   ├── service/                         ← 服务层（接口）
│   │   │   │   ├── StudyService.java
│   │   │   │   └── UserService.java
│   │   │   ├── service/impl/                    ← 服务层（实现）
│   │   │   │   ├── StudyServiceImpl.java
│   │   │   │   └── UserServiceImpl.java
│   │   │   ├── entity/                          ← 数据库实体
│   │   │   │   ├── User.java
│   │   │   │   └── StudyRecord.java
│   │   │   ├── dto/                             ← 请求/响应对象
│   │   │   │   ├── StudyStartRequest.java
│   │   │   │   ├── StudyRecordVO.java
│   │   │   │   └── LoginRequest.java
│   │   │   ├── mapper/                          ← 数据库映射
│   │   │   │   ├── UserMapper.java
│   │   │   │   └── StudyRecordMapper.java
│   │   │   ├── config/                          ← 配置类
│   │   │   │   └── WebConfig.java
│   │   │   └── common/                          ← 公共类
│   │   │       ├── Result.java
│   │   │       ├── BusinessException.java
│   │   │       └── GlobalExceptionHandler.java
│   │   └── resources/
│   │       └── application.yml
│   └── test/
│       └── java/com/example/studytracker/
│           └── StudyTrackerApplicationTests.java
```

### 5.4.2 对比 NestJS 项目结构

```
study-tracker-nest/
├── package.json
├── src/
│   ├── main.ts                    ← 启动文件
│   ├── app.module.ts              ← 根模块
│   ├── study/
│   │   ├── study.controller.ts    ← Controller
│   │   ├── study.service.ts       ← Service
│   │   ├── study.module.ts        ← Module
│   │   ├── dto/
│   │   │   └── study.dto.ts
│   │   └── entities/
│   │       └── study-record.entity.ts
│   ├── auth/
│   │   ├── auth.controller.ts
│   │   ├── auth.service.ts
│   │   └── auth.module.ts
│   └── common/
│       ├── result.ts
│       └── exception.filter.ts
└── .env
```

**核心对应关系：**

| 职责 | Spring Boot | NestJS |
|------|------------|--------|
| 启动入口 | `XxxApplication.java` | `main.ts` |
| 路由处理 | `@RestController` + `@GetMapping` | `@Controller` + `@Get` |
| 业务逻辑 | `@Service` | `@Injectable` Provider |
| 依赖注入 | 构造器注入 | 构造器注入 |
| 请求参数 | `@RequestBody`、`@PathVariable` | `@Body`、`@Param` |
| 模块化 | `@SpringBootApplication` 自动扫描 | `@Module` 显式声明 |

---

## 5.5 Bean 是什么

### 5.5.1 一句话

**Bean = 由 Spring 容器管理的对象。**

你不需要 `new` 来创建 Service、Controller、Repository，Spring 会帮你创建并管理它们的生命周期。

```java
@Service  // 告诉 Spring：这个类交给你管理
public class StudyService {
    // ...
}

// 其他地方使用时，通过构造器注入
@RestController
public class StudyController {
    private final StudyService studyService;
    
    public StudyController(StudyService studyService) {  // Spring 自动传入
        this.studyService = studyService;
    }
}
```

### 5.5.2 类比 NestJS

```typescript
// NestJS
@Injectable()
export class StudyService { }

@Controller()
export class StudyController {
    constructor(private readonly studyService: StudyService) {}  // NestJS 自动传入
}
```

**完全一样的概念！** 只是注解名不同：
- `@Injectable()` → `@Service` / `@Component` / `@Repository`
- `@Controller()` → `@RestController`

---

## 5.6 IOC 和依赖注入

### 5.6.1 什么是 IOC

**IOC（控制反转）：** "不要自己 new 对象，把创建对象的控制权交给框架。"

```java
// ❌ 传统方式：自己控制
public class StudyController {
    private StudyService service = new StudyService();  // 自己 new
}

// ✅ IOC 方式：Spring 控制
public class StudyController {
    private final StudyService service;
    
    public StudyController(StudyService service) {  // Spring 传进来
        this.service = service;
    }
}
```

### 5.6.2 三种注入方式

```java
// 方式一：构造器注入（推荐！）
@RestController
public class StudyController {
    private final StudyService studyService;
    
    public StudyController(StudyService studyService) {
        this.studyService = studyService;
    }
}

// 方式二：Lombok 简化（更简洁）
@RestController
@RequiredArgsConstructor  // 自动生成包含 final 字段的构造器
public class StudyController {
    private final StudyService studyService;
}

// 方式三：@Autowired 字段注入（不推荐，难以测试）
@RestController
public class StudyController {
    @Autowired
    private StudyService studyService;
}
```

**推荐使用方式二（Lombok `@RequiredArgsConstructor`），** 和 NestJS 的构造器注入完全一致。

---

## 5.7 Annotation 注解

### 5.7.1 注解 vs 装饰器

| 特性 | Java Annotation | TypeScript Decorator |
|------|----------------|---------------------|
| 语法 | `@Override` | `@Injectable()` |
| 本质 | 元数据标记 | 函数，可以修改类行为 |
| 运行时 | 保留（通过反射读取） | 取决于实现 |
| 能否修改类 | 不能直接修改 | 可以 |

**Java 注解更"轻"——** 它本质上是给类贴标签，框架通过反射读取标签来决定行为。TypeScript 装饰器更"重"——它可以直接修改类。

### 5.7.2 Spring Boot 常用注解

| 注解 | 作用 | NestJS 类比 |
|------|------|------------|
| `@SpringBootApplication` | 标记启动类 | — |
| `@RestController` | 标记控制器（返回 JSON） | `@Controller()` |
| `@RequestMapping("/api")` | 类级别路径前缀 | `@Controller('api')` |
| `@GetMapping("/users")` | GET 请求 | `@Get('users')` |
| `@PostMapping("/users")` | POST 请求 | `@Post('users')` |
| `@PutMapping("/users/{id}")` | PUT 请求 | `@Put(':id')` |
| `@DeleteMapping("/users/{id}")` | DELETE 请求 | `@Delete(':id')` |
| `@Service` | 标记服务层 | `@Injectable()` |
| `@Repository` | 标记数据访问层 | `@Injectable()` |
| `@Component` | 通用组件 | `@Injectable()` |
| `@Autowired` | 自动注入 | 构造器注入 |
| `@Value("${key}")` | 读取配置 | `@Config()` |
| `@Configuration` | 标记配置类 | `@Module()` |
| `@Bean` | 手动创建 Bean | `providers: [...]` |

---

## 5.8 Controller

### 5.8.1 职责

Controller 只负责：
- 接收 HTTP 请求
- 参数校验
- 调用 Service
- 返回响应

**Controller 不应该包含：**
- 业务逻辑
- 数据库操作
- 复杂的条件判断

### 5.8.2 完整示例

```java
// 文件：src/main/java/com/example/studytracker/controller/StudyController.java
package com.example.studytracker.controller;

import com.example.studytracker.common.Result;
import com.example.studytracker.dto.StudyStartRequest;
import com.example.studytracker.service.StudyService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/study")
@RequiredArgsConstructor
public class StudyController {

    private final StudyService studyService;

    @PostMapping("/start")
    public Result<Long> startStudy(@Valid @RequestBody StudyStartRequest request) {
        Long recordId = studyService.startStudy(request);
        return Result.success(recordId);
    }

    @PostMapping("/end/{recordId}")
    public Result<Void> endStudy(@PathVariable Long recordId) {
        studyService.endStudy(recordId);
        return Result.success();
    }

    @GetMapping("/today")
    public Result<?> getTodayRecords() {
        return Result.success(studyService.getTodayRecords());
    }
}
```

**逐行解释：**

```java
@RestController              // 1. 声明这是一个 REST 控制器（返回 JSON）
@RequestMapping("/api/study") // 2. 所有接口以 /api/study 开头
@RequiredArgsConstructor      // 3. Lombok 自动生成构造器
public class StudyController {

    private final StudyService studyService;  // 4. 依赖注入

    @PostMapping("/start")    // 5. POST /api/study/start
    public Result<Long> startStudy(
        @Valid               // 6. 触发参数校验
        @RequestBody          // 7. 从请求体解析 JSON
        StudyStartRequest request  // 8. 请求参数对象
    ) {
        Long recordId = studyService.startStudy(request);  // 9. 调用 Service
        return Result.success(recordId);  // 10. 返回统一格式
    }
}
```

### 5.8.3 常用请求参数注解

```java
// 路径参数：/api/users/123
@GetMapping("/users/{id}")
public Result<User> getUser(@PathVariable Long id) { }

// 查询参数：/api/users?page=1&size=10
@GetMapping("/users")
public Result<List<User>> getUsers(
    @RequestParam(defaultValue = "1") int page,
    @RequestParam(defaultValue = "10") int size
) { }

// 请求体（JSON）
@PostMapping("/users")
public Result<User> createUser(@RequestBody @Valid CreateUserRequest request) { }

// 请求头
@GetMapping("/profile")
public Result<User> getProfile(@RequestHeader("Authorization") String token) { }
```

**对比 NestJS：**

```typescript
@Get('users/:id')
getUser(@Param('id') id: number) { }

@Get('users')
getUsers(@Query('page') page: number, @Query('size') size: number) { }

@Post('users')
createUser(@Body() request: CreateUserDto) { }

@Get('profile')
getProfile(@Headers('authorization') token: string) { }
```

---

## 5.9 Service

### 5.9.1 职责

Service 负责：
- 业务逻辑
- 调用 Repository/Mapper
- 事务管理
- 数据组装和转换

**Service 不应该负责：**
- 处理 HTTP 请求/响应
- 直接操作 HttpServletRequest/Response

### 5.9.2 接口 + 实现（标准写法）

```java
// 接口：src/main/java/com/example/studytracker/service/StudyService.java
package com.example.studytracker.service;

import com.example.studytracker.dto.StudyStartRequest;
import com.example.studytracker.vo.StudyRecordVO;
import java.util.List;

public interface StudyService {
    Long startStudy(StudyStartRequest request);
    void endStudy(Long recordId);
    List<StudyRecordVO> getTodayRecords();
}
```

```java
// 实现：src/main/java/com/example/studytracker/service/impl/StudyServiceImpl.java
package com.example.studytracker.service.impl;

import com.example.studytracker.dto.StudyStartRequest;
import com.example.studytracker.entity.StudyRecord;
import com.example.studytracker.mapper.StudyRecordMapper;
import com.example.studytracker.service.StudyService;
import com.example.studytracker.vo.StudyRecordVO;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import java.time.LocalDateTime;
import java.util.List;
import java.util.stream.Collectors;

@Service
@RequiredArgsConstructor
public class StudyServiceImpl implements StudyService {

    private final StudyRecordMapper studyRecordMapper;

    @Override
    public Long startStudy(StudyStartRequest request) {
        StudyRecord record = new StudyRecord();
        record.setUserId(request.getUserId());
        record.setProject(request.getProject());
        record.setStartTime(LocalDateTime.now());
        record.setStatus("STUDYING");
        studyRecordMapper.insert(record);
        return record.getId();
    }

    @Override
    public void endStudy(Long recordId) {
        StudyRecord record = studyRecordMapper.selectById(recordId);
        if (record == null) {
            throw new RuntimeException("学习记录不存在");
        }
        record.setEndTime(LocalDateTime.now());
        record.setStatus("COMPLETED");
        studyRecordMapper.updateById(record);
    }

    @Override
    public List<StudyRecordVO> getTodayRecords() {
        List<StudyRecord> records = studyRecordMapper.selectTodayRecords();
        return records.stream()
            .map(this::toVO)
            .collect(Collectors.toList());
    }

    private StudyRecordVO toVO(StudyRecord record) {
        StudyRecordVO vo = new StudyRecordVO();
        vo.setId(record.getId());
        vo.setProject(record.getProject());
        vo.setStartTime(record.getStartTime());
        vo.setEndTime(record.getEndTime());
        vo.setDuration(calculateDuration(record.getStartTime(), record.getEndTime()));
        return vo;
    }

    private long calculateDuration(LocalDateTime start, LocalDateTime end) {
        if (start == null || end == null) return 0;
        return java.time.Duration.between(start, end).toMinutes();
    }
}
```

### 5.9.3 为什么要有接口

很多 Spring Boot 项目对 Service 使用接口 + 实现类的方式。原因：

1. **便于测试** — 可以 mock 接口
2. **便于切换实现** — 比如从 MySQL 切换到 Redis
3. **Spring AOP 需要** — 事务代理基于接口

**但在简单项目中，你也可以直接写实现类，不定义接口。** 很多现代 Spring Boot 项目已经简化了这一点。

---

## 5.10 Entity

### 5.10.1 Entity 是什么

Entity 是数据库表的 Java 对象映射。一个 Entity 类对应一张数据库表，一个字段对应一列。

```java
// 文件：src/main/java/com/example/studytracker/entity/StudyRecord.java
package com.example.studytracker.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;
import java.time.LocalDateTime;

@Data
@TableName("study_record")  // 对应数据库表名
public class StudyRecord {
    @TableId(type = IdType.AUTO)  // 主键自增
    private Long id;
    private Long userId;
    private String project;
    private LocalDateTime startTime;
    private LocalDateTime endTime;
    private String status;
}
```

**对比 TypeORM：**

```typescript
@Entity()
@TableName("study_record")
export class StudyRecord {
    @PrimaryGeneratedColumn()
    id: number;

    @Column()
    userId: number;

    @Column()
    project: string;

    @Column()
    startTime: Date;

    @Column({ nullable: true })
    endTime: Date;

    @Column()
    status: string;
}
```

---

## 5.11 DTO 和 VO

### 5.11.1 概念区分

| 概念 | 全称 | 用途 | 方向 |
|------|------|------|------|
| **DTO** | Data Transfer Object | 接收请求参数 | 前端 → 后端 |
| **VO** | View Object | 返回给前端的数据 | 后端 → 前端 |
| **Entity** | Entity | 数据库映射 | 数据库 ↔ 后端 |

**为什么要区分？** 因为数据库的字段和接口的字段不一样。比如：
- 数据库有 `created_at`，但接口不需要返回
- 接口需要 `duration`（计算出来的），但数据库没有存这个字段

### 5.11.2 DTO 示例

```java
// 文件：src/main/java/com/example/studytracker/dto/StudyStartRequest.java
package com.example.studytracker.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import lombok.Data;

@Data
public class StudyStartRequest {
    @NotNull(message = "用户ID不能为空")
    private Long userId;

    @NotBlank(message = "学习项目不能为空")
    private String project;
}
```

### 5.11.3 VO 示例

```java
// 文件：src/main/java/com/example/studytracker/vo/StudyRecordVO.java
package com.example.studytracker.vo;

import lombok.Data;
import java.time.LocalDateTime;

@Data
public class StudyRecordVO {
    private Long id;
    private String project;
    private LocalDateTime startTime;
    private LocalDateTime endTime;
    private Long duration;  // 学习时长（分钟），计算出来的
    private String status;
}
```

### 5.11.4 对比 NestJS 和 FastAPI

| 概念 | Spring Boot | NestJS | FastAPI |
|------|------------|--------|---------|
| 请求体 | `@RequestBody` DTO | `@Body()` DTO class | Pydantic Schema |
| 响应体 | VO 类 | 直接返回 Entity 或 DTO | Pydantic Schema |
| 参数校验 | `@Valid` + `@NotBlank` | `class-validator` + `ValidationPipe` | Pydantic 自动校验 |

---

## 5.12 参数校验

### 5.12.1 常用校验注解

```java
import jakarta.validation.constraints.*;

@Data
public class CreateUserRequest {
    @NotBlank(message = "用户名不能为空")
    @Size(min = 2, max = 20, message = "用户名长度2-20位")
    private String username;

    @NotBlank(message = "密码不能为空")
    @Size(min = 6, max = 30, message = "密码长度6-30位")
    private String password;

    @Email(message = "邮箱格式不正确")
    private String email;

    @NotNull(message = "年龄不能为空")
    @Min(value = 0, message = "年龄不能小于0")
    @Max(value = 150, message = "年龄不能大于150")
    private Integer age;

    @Pattern(regexp = "^1[3-9]\\d{9}$", message = "手机号格式不正确")
    private String phone;
}
```

### 5.12.2 校验注解速查

| 注解 | 作用 | 适用类型 |
|------|------|----------|
| `@NotNull` | 不能为 null | 任何类型 |
| `@NotBlank` | 不能为 null 且不能全是空格 | String |
| `@NotEmpty` | 不能为 null 且不能为空集合/字符串 | String、Collection、Map |
| `@Size(min, max)` | 长度范围 | String、Collection |
| `@Min(value)` | 最小值 | 数字 |
| `@Max(value)` | 最大值 | 数字 |
| `@Email` | 邮箱格式 | String |
| `@Pattern(regexp)` | 正则匹配 | String |

---

## 5.13 全局异常处理

### 5.13.1 定义业务异常

```java
// 文件：src/main/java/com/example/studytracker/common/BusinessException.java
package com.example.studytracker.common;

import lombok.Getter;

@Getter
public class BusinessException extends RuntimeException {
    private final int code;

    public BusinessException(int code, String message) {
        super(message);
        this.code = code;
    }

    public BusinessException(String message) {
        this(400, message);
    }
}
```

### 5.13.2 全局异常处理器

```java
// 文件：src/main/java/com/example/studytracker/common/GlobalExceptionHandler.java
package com.example.studytracker.common;

import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.stream.Collectors;

@Slf4j
@RestControllerAdvice
public class GlobalExceptionHandler {

    // 处理参数校验异常
    @ExceptionHandler(MethodArgumentNotValidException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public Result<Void> handleValidation(MethodArgumentNotValidException e) {
        String message = e.getBindingResult().getFieldErrors().stream()
            .map(FieldError::getDefaultMessage)
            .collect(Collectors.joining(", "));
        return Result.error(400, message);
    }

    // 处理业务异常
    @ExceptionHandler(BusinessException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public Result<Void> handleBusiness(BusinessException e) {
        return Result.error(e.getCode(), e.getMessage());
    }

    // 处理其他未捕获异常
    @ExceptionHandler(Exception.class)
    @ResponseStatus(HttpStatus.INTERNAL_SERVER_ERROR)
    public Result<Void> handleUnknown(Exception e) {
        log.error("未知异常", e);
        return Result.error(500, "服务器内部错误");
    }
}
```

**对比 NestJS：**

```typescript
// NestJS Exception Filter
@Catch()
export class GlobalExceptionFilter implements ExceptionFilter {
    catch(exception: unknown, host: ArgumentsHost) {
        const ctx = host.switchToHttp();
        const response = ctx.getResponse<Response>();

        if (exception instanceof BadRequestException) {
            response.status(400).json(Result.error(400, exception.message));
        } else {
            response.status(500).json(Result.error(500, '服务器内部错误'));
        }
    }
}
```

---

## 5.14 统一返回结构

```java
// 文件：src/main/java/com/example/studytracker/common/Result.java
package com.example.studytracker.common;

import lombok.Data;

@Data
public class Result<T> {
    private int code;
    private String message;
    private T data;

    private Result() {}

    public static <T> Result<T> success() {
        return success(null);
    }

    public static <T> Result<T> success(T data) {
        Result<T> result = new Result<>();
        result.code = 200;
        result.message = "success";
        result.data = data;
        return result;
    }

    public static <T> Result<T> error(int code, String message) {
        Result<T> result = new Result<>();
        result.code = code;
        result.message = message;
        return result;
    }
}
```

**返回格式：**

```json
// 成功
{ "code": 200, "message": "success", "data": { "id": 1, "project": "Java" } }

// 失败
{ "code": 400, "message": "学习项目不能为空", "data": null }
```

---

## 5.15 完整接口示例

把所有知识串起来，写一个完整的用户注册接口：

```java
// --- DTO ---
@Data
public class RegisterRequest {
    @NotBlank(message = "用户名不能为空")
    @Size(min = 2, max = 20, message = "用户名长度2-20位")
    private String username;

    @NotBlank(message = "密码不能为空")
    @Size(min = 6, max = 30, message = "密码长度6-30位")
    private String password;

    @Email(message = "邮箱格式不正确")
    private String email;
}

// --- VO ---
@Data
public class UserVO {
    private Long id;
    private String username;
    private String email;
}

// --- Controller ---
@RestController
@RequestMapping("/api/auth")
@RequiredArgsConstructor
public class AuthController {
    private final UserService userService;

    @PostMapping("/register")
    public Result<UserVO> register(@Valid @RequestBody RegisterRequest request) {
        UserVO user = userService.register(request);
        return Result.success(user);
    }
}

// --- Service ---
@Service
@RequiredArgsConstructor
public class UserServiceImpl implements UserService {
    private final UserMapper userMapper;

    @Override
    public UserVO register(RegisterRequest request) {
        // 检查用户名是否已存在
        if (userMapper.selectByUsername(request.getUsername()) != null) {
            throw new BusinessException("用户名已存在");
        }
        // 创建用户
        User user = new User();
        user.setUsername(request.getUsername());
        user.setPassword(request.getPassword());  // 实际项目需要加密
        user.setEmail(request.getEmail());
        userMapper.insert(user);
        // 返回 VO
        return toVO(user);
    }

    private UserVO toVO(User user) {
        UserVO vo = new UserVO();
        vo.setId(user.getId());
        vo.setUsername(user.getUsername());
        vo.setEmail(user.getEmail());
        return vo;
    }
}
```

**请求与响应：**

```bash
# 请求
curl -X POST http://localhost:8080/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"123456","email":"alice@example.com"}'

# 响应
{"code":200,"message":"success","data":{"id":1,"username":"alice","email":"alice@example.com"}}

# 参数校验失败
curl -X POST http://localhost:8080/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"","password":"123","email":"not-email"}'

# 响应
{"code":400,"message":"用户名不能为空, 密码长度6-30位, 邮箱格式不正确","data":null}
```

---

## 5.16 各层常见错误写法

### Controller 层

```java
// ❌ 错误：在 Controller 里写业务逻辑
@PostMapping("/start")
public Result<Long> startStudy(@RequestBody StudyStartRequest request) {
    if (request.getProject() == null) {  // 应该用 @Valid 校验
        return Result.error(400, "项目不能为空");
    }
    // 业务逻辑不应该在 Controller
    if (studyRecordMapper.countTodayRecords() > 10) {
        return Result.error(400, "今日已达上限");
    }
    StudyRecord record = new StudyRecord();
    record.setUserId(request.getUserId());
    // ...
    studyRecordMapper.insert(record);
    return Result.success(record.getId());
}

// ✅ 正确：Controller 只做路由和调用
@PostMapping("/start")
public Result<Long> startStudy(@Valid @RequestBody StudyStartRequest request) {
    return Result.success(studyService.startStudy(request));
}
```

### Service 层

```java
// ❌ 错误：Service 直接操作 HttpServletRequest
public void doSomething(HttpServletRequest request) {
    String token = request.getHeader("Authorization");
    // ...
}

// ✅ 正确：Service 不感知 HTTP
public void doSomething(Long userId) {
    // 只处理业务逻辑
}
```

### Entity 层

```java
// ❌ 错误：Entity 暴露给前端
@GetMapping("/users")
public List<User> getUsers() {  // 返回 Entity，密码也返回了
    return userMapper.selectList(null);
}

// ✅ 正确：返回 VO
@GetMapping("/users")
public Result<List<UserVO>> getUsers() {
    return Result.success(userService.getUsers());
}
```

---

## 5.17 常见错误

### 错误一：Controller 没被扫描到

```java
// 症状：接口 404
// 原因：Controller 不在启动类所在包或其子包下

// 启动类在 com.example.studytracker
// Controller 必须在 com.example.studytracker 或 com.example.studytracker.xxx 下
```

### 错误二：循环依赖

```java
// ServiceA 注入 ServiceB，ServiceB 注入 ServiceA
// 症状：启动报错 "Circular dependency"

// 解决：重新设计，提取公共逻辑到第三个 Service
```

### 错误三：@Autowired 字段为 null

```java
// 症状：调用时 NPE
// 原因：手动 new 了对象，而不是让 Spring 管理

// ❌
StudyService service = new StudyService();  // 手动 new，不会注入依赖

// ✅ 让 Spring 管理
@RequiredArgsConstructor
public class StudyController {
    private final StudyService service;  // Spring 自动注入
}
```

---

## 5.18 三道小练习

### 练习 1：写一个 Controller

写一个 `HealthController`，提供一个 `GET /api/health` 接口，返回：

```json
{"code": 200, "message": "success", "data": {"status": "UP", "timestamp": "2026-07-25T10:00:00"}}
```

### 练习 2：写一个带校验的接口

写一个 `POST /api/feedback` 接口，接收：

```json
{"userId": 1, "content": "很好用", "rating": 5}
```

要求：
- userId 不能为空
- content 不能为空，长度 1-500
- rating 必须在 1-5 之间

### 练习 3：全局异常处理

修改 `GlobalExceptionHandler`，添加对 `IllegalArgumentException` 的处理，返回 400 状态码。

---

## 5.19 参考答案

### 练习 1

```java
@RestController
@RequestMapping("/api")
public class HealthController {

    @GetMapping("/health")
    public Result<Map<String, Object>> health() {
        Map<String, Object> data = new HashMap<>();
        data.put("status", "UP");
        data.put("timestamp", LocalDateTime.now().toString());
        return Result.success(data);
    }
}
```

### 练习 2

```java
@Data
public class FeedbackRequest {
    @NotNull(message = "用户ID不能为空")
    private Long userId;

    @NotBlank(message = "反馈内容不能为空")
    @Size(max = 500, message = "反馈内容不能超过500字")
    private String content;

    @NotNull(message = "评分不能为空")
    @Min(value = 1, message = "评分最小为1")
    @Max(value = 5, message = "评分最大为5")
    private Integer rating;
}

@RestController
@RequestMapping("/api")
@RequiredArgsConstructor
public class FeedbackController {
    @PostMapping("/feedback")
    public Result<Void> submit(@Valid @RequestBody FeedbackRequest request) {
        return Result.success();
    }
}
```

### 练习 3

```java
@ExceptionHandler(IllegalArgumentException.class)
@ResponseStatus(HttpStatus.BAD_REQUEST)
public Result<Void> handleIllegalArgument(IllegalArgumentException e) {
    return Result.error(400, e.getMessage());
}
```

---

## 5.20 本章速查表

| 概念 | Spring Boot | NestJS | FastAPI |
|------|------------|--------|---------|
| 启动入口 | `@SpringBootApplication` + `main()` | `NestFactory.create(AppModule)` | `uvicorn.run(app)` |
| 路由 | `@RestController` + `@GetMapping` | `@Controller()` + `@Get()` | `@app.get()` |
| 请求体 | `@RequestBody` + DTO | `@Body()` + DTO | Pydantic Schema |
| 路径参数 | `@PathVariable` | `@Param()` | `{param}` in path |
| 查询参数 | `@RequestParam` | `@Query()` | `Query()` |
| 业务层 | `@Service` | `@Injectable()` | 普通函数/类 |
| 依赖注入 | 构造器注入 | 构造器注入 | `Depends()` |
| 参数校验 | `@Valid` + `@NotBlank` | `ValidationPipe` + `class-validator` | Pydantic 内置 |
| 异常处理 | `@RestControllerAdvice` | `ExceptionFilter` | `@app.exception_handler` |
| 统一返回 | `Result<T>` 泛型类 | `Result<T>` 泛型类 | 自定义响应模型 |

---

## 5.21 是否需要深入学习

本章是**整本教程最核心的一章**，必须掌握。建议：

1. 理解每层职责，不要把所有代码堆在 Controller
2. 记住注解的对应关系（`@RestController` ↔ NestJS `@Controller`）
3. 动手写一个完整的 Controller → Service → Entity 链路
4. 参数校验和全局异常处理是必须掌握的

**准备好了吗？** 继续阅读 [第六章：数据库基础 →](./java-database)