# 第八部分：Java 调用 Python Agent 服务

## 8.1 本章目标

读完本章后，你应该能：

1. 理解 Java + Python 混合架构的设计动机
2. 用 `RestTemplate` 从 Java 发起 HTTP 请求调用 Python 服务
3. 处理超时、异常、日志记录
4. 设计统一错误码
5. 理解同步请求和异步任务的区别

---

## 8.2 为什么企业项目可能采用这种架构

**典型场景：**

```
用户请求 → Java Spring Boot（用户管理、权限、知识库、文档存储）
                ↓ HTTP 调用
           Python FastAPI（RAG、Agent、大模型调用）
                ↓ 返回任务ID
           Java 轮询任务状态 → 返回给前端
```

**为什么这样分：**

| 职责 | 用 Java | 用 Python |
|------|---------|-----------|
| 用户管理、权限 | ✅ Spring Security 生态成熟 | — |
| 数据库事务、ORM | ✅ MyBatis-Plus、JPA | — |
| 文件存储、文档管理 | ✅ 企业级文件处理 | — |
| 大模型调用、RAG | — | ✅ LangChain、LlamaIndex |
| Agent 编排 | — | ✅ LangGraph、CrewAI |
| 数据科学、NLP | — | ✅ numpy、pandas、transformers |

**结论：** Java 负责"企业级业务系统"，Python 负责"AI 能力"。两者通过 HTTP API 通信。

---

## 8.3 配置 RestTemplate

```java
// 文件：src/main/java/com/example/studytracker/config/RestTemplateConfig.java
package com.example.studytracker.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestTemplate;

@Configuration
public class RestTemplateConfig {

    @Bean
    public RestTemplate restTemplate() {
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(5000);   // 连接超时 5 秒
        factory.setReadTimeout(30000);     // 读取超时 30 秒（AI 可能较慢）
        return new RestTemplate(factory);
    }
}
```

**对比 Python 的 httpx：**

```python
# Python httpx
async with httpx.AsyncClient(timeout=30.0) as client:
    response = await client.post("http://python-service:8000/api/agent/chat")
```

---

## 8.4 Python Agent 服务配置

```yaml
# application.yml
app:
  python-agent:
    base-url: http://localhost:8000
    timeout: 30000
    endpoints:
      chat: /api/agent/chat
      task-status: /api/agent/task/{taskId}
```

```java
// 配置类
@Data
@Configuration
@ConfigurationProperties(prefix = "app.python-agent")
public class PythonAgentConfig {
    private String baseUrl;
    private int timeout;
    private Map<String, String> endpoints;
}
```

---

## 8.5 调用 Python 服务

### 8.5.1 定义请求和响应

```java
// 请求 DTO（发给 Python 的）
@Data
public class AgentChatRequest {
    private String question;
    private String knowledgeBaseId;
    private Long userId;
}

// 响应 DTO（Python 返回的）
@Data
public class AgentChatResponse {
    private String taskId;
    private String status;  // "processing" / "completed" / "failed"
    private String answer;
    private String error;
}
```

### 8.5.2 封装调用服务

```java
// 文件：src/main/java/com/example/studytracker/service/AgentService.java
package com.example.studytracker.service;

import com.example.studytracker.common.BusinessException;
import com.example.studytracker.config.PythonAgentConfig;
import com.example.studytracker.dto.AgentChatRequest;
import com.example.studytracker.dto.AgentChatResponse;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.*;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestTemplate;

import java.util.Map;

@Slf4j
@Service
@RequiredArgsConstructor
public class AgentService {

    private final RestTemplate restTemplate;
    private final PythonAgentConfig config;

    /**
     * 向 Python Agent 发起对话请求
     * 返回任务 ID，前端通过轮询获取结果
     */
    public AgentChatResponse chat(AgentChatRequest request) {
        String url = config.getBaseUrl() + config.getEndpoints().get("chat");

        // 构建请求头
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);

        // 构建请求体
        HttpEntity<AgentChatRequest> entity = new HttpEntity<>(request, headers);

        long startTime = System.currentTimeMillis();
        try {
            log.info("调用 Python Agent: url={}, question={}", url, request.getQuestion());

            ResponseEntity<AgentChatResponse> response = restTemplate.postForEntity(
                url, entity, AgentChatResponse.class
            );

            long elapsed = System.currentTimeMillis() - startTime;
            log.info("Python Agent 响应: taskId={}, 耗时={}ms",
                response.getBody() != null ? response.getBody().getTaskId() : "null", elapsed);

            if (response.getBody() == null) {
                throw new BusinessException("Agent 服务返回空响应");
            }

            return response.getBody();
        } catch (RestClientException e) {
            long elapsed = System.currentTimeMillis() - startTime;
            log.error("调用 Python Agent 失败: url={}, 耗时={}ms", url, elapsed, e);
            throw new BusinessException(503, "AI 服务暂时不可用，请稍后重试");
        }
    }

    /**
     * 查询任务状态
     */
    public AgentChatResponse getTaskStatus(String taskId) {
        String endpoint = config.getEndpoints().get("task-status");
        String url = config.getBaseUrl() + endpoint.replace("{taskId}", taskId);

        try {
            ResponseEntity<AgentChatResponse> response = restTemplate.getForEntity(
                url, AgentChatResponse.class
            );
            return response.getBody();
        } catch (RestClientException e) {
            log.error("查询任务状态失败: taskId={}", taskId, e);
            throw new BusinessException("查询任务状态失败");
        }
    }
}
```

---

## 8.6 Controller 层

```java
@RestController
@RequestMapping("/api/agent")
@RequiredArgsConstructor
public class AgentController {

    private final AgentService agentService;

    @PostMapping("/chat")
    public Result<AgentChatResponse> chat(@RequestBody AgentChatRequest request) {
        AgentChatResponse response = agentService.chat(request);
        return Result.success(response);
    }

    @GetMapping("/task/{taskId}")
    public Result<AgentChatResponse> getTaskStatus(@PathVariable String taskId) {
        AgentChatResponse response = agentService.getTaskStatus(taskId);
        return Result.success(response);
    }
}
```

---

## 8.7 同步请求 vs 异步任务

### 8.7.1 问题

AI 模型调用可能需要 10-30 秒，如果 Java 同步等待，会阻塞线程：

```java
// ❌ 同步等待：如果 Python 处理 30 秒，Java 线程也阻塞 30 秒
@PostMapping("/chat-sync")
public Result<AgentChatResponse> chatSync(@RequestBody AgentChatRequest request) {
    return Result.success(agentService.chatSync(request));  // 阻塞 30 秒
}
```

### 8.7.2 解决方案一：异步任务模式

Python 返回任务 ID，Java 立即返回，前端轮询：

```java
// Java 立即返回任务 ID
@PostMapping("/chat")
public Result<AgentChatResponse> chat(@RequestBody AgentChatRequest request) {
    AgentChatResponse response = agentService.chat(request);  // 快速返回 taskId
    return Result.success(response);
}

// 前端轮询这个接口
@GetMapping("/task/{taskId}")
public Result<AgentChatResponse> getTaskStatus(@PathVariable String taskId) {
    return Result.success(agentService.getTaskStatus(taskId));
}
```

**前端轮询代码：**

```javascript
async function chat(question) {
    // 1. 发起对话
    const { taskId } = await fetch('/api/agent/chat', {
        method: 'POST',
        body: JSON.stringify({ question, knowledgeBaseId: 'kb-1' })
    }).then(r => r.json()).then(d => d.data);

    // 2. 轮询任务状态
    while (true) {
        await sleep(2000);  // 每 2 秒查一次
        const result = await fetch(`/api/agent/task/${taskId}`)
            .then(r => r.json()).then(d => d.data);

        if (result.status === 'completed') return result.answer;
        if (result.status === 'failed') throw new Error(result.error);
    }
}
```

### 8.7.3 解决方案二：Java 异步

```java
@PostMapping("/chat-async")
public Result<String> chatAsync(@RequestBody AgentChatRequest request) {
    CompletableFuture.runAsync(() -> {
        try {
            AgentChatResponse response = agentService.chatSync(request);
            // 结果存入数据库或通过 WebSocket 推送
            saveResult(response);
        } catch (Exception e) {
            log.error("异步任务失败", e);
        }
    });
    return Result.success("任务已提交");
}
```

---

## 8.8 统一错误码设计

```java
// 文件：src/main/java/com/example/studytracker/common/ErrorCode.java
public class ErrorCode {
    // 通用错误
    public static final int SUCCESS = 200;
    public static final int BAD_REQUEST = 400;
    public static final int UNAUTHORIZED = 401;
    public static final int FORBIDDEN = 403;
    public static final int NOT_FOUND = 404;
    public static final int INTERNAL_ERROR = 500;

    // 业务错误
    public static final int USER_NOT_FOUND = 1001;
    public static final int PASSWORD_ERROR = 1002;
    public static final int RECORD_NOT_FOUND = 2001;

    // AI 服务错误
    public static final int AI_SERVICE_UNAVAILABLE = 5001;
    public static final int AI_TASK_TIMEOUT = 5002;
    public static final int AI_TASK_FAILED = 5003;
}
```

---

## 8.9 调用日志记录

```java
@Slf4j
@Service
public class AgentService {

    private void logCall(String url, AgentChatRequest request, long startTime,
                         AgentChatResponse response, Exception error) {
        long elapsed = System.currentTimeMillis() - startTime;
        if (error != null) {
            log.error("Agent调用失败 | url={} | question={} | 耗时={}ms | 错误={}",
                url, request.getQuestion(), elapsed, error.getMessage());
        } else {
            log.info("Agent调用成功 | url={} | taskId={} | 耗时={}ms",
                url, response.getTaskId(), elapsed);
        }
    }
}
```

---

## 8.10 本章速查表

| 操作 | 代码 |
|------|------|
| 发送 POST | `restTemplate.postForEntity(url, entity, ResponseType.class)` |
| 发送 GET | `restTemplate.getForEntity(url, ResponseType.class)` |
| 设置超时 | `SimpleClientHttpRequestFactory` |
| 异步执行 | `CompletableFuture.runAsync(() -> { ... })` |
| 调用日志 | `log.info("调用耗时={}ms", elapsed)` |
| 异常处理 | `catch (RestClientException e)` |

---

## 8.11 是否需要深入学习

本章标记为"看懂即可"。理解 Java 调用 Python 的架构模式即可，具体代码可以借助 AI 生成。

**准备好了吗？** 继续阅读 [第九章：实战项目 →](./java-project-practice)