# 电商智能客服 Agent：快速启动

## 你现在需要准备什么

只需要安装并启动 Docker Desktop。首次体验不需要：

- 手动安装 MySQL
- 手动创建数据库
- 安装 Maven
- 安装 Python
- 配置模型 API Key

默认使用本地演示 Agent。Docker 会自动创建 `ecommerce_db`、数据表和测试数据。

## 启动

在项目目录打开 PowerShell：

```powershell
docker compose up --build -d
```

也可以运行：

```powershell
.\start-demo.ps1
```

首次构建需要下载 MySQL、Java、Python 镜像和项目依赖，通常会比后续启动慢。

查看状态：

```powershell
docker compose ps
```

Redis、MySQL、backend、agent 四个服务均启动后访问：

```text
http://localhost:8000
```

演示账号：

```text
用户名：testuser
密码：password
```

## 推荐演示流程

1. 不登录，提问：“推荐 3000 元以内的手机”。
2. 登录 `testuser / password`。
3. 提问：“查看我的购物车”。
4. 提问：“查询我的订单”。
5. 提问：“取消订单 1”，观察二次确认卡片并选择是否执行。

## Agent 项目亮点

- SSE 执行时间线：聊天界面实时展示 Agent 处理、工具调用与确认状态。
- Redis 持久化：会话历史、确认令牌与 LangGraph 工作流 Checkpointer 可跨服务重启恢复。
- LangGraph 人工确认：取消订单在 `interrupt` 处暂停，用户确认后再恢复工作流。
- RAG：商品规格与演示售后政策由知识库工具检索；实时价格和库存仍只信任商城后端。
- MCP Server：可通过 `python -m app.mcp_server` 以 stdio 暴露安全的商品/订单工具；取消操作仅支持预检。

## 本地验证

```powershell
# Java 后端
.\mvnw.cmd test

# Python Agent（含评估集）
cd agent-service
.\.venv\Scripts\python.exe -m pytest -q
```

Python 评估集位于 `agent-service/evals/demo_cases.json`，覆盖商品推荐、登录边界、取消确认和提示注入防护。

## 停止

```powershell
docker compose down
```

或：

```powershell
.\stop-demo.ps1
```

普通停止不会删除数据库数据。

## 重置数据库

只恢复面试演示使用的订单 1 和对应库存：

```powershell
.\reset-demo.ps1
```

如需删除全部 Docker 项目数据，并在下次启动时重新灌入种子数据：

```powershell
docker compose down -v
docker compose up --build -d
```

## 切换真实模型

复制 `.env.docker.example` 为 `.env`，然后修改：

```dotenv
AGENT_MODE=live
OPENAI_API_KEY=在本地填写你的密钥
OPENAI_MODEL=gpt-5.4-mini
```

不要提交或发送 `.env` 文件。修改后重新启动 `agent` 服务：

```powershell
docker compose up --build -d agent
```

## 常用地址

- 聊天页面：http://localhost:8000
- Agent API 文档：http://localhost:8000/docs
- Java API 文档：http://localhost:8080/api/doc.html

## 豆包真实多轮记忆验收

确认三个容器已启动且根目录 `.env` 已配置后，在 PowerShell 执行：

```powershell
.\verify-memory-live.ps1
```

脚本会自动检查 Docker、Agent 健康状态和真实模型模式，然后验证：

- 连续商品推荐与“第二个”“它”的多轮指代；
- 登录后的订单上下文；
- 服务端会话清空；
- 清空后旧商品指代不应继续生效。

脚本不会读取或输出 `.env`，不会显示完整登录令牌，也不会执行取消订单等写操作。
