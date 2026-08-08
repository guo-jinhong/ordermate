# OrderMate 部署指南

## 部署组成

默认 Docker Compose 启动三个服务：

```text
mysql   MySQL 8
backend Spring Boot
agent   FastAPI Agent 与聊天前端
```

Redis 是可选外部依赖，默认 Compose 不启动。只有配置 `REDIS_URL` 后才启用会话和检查点持久化。

## 本地 Docker 部署

前置条件：Docker Desktop 或 Linux Docker Engine + Compose v2。

```powershell
docker compose up --build -d
docker compose ps
```

默认端口：

| 服务 | 容器端口 | 主机端口 |
| --- | ---: | ---: |
| MySQL | 3306 | 3307 |
| Java backend | 8080 | 8080 |
| Agent | 8000 | 8000 |

访问：

- <http://localhost:8000>
- <http://localhost:8000/docs>
- <http://localhost:8080/api/doc.html>

停止但保留数据：

```powershell
docker compose down
```

删除数据库卷并重新初始化：

```powershell
docker compose down -v
docker compose up --build -d
```

> `down -v` 是破坏性操作，只能用于确认可以丢弃数据的演示环境。

## 环境变量

复制示例：

```powershell
Copy-Item .env.docker.example .env
```

| 变量 | 默认值 | 生产要求 |
| --- | --- | --- |
| `MYSQL_ROOT_PASSWORD` | `123456` | 必须换成强密码 |
| `JWT_SECRET` | 本地演示值 | 必须换成长随机值 |
| `BACKEND_HOST_PORT` | `8080` | 通常不直接公网开放 |
| `AGENT_HOST_PORT` | `8000` | 由反向代理访问 |
| `AGENT_MODE` | `demo` | 按需求选择 demo/live |
| `OPENAI_API_KEY` | 空 | live 模式必填且不得提交 |
| `OPENAI_MODEL` | `gpt-5.4-mini` | 填写供应商当前可用模型名 |
| `OPENAI_BASE_URL` | 空 | DeepSeek 可使用兼容 API 地址 |
| `REDIS_URL` | 空 | 可选，必须能从 Agent 容器访问 |
| `CORS_ALLOWED_ORIGINS` | 空 | 生产 Java 服务必须配置明确域名 |

DeepSeek live 示例：

```dotenv
AGENT_MODE=live
OPENAI_API_KEY=真实Key
OPENAI_MODEL=供应商当前支持的模型名
OPENAI_BASE_URL=https://api.deepseek.com
```

不要把文档中的示例模型名当成长期固定值。上线前应以模型供应商控制台和 API 文档为准。

## 本地验证

```powershell
docker compose config --services
docker compose ps
Invoke-RestMethod http://localhost:8000/health
```

登录测试：

```powershell
$body = @{username='testuser'; password='password'} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:8000/auth/login -ContentType application/json -Body $body
```

日志：

```powershell
docker compose logs --tail 200 backend
docker compose logs --tail 200 agent
docker compose logs --tail 200 mysql
```

## 云服务器部署

建议最低演示配置：2 vCPU、4 GB 内存、40 GB 磁盘。服务器安装 Git、Docker Engine 和 Compose v2。

```bash
git clone https://github.com/guo-jinhong/ordermate.git
cd ordermate
cp .env.docker.example .env
nano .env
docker compose up --build -d
docker compose ps
```

安全组建议：

- 开放 80/443。
- SSH 22 仅允许可信来源。
- 不开放 3307、Redis、8000、8080；由反向代理访问应用。

## Nginx 与 SSE

示例 `/etc/nginx/sites-available/ordermate.conf`：

```nginx
server {
    listen 80;
    server_name your-domain.example;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
    }
}
```

验证并加载：

```bash
sudo nginx -t
sudo systemctl reload nginx
```

SSE 需要关闭代理缓冲，并给予足够读取超时。

## HTTPS

以 Certbot 为例：

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.example
sudo certbot renew --dry-run
```

## 更新部署

更新前先记录当前提交并备份数据库：

```bash
git rev-parse HEAD
docker compose exec mysql sh -c 'mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" ecommerce_db' > ecommerce_db.sql
git pull --ff-only
docker compose build
docker compose up -d
docker compose ps
```

备份文件含业务数据和密码摘要，应限制权限、加密保存且不得提交 Git。

## 回滚

如果新版本失败：

1. 查看 `docker compose logs` 确认问题。
2. 切回更新前记录的已知良好提交或镜像标签。
3. 重新执行 `docker compose build` 和 `up -d`。
4. 只有发生不兼容数据变更且确认必要时，才从备份恢复数据库。

当前项目尚未引入数据库迁移工具，因此正式生产化前应先增加 Flyway/Liquibase，避免依赖手工 SQL 回滚。

## 生产检查清单

- Java 与 Python 全量测试通过。
- Docker 冷启动和健康检查通过。
- `.env` 不在 Git 跟踪中。
- 默认数据库密码、JWT Secret 已替换。
- CORS 只允许正式域名。
- HTTPS 已启用。
- 数据库和调试端口未暴露公网。
- live 模式模型名、Key、配额和超时已验证。
- SSE 经过 Nginx 实际验证。
- 备份、恢复和回滚完成演练。
- 日志、录屏和截图没有暴露密钥或完整令牌。

## 常见问题

### 端口占用

在 `.env` 修改：

```dotenv
BACKEND_HOST_PORT=18080
AGENT_HOST_PORT=18000
```

### MySQL 初始化没有执行

初始化脚本只在 volume 为空时执行。演示环境确认可以丢弃数据后，使用 `docker compose down -v` 重建。

### Agent 无法访问 Java

容器内地址应为 `http://backend:8080/api`，不能使用 `localhost:8080`。

### live 模式缺少 Key

检查 `.env` 后运行：

```powershell
docker compose up --build -d agent
docker compose logs -f agent
```

### SSE 本地正常、代理后不流式

检查 Nginx 的 `proxy_buffering off`、`proxy_cache off` 和 `proxy_read_timeout`。

### Docker daemon 未启动

先启动 Docker Desktop，再运行 `docker info`。如果 `docker compose` 不可用，更新 Docker Desktop 或安装 Compose v2。
