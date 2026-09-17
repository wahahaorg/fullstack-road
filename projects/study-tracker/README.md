# Study Tracker 学习时间记录系统

> 对应教程章节：[Java 实战项目 — 学习时间记录系统](../../guide/java-project-practice.md)

基于 **Spring Boot 3 + Java 17 + MyBatis-Plus + MySQL 8 + JWT** 实现的企业级后端入门实战工程。

## 🎯 业务功能清单

1. **用户体系**：账号注册、BCrypt 密码哈希、JWT 无状态登录鉴权。
2. **学习追踪**：开始学习打卡、结束学习计时、记录自动持久化。
3. **记录查询**：今日学习打卡记录即时查询、历史记录分页与时间倒序排列。
4. **统计分析**：总学习时长与记录数汇总、按项目维度的分组分钟数统计（Stream API 聚合）。
5. **工程规范**：统一返回体 `Result<T>`、业务异常体系 `BusinessException`、全局拦截 `GlobalExceptionHandler`、DTO 参数校验。

## 📁 目录分层结构

```text
projects/study-tracker/
├── pom.xml                               # Maven 依赖配置 (Spring Boot 3.2, Java 17)
├── compose.yaml                          # Docker Compose 本地 MySQL 8.0 一键启动
├── README.md                             # 项目说明与接口测试指南
└── src/
    ├── main/
    │   ├── resources/
    │   │   ├── application.yml           # 服务端口、数据源、MyBatis-Plus 与 JWT 配置
    │   │   └── schema.sql                # 数据库建库建表与索引脚本
    │   └── java/com/example/studytracker/
    │       ├── StudyTrackerApplication.java  # 启动类
    │       ├── config/                   # MyBatis-Plus 分页、Security、Web 拦截器配置
    │       ├── common/                   # Result 统一响应、BusinessException、全局异常
    │       ├── controller/               # AuthController, StudyController
    │       ├── dto/                      # 接口入参请求体校验
    │       ├── vo/                       # 出参视图对象
    │       ├── entity/                   # User, StudyRecord 实体
    │       ├── mapper/                   # MyBatis-Plus 数据访问接口
    │       ├── service/                  # 业务接口与实现类
    │       ├── interceptor/              # JWT 请求拦截与上下文透传
    │       └── util/                     # JJWT 签名与验签工具
    └── test/                             # 自动化单元与集成测试
```

## 🚀 快速本地运行

### 1. 启动本地 MySQL 数据库

确保已安装并启动 Docker，在当前目录下执行：

```bash
docker compose up -d
```

Compose 会启动 MySQL 8.0 容器，并自动挂载执行 `schema.sql` 完成建库与建表。

### 2. 编译并启动 Spring Boot 应用

确保本地已安装 JDK 17 与 Maven 3.8+：

```bash
mvn clean compile
mvn spring-boot:run
```

应用启动成功后监听端口 `http://localhost:8080`。

## 🧪 接口测试流程 (cURL)

### 1. 用户注册
```bash
curl -X POST http://localhost:8080/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"developer","password":"password123","email":"dev@example.com"}'
```

### 2. 用户登录获取 JWT Token
```bash
curl -X POST http://localhost:8080/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"developer","password":"password123"}'
```

### 3. 开始学习打卡
```bash
TOKEN="<替换为登录返回的token>"

curl -X POST http://localhost:8080/api/study/start \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"userId":1,"project":"Spring Boot 实战"}'
```

### 4. 结束学习
```bash
RECORD_ID=1

curl -X POST http://localhost:8080/api/study/end/$RECORD_ID \
  -H "Authorization: Bearer $TOKEN"
```

### 5. 查询今日记录与聚合统计
```bash
# 今日打卡记录
curl -X GET http://localhost:8080/api/study/today \
  -H "Authorization: Bearer $TOKEN"

# 学习时长统计 (总时长、各项目分钟数汇总)
curl -X GET http://localhost:8080/api/study/statistics \
  -H "Authorization: Bearer $TOKEN"
```
