# 第六部分：数据库基础

## 6.1 本章目标

读完本章后，你应该能：

1. 配置 Spring Boot 连接 MySQL
2. 使用 MyBatis-Plus 完成 Entity 到数据库表的映射
3. 实现基本的 CRUD 操作
4. 实现分页查询和条件查询
5. 理解 `@Transactional` 事务的基本用法
6. 排查常见数据库异常

---

## 6.2 为什么需要学习这一章

没有数据库，后端只能做"假"接口。这一章让你的数据真正持久化，是连接"接口"和"数据"的关键。

我们会用 **MyBatis-Plus**（而不是 JPA），因为它在国内企业中使用更广泛，且对 SQL 的控制更直接。

---

## 6.3 Spring Boot 连接 MySQL

### 6.3.1 添加依赖

```xml
<!-- pom.xml -->
<dependencies>
    <!-- MySQL 驱动 -->
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
</dependencies>
```

### 6.3.2 配置数据库连接

```yaml
# application.yml
spring:
  datasource:
    url: jdbc:mysql://localhost:3306/study_tracker?useSSL=false&serverTimezone=Asia/Shanghai&characterEncoding=utf-8
    username: root
    password: ${DB_PASSWORD:root}
    driver-class-name: com.mysql.cj.jdbc.Driver

mybatis-plus:
  configuration:
    log-impl: org.apache.ibatis.logging.stdout.StdOutImpl  # 打印 SQL（开发环境）
    map-underscore-to-camel-case: true  # 自动下划线转驼峰：user_id → userId
  global-config:
    db-config:
      id-type: auto  # 主键自增
```

**配置说明：**

| 配置项 | 作用 |
|--------|------|
| `url` | 数据库连接地址，`study_tracker` 是数据库名 |
| `useSSL=false` | 本地开发禁用 SSL |
| `serverTimezone` | 时区设置 |
| `log-impl` | 控制台打印 SQL，方便调试 |
| `map-underscore-to-camel-case` | 自动将 `user_id` 映射到 `userId` |

---

## 6.4 Entity 与数据库表

### 6.4.1 建表 SQL

```sql
-- 在 MySQL 中执行
CREATE DATABASE IF NOT EXISTS study_tracker DEFAULT CHARACTER SET utf8mb4;

USE study_tracker;

CREATE TABLE user (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password VARCHAR(100) NOT NULL,
    email VARCHAR(100),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE study_record (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    project VARCHAR(100) NOT NULL COMMENT '学习项目',
    start_time DATETIME NOT NULL,
    end_time DATETIME,
    status VARCHAR(20) NOT NULL DEFAULT 'STUDYING' COMMENT 'STUDYING/COMPLETED',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 6.4.2 Entity 类

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
    private LocalDateTime createdAt;
}
```

**MyBatis-Plus 注解：**

| 注解 | 作用 | 类比 TypeORM |
|------|------|-------------|
| `@TableName("表名")` | 指定表名 | `@Entity('表名')` |
| `@TableId(type = IdType.AUTO)` | 主键自增 | `@PrimaryGeneratedColumn()` |
| `@TableField("字段名")` | 指定字段名（通常不需要） | `@Column('字段名')` |
| `@TableField(exist = false)` | 这个字段不在数据库里 | — |

---

## 6.5 Mapper

### 6.5.1 Mapper 是什么

Mapper 是数据库操作接口。MyBatis-Plus 的 `BaseMapper` 已经提供了大部分 CRUD 方法，你只需要定义接口。

```java
// 文件：src/main/java/com/example/studytracker/mapper/StudyRecordMapper.java
package com.example.studytracker.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.example.studytracker.entity.StudyRecord;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Select;
import java.util.List;

@Mapper  // 告诉 Spring 这是一个 Mapper
public interface StudyRecordMapper extends BaseMapper<StudyRecord> {

    // MyBatis-Plus 自动提供的方法：
    // insert(T entity)          插入
    // deleteById(Serializable id) 按ID删除
    // updateById(T entity)      按ID更新
    // selectById(Serializable id) 按ID查询
    // selectList(Wrapper<T> wrapper) 条件查询
    // selectPage(Page<T> page, Wrapper<T> wrapper) 分页查询

    // 自定义查询：查询今日学习记录
    @Select("SELECT * FROM study_record WHERE user_id = #{userId} AND DATE(start_time) = CURDATE()")
    List<StudyRecord> selectTodayRecords(Long userId);
}
```

### 6.5.2 对比 TypeORM Repository

```typescript
// TypeORM
@Injectable()
export class StudyRecordRepository extends Repository<StudyRecord> {
    async findTodayRecords(userId: number): Promise<StudyRecord[]> {
        return this.find({
            where: { userId, startTime: Raw(alias => `DATE(${alias}) = CURDATE()`) }
        });
    }
}
```

**MyBatis-Plus 的 `BaseMapper` 已经是"开箱即用的 Repository"，** 不需要自己写 `findById`、`save` 等方法。

---

## 6.6 CRUD 操作

### 6.6.1 增（Insert）

```java
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
        studyRecordMapper.insert(record);  // MyBatis-Plus 自动生成 SQL
        return record.getId();  // 插入后 id 自动回填
    }
}
```

**生成的 SQL：**

```sql
INSERT INTO study_record (user_id, project, start_time, status)
VALUES (1, 'Java', '2026-07-25 10:00:00', 'STUDYING');
```

### 6.6.2 查（Select）

```java
// 按 ID 查询
StudyRecord record = studyRecordMapper.selectById(1L);

// 查询所有
List<StudyRecord> all = studyRecordMapper.selectList(null);

// 条件查询（见 6.7 节）
```

### 6.6.3 改（Update）

```java
@Override
public void endStudy(Long recordId) {
    StudyRecord record = studyRecordMapper.selectById(recordId);
    if (record == null) {
        throw new BusinessException("学习记录不存在");
    }
    record.setEndTime(LocalDateTime.now());
    record.setStatus("COMPLETED");
    studyRecordMapper.updateById(record);  // 按 ID 更新
}
```

**生成的 SQL：**

```sql
UPDATE study_record SET end_time = '2026-07-25 12:00:00', status = 'COMPLETED'
WHERE id = 1;
```

### 6.6.4 删（Delete）

```java
// 按 ID 删除
studyRecordMapper.deleteById(1L);

// 条件删除
LambdaQueryWrapper<StudyRecord> wrapper = new LambdaQueryWrapper<>();
wrapper.eq(StudyRecord::getStatus, "STUDYING");
studyRecordMapper.delete(wrapper);
```

---

## 6.7 条件查询

### 6.7.1 QueryWrapper 基础

MyBatis-Plus 用 `QueryWrapper` 构建查询条件，不需要写 SQL：

```java
// 查询某用户的所有学习记录
LambdaQueryWrapper<StudyRecord> wrapper = new LambdaQueryWrapper<>();
wrapper.eq(StudyRecord::getUserId, userId)  // 等于
       .orderByDesc(StudyRecord::getStartTime);  // 按时间倒序
List<StudyRecord> records = studyRecordMapper.selectList(wrapper);
```

### 6.7.2 常用条件

| 方法 | 含义 | 示例 |
|------|------|------|
| `eq` | 等于 = | `eq(StudyRecord::getStatus, "COMPLETED")` |
| `ne` | 不等于 != | `ne(StudyRecord::getStatus, "DELETED")` |
| `gt` | 大于 > | `gt(StudyRecord::getStartTime, date)` |
| `ge` | 大于等于 >= | `ge(StudyRecord::getStartTime, date)` |
| `lt` | 小于 < | `lt(StudyRecord::getStartTime, date)` |
| `le` | 小于等于 <= | `le(StudyRecord::getStartTime, date)` |
| `like` | 模糊匹配 | `like(StudyRecord::getProject, "Java")` |
| `in` | 在集合中 | `in(StudyRecord::getStatus, list)` |
| `isNull` | 为 null | `isNull(StudyRecord::getEndTime)` |
| `isNotNull` | 不为 null | `isNotNull(StudyRecord::getEndTime)` |
| `orderByAsc` | 升序 | `orderByAsc(StudyRecord::getStartTime)` |
| `orderByDesc` | 降序 | `orderByDesc(StudyRecord::getStartTime)` |
| `between` | 在区间内 | `between(StudyRecord::getStartTime, start, end)` |

### 6.7.3 复杂查询示例

```java
// 查询某用户某天的已完成记录
public List<StudyRecord> getRecords(Long userId, LocalDate date) {
    LocalDateTime startOfDay = date.atStartOfDay();
    LocalDateTime endOfDay = date.plusDays(1).atStartOfDay();

    LambdaQueryWrapper<StudyRecord> wrapper = new LambdaQueryWrapper<>();
    wrapper.eq(StudyRecord::getUserId, userId)
           .eq(StudyRecord::getStatus, "COMPLETED")
           .between(StudyRecord::getStartTime, startOfDay, endOfDay)
           .orderByDesc(StudyRecord::getStartTime);

    return studyRecordMapper.selectList(wrapper);
}
```

---

## 6.8 分页查询

### 6.8.1 配置分页插件

```java
// 文件：src/main/java/com/example/studytracker/config/MyBatisPlusConfig.java
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
```

### 6.8.2 分页查询代码

```java
// Service 中
public IPage<StudyRecord> getRecordsPage(Long userId, int pageNum, int pageSize) {
    Page<StudyRecord> page = new Page<>(pageNum, pageSize);

    LambdaQueryWrapper<StudyRecord> wrapper = new LambdaQueryWrapper<>();
    wrapper.eq(StudyRecord::getUserId, userId)
           .orderByDesc(StudyRecord::getStartTime);

    return studyRecordMapper.selectPage(page, wrapper);
    // 返回的 IPage 包含：
    // .getRecords() → 当前页数据
    // .getTotal()   → 总记录数
    // .getPages()   → 总页数
    // .getCurrent() → 当前页码
    // .getSize()    → 每页大小
}
```

```java
// Controller 中
@GetMapping("/records")
public Result<Map<String, Object>> getRecords(
    @RequestParam Long userId,
    @RequestParam(defaultValue = "1") int page,
    @RequestParam(defaultValue = "10") int size
) {
    IPage<StudyRecord> pageResult = studyService.getRecordsPage(userId, page, size);

    Map<String, Object> result = new HashMap<>();
    result.put("list", pageResult.getRecords());
    result.put("total", pageResult.getTotal());
    result.put("page", pageResult.getCurrent());
    result.put("pageSize", pageResult.getSize());

    return Result.success(result);
}
```

**返回格式：**

```json
{
    "code": 200,
    "message": "success",
    "data": {
        "list": [{ "id": 1, "project": "Java", "startTime": "..." }],
        "total": 25,
        "page": 1,
        "pageSize": 10
    }
}
```

---

## 6.9 事务

### 6.9.1 什么是事务

事务保证一组数据库操作要么全部成功，要么全部失败。

```java
@Service
@RequiredArgsConstructor
public class StudyServiceImpl implements StudyService {

    @Transactional  // 这个方法的所有数据库操作在一个事务中
    @Override
    public void transferStudyRecord(Long fromUserId, Long toUserId, Long recordId) {
        StudyRecord record = studyRecordMapper.selectById(recordId);
        if (record == null || !record.getUserId().equals(fromUserId)) {
            throw new BusinessException("记录不属于该用户");
        }
        record.setUserId(toUserId);
        studyRecordMapper.updateById(record);  // 如果这步失败，日志不会插入

        // 记录转移日志
        TransferLog log = new TransferLog();
        log.setFromUserId(fromUserId);
        log.setToUserId(toUserId);
        log.setRecordId(recordId);
        transferLogMapper.insert(log);  // 如果这步失败，上面的更新也会回滚
    }
}
```

### 6.9.2 @Transactional 关键属性

```java
@Transactional(
    rollbackFor = Exception.class,  // 任何异常都回滚（默认只回滚 RuntimeException）
    propagation = Propagation.REQUIRED,  // 默认：加入已有事务或新建
    timeout = 30  // 超时 30 秒
)
```

### 6.9.3 事务失效的常见情况

```java
// ❌ 情况一：同类方法调用（不经过代理）
public void methodA() {
    this.methodB();  // 直接调用，@Transactional 不生效
}

@Transactional
public void methodB() { }

// ✅ 解决：注入自己，通过代理调用
@Autowired
private StudyService self;

public void methodA() {
    self.methodB();  // 通过代理调用，事务生效
}

// ❌ 情况二：异常被 catch 了
@Transactional
public void doSomething() {
    try {
        userMapper.insert(user);
        int x = 1 / 0;  // 异常
    } catch (Exception e) {
        log.error("出错了", e);  // 异常被吞了，事务不回滚！
    }
}

// ✅ 解决：catch 后重新抛出，或手动回滚
@Transactional
public void doSomething() {
    try {
        userMapper.insert(user);
        int x = 1 / 0;
    } catch (Exception e) {
        log.error("出错了", e);
        TransactionAspectSupport.currentTransactionStatus().setRollbackOnly();
        throw new BusinessException("操作失败");
    }
}
```

---

## 6.10 数据库异常排查

### 6.10.1 常见错误及解决

**错误一：连接被拒绝**

```
java.sql.SQLException: Access denied for user 'root'@'localhost'
```

**解决：** 检查 `application.yml` 中的用户名密码是否正确。

**错误二：数据库不存在**

```
java.sql.SQLSyntaxErrorException: Unknown database 'study_tracker'
```

**解决：** 先创建数据库 `CREATE DATABASE study_tracker;`

**错误三：表不存在**

```
java.sql.SQLSyntaxErrorException: Table 'study_tracker.study_record' doesn't exist
```

**解决：** 执行建表 SQL。

**错误四：时区问题**

```
The server time zone value '???±??????' is unrecognized
```

**解决：** 在 URL 中添加 `serverTimezone=Asia/Shanghai`

**错误五：字段映射不上**

```
org.apache.ibatis.binding.BindingException: Invalid bound statement
```

**解决：** 检查 `@MapperScan` 或 `@Mapper` 注解是否正确。

### 6.10.2 调试 SQL

开启 SQL 日志：

```yaml
mybatis-plus:
  configuration:
    log-impl: org.apache.ibatis.logging.stdout.StdOutImpl
```

控制台输出：

```
==>  Preparing: SELECT * FROM study_record WHERE user_id = ? AND DATE(start_time) = CURDATE()
==> Parameters: 1(Long)
<==      Total: 3
```

---

## 6.11 完整示例

```java
// Service 完整实现
@Service
@RequiredArgsConstructor
@Slf4j
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
        if (record == null) {
            throw new BusinessException("学习记录不存在");
        }
        if (!"STUDYING".equals(record.getStatus())) {
            throw new BusinessException("该记录已结束");
        }
        record.setEndTime(LocalDateTime.now());
        record.setStatus("COMPLETED");
        studyRecordMapper.updateById(record);
    }

    @Override
    public List<StudyRecordVO> getTodayRecords(Long userId) {
        List<StudyRecord> records = studyRecordMapper.selectTodayRecords(userId);
        return records.stream().map(this::toVO).collect(Collectors.toList());
    }

    @Override
    public IPage<StudyRecordVO> getRecordsPage(Long userId, int pageNum, int pageSize) {
        Page<StudyRecord> page = new Page<>(pageNum, pageSize);

        LambdaQueryWrapper<StudyRecord> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(StudyRecord::getUserId, userId)
               .orderByDesc(StudyRecord::getStartTime);

        IPage<StudyRecord> recordPage = studyRecordMapper.selectPage(page, wrapper);

        // 转换为 VO 分页
        Page<StudyRecordVO> voPage = new Page<>(pageNum, pageSize, recordPage.getTotal());
        voPage.setRecords(recordPage.getRecords().stream().map(this::toVO).collect(Collectors.toList()));
        return voPage;
    }

    @Override
    public Map<String, Object> getStatistics(Long userId) {
        LambdaQueryWrapper<StudyRecord> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(StudyRecord::getUserId, userId)
               .eq(StudyRecord::getStatus, "COMPLETED");

        List<StudyRecord> records = studyRecordMapper.selectList(wrapper);

        // 按项目统计
        Map<String, Long> projectStats = records.stream()
            .collect(Collectors.groupingBy(
                StudyRecord::getProject,
                Collectors.summingLong(r ->
                    Duration.between(r.getStartTime(), r.getEndTime()).toMinutes()
                )
            ));

        // 总时长
        long totalMinutes = records.stream()
            .mapToLong(r -> Duration.between(r.getStartTime(), r.getEndTime()).toMinutes())
            .sum();

        Map<String, Object> result = new HashMap<>();
        result.put("totalMinutes", totalMinutes);
        result.put("totalRecords", records.size());
        result.put("projectStats", projectStats);
        return result;
    }

    private StudyRecordVO toVO(StudyRecord record) {
        StudyRecordVO vo = new StudyRecordVO();
        vo.setId(record.getId());
        vo.setProject(record.getProject());
        vo.setStartTime(record.getStartTime());
        vo.setEndTime(record.getEndTime());
        vo.setStatus(record.getStatus());
        if (record.getEndTime() != null) {
            vo.setDuration(Duration.between(record.getStartTime(), record.getEndTime()).toMinutes());
        }
        return vo;
    }
}
```

---

## 6.12 三道小练习

### 练习 1：CRUD

写一个 `UserService`，实现用户的增删改查：
- `createUser(RegisterRequest request)` — 创建用户
- `getUserById(Long id)` — 查询用户
- `updateEmail(Long id, String email)` — 更新邮箱
- `deleteUser(Long id)` — 删除用户

### 练习 2：条件查询

用 `LambdaQueryWrapper` 查询"已完成"且"学习时长超过 60 分钟"的记录。

### 练习 3：事务

写一个 `@Transactional` 方法，创建用户的同时创建一条默认学习记录，如果任一步失败，两步都回滚。

---

## 6.13 参考答案

### 练习 1

```java
@Service
@RequiredArgsConstructor
public class UserServiceImpl implements UserService {
    private final UserMapper userMapper;

    @Override
    public Long createUser(RegisterRequest request) {
        User user = new User();
        user.setUsername(request.getUsername());
        user.setPassword(request.getPassword());
        user.setEmail(request.getEmail());
        userMapper.insert(user);
        return user.getId();
    }

    @Override
    public User getUserById(Long id) {
        return userMapper.selectById(id);
    }

    @Override
    public void updateEmail(Long id, String email) {
        User user = userMapper.selectById(id);
        if (user == null) throw new BusinessException("用户不存在");
        user.setEmail(email);
        userMapper.updateById(user);
    }

    @Override
    public void deleteUser(Long id) {
        userMapper.deleteById(id);
    }
}
```

### 练习 2

```java
LambdaQueryWrapper<StudyRecord> wrapper = new LambdaQueryWrapper<>();
wrapper.eq(StudyRecord::getStatus, "COMPLETED")
       .apply("TIMESTAMPDIFF(MINUTE, start_time, end_time) > 60");
```

### 练习 3

```java
@Transactional
public Long createUserWithRecord(RegisterRequest request) {
    User user = new User();
    user.setUsername(request.getUsername());
    user.setPassword(request.getPassword());
    userMapper.insert(user);

    StudyRecord record = new StudyRecord();
    record.setUserId(user.getId());
    record.setProject("默认项目");
    record.setStartTime(LocalDateTime.now());
    record.setStatus("STUDYING");
    studyRecordMapper.insert(record);

    return user.getId();
}
```

---

## 6.14 本章速查表

| 操作 | 代码 |
|------|------|
| 插入 | `mapper.insert(entity)` |
| 按ID查 | `mapper.selectById(id)` |
| 按ID改 | `mapper.updateById(entity)` |
| 按ID删 | `mapper.deleteById(id)` |
| 条件查询 | `mapper.selectList(wrapper)` |
| 分页 | `mapper.selectPage(page, wrapper)` |
| 事务 | `@Transactional` |
| 等于条件 | `wrapper.eq(Entity::getField, value)` |

---

## 6.15 是否需要深入学习

本章内容**必须掌握**。CRUD 和分页是日常开发的核心。

跳过：复杂 SQL 优化、分库分表、读写分离（这些是高级话题，需要时再学）。

**准备好了吗？** 继续阅读 [第七章：登录与接口鉴权 →](./java-auth)