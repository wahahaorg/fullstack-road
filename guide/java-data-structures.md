---
title: 第三部分：Java 常用数据结构
---

# 第三部分：Java 常用数据结构

## 3.1 本章目标

读完本章后，你应该能：

1. 使用 Array、ArrayList、HashSet、HashMap 处理日常数据
2. 用 for-each、Iterator、Lambda 三种方式遍历集合
3. 用 Stream API 替代 for 循环做过滤、映射、分组、聚合
4. 用 Optional 优雅地处理可能为 null 的值
5. 面对同一组需求，能分别用 JavaScript、Python、Java 写出来

---

## 3.2 为什么需要学习这一章

数据结构是日常编码中使用频率最高的知识。Java 的集合框架比 JS 和 Python 更"重"，但设计也更严谨。

本章的独特之处：**同一组需求，三种语言对比展示**，让你直观感受差异。

---

## 3.3 Array（数组）

### 3.3.1 基本用法

```java
// 声明并初始化
int[] numbers = {1, 2, 3, 4, 5};
String[] names = {"Alice", "Bob", "Charlie"};

// 先声明再赋值
int[] scores = new int[3];  // 长度固定为 3
scores[0] = 90;
scores[1] = 85;
scores[2] = 95;

// 访问
System.out.println(names[0]);     // Alice
System.out.println(numbers.length); // 5（注意是 length，不是 length()）
```

**对比：**

```typescript
// TypeScript
const numbers: number[] = [1, 2, 3, 4, 5];
console.log(numbers.length);  // length 是属性
```

```python
# Python
numbers = [1, 2, 3, 4, 5]
print(len(numbers))  # len() 是函数
```

**Java 数组的限制：** 长度固定，创建后不能增减元素。日常开发中，90% 的情况用 `ArrayList` 而不是数组。

### 3.3.2 数组 vs ArrayList

| | Array | ArrayList |
|------|-------|-----------|
| 长度 | 固定 | 动态 |
| 语法 | `int[] arr = new int[3];` | `List<Integer> list = new ArrayList<>();` |
| 访问 | `arr[0]` | `list.get(0)` |
| 修改 | `arr[0] = 1;` | `list.set(0, 1);` |
| 添加 | 不支持 | `list.add(1);` |
| 删除 | 不支持 | `list.remove(0);` |
| 长度 | `arr.length` | `list.size()` |

---

## 3.4 List（ArrayList）

### 3.4.1 基本操作

```java
import java.util.ArrayList;
import java.util.List;

List<String> names = new ArrayList<>();

// 添加
names.add("Alice");
names.add("Bob");
names.add("Charlie");

// 访问
String first = names.get(0);  // Alice

// 修改
names.set(1, "Bobby");  // Bob → Bobby

// 删除
names.remove(0);         // 删除索引 0
names.remove("Charlie"); // 删除值为 "Charlie" 的元素

// 判断
boolean hasAlice = names.contains("Alice");
boolean isEmpty = names.isEmpty();
int size = names.size();
```

### 3.4.2 快速初始化

```java
// Java 9+
List<String> names = List.of("Alice", "Bob", "Charlie");  // 不可变

// 需要可变列表
List<String> names = new ArrayList<>(List.of("Alice", "Bob", "Charlie"));

// 传统方式（Java 8）
List<String> names = Arrays.asList("Alice", "Bob", "Charlie");
```

**注意：** `List.of()` 创建的列表不可变，不能 add/remove。`Arrays.asList()` 创建的列表长度固定，不能 add/remove 但可以 set。

### 3.4.3 遍历方式对比

```java
List<String> names = List.of("Alice", "Bob", "Charlie");

// 方式一：for-i（传统）
for (int i = 0; i < names.size(); i++) {
    System.out.println(names.get(i));
}

// 方式二：for-each（推荐）
for (String name : names) {
    System.out.println(name);
}

// 方式三：forEach + Lambda（Java 8+）
names.forEach(name -> System.out.println(name));

// 方式四：方法引用（最简洁）
names.forEach(System.out::println);
```

---

## 3.5 Set（HashSet）

Set 是无序、不重复的集合。

```java
import java.util.HashSet;
import java.util.Set;

Set<String> tags = new HashSet<>();
tags.add("Java");
tags.add("Spring");
tags.add("Java");  // 重复，不会添加
tags.add("MySQL");

System.out.println(tags.size());  // 3
System.out.println(tags);         // [Java, MySQL, Spring]（顺序不保证）

// 判断存在
boolean hasJava = tags.contains("Java");  // true

// 删除
tags.remove("MySQL");
```

**对比：**

```typescript
// TypeScript
const tags = new Set<string>();
tags.add("Java");
tags.add("Spring");
tags.add("Java");  // 重复，不会添加
console.log(tags.size);  // 3
```

```python
# Python
tags = set()
tags.add("Java")
tags.add("Spring")
tags.add("Java")  # 重复，不会添加
print(len(tags))  # 3
```

---

## 3.6 Map（HashMap）

### 3.6.1 基本操作

```java
import java.util.HashMap;
import java.util.Map;

Map<String, Integer> scores = new HashMap<>();

// 添加/修改
scores.put("Alice", 90);
scores.put("Bob", 85);
scores.put("Charlie", 95);

// 访问
int aliceScore = scores.get("Alice");  // 90
Integer bobScore = scores.get("Bob");  // 85（Integer 可以为 null）

// 安全的访问
Integer unknownScore = scores.get("Unknown");  // null
int score = scores.getOrDefault("Unknown", 0);  // 0

// 判断
boolean hasAlice = scores.containsKey("Alice");
boolean hasPerfect = scores.containsValue(100);

// 删除
scores.remove("Bob");

// 大小
int size = scores.size();  // 2
```

### 3.6.2 遍历 Map

```java
Map<String, Integer> scores = Map.of("Alice", 90, "Bob", 85, "Charlie", 95);

// 遍历 key
for (String name : scores.keySet()) {
    System.out.println(name);
}

// 遍历 value
for (Integer score : scores.values()) {
    System.out.println(score);
}

// 遍历 entry（最常用）
for (Map.Entry<String, Integer> entry : scores.entrySet()) {
    System.out.println(entry.getKey() + ": " + entry.getValue());
}

// Lambda 方式
scores.forEach((name, score) -> {
    System.out.println(name + ": " + score);
});
```

### 3.6.3 三种语言对比

**同一组数据：**

```typescript
// TypeScript
const scores = new Map<string, number>();
scores.set("Alice", 90);
scores.set("Bob", 85);
scores.set("Charlie", 95);

// 访问
const alice = scores.get("Alice");  // 90
const unknown = scores.get("Unknown");  // undefined

// 遍历
scores.forEach((score, name) => console.log(name, score));
```

```python
# Python
scores = {}
scores["Alice"] = 90
scores["Bob"] = 85
scores["Charlie"] = 95

# 访问
alice = scores["Alice"]  # 90
unknown = scores.get("Unknown")  # None（不会报错）
unknown = scores.get("Unknown", 0)  # 0

# 遍历
for name, score in scores.items():
    print(name, score)
```

```java
// Java
Map<String, Integer> scores = new HashMap<>();
scores.put("Alice", 90);
scores.put("Bob", 85);
scores.put("Charlie", 95);

// 访问
Integer alice = scores.get("Alice");  // 90
Integer unknown = scores.get("Unknown");  // null
int safe = scores.getOrDefault("Unknown", 0);  // 0

// 遍历
scores.forEach((name, score) -> System.out.println(name + ": " + score));
```

---

## 3.7 Lambda 表达式

### 3.7.1 什么是 Lambda

Lambda 是 Java 8 引入的语法，让你可以用简洁的方式写匿名函数。

```java
// 传统写法：匿名内部类
Runnable task = new Runnable() {
    @Override
    public void run() {
        System.out.println("Hello");
    }
};

// Lambda 写法
Runnable task = () -> System.out.println("Hello");
```

**Lambda 语法：**

```java
(参数) -> { 函数体 }
// 或
(参数) -> 表达式
```

**对比箭头函数：**

```typescript
// TypeScript
const task = () => console.log("Hello");
const add = (a: number, b: number) => a + b;
```

```python
# Python
task = lambda: print("Hello")
add = lambda a, b: a + b
```

### 3.7.2 常见 Lambda 用法

```java
// 单参数：括号可省略
name -> System.out.println(name)

// 多参数：括号不能省略
(a, b) -> a + b

// 多行：需要大括号和 return
(a, b) -> {
    int result = a + b;
    return result;
}

// 方法引用：比 Lambda 更简洁
System.out::println       // 等价于 x -> System.out.println(x)
String::toUpperCase       // 等价于 s -> s.toUpperCase()
Math::max                 // 等价于 (a, b) -> Math.max(a, b)
```

---

## 3.8 Stream API

Stream 是 Java 8 最重要的特性。它让你用声明式的方式处理集合数据，替代大量 for 循环。

### 3.8.1 核心概念

Stream 不是数据结构，而是**数据处理的流水线**。它和 JavaScript 的 `map`/`filter`/`reduce` 理念完全一致。

```java
// 传统写法
List<String> result = new ArrayList<>();
for (String name : names) {
    if (name.startsWith("A")) {
        result.add(name.toUpperCase());
    }
}

// Stream 写法
List<String> result = names.stream()
    .filter(name -> name.startsWith("A"))
    .map(String::toUpperCase)
    .collect(Collectors.toList());
```

### 3.8.2 中间操作 vs 终端操作

**中间操作**（返回 Stream，可以链式调用）：

| 操作 | 作用 | JS 类比 | Python 类比 |
|------|------|---------|------------|
| `filter` | 过滤 | `Array.filter()` | `filter()` |
| `map` | 转换 | `Array.map()` | `map()` |
| `sorted` | 排序 | `Array.sort()` | `sorted()` |
| `distinct` | 去重 | `[...new Set(arr)]` | `set()` |
| `limit` | 截取前 n 个 | `Array.slice(0, n)` | `[:n]` |
| `skip` | 跳过前 n 个 | `Array.slice(n)` | `[n:]` |
| `peek` | 调试查看 | 无直接对应 | 无直接对应 |

**终端操作**（触发计算，返回最终结果）：

| 操作 | 作用 | JS 类比 |
|------|------|---------|
| `collect(Collectors.toList())` | 收集为 List | `Array.from()` |
| `collect(Collectors.toSet())` | 收集为 Set | `new Set(arr)` |
| `collect(Collectors.toMap(...))` | 收集为 Map | `Object.fromEntries()` |
| `count()` | 计数 | `Array.length` |
| `findFirst()` | 找第一个 | `Array.find()` |
| `findAny()` | 找任意一个 | — |
| `anyMatch(...)` | 是否有匹配 | `Array.some()` |
| `allMatch(...)` | 是否全部匹配 | `Array.every()` |
| `noneMatch(...)` | 是否全不匹配 | — |
| `forEach(...)` | 遍历 | `Array.forEach()` |
| `reduce(...)` | 聚合 | `Array.reduce()` |
| `max(...)` / `min(...)` | 最大/最小 | `Math.max(...arr)` |

### 3.8.3 完整示例：同一组需求，三种语言

**准备数据：** 学习记录列表，每条记录包含用户名、学习项目、学习时长（分钟）。

```java
// Java 数据类
public class StudyRecord {
    private String user;
    private String project;
    private int minutes;

    public StudyRecord(String user, String project, int minutes) {
        this.user = user;
        this.project = project;
        this.minutes = minutes;
    }

    public String getUser() { return user; }
    public String getProject() { return project; }
    public int getMinutes() { return minutes; }

    @Override
    public String toString() {
        return user + " - " + project + ": " + minutes + "min";
    }
}

// 测试数据
List<StudyRecord> records = List.of(
    new StudyRecord("Alice", "Java", 90),
    new StudyRecord("Alice", "Spring", 45),
    new StudyRecord("Alice", "Java", 120),
    new StudyRecord("Bob", "Python", 60),
    new StudyRecord("Bob", "Java", 30),
    new StudyRecord("Charlie", "Python", 75),
    new StudyRecord("Charlie", "Spring", 60),
    new StudyRecord("Charlie", "Java", 150)
);
```

```typescript
// TypeScript 数据
interface StudyRecord {
    user: string;
    project: string;
    minutes: number;
}

const records: StudyRecord[] = [
    { user: "Alice", project: "Java", minutes: 90 },
    { user: "Alice", project: "Spring", minutes: 45 },
    { user: "Alice", project: "Java", minutes: 120 },
    { user: "Bob", project: "Python", minutes: 60 },
    { user: "Bob", project: "Java", minutes: 30 },
    { user: "Charlie", project: "Python", minutes: 75 },
    { user: "Charlie", project: "Spring", minutes: 60 },
    { user: "Charlie", project: "Java", minutes: 150 },
];
```

```python
# Python 数据
from dataclasses import dataclass

@dataclass
class StudyRecord:
    user: str
    project: str
    minutes: int

records = [
    StudyRecord("Alice", "Java", 90),
    StudyRecord("Alice", "Spring", 45),
    StudyRecord("Alice", "Java", 120),
    StudyRecord("Bob", "Python", 60),
    StudyRecord("Bob", "Java", 30),
    StudyRecord("Charlie", "Python", 75),
    StudyRecord("Charlie", "Spring", 60),
    StudyRecord("Charlie", "Java", 150),
]
```

**需求 1：过滤学习时长超过 60 分钟的记录**

```java
// Java
List<StudyRecord> longRecords = records.stream()
    .filter(r -> r.getMinutes() > 60)
    .collect(Collectors.toList());
// 结果：Alice-Java:90, Alice-Java:120, Charlie-Python:75, Charlie-Java:150
```

```typescript
// TypeScript
const longRecords = records.filter(r => r.minutes > 60);
```

```python
# Python
long_records = [r for r in records if r.minutes > 60]
```

**需求 2：提取所有用户姓名，去重**

```java
// Java
Set<String> users = records.stream()
    .map(StudyRecord::getUser)
    .collect(Collectors.toSet());
// 结果：[Alice, Bob, Charlie]
```

```typescript
// TypeScript
const users = [...new Set(records.map(r => r.user))];
```

```python
# Python
users = {r.user for r in records}
```

**需求 3：按用户分组，计算每人总学习时长**

```java
// Java
Map<String, Integer> totalByUser = records.stream()
    .collect(Collectors.groupingBy(
        StudyRecord::getUser,
        Collectors.summingInt(StudyRecord::getMinutes)
    ));
// 结果：{Alice=255, Bob=90, Charlie=285}
```

```typescript
// TypeScript
const totalByUser = records.reduce((acc, r) => {
    acc[r.user] = (acc[r.user] || 0) + r.minutes;
    return acc;
}, {} as Record<string, number>);
```

```python
# Python
from collections import defaultdict
total_by_user = defaultdict(int)
for r in records:
    total_by_user[r.user] += r.minutes
```

**需求 4：找出学习时长最多的记录**

```java
// Java
StudyRecord maxRecord = records.stream()
    .max(Comparator.comparingInt(StudyRecord::getMinutes))
    .orElse(null);
// 结果：Charlie - Java: 150min
```

```typescript
// TypeScript
const maxRecord = records.reduce((max, r) =>
    r.minutes > max.minutes ? r : max
);
```

```python
# Python
max_record = max(records, key=lambda r: r.minutes)
```

**需求 5：按项目分组，统计每项的学习人数和总时长**

```java
// Java
Map<String, Long> peopleByProject = records.stream()
    .collect(Collectors.groupingBy(
        StudyRecord::getProject,
        Collectors.mapping(StudyRecord::getUser, Collectors.toSet())
    ))
    .entrySet().stream()
    .collect(Collectors.toMap(
        Map.Entry::getKey,
        e -> (long) e.getValue().size()
    ));

Map<String, Integer> totalByProject = records.stream()
    .collect(Collectors.groupingBy(
        StudyRecord::getProject,
        Collectors.summingInt(StudyRecord::getMinutes)
    ));
// 结果：
// peopleByProject: {Java=3, Spring=2, Python=2}
// totalByProject:  {Java=390, Spring=105, Python=135}
```

```typescript
// TypeScript
const peopleByProject = {} as Record<string, Set<string>>;
const totalByProject = {} as Record<string, number>;
for (const r of records) {
    (peopleByProject[r.project] ??= new Set()).add(r.user);
    totalByProject[r.project] = (totalByProject[r.project] || 0) + r.minutes;
}
// 转换为人数
const peopleCount = Object.fromEntries(
    Object.entries(peopleByProject).map(([k, v]) => [k, v.size])
);
```

```python
# Python
people_by_project = {}
total_by_project = defaultdict(int)
for r in records:
    people_by_project.setdefault(r.project, set()).add(r.user)
    total_by_project[r.project] += r.minutes
people_count = {k: len(v) for k, v in people_by_project.items()}
```

---

## 3.9 Optional

### 3.9.1 为什么需要 Optional

Java 中最常见的运行时错误是 `NullPointerException`。Optional 是一个容器，可能包含值，也可能为空，强迫你处理空值情况。

```java
// 不用 Optional：可能 NPE
User user = findUserById(1L);
String city = user.getAddress().getCity();  // 如果 address 为 null，NPE！

// 用 Optional：强制处理空值
Optional<User> userOpt = findUserById(1L);
String city = userOpt
    .map(User::getAddress)
    .map(Address::getCity)
    .orElse("未知");
```

### 3.9.2 Optional 常用方法

```java
// 创建 Optional
Optional<String> present = Optional.of("hello");      // 值不能为 null
Optional<String> nullable = Optional.ofNullable(x);    // 值可以为 null
Optional<String> empty = Optional.empty();             // 显式空

// 判断是否有值
if (optional.isPresent()) {
    String value = optional.get();
}

// 有值时执行操作
optional.ifPresent(value -> System.out.println(value));

// 有值时转换
Optional<Integer> length = optional.map(String::length);

// 有值时返回，否则返回默认值
String value = optional.orElse("默认值");

// 有值时返回，否则调用函数生成默认值
String value = optional.orElseGet(() -> loadFromDatabase());

// 有值时返回，否则抛异常
String value = optional.orElseThrow(() -> new RuntimeException("值不存在"));
```

### 3.9.3 实战：安全地访问嵌套对象

```java
// 假设有这样的对象链：User → Address → City → Name
// 传统写法：层层判空
public String getCityName(User user) {
    if (user != null) {
        Address address = user.getAddress();
        if (address != null) {
            City city = address.getCity();
            if (city != null) {
                return city.getName();
            }
        }
    }
    return "未知";
}

// Optional 写法：一行搞定
public String getCityName(User user) {
    return Optional.ofNullable(user)
        .map(User::getAddress)
        .map(Address::getCity)
        .map(City::getName)
        .orElse("未知");
}
```

### 3.9.4 类比 TypeScript

```typescript
// TypeScript 可选链（Optional Chaining）
const cityName = user?.address?.city?.name ?? "未知";

// 等价于 Java 的 Optional 链
```

TypeScript 的 `?.` 语法更简洁，但 Java 的 Optional 还可以做更多操作（如 `orElseThrow`、`filter` 等）。

### 3.9.5 Optional 使用原则

- ✅ 方法的返回值可以用 Optional
- ✅ Entity 的 getter 可以返回 Optional（如果字段可能为 null）
- ❌ 不要用 Optional 作为字段类型
- ❌ 不要用 Optional 作为方法参数
- ❌ 不要对 Optional 调用 `get()` 而不先检查 `isPresent()`

---

## 3.10 完整代码示例

```java
// 文件：DataStructureDemo.java
import java.util.*;
import java.util.stream.Collectors;

public class DataStructureDemo {

    public static class StudyRecord {
        private final String user;
        private final String project;
        private final int minutes;

        public StudyRecord(String user, String project, int minutes) {
            this.user = user;
            this.project = project;
            this.minutes = minutes;
        }

        public String getUser() { return user; }
        public String getProject() { return project; }
        public int getMinutes() { return minutes; }

        @Override
        public String toString() {
            return user + " - " + project + ": " + minutes + "min";
        }
    }

    public static void main(String[] args) {
        List<StudyRecord> records = List.of(
            new StudyRecord("Alice", "Java", 90),
            new StudyRecord("Alice", "Spring", 45),
            new StudyRecord("Alice", "Java", 120),
            new StudyRecord("Bob", "Python", 60),
            new StudyRecord("Bob", "Java", 30),
            new StudyRecord("Charlie", "Python", 75),
            new StudyRecord("Charlie", "Spring", 60),
            new StudyRecord("Charlie", "Java", 150)
        );

        // 1. 过滤
        List<StudyRecord> longRecords = records.stream()
            .filter(r -> r.getMinutes() > 60)
            .collect(Collectors.toList());
        System.out.println("1. 超过60分钟：" + longRecords);

        // 2. 去重用户
        Set<String> users = records.stream()
            .map(StudyRecord::getUser)
            .collect(Collectors.toSet());
        System.out.println("2. 用户列表：" + users);

        // 3. 按用户分组求和
        Map<String, Integer> totalByUser = records.stream()
            .collect(Collectors.groupingBy(
                StudyRecord::getUser,
                Collectors.summingInt(StudyRecord::getMinutes)
            ));
        System.out.println("3. 用户总时长：" + totalByUser);

        // 4. 学习时长最多的记录
        StudyRecord maxRecord = records.stream()
            .max(Comparator.comparingInt(StudyRecord::getMinutes))
            .orElse(null);
        System.out.println("4. 最长记录：" + maxRecord);

        // 5. 按项目分组统计
        Map<String, Long> peopleByProject = records.stream()
            .collect(Collectors.groupingBy(
                StudyRecord::getProject,
                Collectors.mapping(StudyRecord::getUser, Collectors.toSet())
            ))
            .entrySet().stream()
            .collect(Collectors.toMap(
                Map.Entry::getKey,
                e -> (long) e.getValue().size()
            ));
        System.out.println("5. 项目学习人数：" + peopleByProject);

        // 6. Optional 示例
        Optional<StudyRecord> found = records.stream()
            .filter(r -> r.getMinutes() > 200)
            .findFirst();
        String result = found
            .map(StudyRecord::toString)
            .orElse("没有超过200分钟的记录");
        System.out.println("6. " + result);
    }
}
```

**编译运行：**

```bash
javac DataStructureDemo.java
java DataStructureDemo
```

**输出：**

```
1. 超过60分钟：[Alice - Java: 90min, Alice - Java: 120min, Charlie - Python: 75min, Charlie - Java: 150min]
2. 用户列表：[Alice, Bob, Charlie]
3. 用户总时长：{Alice=255, Bob=90, Charlie=285}
4. 最长记录：Charlie - Java: 150min
5. 项目学习人数：{Java=3, Spring=2, Python=2}
6. 没有超过200分钟的记录
```

---

## 3.11 在 Spring Boot 项目中的实际位置

| 数据结构 | 在 Spring Boot 中的典型用法 |
|----------|--------------------------|
| `List<T>` | Controller 返回列表、Service 批量查询 |
| `Set<T>` | 去重、权限集合 |
| `Map<String, Object>` | 动态查询参数、配置项 |
| `Stream` | Service 层数据处理、DTO 转换 |
| `Optional` | Repository 返回值、Service 层安全访问 |
| `Collectors.groupingBy` | 统计报表、数据聚合 |
| `List.of()` | 常量列表、测试数据 |

---

## 3.12 常见错误

### 错误一：对空 Stream 的终端操作

```java
List<String> empty = List.of();
String first = empty.stream().findFirst().get();  // ❌ NoSuchElementException

// 正确：
String first = empty.stream().findFirst().orElse(null);
```

### 错误二：Stream 只能消费一次

```java
Stream<String> stream = names.stream();
stream.forEach(System.out::println);
stream.forEach(System.out::println);  // ❌ IllegalStateException: stream已被消费
```

### 错误三：Map 的 key 不存在

```java
Map<String, Integer> map = new HashMap<>();
int value = map.get("key");  // 返回 null，自动拆箱时 NPE！

// 正确：
int value = map.getOrDefault("key", 0);
```

### 错误四：在 Lambda 中修改外部变量

```java
int sum = 0;
List.of(1, 2, 3).forEach(n -> sum += n);  // ❌ 编译错误！Lambda 中变量必须是 final
```

---

## 3.13 三道小练习

### 练习 1：Stream 操作

给定 `List<Integer> numbers = List.of(1, 2, 3, 4, 5, 6, 7, 8, 9, 10);`

用 Stream 完成：
1. 过滤出偶数
2. 每个数乘以 2
3. 求和

### 练习 2：数据分组

给定学生成绩列表：`List<Score>`（包含 name 和 score 字段），用 Stream 按"及格（≥60）"和"不及格（<60）"分组。

### 练习 3：Optional 实战

写一个方法 `getUserEmail`，输入 `userId`，从模拟数据库查找用户，返回邮箱。如果用户不存在或邮箱为空，返回 `"no-email@example.com"`。

---

## 3.14 参考答案

### 练习 1

```java
int result = numbers.stream()
    .filter(n -> n % 2 == 0)  // 偶数
    .map(n -> n * 2)           // 乘2
    .reduce(0, Integer::sum);  // 求和
// 或用 .mapToInt(n -> n).sum()
// 结果：60
```

### 练习 2

```java
Map<Boolean, List<Score>> grouped = scores.stream()
    .collect(Collectors.partitioningBy(s -> s.getScore() >= 60));
// grouped.get(true)  → 及格列表
// grouped.get(false) → 不及格列表
```

### 练习 3

```java
public String getUserEmail(Long userId) {
    return Optional.ofNullable(findUserById(userId))
        .map(User::getEmail)
        .filter(email -> !email.isEmpty())
        .orElse("no-email@example.com");
}
```

---

## 3.15 本章速查表

| 操作 | Java | TypeScript | Python |
|------|------|------------|--------|
| 列表 | `List<String> list = new ArrayList<>();` | `const list: string[] = [];` | `list = []` |
| 添加 | `list.add("a");` | `list.push("a");` | `list.append("a")` |
| 访问 | `list.get(0)` | `list[0]` | `list[0]` |
| 长度 | `list.size()` | `list.length` | `len(list)` |
| 集合 | `Set<String> set = new HashSet<>();` | `const set = new Set<string>();` | `set()` |
| 字典 | `Map<String, Integer> map = new HashMap<>();` | `const map = new Map<string, number>();` | `{}` |
| 过滤 | `stream.filter(x -> x > 0)` | `arr.filter(x => x > 0)` | `[x for x in arr if x > 0]` |
| 映射 | `stream.map(x -> x * 2)` | `arr.map(x => x * 2)` | `[x * 2 for x in arr]` |
| 聚合 | `stream.reduce(0, Integer::sum)` | `arr.reduce((a, b) => a + b, 0)` | `sum(arr)` |
| 分组 | `Collectors.groupingBy(...)` | `Object.groupBy(arr, fn)` | `itertools.groupby()` |
| 空值安全 | `Optional.ofNullable(x).orElse(0)` | `x ?? 0` | `x or 0` |

---

## 3.16 是否需要深入学习

本章内容**必须掌握**。Stream 和 Optional 是 Java 日常开发的核心工具，会大量出现在 Spring Boot 项目的 Service 层。

建议：

1. 动手跑一遍 DataStructureDemo 完整代码
2. 完成三道练习
3. 重点掌握：Stream 的 filter/map/collect、Optional 的 map/orElse
4. 不要在第一次学习时追求 Stream 的所有用法，先掌握最常见的 5-6 个操作

**准备好了吗？** 继续阅读 [第四章：理解 Java 工程 →](./java-engineering)