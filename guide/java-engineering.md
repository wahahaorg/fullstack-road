# 第四部分：理解 Java 工程

## 4.1 本章目标

读完本章后，你应该能：

1. 理解 Maven 是什么，以及它和 npm/pnpm 的对应关系
2. 看懂 pom.xml 的结构
3. 理解 dependency 的 scope 和作用
4. 知道 Maven 生命周期各阶段做什么
5. 理解 Java 的 package 和 import 机制
6. 知道 jar 包是什么
7. 理解 application.yml 的基本结构
8. 看懂 Java 程序的日志和异常堆栈

---

## 4.2 为什么需要学习这一章

如果说前两章学的是"怎么写 Java 代码"，这一章学的是"怎么组织 Java 项目"。不学这一章，你看到别人的 Java 项目会一脸茫然——不知道 pom.xml 在干嘛，不知道为什么目录那么深，不知道怎么跑起来。

---

## 4.3 Maven 是什么

### 4.3.1 一句话类比

| Maven 概念 | npm/pnpm 类比 |
|-----------|--------------|
| Maven 本身 | npm / pnpm |
| pom.xml | package.json |
| 本地仓库 `~/.m2/repository/` | node_modules |
| Maven Central | npm registry |
| dependency | dependencies |
| plugin | devDependencies 中的构建工具 |

### 4.3.2 Maven 负责三件事

1. **依赖管理** — 下载 jar 包（相当于 npm install）
2. **构建** — 编译、测试、打包（相当于 npm run build）
3. **项目标准化** — 统一目录结构（npm 不强制项目结构，Maven 强制）

### 4.3.3 安装 Maven

```bash
# macOS
brew install maven

# 验证
mvn --version
```

---

## 4.4 pom.xml 怎么看

### 4.4.1 一个最小的 pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <!-- 项目坐标（唯一的身份标识） -->
    <groupId>com.example</groupId>      <!-- 组织名，类似 npm scope -->
    <artifactId>study-tracker</artifactId>  <!-- 项目名，类似 package name -->
    <version>0.0.1-SNAPSHOT</version>    <!-- 版本号 -->
    <packaging>jar</packaging>           <!-- 打包方式：jar / war -->

    <!-- 项目基本信息 -->
    <name>study-tracker</name>
    <description>学习时间记录系统</description>

    <!-- 属性配置 -->
    <properties>
        <java.version>17</java.version>
    </properties>
</project>
```

### 4.4.2 对比 package.json

```json
{
    "name": "@example/study-tracker",   // groupId + artifactId
    "version": "0.0.1",                // version
    "description": "学习时间记录系统"
}
```

### 4.4.3 项目坐标（GAV）

Maven 用三个坐标唯一确定一个项目：

- **groupId** — 组织或公司域名倒写（如 `com.example`、`org.springframework.boot`）
- **artifactId** — 项目名（如 `study-tracker`、`spring-boot-starter-web`）
- **version** — 版本号

这和 npm 的 `@scope/package-name@version` 是同一个概念。

---

## 4.5 dependency 是什么

### 4.5.1 添加依赖

```xml
<dependencies>
    <!-- Spring Boot Web 起步依赖 -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
        <version>3.2.0</version>
    </dependency>

    <!-- MySQL 驱动 -->
    <dependency>
        <groupId>com.mysql</groupId>
        <artifactId>mysql-connector-j</artifactId>
        <version>8.2.0</version>
        <scope>runtime</scope>  <!-- 运行时才需要 -->
    </dependency>

    <!-- Lombok：简化代码 -->
    <dependency>
        <groupId>org.projectlombok</groupId>
        <artifactId>lombok</artifactId>
        <version>1.18.30</version>
        <scope>provided</scope>  <!-- 编译时需要，不打入最终包 -->
    </dependency>

    <!-- 测试依赖 -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <version>3.2.0</version>
        <scope>test</scope>  <!-- 仅测试时使用 -->
    </dependency>
</dependencies>
```

**对比 npm：**

```bash
npm install express          # 相当于添加 dependency
npm install -D typescript    # 相当于 scope=provided（开发时用）
npm install -D jest          # 相当于 scope=test
```

### 4.5.2 dependency scope（依赖范围）

| scope | 含义 | npm 类比 | 什么时候用 |
|-------|------|----------|-----------|
| `compile`（默认） | 编译、测试、运行都需要 | `dependencies` | 大部分情况 |
| `runtime` | 编译不需要，运行需要 | `dependencies` | 数据库驱动 |
| `provided` | 编译和测试需要，运行不需要 | `devDependencies` | Lombok、Servlet API |
| `test` | 仅测试需要 | `devDependencies` | JUnit、Mockito |

### 4.5.3 依赖传递

Maven 会自动下载依赖的依赖（传递依赖），和 npm 一样。

但如果出现版本冲突，Maven 的规则是"最短路径优先"和"先声明优先"。

---

## 4.6 Maven 生命周期

### 4.6.1 三个标准生命周期

Maven 有三个独立的生命周期：

| 生命周期 | 用途 | 常用阶段 |
|----------|------|----------|
| **clean** | 清理项目 | `clean`：删除 target 目录 |
| **default** | 构建项目 | `compile`、`test`、`package`、`install` |
| **site** | 生成项目文档 | 很少用 |

### 4.6.2 default 生命周期关键阶段

```
validate → compile → test → package → verify → install → deploy
```

| 阶段 | 作用 | npm 类比 |
|------|------|----------|
| `compile` | 编译源代码 | `tsc` |
| `test` | 运行测试 | `npm test` |
| `package` | 打包（生成 jar 文件） | `npm run build` |
| `install` | 安装到本地仓库 | `npm link`（近似） |
| `deploy` | 部署到远程仓库 | `npm publish` |

**重要：** 执行后面的阶段会自动执行前面的阶段。比如 `mvn package` 会先执行 `compile` 和 `test`。

### 4.6.3 常用命令

```bash
mvn clean                    # 清空 target 目录
mvn compile                  # 编译
mvn test                     # 运行测试
mvn package                  # 打包成 jar
mvn clean package            # 清空 + 打包
mvn spring-boot:run          # 运行 Spring Boot 项目
mvn clean package -DskipTests  # 跳过测试打包
```

---

## 4.7 package 和 import

### 4.7.1 package

Java 的 `package` 是代码组织方式，和 TypeScript 的 namespace 或 Python 的 package 类似。

```java
// 文件：src/main/java/com/example/studytracker/controller/StudyController.java
package com.example.studytracker.controller;  // 声明所属包

public class StudyController {
    // ...
}
```

**规则：**
- package 名称必须和目录结构一致
- 约定使用反向域名格式（如 `com.example.studytracker`）
- 同一个包下的类可以直接互相访问（不需要 import）

### 4.7.2 import

```java
package com.example.studytracker.controller;

import com.example.studytracker.service.StudyService;  // 导入其他包的类
import java.util.List;                                   // 导入 JDK 的类
import java.util.*;                                      // 导入包下所有类（不推荐）

public class StudyController {
    private StudyService studyService;  // 使用导入的类
}
```

**对比：**

```typescript
// TypeScript
import { StudyService } from '../service/study.service';
```

```python
# Python
from service.study_service import StudyService
```

**Java 的 `import` 不是"导入文件"，而是"导入类"。** 它和 TypeScript 的 import 概念一致，但语法不同。

### 4.7.3 不需要 import 的情况

- 同一个 package 下的类
- `java.lang` 包下的类（如 `String`、`Integer`、`System`），自动导入

---

## 4.8 jar 包是什么

### 4.8.1 一句话

jar（Java Archive）就是 Java 的"打包产物"，本质上是一个 zip 文件，里面包含：

- 编译后的 `.class` 文件
- 资源文件（配置文件、图片等）
- `META-INF/MANIFEST.MF`（元数据）

### 4.8.2 类比

| 概念 | Java | Node.js | Python |
|------|------|---------|--------|
| 打包产物 | `.jar` | `dist/` 目录 | `.whl` 文件 |
| 可执行文件 | Spring Boot fat jar | `node dist/index.js` | `python -m app` |
| 依赖管理 | 打入 jar 或声明式 | `node_modules` | `site-packages` |

### 4.8.3 Spring Boot 的 fat jar

Spring Boot 打包时会把所有依赖（Tomcat、Spring、MySQL 驱动等）都打入一个 jar 包，称为 **fat jar**（或 uber jar）。

```bash
# 打包
mvn clean package

# 运行（不需要额外配置，直接 java -jar）
java -jar target/study-tracker-0.0.1-SNAPSHOT.jar
```

这和 Node.js 把依赖打入 `node_modules` 不同——Java 的 fat jar 是一个**单一文件**，可以直接部署。

---

## 4.9 Java 项目如何启动

### 4.9.1 启动类

```java
// 文件：src/main/java/com/example/studytracker/StudyTrackerApplication.java
package com.example.studytracker;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication  // 这个注解包含了三个注解：
                        // @Configuration、@EnableAutoConfiguration、@ComponentScan
public class StudyTrackerApplication {
    public static void main(String[] args) {
        SpringApplication.run(StudyTrackerApplication.class, args);
    }
}
```

**对比 NestJS：**

```typescript
// NestJS main.ts
import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module';

async function bootstrap() {
    const app = await NestFactory.create(AppModule);
    await app.listen(3000);
}
bootstrap();
```

### 4.9.2 三种启动方式

```bash
# 方式一：Maven 插件启动（开发时常用）
mvn spring-boot:run

# 方式二：打包后启动（生产环境）
mvn clean package
java -jar target/study-tracker-0.0.1-SNAPSHOT.jar

# 方式三：IDEA 中直接运行 main 方法（开发时最常用）
# 右键 StudyTrackerApplication.java → Run
```

---

## 4.10 环境变量和配置文件

### 4.10.1 application.yml 基础

```yaml
# 文件：src/main/resources/application.yml

# 服务器配置
server:
  port: 8080

# 数据库配置
spring:
  datasource:
    url: jdbc:mysql://localhost:3306/study_tracker
    username: root
    password: ${DB_PASSWORD:root}  # 环境变量优先，默认 root
    driver-class-name: com.mysql.cj.jdbc.Driver

# 自定义配置
app:
  jwt:
    secret: ${JWT_SECRET:my-secret-key}
    expiration: 86400000  # 24小时，单位毫秒
  python-agent:
    url: http://localhost:8000
    timeout: 30000
```

**对比：**

| 概念 | Java | Node.js | Python |
|------|------|---------|--------|
| 配置文件 | `application.yml` | `.env` + `config.ts` | `.env` + `config.py` |
| 环境变量 | `${DB_PASSWORD:root}` | `process.env.DB_PASSWORD` | `os.environ.get("DB_PASSWORD")` |
| 多环境 | `application-dev.yml` | `.env.development` | `config/dev.py` |

### 4.10.2 多环境配置

```
application.yml           # 公共配置
application-dev.yml       # 开发环境
application-prod.yml      # 生产环境
```

通过 `spring.profiles.active` 指定激活哪个：

```yaml
# application.yml
spring:
  profiles:
    active: dev  # 激活 application-dev.yml
```

或在启动时指定：

```bash
java -jar app.jar --spring.profiles.active=prod
```

### 4.10.3 在代码中读取配置

```java
// 方式一：@Value 注解（简单值）
@Value("${app.jwt.secret}")
private String jwtSecret;

// 方式二：@ConfigurationProperties（批量读取）
@ConfigurationProperties(prefix = "app.python-agent")
public class PythonAgentConfig {
    private String url;
    private int timeout;
    // getter / setter
}
```

---

## 4.11 日志和异常堆栈怎么看

### 4.11.1 Spring Boot 默认日志

Spring Boot 使用 SLF4J + Logback 作为日志框架：

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

@RestController
public class StudyController {
    private static final Logger log = LoggerFactory.getLogger(StudyController.class);

    @GetMapping("/api/study/today")
    public Result<?> getToday() {
        log.info("查询今日学习记录，用户ID：{}", getCurrentUserId());
        // ...
    }
}
```

**日志级别（从高到低）：**

```
ERROR > WARN > INFO > DEBUG > TRACE
```

**配置日志级别：**

```yaml
# application.yml
logging:
  level:
    com.example.studytracker: DEBUG    # 自己的代码 DEBUG
    org.springframework: WARN          # Spring 框架只输出 WARN 以上
```

### 4.11.2 看懂异常堆栈

```
2026-07-25 10:30:00.123 ERROR 12345 --- [nio-8080-exec-1] c.e.s.controller.StudyController        : 查询学习记录失败

java.lang.NullPointerException: Cannot invoke "String.length()" because "name" is null
    at com.example.studytracker.service.StudyService.getUserStudyTime(StudyService.java:45)  ← 根本原因
    at com.example.studytracker.controller.StudyController.getToday(StudyController.java:30)
    at java.base/jdk.internal.reflect.NativeMethodAccessorImpl.invoke0(Native Method)
    at org.springframework.web.method.support.InvocableHandlerMethod.doInvoke(...)
    ...
```

**阅读方法：**
1. 第一行是异常类型和消息
2. 找到第一个 **你自己的代码**（不是 JDK 或框架的），通常是问题根源
3. 上面例子中：`StudyService.java:45` 是出问题的地方
4. 从下往上看调用链，了解请求是如何到达出错位置的

### 4.11.3 对比日志

| 概念 | Java | Node.js | Python |
|------|------|---------|--------|
| 日志框架 | SLF4J + Logback | Winston / Pino | logging |
| 错误堆栈 | 异常堆栈（极其详细） | Error stack trace | Traceback |
| 日志格式 | 可配置（JSON、文本） | 可配置 | 可配置 |

---

## 4.12 完整示例：创建一个 Maven 项目

### 4.12.1 手动创建

```bash
# 创建目录结构
mkdir -p hello-maven/src/main/java/com/example
mkdir -p hello-maven/src/main/resources
mkdir -p hello-maven/src/test/java/com/example

# 创建 pom.xml
cat > hello-maven/pom.xml << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>hello-maven</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.source>17</maven.compiler.source>
        <maven.compiler.target>17</maven.compiler.target>
    </properties>

    <dependencies>
        <dependency>
            <groupId>com.google.code.gson</groupId>
            <artifactId>gson</artifactId>
            <version>2.10.1</version>
        </dependency>
    </dependencies>
</project>
EOF

# 创建 Main.java
cat > hello-maven/src/main/java/com/example/Main.java << 'EOF'
package com.example;

import com.google.gson.Gson;

public class Main {
    public static void main(String[] args) {
        Gson gson = new Gson();
        String json = gson.toJson(new Person("Alice", 25));
        System.out.println(json);
    }

    static class Person {
        String name;
        int age;
        Person(String name, int age) {
            this.name = name;
            this.age = age;
        }
    }
}
EOF

# 编译并运行
cd hello-maven
mvn compile
mvn exec:java -Dexec.mainClass="com.example.Main"
```

---

## 4.13 在 Spring Boot 项目中的实际位置

| 概念 | 实际位置 |
|------|----------|
| pom.xml | 项目根目录 |
| 启动类 | `src/main/java/.../XxxApplication.java` |
| 配置文件 | `src/main/resources/application.yml` |
| 编译产物 | `target/` |
| 日志输出 | 控制台 + `logs/` 目录（如果配置了文件输出） |

---

## 4.14 常见错误

### 错误一：依赖下载失败

```bash
# 症状：mvn compile 报错 "Could not resolve dependencies"
# 原因：网络问题或 Maven 仓库配置

# 解决：检查 ~/.m2/settings.xml 中的镜像配置
# 国内常用阿里云镜像：
```

```xml
<mirror>
    <id>aliyun</id>
    <mirrorOf>central</mirrorOf>
    <name>Aliyun Maven Mirror</name>
    <url>https://maven.aliyun.com/repository/public</url>
</mirror>
```

### 错误二：找不到主类

```bash
# 症状：java -jar target/app.jar 报错 "no main manifest attribute"
# 原因：没有配置打包插件

# 解决：在 pom.xml 添加 Spring Boot Maven Plugin
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
```

### 错误三：端口被占用

```bash
# 症状：启动报错 "Port 8080 was already in use"
# 解决：修改端口
```

```yaml
# application.yml
server:
  port: 8081
```

---

## 4.15 三道小练习

### 练习 1：pom.xml 解读

看下面的 pom.xml 片段，回答：

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>com.mysql</groupId>
    <artifactId>mysql-connector-j</artifactId>
    <scope>runtime</scope>
</dependency>
```

1. 第一个依赖的 scope 是什么？
2. 为什么 MySQL 驱动的 scope 是 runtime？
3. 这两个依赖对应的 npm 安装命令是什么？

### 练习 2：创建 Maven 项目

用命令行创建一个 Maven 项目，添加 Gson 依赖，写一个程序把 `Map<String, Object>` 转成 JSON 并打印。

### 练习 3：日志分析

下面是一段异常堆栈，找出问题出在哪个文件的哪一行：

```
java.lang.NullPointerException
    at com.example.service.UserService.getUser(UserService.java:32)
    at com.example.controller.UserController.getUser(UserController.java:18)
    at sun.reflect.NativeMethodAccessorImpl.invoke0(Native Method)
```

---

## 4.16 参考答案

### 练习 1

1. compile（默认）
2. 因为编译时不需要 MySQL 驱动类，运行时连接数据库才需要
3. `npm install spring-boot-starter-web` 和 `npm install mysql2`

### 练习 2

略（参考 4.12 节的完整示例）

### 练习 3

问题出在 `UserService.java` 的第 32 行，`UserController.java` 第 18 行调用了它。

---

## 4.17 本章速查表

| 概念 | 一句话 | npm 类比 |
|------|--------|----------|
| pom.xml | 项目配置文件 | package.json |
| dependency | 依赖声明 | dependencies |
| Maven Central | 中央仓库 | npm registry |
| `~/.m2/repository/` | 本地仓库 | node_modules |
| `mvn clean` | 清空构建产物 | `rm -rf dist/` |
| `mvn compile` | 编译 | `tsc` |
| `mvn package` | 打包成 jar | `npm run build` |
| jar | Java 打包产物 | dist/ 目录 |
| `java -jar app.jar` | 运行 Java 程序 | `node dist/index.js` |
| application.yml | 配置文件 | .env + config.ts |
| `@Value` | 读取配置 | `process.env.XXX` |

---

## 4.18 是否需要深入学习

本章内容**必须掌握**。pom.xml 和 Maven 生命周期是看懂任何 Java 项目的前提。

建议：

1. 实际创建一个 Maven 项目并跑通
2. 配置阿里云镜像加速依赖下载
3. 学会用 `mvn clean package` 和 `java -jar` 启动项目

**准备好了吗？** 继续阅读 [第五章：Spring Boot 入门 →](./java-springboot-intro)