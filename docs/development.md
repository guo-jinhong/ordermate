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

## 完整 Windows 启动脚本

```powershell
.\start-local-full.ps1 `
  -MySqlHost 127.0.0.1 `
  -MySqlPort 3306 `
  -BackendPort 8080 `
  -AgentPort 18000 `
  -NoBrowser
```

主要参数：

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `MySqlHost` | `127.0.0.1` | MySQL 主机 |
| `MySqlPort` | `3306` | MySQL 端口 |
| `MySqlUser` | `root` | 本地开发账号 |
| `BackendDatabase` | `ecommerce_db` | Java 业务库 |
| `BackendPort` | `8080` | Java 端口 |
| `AgentPort` | `18000` | Agent 端口 |
| `NoDockerMySql` | false | 不使用 Docker MySQL 兜底 |
| `NoBrowser` | false | 启动后不打开浏览器 |

密码也可以作为参数传入，但更推荐放在未跟踪的 `.env` 中，避免出现在终端历史。

停止本地进程：

```powershell
.\stop-local-full.ps1
```

运行 PID 和日志保存在 `.run/`，该目录不会进入 Git。

## Agent 环境变量

| 变量 | 默认值 | 敏感 | 说明 |
| --- | --- | --- | --- |
| `AGENT_MODE` | `auto` | 否 | `demo`、`live` 或 `auto` |
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
