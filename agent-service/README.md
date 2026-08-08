# OrderMate Agent Service

FastAPI Agent 服务负责聊天 API、SSE 流式事件、模型工具调用、会话状态、确认工作流、知识检索和浏览器演示页面。业务事实与写操作最终由 Spring Boot API 控制。

## 运行模式

- `demo`：确定性本地 Agent，无需模型 Key。
- `live`：调用 OpenAI-compatible 模型接口。
- `auto`：有 `OPENAI_API_KEY` 时使用 live，否则使用 demo。

live 路径兼容 Chat Completions，并在客户端可用时支持 Responses API 回退。DeepSeek 等兼容服务通过 `OPENAI_BASE_URL` 配置。

## 工具

主要工具包括：

- `search_products`
- `get_product_detail`
- `search_knowledge_base`
- `get_cart`
- `add_to_cart`
- `update_cart`
- `remove_from_cart`
- `clear_cart`
- `get_my_orders`
- `get_order_detail`
- `create_order`
- `pay_order`
- `cancel_order`

购物车和订单工具需要登录 JWT。下单、支付、取消订单等风险动作通过确认工作流处理；模型不能绕过 Java 后端权限和业务校验。

## 本地开发

```powershell
cd agent-service
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

访问：

- 页面：<http://localhost:8000>
- API 文档：<http://localhost:8000/docs>
- 健康检查：<http://localhost:8000/health>

测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## 配置

复制 `.env.example` 为 `.env`，不要提交真实 `.env`。

最小 demo 配置：

```dotenv
AGENT_MODE=demo
ECOMMERCE_BACKEND=api
ECOMMERCE_API_BASE_URL=http://localhost:8080/api
```

DeepSeek live 示例：

```dotenv
AGENT_MODE=live
OPENAI_API_KEY=本地真实Key
OPENAI_MODEL=供应商当前支持的模型名
OPENAI_BASE_URL=https://api.deepseek.com
```

其他参数见 [../docs/development.md](../docs/development.md)。

## 状态与持久化

未设置 `REDIS_URL` 时，会话历史、结构化状态和确认令牌保存在进程内存中，服务重启后丢失。

设置 Redis 后，可启用 Redis 状态存储和 LangGraph checkpointer。Redis 必须由运行环境单独提供；当前根目录默认 Compose 不启动 Redis。

## 数据访问边界

- 商品、购物车和订单通过 Spring Boot API 访问。
- Agent 不直接写业务表。
- 知识库可从 MySQL 读取，并在数据库不可用时回退到 `app/knowledge/documents.json`。
- SQLite 仅用于本地开发适配，生成的数据库文件不会提交 Git。

## MCP Server

项目提供 stdio MCP Server：

```powershell
.\.venv\Scripts\python.exe -m app.mcp_server
```

MCP 暴露商品、知识和受控订单工具。取消工具只允许预检，实际写操作仍需在 OrderMate UI 完成用户确认。

## 安全要求

- 不记录完整 JWT、Key 或密码。
- 不把真实 Key 放入测试、示例或截图。
- 工具参数和权限必须由后端再次校验。
- 价格、库存、购物车和订单答案必须基于工具结果。

详见 [../docs/security.md](../docs/security.md) 和 [../docs/agent-rules.md](../docs/agent-rules.md)。
