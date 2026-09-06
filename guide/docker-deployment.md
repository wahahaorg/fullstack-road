---
title: Docker 与部署
---

# Docker 与部署

> 前端转后端必须跨过的坎——不是代码写完就结束，而是能把它跑在服务器上。

## Docker 是什么？为什么后端必须学？

Docker 把应用和它的运行环境打包成一个**镜像**，镜像启动后成为**容器**。

```
应用代码 + 运行时 + 系统依赖 + 配置文件 = 镜像 → 容器
```

**前端开发者容易理解的角度：**
- 过去："在我电脑上能跑啊" — 环境不一致导致问题
- Docker 后：镜像在哪台机器跑都一样

---

## 写一个 Node.js 应用的 Dockerfile

```dockerfile
# 多阶段构建（推荐）

# 第一阶段：安装依赖 + 构建
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY . .

# 第二阶段：最小运行镜像
FROM node:20-alpine
WORKDIR /app
# 从 builder 阶段只复制需要的文件
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/package.json ./

EXPOSE 3000
CMD ["node", "dist/main.js"]
```

**多阶段构建的好处：**
- 最终镜像只包含运行时需要的文件（不包含构建工具、源码等）
- 镜像体积从 1GB+ 缩小到 100-200MB
- 减少攻击面

### Python FastAPI 的 Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# 安装系统依赖（如果有需要编译的 Python 包）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### NestJS 的 Dockerfile

```dockerfile
# 构建阶段
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# 运行阶段
FROM node:20-alpine
WORKDIR /app
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./
EXPOSE 3000
CMD ["node", "dist/main.js"]
```

### .dockerignore（防止把不需要的文件打包进镜像）

```text
node_modules
.git
.gitignore
.env
.env.local
*.md
.vscode
.idea
dist              # 如果使用多阶段构建，构建阶段会生成
__pycache__
*.pyc
.venv
.pytest_cache
```

---

## docker-compose：多容器编排

```yaml
# docker-compose.yml
version: '3.8'

services:
  app:
    build: .
    ports:
      - "3000:3000"
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_started
    environment:
      - NODE_ENV=production
      - DB_HOST=db
      - REDIS_HOST=redis
    volumes:
      - uploads:/app/uploads

  db:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: ${DB_PASSWORD}
      MYSQL_DATABASE: app
    ports:
      - "3306:3306"
    volumes:
      - mysql_data:/var/lib/mysql
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]
      interval: 5s
      timeout: 3s

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

volumes:
  mysql_data:
  redis_data:
  uploads:
```

启动：`docker-compose up -d`
查看日志：`docker-compose logs -f app`
停止并清理：`docker-compose down -v`

---

## nginx 反向代理

```nginx
# nginx.conf
server {
    listen 80;
    server_name api.example.com;

    # HTTPS 重定向（推荐用 Certbot 自动配置）
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name api.example.com;

    ssl_certificate /etc/letsencrypt/live/api.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.example.com/privkey.pem;

    # API 代理到 NestJS / FastAPI
    location /api/ {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket 支持
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    # 静态文件
    location /uploads/ {
        alias /var/www/app/uploads/;
        expires 30d;
    }
}
```

---

## 部署工作流（GitHub Actions）

```yaml
# .github/workflows/deploy.yml
name: Deploy

on:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
      - run: npm ci
      - run: npm run lint
      - run: npm run test

  deploy:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build and push Docker image
        run: |
          docker build -t app:${{ github.sha }} .
          # 推送到镜像仓库（Docker Hub / GitHub Container Registry）
          docker tag app:${{ github.sha }} ghcr.io/yourname/app:latest
          docker push ghcr.io/yourname/app:latest

      - name: Deploy to server
        uses: appleboy/ssh-action@v1.0.0
        with:
          host: ${{ secrets.HOST }}
          username: ${{ secrets.USERNAME }}
          key: ${{ secrets.SSH_KEY }}
          script: |
            cd /opt/app
            docker-compose pull
            docker-compose up -d
```

---

## 进程管理：PM2（Node 应用）

```bash
npm install -g pm2

# 启动
pm2 start dist/main.js --name my-app

# 常用命令
pm2 list              # 查看所有进程
pm2 logs              # 查看日志
pm2 monit             # 实时监控
pm2 restart my-app    # 重启
pm2 stop my-app       # 停止
pm2 delete my-app     # 删除

# 开机自启
pm2 startup
pm2 save
```

**PM2 配置 ecosystem.config.js：**

```js
module.exports = {
  apps: [{
    name: 'my-app',
    script: 'dist/main.js',
    instances: 'max',          // CPU 核数
    exec_mode: 'cluster',      // 集群模式
    env: {
      NODE_ENV: 'production',
    },
    max_memory_restart: '500M',
    error_file: './logs/err.log',
    out_file: './logs/out.log',
    merge_logs: true,
  }]
}
```

---

## 环境变量管理

### 开发环境

```bash
# .env
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=dev_password
JWT_SECRET=dev-secret-key-change-in-production

# .env.local（不提交 Git，覆盖 .env）
DB_PASSWORD=my-local-password
```

```bash
# .env.production（部署时手动配置，不建议提交 Git）
DB_HOST=production-db.example.com
```

### 后端读取

**NestJS**：`@nestjs/config`（`ConfigModule.forRoot()`）
**FastAPI**：`pydantic-settings`（`class Settings(BaseSettings)`）

**原则：**
- 代码不包含任何密钥
- `.env` 不提交 Git（加到 `.gitignore`）
- 生产密钥通过 CI/CD Secrets 或 云平台环境变量注入
- 本地开发使用 `.env.local`

---

## 健康检查接口

每台服务器都应该有：

```typescript
// NestJS
@Get('/health')
health() {
  return {
    status: 'ok',
    timestamp: new Date().toISOString(),
    uptime: process.uptime(),
    memory: process.memoryUsage(),
  }
}
```

```python
# FastAPI
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "uptime": time.time() - start_time,
    }
```

---

## 面试怎么说

> 我做的项目都用 Docker 容器化，写多阶段构建的 Dockerfile 减小镜像体积，用 docker-compose 编排后端服务、数据库和缓存。部署时用 nginx 做反向代理和 SSL 终结，Node 应用通过 PM2 做进程管理和集群模式。CI/CD 用 GitHub Actions，测试通过后自动构建镜像并部署到服务器。环境变量通过 `.env` + CI Secrets 分层管理，不提交到代码仓库。

---

## 面试问答

**1. 多阶段构建到底优化了什么？**

- builder 阶段装全量依赖、跑构建，最终镜像只从 builder `COPY --from` 运行时需要的文件（dist、node_modules、package.json）
- 最终镜像不含构建工具和源码，体积从 1GB+ 缩到 100-200MB，攻击面也小
- 配合 `.dockerignore` 排除 node_modules、.git、.env 等，避免把不需要的文件打进镜像，上下文更小、构建更快

**2. 从 push 到 main 到服务更新，CI/CD 链路经过哪几步？**

- 第一个 job 跑测试：`npm ci`、lint、test
- 第二个 job 构建镜像（tag 用 git sha）并推送到镜像仓库（GHCR / Docker Hub）
- 通过 SSH 到服务器执行 `docker-compose pull && docker-compose up -d` 拉新镜像重启
- 用 `needs: test` 保证测试不过不部署；服务器 host、用户名、SSH key 走 GitHub Secrets，不写进仓库

**3. 环境变量怎么分层管理？**

- `.env` 放基础配置，`.env.local` 本地覆盖且不提交 Git，`.env.production` 部署时手动配置、不建议提交 Git
- 原则是代码不包含任何密钥，生产密钥通过 CI/CD Secrets 或云平台环境变量注入
- Nest 用 `@nestjs/config` 的 `ConfigModule.forRoot()`，FastAPI 用 pydantic-settings 的 `BaseSettings`
- 别踩的坑：`.env` 一旦进了 Git 或被打进镜像，密钥就等于公开了，`.gitignore` 和 `.dockerignore` 都要覆盖它

**4. PM2 在这套部署里解决什么问题？**

- cluster 模式配 `instances: 'max'` 按 CPU 核数起多个进程，充分利用多核
- `max_memory_restart` 内存超限自动重启，进程挂了由 PM2 拉起
- `pm2 startup` + `pm2 save` 配置开机自启，服务器重启后服务自动恢复
- 加分：能说出日常运维命令——`pm2 logs` 看日志、`pm2 monit` 实时监控、`pm2 restart` 重启

**5. 为什么要加一层 nginx 反向代理，Node 直接对公网不行吗？**

- 证书（Let's Encrypt 的 fullchain.pem）和 443 监听放在 nginx，80 端口 301 跳转到 HTTPS
- 静态文件（如 `/uploads/`）由 nginx 直接 alias 返回并配 `expires 30d` 缓存，不占 Node 的事件循环
- 代理转发时带上 `X-Real-IP`、`X-Forwarded-For`、`X-Forwarded-Proto`，后端才能拿到真实客户端 IP 和协议
- 别踩的坑：WebSocket 代理必须加 `proxy_http_version 1.1` 和 `Upgrade` / `Connection "upgrade"` 两组头，否则握手升不了级
