---
title: 第九部分：实战项目 — 学习时间记录系统
---

# 第九部分：实战项目 — 学习时间记录系统

## 9.1 本章目标

本章带你从零实现一个完整的 Spring Boot 后端项目，串起前面所有知识。

**功能：**

1. 用户注册/登录
2. 开始学习 / 结束学习
3. 查询今日学习时长
4. 查询学习记录（分页）
5. 按日期统计
6. 按学习项目分类统计
7. MySQL 数据持久化
8. 参数校验 + 全局异常处理 + 统一返回结构

---

## 9.2 项目结构

```
study-tracker/
├── pom.xml
└── src/main/
    ├── java/com/example/studytracker/
    │   ├── StudyTrackerApplication.java
    │   ├── config/
    │   │   ├── MyBatisPlusConfig.java
    │   │   ├── SecurityConfig.java
    │   │   └── WebConfig.java
    │   ├── common/
    │   │   ├── Result.java
    │   │   ├── BusinessException.java
    │   │   ├── ErrorCode.java
    │   │   └── GlobalExceptionHandler.java
    │   ├── controller/
    │   │   ├── AuthController.java
    │   │   └── StudyController.java
    │   ├── dto/
    │   │   ├── LoginRequest.java
    │   │   ├── RegisterRequest.java
    │   │   └── StudyStartRequest.java
    │   ├── vo/
    │   │   ├── LoginResponse.java
    │   │   ├── StudyRecordVO.java
    │   │   └── StatisticsVO.java
    │   ├── entity/
    │   │   ├── User.java
    │   │   └── StudyRecord.java
    │   ├── mapper/
    │   │   ├── UserMapper.java
    │   │   └── StudyRecordMapper.java
    │   ├── service/
    │   │   ├── UserService.java
    │   │   └── StudyService.java
    │   ├── service/impl/
    │   │   ├── UserServiceImpl.java
    │   │   └── StudyServiceImpl.java
    │   ├── interceptor/
    │   │   └── AuthInterceptor.java
    │   └── util/
    │       └── JwtUtil.java
    └── resources/
        └── application.yml
```

---

## 9.3 pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.2.0</version>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>study-tracker</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>study-tracker</name>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <!-- Spring Boot Web -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>

        <!-- 参数校验 -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>

        <!-- MySQL -->
        <dependency>
            <groupId>com.mysql</groupId>
            <artifactId>mysql-connector-j</artifactId>
            <scope>runtime</scope>
        </dependency>

        <!-- MyBatis-Plus -->
        <dependency>
            <groupId>com.baomidou</groupId>
            <artifactId>mybatis-plus-spring-boot3-starter</artifactId>
            <version>3.5.7</version>
        </dependency>

        <!-- JWT -->
        <dependency>
            <groupId>io.jsonwebtoken</groupId>
            <artifactId>jjwt-api</artifactId>
            <version>0.12.5</version>
        </dependency>
        <dependency>
            <groupId>io.jsonwebtoken</groupId>
            <artifactId>jjwt-impl</artifactId>
            <version>0.12.5</version>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>io.jsonwebtoken</groupId>
            <artifactId>jjwt-jackson</artifactId>
            <version>0.12.5</version>
            <scope>runtime</scope>
        </dependency>

        <!-- 密码加密 -->
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-crypto</artifactId>
        </dependency>

        <!-- Lombok -->
        <dependency>
            <groupId>org.projectlombok</groupId>
            <artifactId>lombok</artifactId>
            <optional>true</optional>
        </dependency>

        <!-- 测试 -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <configuration>
                    <excludes>
                        <exclude>
                            <groupId>org.projectlombok</groupId>
                            <artifactId>lombok</artifactId>
                        </exclude>
                    </excludes>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

---

## 9.4 application.yml

```yaml
server:
  port: 8080

spring:
  datasource:
    url: jdbc:mysql://localhost:3306/study_tracker?useSSL=false&serverTimezone=Asia/Shanghai&characterEncoding=utf-8
    username: root
    password: ${DB_PASSWORD:root}
    driver-class-name: com.mysql.cj.jdbc.Driver

mybatis-plus:
  configuration:
    log-impl: org.apache.ibatis.logging.stdout.StdOutImpl
    map-underscore-to-camel-case: true
  global-config:
    db-config:
      id-type: auto

app:
  jwt:
    secret: ${JWT_SECRET:my-secret-key-that-is-at-least-256-bits-long-for-hs256}
    expiration: 86400000

logging:
  level:
    com.example.studytracker: DEBUG
```

---

## 9.5 数据库建表 SQL

```sql
CREATE DATABASE IF NOT EXISTS study_tracker DEFAULT CHARACTER SET utf8mb4;
USE study_tracker;

DROP TABLE IF EXISTS study_record;
DROP TABLE IF EXISTS user;

CREATE TABLE user (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password VARCHAR(100) NOT NULL,
    email VARCHAR(100),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE study_record (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    project VARCHAR(100) NOT NULL COMMENT '学习项目',
    start_time DATETIME NOT NULL,
    end_time DATETIME,
    status VARCHAR(20) NOT NULL DEFAULT 'STUDYING' COMMENT 'STUDYING/COMPLETED',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_id (user_id),
    INDEX idx_user_date (user_id, start_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

---

## 9.6 核心代码

### 9.6.1 启动类

```java
package com.example.studytracker;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StudyTrackerApplication {
    public static void main(String[] args) {
        SpringApplication.run(StudyTrackerApplication.class, args);
    }
}
```

### 9.6.2 统一返回结构

```java
package com.example.studytracker.common;

import lombok.Data;

@Data
public class Result<T> {
    private int code;
    private String message;
    private T data;

    private Result() {}

    public static <T> Result<T> success() { return success(null); }

    public static <T> Result<T> success(T data) {
        Result<T> r = new Result<>();
        r.code = 200;
        r.message = "success";
        r.data = data;
        return r;
    }

    public static <T> Result<T> error(int code, String message) {
        Result<T> r = new Result<>();
        r.code = code;
        r.message = message;
        return r;
    }
}
```

### 9.6.3 业务异常

```java
package com.example.studytracker.common;

import lombok.Getter;

@Getter
public class BusinessException extends RuntimeException {
    private final int code;
    public BusinessException(String message) { this(400, message); }
    public BusinessException(int code, String message) {
        super(message);
        this.code = code;
    }
}
```

### 9.6.4 全局异常处理

```java
package com.example.studytracker.common;

import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.*;

import java.util.stream.Collectors;

@Slf4j
@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public Result<Void> handleValidation(MethodArgumentNotValidException e) {
        String msg = e.getBindingResult().getFieldErrors().stream()
            .map(FieldError::getDefaultMessage)
            .collect(Collectors.joining(", "));
        return Result.error(400, msg);
    }

    @ExceptionHandler(BusinessException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public Result<Void> handleBusiness(BusinessException e) {
        return Result.error(e.getCode(), e.getMessage());
    }

    @ExceptionHandler(Exception.class)
    @ResponseStatus(HttpStatus.INTERNAL_SERVER_ERROR)
    public Result<Void> handleUnknown(Exception e) {
        log.error("未知异常", e);
        return Result.error(500, "服务器内部错误");
    }
}
```

### 9.6.5 Entity

```java
// User.java
package com.example.studytracker.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import java.time.LocalDateTime;

@Data
@TableName("user")
public class User {
    @TableId(type = IdType.AUTO)
    private Long id;
    private String username;
    private String password;
    private String email;
    private LocalDateTime createdAt;
}

// StudyRecord.java
package com.example.studytracker.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import java.time.LocalDateTime;

@Data
@TableName("study_record")
public class StudyRecord {
    @TableId(type = IdType.AUTO)
    private Long id;
    private Long userId;
    private String project;
    private LocalDateTime startTime;
    private LocalDateTime endTime;
    private String status;
    private LocalDateTime createdAt;
}
```

### 9.6.6 DTO 和 VO

```java
// LoginRequest.java
package com.example.studytracker.dto;

import jakarta.validation.constraints.NotBlank;
import lombok.Data;

@Data
public class LoginRequest {
    @NotBlank(message = "用户名不能为空")
    private String username;
    @NotBlank(message = "密码不能为空")
    private String password;
}

// RegisterRequest.java
package com.example.studytracker.dto;

import jakarta.validation.constraints.*;
import lombok.Data;

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

// StudyStartRequest.java
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

// LoginResponse.java
package com.example.studytracker.vo;

import lombok.Data;

@Data
public class LoginResponse {
    private String token;
    private Long userId;
    private String username;
}

// StudyRecordVO.java
package com.example.studytracker.vo;

import lombok.Data;
import java.time.LocalDateTime;

@Data
public class StudyRecordVO {
    private Long id;
    private String project;
    private LocalDateTime startTime;
    private LocalDateTime endTime;
    private Long duration;
    private String status;
}

// StatisticsVO.java
package com.example.studytracker.vo;

import lombok.Data;
import java.util.Map;

@Data
public class StatisticsVO {
    private long totalMinutes;
    private int totalRecords;
    private Map<String, Long> projectStats;
}
```

### 9.6.7 Mapper

```java
// UserMapper.java
package com.example.studytracker.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.example.studytracker.entity.User;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Select;

@Mapper
public interface UserMapper extends BaseMapper<User> {
    @Select("SELECT * FROM user WHERE username = #{username}")
    User selectByUsername(String username);
}

// StudyRecordMapper.java
package com.example.studytracker.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.example.studytracker.entity.StudyRecord;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Select;
import java.util.List;

@Mapper
public interface StudyRecordMapper extends BaseMapper<StudyRecord> {
    @Select("SELECT * FROM study_record WHERE user_id = #{userId} AND DATE(start_time) = CURDATE() ORDER BY start_time DESC")
    List<StudyRecord> selectTodayRecords(Long userId);
}
```

### 9.6.8 JWT 工具类

```java
package com.example.studytracker.util;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import javax.crypto.SecretKey;
import java.nio.charset.StandardCharsets;
import java.util.Date;

@Component
public class JwtUtil {

    @Value("${app.jwt.secret}")
    private String secret;

    @Value("${app.jwt.expiration}")
    private long expiration;

    private SecretKey getKey() {
        return Keys.hmacShaKeyFor(secret.getBytes(StandardCharsets.UTF_8));
    }

    public String generateToken(Long userId, String username) {
        Date now = new Date();
        return Jwts.builder()
            .subject(userId.toString())
            .claim("username", username)
            .issuedAt(now)
            .expiration(new Date(now.getTime() + expiration))
            .signWith(getKey())
            .compact();
    }

    public Long getUserIdFromToken(String token) {
        return Long.parseLong(parseToken(token).getSubject());
    }

    public boolean validateToken(String token) {
        try {
            parseToken(token);
            return true;
        } catch (Exception e) {
            return false;
        }
    }

    private Claims parseToken(String token) {
        return Jwts.parser().verifyWith(getKey()).build()
            .parseSignedClaims(token).getPayload();
    }
}
```

### 9.6.9 配置类

```java
// SecurityConfig.java
package com.example.studytracker.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

@Configuration
public class SecurityConfig {
    @Bean
    public PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }
}

// MyBatisPlusConfig.java
package com.example.studytracker.config;

import com.baomidou.mybatisplus.annotation.DbType;
import com.baomidou.mybatisplus.extension.plugins.MybatisPlusInterceptor;
import com.baomidou.mybatisplus.extension.plugins.inner.PaginationInnerInterceptor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MyBatisPlusConfig {
    @Bean
    public MybatisPlusInterceptor mybatisPlusInterceptor() {
        MybatisPlusInterceptor interceptor = new MybatisPlusInterceptor();
        interceptor.addInnerInterceptor(new PaginationInnerInterceptor(DbType.MYSQL));
        return interceptor;
    }
}

// WebConfig.java
package com.example.studytracker.config;

import com.example.studytracker.interceptor.AuthInterceptor;
import lombok.RequiredArgsConstructor;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
@RequiredArgsConstructor
public class WebConfig implements WebMvcConfigurer {
    private final AuthInterceptor authInterceptor;

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(authInterceptor)
            .addPathPatterns("/api/study/**")
            .excludePathPatterns("/api/auth/**", "/api/health");
    }
}
```

### 9.6.10 拦截器

```java
package com.example.studytracker.interceptor;

import com.example.studytracker.util.JwtUtil;
import jakarta.servlet.http.*;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;

@Component
@RequiredArgsConstructor
public class AuthInterceptor implements HandlerInterceptor {
    private final JwtUtil jwtUtil;

    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response,
                             Object handler) throws Exception {
        if ("OPTIONS".equalsIgnoreCase(request.getMethod())) return true;

        String authHeader = request.getHeader("Authorization");
        if (authHeader == null || !authHeader.startsWith("Bearer ")) {
            sendError(response, 401, "未登录");
            return false;
        }

        String token = authHeader.substring(7);
        if (!jwtUtil.validateToken(token)) {
            sendError(response, 401, "Token无效或已过期");
            return false;
        }

        request.setAttribute("userId", jwtUtil.getUserIdFromToken(token));
        return true;
    }

    private void sendError(HttpServletResponse response, int code, String msg) throws Exception {
        response.setStatus(code);
        response.setContentType("application/json;charset=UTF-8");
        response.getWriter().write("{\"code\":" + code + ",\"message\":\"" + msg + "\",\"data\":null}");
    }
}
```

### 9.6.11 Service

```java
// UserService.java
package com.example.studytracker.service;

import com.example.studytracker.dto.LoginRequest;
import com.example.studytracker.dto.RegisterRequest;
import com.example.studytracker.vo.LoginResponse;
import com.example.studytracker.vo.UserVO;

public interface UserService {
    UserVO register(RegisterRequest request);
    LoginResponse login(LoginRequest request);
}

// StudyService.java
package com.example.studytracker.service;

import com.example.studytracker.dto.StudyStartRequest;
import com.example.studytracker.vo.StatisticsVO;
import com.example.studytracker.vo.StudyRecordVO;
import com.baomidou.mybatisplus.core.metadata.IPage;
import java.util.List;

public interface StudyService {
    Long startStudy(StudyStartRequest request);
    void endStudy(Long recordId);
    List<StudyRecordVO> getTodayRecords(Long userId);
    IPage<StudyRecordVO> getRecordsPage(Long userId, int pageNum, int pageSize);
    StatisticsVO getStatistics(Long userId);
}
```

### 9.6.12 Service 实现

```java
// UserServiceImpl.java
package com.example.studytracker.service.impl;

import com.example.studytracker.common.BusinessException;
import com.example.studytracker.dto.LoginRequest;
import com.example.studytracker.dto.RegisterRequest;
import com.example.studytracker.entity.User;
import com.example.studytracker.mapper.UserMapper;
import com.example.studytracker.service.UserService;
import com.example.studytracker.util.JwtUtil;
import com.example.studytracker.vo.LoginResponse;
import com.example.studytracker.vo.UserVO;
import lombok.RequiredArgsConstructor;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;

@Service
@RequiredArgsConstructor
public class UserServiceImpl implements UserService {
    private final UserMapper userMapper;
    private final PasswordEncoder passwordEncoder;
    private final JwtUtil jwtUtil;

    @Override
    public UserVO register(RegisterRequest request) {
        if (userMapper.selectByUsername(request.getUsername()) != null) {
            throw new BusinessException("用户名已存在");
        }
        User user = new User();
        user.setUsername(request.getUsername());
        user.setPassword(passwordEncoder.encode(request.getPassword()));
        user.setEmail(request.getEmail());
        userMapper.insert(user);
        return toVO(user);
    }

    @Override
    public LoginResponse login(LoginRequest request) {
        User user = userMapper.selectByUsername(request.getUsername());
        if (user == null || !passwordEncoder.matches(request.getPassword(), user.getPassword())) {
            throw new BusinessException("用户名或密码错误");
        }
        LoginResponse resp = new LoginResponse();
        resp.setToken(jwtUtil.generateToken(user.getId(), user.getUsername()));
        resp.setUserId(user.getId());
        resp.setUsername(user.getUsername());
        return resp;
    }

    private UserVO toVO(User user) {
        UserVO vo = new UserVO();
        vo.setId(user.getId());
        vo.setUsername(user.getUsername());
        vo.setEmail(user.getEmail());
        return vo;
    }
}

// StudyServiceImpl.java
package com.example.studytracker.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.example.studytracker.common.BusinessException;
import com.example.studytracker.dto.StudyStartRequest;
import com.example.studytracker.entity.StudyRecord;
import com.example.studytracker.mapper.StudyRecordMapper;
import com.example.studytracker.service.StudyService;
import com.example.studytracker.vo.StatisticsVO;
import com.example.studytracker.vo.StudyRecordVO;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

@Slf4j
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
        log.info("用户 {} 开始学习 {}", request.getUserId(), request.getProject());
        return record.getId();
    }

    @Override
    public void endStudy(Long recordId) {
        StudyRecord record = studyRecordMapper.selectById(recordId);
        if (record == null) throw new BusinessException("学习记录不存在");
        if (!"STUDYING".equals(record.getStatus())) throw new BusinessException("该记录已结束");
        record.setEndTime(LocalDateTime.now());
        record.setStatus("COMPLETED");
        studyRecordMapper.updateById(record);
    }

    @Override
    public List<StudyRecordVO> getTodayRecords(Long userId) {
        return studyRecordMapper.selectTodayRecords(userId).stream()
            .map(this::toVO).collect(Collectors.toList());
    }

    @Override
    public IPage<StudyRecordVO> getRecordsPage(Long userId, int pageNum, int pageSize) {
        Page<StudyRecord> page = new Page<>(pageNum, pageSize);
        LambdaQueryWrapper<StudyRecord> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(StudyRecord::getUserId, userId)
               .orderByDesc(StudyRecord::getStartTime);
        IPage<StudyRecord> recordPage = studyRecordMapper.selectPage(page, wrapper);

        Page<StudyRecordVO> voPage = new Page<>(pageNum, pageSize, recordPage.getTotal());
        voPage.setRecords(recordPage.getRecords().stream().map(this::toVO).collect(Collectors.toList()));
        return voPage;
    }

    @Override
    public StatisticsVO getStatistics(Long userId) {
        LambdaQueryWrapper<StudyRecord> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(StudyRecord::getUserId, userId)
               .eq(StudyRecord::getStatus, "COMPLETED")
               .isNotNull(StudyRecord::getEndTime);
        List<StudyRecord> records = studyRecordMapper.selectList(wrapper);

        Map<String, Long> projectStats = records.stream()
            .collect(Collectors.groupingBy(StudyRecord::getProject,
                Collectors.summingLong(r -> Duration.between(r.getStartTime(), r.getEndTime()).toMinutes())));

        long totalMinutes = records.stream()
            .mapToLong(r -> Duration.between(r.getStartTime(), r.getEndTime()).toMinutes()).sum();

        StatisticsVO vo = new StatisticsVO();
        vo.setTotalMinutes(totalMinutes);
        vo.setTotalRecords(records.size());
        vo.setProjectStats(projectStats);
        return vo;
    }

    private StudyRecordVO toVO(StudyRecord r) {
        StudyRecordVO vo = new StudyRecordVO();
        vo.setId(r.getId());
        vo.setProject(r.getProject());
        vo.setStartTime(r.getStartTime());
        vo.setEndTime(r.getEndTime());
        vo.setStatus(r.getStatus());
        if (r.getEndTime() != null) {
            vo.setDuration(Duration.between(r.getStartTime(), r.getEndTime()).toMinutes());
        }
        return vo;
    }
}
```

### 9.6.13 Controller

```java
// AuthController.java
package com.example.studytracker.controller;

import com.example.studytracker.common.Result;
import com.example.studytracker.dto.LoginRequest;
import com.example.studytracker.dto.RegisterRequest;
import com.example.studytracker.service.UserService;
import com.example.studytracker.vo.LoginResponse;
import com.example.studytracker.vo.UserVO;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/auth")
@RequiredArgsConstructor
public class AuthController {
    private final UserService userService;

    @PostMapping("/register")
    public Result<UserVO> register(@Valid @RequestBody RegisterRequest request) {
        return Result.success(userService.register(request));
    }

    @PostMapping("/login")
    public Result<LoginResponse> login(@Valid @RequestBody LoginRequest request) {
        return Result.success(userService.login(request));
    }
}

// StudyController.java
package com.example.studytracker.controller;

import com.baomidou.mybatisplus.core.metadata.IPage;
import com.example.studytracker.common.Result;
import com.example.studytracker.dto.StudyStartRequest;
import com.example.studytracker.service.StudyService;
import com.example.studytracker.vo.StatisticsVO;
import com.example.studytracker.vo.StudyRecordVO;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;
import java.util.*;

@RestController
@RequestMapping("/api/study")
@RequiredArgsConstructor
public class StudyController {
    private final StudyService studyService;

    private Long getUserId(HttpServletRequest request) {
        return (Long) request.getAttribute("userId");
    }

    @PostMapping("/start")
    public Result<Long> startStudy(@Valid @RequestBody StudyStartRequest request) {
        return Result.success(studyService.startStudy(request));
    }

    @PostMapping("/end/{recordId}")
    public Result<Void> endStudy(@PathVariable Long recordId) {
        studyService.endStudy(recordId);
        return Result.success();
    }

    @GetMapping("/today")
    public Result<List<StudyRecordVO>> getTodayRecords(HttpServletRequest request) {
        return Result.success(studyService.getTodayRecords(getUserId(request)));
    }

    @GetMapping("/records")
    public Result<Map<String, Object>> getRecords(
        HttpServletRequest request,
        @RequestParam(defaultValue = "1") int page,
        @RequestParam(defaultValue = "10") int size
    ) {
        IPage<StudyRecordVO> pageResult = studyService.getRecordsPage(getUserId(request), page, size);
        Map<String, Object> map = new HashMap<>();
        map.put("list", pageResult.getRecords());
        map.put("total", pageResult.getTotal());
        map.put("page", pageResult.getCurrent());
        map.put("pageSize", pageResult.getSize());
        return Result.success(map);
    }

    @GetMapping("/statistics")
    public Result<StatisticsVO> getStatistics(HttpServletRequest request) {
        return Result.success(studyService.getStatistics(getUserId(request)));
    }
}
```

---

## 9.7 接口测试

### 9.7.1 注册

```bash
curl -X POST http://localhost:8080/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"123456","email":"alice@test.com"}'
```

```json
{"code":200,"message":"success","data":{"id":1,"username":"alice","email":"alice@test.com"}}
```

### 9.7.2 登录

```bash
curl -X POST http://localhost:8080/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"123456"}'
```

```json
{"code":200,"message":"success","data":{"token":"eyJhbG...","userId":1,"username":"alice"}}
```

### 9.7.3 开始学习

```bash
TOKEN="eyJhbG..."  # 替换为实际 token

curl -X POST http://localhost:8080/api/study/start \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"userId":1,"project":"Java"}'
```

```json
{"code":200,"message":"success","data":1}
```

### 9.7.4 结束学习

```bash
curl -X POST http://localhost:8080/api/study/end/1 \
  -H "Authorization: Bearer $TOKEN"
```

```json
{"code":200,"message":"success","data":null}
```

### 9.7.5 查询今日记录

```bash
curl http://localhost:8080/api/study/today \
  -H "Authorization: Bearer $TOKEN"
```

```json
{"code":200,"message":"success","data":[{"id":1,"project":"Java","startTime":"...","endTime":"...","duration":120,"status":"COMPLETED"}]}
```

### 9.7.6 分页查询

```bash
curl "http://localhost:8080/api/study/records?page=1&size=5" \
  -H "Authorization: Bearer $TOKEN"
```

### 9.7.7 统计

```bash
curl http://localhost:8080/api/study/statistics \
  -H "Authorization: Bearer $TOKEN"
```

```json
{"code":200,"message":"success","data":{"totalMinutes":120,"totalRecords":1,"projectStats":{"Java":120}}}
```

---

## 9.8 测试步骤

1. 启动 MySQL，创建数据库和表
2. 修改 `application.yml` 中的数据库密码
3. 运行 `mvn spring-boot:run`
4. 按 9.7 节顺序测试接口
5. 验证参数校验（传空 username 看返回 400）
6. 验证鉴权（不带 Token 访问 /api/study/today 看返回 401）

---

## 9.9 常见问题排查

**Q: 启动报错 "Access denied for user"**
A: 检查 application.yml 中的数据库用户名密码

**Q: 启动报错 "Unknown database"**
A: 先执行 `CREATE DATABASE study_tracker;`

**Q: 接口返回 401**
A: 检查 Authorization 头格式是否为 `Bearer xxx`

**Q: 接口返回 500**
A: 查看控制台异常堆栈，定位到自己的代码行

**Q: Token 过期**
A: 默认 24 小时，重新登录获取新 Token

---

## 9.10 本章速查表

| 接口 | 方法 | 路径 | 鉴权 |
|------|------|------|------|
| 注册 | POST | /api/auth/register | 否 |
| 登录 | POST | /api/auth/login | 否 |
| 开始学习 | POST | /api/study/start | 是 |
| 结束学习 | POST | /api/study/end/{id} | 是 |
| 今日记录 | GET | /api/study/today | 是 |
| 分页记录 | GET | /api/study/records?page=1&size=10 | 是 |
| 统计 | GET | /api/study/statistics | 是 |

---

## 9.11 是否需要深入学习

本章是**实战项目**，必须掌握。建议动手跑一遍完整流程，这是检验你前 8 章学习成果的最好方式。

**准备好了吗？** 继续阅读 [第十章：阅读陌生项目的方法 →](./java-reading-project)