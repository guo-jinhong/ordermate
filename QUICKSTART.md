# OrderMate 快速启动

这份文档面向第一次运行项目的人。推荐先使用 Docker demo 模式，确认完整链路可用后再切换真实模型。

## 1. 准备环境

安装并启动 Docker Desktop，确认以下命令可用：

```powershell
docker --version
docker compose version
```

首次构建需要联网下载 MySQL、Java、Python 镜像和项目依赖，耗时取决于网络环境。

## 2. 启动默认演示

在项目根目录运行：

```powershell
docker compose up --build -d
docker compose ps
```

也可以使用 Windows 辅助脚本：

```powershell
.\start-demo.ps1
```

默认服务和地址：

| 服务 | 地址/端口 |
| --- | --- |
| 聊天页面 | <http://localhost:8000> |
| Agent API 文档 | <http://localhost:8000/docs> |
| Java API 文档 | <http://localhost:8080/api/doc.html> |
| MySQL（仅本机调试） | `localhost:3307` |

默认 Compose 只启动 `mysql`、`backend`、`agent`。Redis 是可选能力，默认没有启动。

如果本地 `.env` 修改了 `AGENT_HOST_PORT` 或 `BACKEND_HOST_PORT`，请以 `docker compose ps` 显示的端口为准。

## 3. 登录与演示

```text
用户名：testuser
密码：password
```

推荐依次测试：

1. 未登录提问：`推荐 3000 元以内的手机`
2. 登录演示账号。
3. 提问：`查看我的购物车`
4. 提问：`查询我的订单`
5. 提问：`取消订单 1`
6. 检查系统是否先显示确认卡，而不是直接执行写操作。

## 4. 健康检查

```powershell
Invoke-RestMethod http://localhost:8000/health
```

默认应返回 `status=ok`，并显示 `agent_mode=demo`。

## 5. 停止服务

```powershell
docker compose down
```

或：

```powershell
.\stop-demo.ps1
```

普通停止不会删除 MySQL volume。

## 6. 重置演示数据

只重置脚本支持的演示订单状态：

```powershell
.\reset-demo.ps1
```

彻底删除容器数据并重新初始化：

```powershell
docker compose down -v
docker compose up --build -d
```

> `down -v` 会永久删除该 Compose 项目的数据库卷。不要对保存真实数据的环境执行。

## 7. 切换真实模型

复制示例环境变量：

```powershell
Copy-Item .env.docker.example .env
```

在本地 `.env` 中填写：

```dotenv
AGENT_MODE=live
OPENAI_API_KEY=你的真实Key
OPENAI_MODEL=模型服务当前支持的模型名
OPENAI_BASE_URL=https://api.deepseek.com
```

重新构建 Agent：

```powershell
docker compose up --build -d agent
docker compose logs -f agent
```

真实 Key 不得写进 README、示例文件、截图、录屏终端输出或 Git 提交。

## 8. 运行测试

Java：

```powershell
.\mvnw.cmd test
```

Python：

```powershell
cd agent-service
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

## 9. Windows 本地进程模式

如果需要不通过 Docker 启动 Java 和 Python 进程，可使用：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start-local-full.ps1
```

该模式默认使用：

- Agent：`http://localhost:18000`
- Java：`http://localhost:8080/api`
- MySQL：`localhost:3306`

停止：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\stop-local-full.ps1
```

Docker 模式和本地进程模式端口不同，详细参数见 [docs/development.md](docs/development.md)。

## 10. 常见问题

- 页面打不开：先运行 `docker compose ps`，再查看 `docker compose logs agent`。
- 后端连接失败：容器内必须使用 `http://backend:8080/api`，不能使用 `localhost:8080`。
- live 模式提示缺少 Key：检查 `.env`，然后重建 Agent 容器。
- 端口占用：在 `.env` 修改 `AGENT_HOST_PORT` 和 `BACKEND_HOST_PORT`。
- MySQL 初始化脚本没有重新执行：只有空 volume 才会执行；确认可以丢弃数据后再使用 `down -v`。

更多排查和服务器部署说明见 [docs/deployment.md](docs/deployment.md)。
