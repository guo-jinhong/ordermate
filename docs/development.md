# 本地开发指南

## 环境要求

- Java 17
- Python 3.12
- MySQL 8
- Maven Wrapper（仓库已包含）
- 可选：Docker Desktop、Redis

只想体验项目时优先使用 [QUICKSTART.md](../QUICKSTART.md) 的 Docker 方式。本文件面向需要修改 Java 或 Python 代码的开发者。

## Java 后端

准备 `ecommerce_db`，并执行：

```powershell
mysql -u root -p < src/main/resources/sql/schema.sql
mysql -u root -p ecommerce_db < src/main/resources/sql/data.sql
.\mvnw.cmd spring-boot:run
```

默认地址：`http://localhost:8080/api`。

测试：

```powershell
.\mvnw.cmd test
```

生产 profile 通过 `DB_URL`、`DB_USERNAME`、`DB_PASSWORD`、`JWT_SECRET` 和 `CORS_ALLOWED_ORIGINS` 注入配置。

## Python Agent

```powershell
cd agent-service
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

运行单个测试：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_api.py -q
```

## Windows 本地启动

```powershell
.\start-dev-stack.ps1
```

也可双击根目录的 `一键启动Vue.bat`。临时公网演示使用 `一键启动公网.bat`，会构建 Vue 并启动 ngrok；普通本地模式不开放公网。

服务地址：Vue `http://localhost:5173`、Agent `http://localhost:8000`、Java `http://localhost:8080/api`、MySQL `localhost:3306`。`start-dev-stack.ps1` 支持 `-Mode`、`-PublicDemo`、`-NoBrowser` 和 `-NoPause` 参数；公网快捷命令已自动传入所需参数。

密码和模型 Key 应放在未跟踪的 `.env` 中。停止时关闭对应的服务窗口；公网模式还要关闭 ngrok 窗口。

## Agent 环境变量

| 变量 | 默认值 | 敏感 | 说明 |
| --- | --- | --- | --- |
| `AGENT_MODE` | `auto` | 否 | `demo`、`live` 或 `auto` |
| `EMBEDDING_API_KEY` | 空 | 否 | 独立 Embedding 服务凭据；不得默认复用聊天 Key |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | 否 | Embedding 服务实际支持的模型名 |
| `EMBEDDING_BASE_URL` | 空 | 否 | 独立 Embedding 服务地址 |
| `OPENAI_API_KEY` | 空 | 是 | live 模式模型 Key |
| `OPENAI_MODEL` | `gpt-5.4-mini` | 否 | 模型服务支持的模型名 |
| `OPENAI_BASE_URL` | 空 | 否 | OpenAI-compatible API 地址 |
| `ECOMMERCE_API_BASE_URL` | `http://localhost:8080/api` | 否 | Java API 地址 |
| `REQUEST_TIMEOUT_SECONDS` | `15` | 否 | 后端/模型请求超时 |
| `MAX_TOOL_ROUNDS` | `5` | 否 | 最大工具调用轮数 |
| `REDIS_URL` | 空 | 可能 | 可选 Redis 连接串 |
| `CONVERSATION_MAX_MESSAGES` | `12` | 否 | 会话消息上限 |
| `CONVERSATION_TTL_SECONDS` | `1800` | 否 | 会话保留秒数 |
| `DB_TYPE` | `sqlite` | 否 | Agent 知识数据适配类型 |
| `SQLITE_PATH` | `agent_service_dev.db` | 否 | SQLite 开发文件路径 |
| `MYSQL_PASSWORD` | `123456` | 是 | MySQL 密码，生产必须替换 |

完整示例见 `agent-service/.env.example`。

## 分支与提交前检查

```powershell
git status --short
git diff
.\mvnw.cmd test
agent-service\.venv\Scripts\python.exe -m pytest -q agent-service\tests
docker compose config --services
```

确认没有 `.env`、数据库、日志、PID、虚拟环境或构建产物进入待提交列表。
