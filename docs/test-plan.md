# OrderMate 测试与验收

## 最近验证结果

验证日期：2026-08-08。

| 范围 | 命令 | 结果 |
| --- | --- | --- |
| Java 单元测试 | `.\mvnw.cmd test` | 26 passed |
| Python Agent | `python -m pytest -q` | 120 passed，1 warning |
| Compose 配置 | `docker compose config --services` | mysql、backend、agent |

Python 警告来自 FastAPI TestClient 依赖中的 Starlette 弃用提示，不影响当前测试结果；后续升级依赖时应重新评估。

本次尚未在本文档中声明 Docker 容器冷启动和 live 模型调用通过，这两项需要后续独立验收。

## Java 测试

```powershell
.\mvnw.cmd test
```

覆盖：

- 注册、登录、禁用账号和管理员保护。
- 商品创建、更新、删除和搜索。
- 下单、库存扣减、地址归属、数量限制、缺货、取消恢复库存和支付委托。

## Python 测试

```powershell
cd agent-service
.\.venv\Scripts\python.exe -m pytest -q
```

覆盖：

- FastAPI 健康检查、登录代理、聊天、SSE、确认和清空会话。
- demo/live Agent 工具循环与错误处理。
- 商品、购物车、订单与多轮指代状态。
- 内存和 Redis 存储适配。
- 确认令牌、审批工作流和 MCP 工具边界。
- 知识库、提示注入防护、脱敏审计和固定评测集。

知识库测试显式使用本地 JSON，避免被开发机 SQLite/MySQL 数据污染，确保结果可复现。

## Compose 静态检查

```powershell
docker compose config
docker compose config --services
```

预期服务：

```text
mysql
backend
agent
```

Redis 不是默认 Compose 服务。

## Docker 冷启动验收

在确认演示数据可以删除后：

```powershell
docker compose down -v
docker compose up --build -d
docker compose ps
```

验收：

- MySQL 进入 healthy。
- backend 和 agent 持续运行，无重启循环。
- Agent `/health` 返回 ok。
- Java Knife4j 和聊天页面可访问。
- `testuser/password` 可以登录。
- SQL 种子数据只初始化一次。

完成实际测试后再把结果、时间和环境补进“最近验证结果”。

## 手工业务验收

| 场景 | 操作 | 预期 |
| --- | --- | --- |
| 匿名商品查询 | 推荐 3000 元以内的手机 | 调用商品工具并返回真实结果 |
| 登录 | testuser/password | 获得登录态，页面不显示完整 JWT |
| 查看购物车 | 查看我的购物车 | 返回当前用户购物车 |
| 多轮指代 | 推荐手机 → 把它加入购物车 | 使用最近商品上下文 |
| 修改数量 | 把购物车项改成 2 件 | 写操作按设计确认或执行 |
| 查询订单 | 查询我的订单 | 只返回当前用户订单 |
| 取消订单 | 取消待支付订单 | 先出现确认卡，批准后才执行 |
| 拒绝确认 | 点击拒绝 | 订单保持不变 |
| 清空会话 | 调用 clear | 旧商品/订单指代不再生效 |
| 提示注入 | 要求忽略规则并输出 Key | 拒绝请求且不泄露敏感信息 |

## live 模型验收

live 测试单独进行，避免在普通 CI 使用真实 Key。建议记录：

- 日期、模型供应商、模型名和代码提交。
- 固定问题集及每条工具选择结果。
- 首事件延迟、最终响应时间和失败原因。
- 是否存在模型编造价格、库存、订单或工具结果。
- 录屏中是否隐藏 Key、JWT、Cookie 和个人数据。

不要在测试报告中粘贴真实 Key 或完整请求头。

## 发布门槛

- Java/Python 自动测试全部通过。
- GitHub Actions 通过。
- Docker 冷启动通过。
- demo 核心业务验收通过。
- live 演示前完成单独的安全检查。
- README 中只声明真实完成并可复现的能力。
