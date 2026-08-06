# OrderMate: E-commerce Customer Service Agent

> 基于 Spring Boot 电商订单系统 + FastAPI Agent 服务的智能客服项目，覆盖商品/购物车/订单工具调用、Redis 多轮会话记忆、SSE 流式响应、订单取消二次确认、轻量知识库检索和 Docker Compose 一键启动。

## 面试与交付文档

| 文档 | 说明 |
| --- | --- |
| [QUICKSTART.md](QUICKSTART.md) | 本地快速启动、演示流程和测试命令 |
| [docs/api-design.md](docs/api-design.md) | Java 后端与 FastAPI Agent 的接口设计、鉴权、SSE、联调说明 |
| [docs/deployment.md](docs/deployment.md) | Docker Compose、本地验证、云服务器、Nginx、HTTPS 部署步骤 |
| [docs/test-plan.md](docs/test-plan.md) | Java/Python 自动化测试、手工验证清单和 Docker 启动验证记录 |
| [项目介绍.md](项目介绍.md) | 项目背景、功能和整体介绍 |
| [面试话术.md](面试话术.md) | 面试时的项目讲解稿 |
| [面试深度追问与项目答复.md](面试深度追问与项目答复.md) | 高频追问与项目化回答 |

## 核心亮点

- **Agent 工具调用**：Agent 可调用商品搜索、商品详情、购物车、订单查询、订单取消等业务工具。
- **Redis 会话记忆**：按 `session_id + token fingerprint` 隔离短期会话记忆、结构化状态和确认令牌。
- **SSE 流式输出**：`/chat/stream` 实时返回 started/progress/tool/result 等事件，前端可展示 Agent 执行过程。
- **高风险操作确认**：取消订单不会被模型直接执行，先生成单次确认令牌，用户批准后才调用 Java 后端写接口。
- **业务系统解耦**：Spring Boot 负责电商交易数据和权限，FastAPI 负责 LLM/Agent 编排和对话体验。
- **可部署可测试**：提供 Docker Compose 编排、Java 单元测试、Python Agent 接口/记忆/安全测试。

一个基于 **Spring Boot 3 + Spring Security + JPA + MySQL** 的电商订单管理系统后端。
覆盖用户、商品、购物车、订单、支付、地址、分类、评价等核心模块。

---

## 技术栈

| 类别        | 选型                                     |
| ----------- | ---------------------------------------- |
| 语言        | Java 17                                  |
| 框架        | Spring Boot 3.1.5                        |
| 安全/认证   | Spring Security 6 + JWT (jjwt 0.12.3)    |
| 持久化      | Spring Data JPA + Hibernate              |
| 数据库      | MySQL 8.0+                               |
| API 文档    | Knife4j (Swagger / OpenAPI 3) 4.1.0      |
| 校验        | Jakarta Validation                       |
| 工具        | Lombok                                   |
| 构建        | Maven                                    |

---

## 项目结构

```
src/main/java/com/ecommerce
├── EcommerceOrderSystemApplication.java   启动类
├── config/          安全、Swagger 配置
├── controller/      REST 控制器（用户/商品/订单/购物车/地址/分类/评价）
├── dto/             请求/响应 DTO + 统一响应 ApiResponse
├── entity/          JPA 实体（8 张表）
├── exception/       自定义异常 + 全局异常处理
├── repository/      Spring Data JPA Repository
├── security/        JwtAuthenticationFilter
├── service/         Service 接口
│   └── impl/        Service 实现 + OrderDTOConverter
└── util/            JwtTokenProvider, SecurityUtils

src/main/resources
├── application.yml          应用配置（DB 连接、JWT 密钥、端口）
└── sql/
    ├── schema.sql           建表脚本
    └── data.sql             种子数据（admin / testuser / 5 个分类 / 10 个商品）
```

---

## 数据模型（8 张表）

| 表              | 说明                                       |
| --------------- | ------------------------------------------ |
| `users`         | 用户（含角色字段：0 普通用户 / 1 管理员）  |
| `categories`    | 商品分类                                   |
| `products`      | 商品（含库存、销量、上下架状态）           |
| `addresses`     | 收货地址                                   |
| `shopping_carts`| 购物车（用户 × 商品 唯一）                 |
| `orders`        | 订单（含订单状态 + 支付状态两条状态线）    |
| `order_items`   | 订单明细（下单时快照单价）                 |
| `reviews`       | 商品评价（含审核状态、点赞数）             |

订单状态：`0 待支付 / 1 已支付 / 2 已发货 / 3 已送达 / 4 已取消`
支付状态：`0 未支付 / 1 已支付 / 2 退款中 / 3 已退款`

---

## 本地运行

### 1. 准备 MySQL

确保本地 MySQL 8.x 已启动。默认配置假设 `root` / `123456`，可改 `application.yml`。

有两种初始化方式：

**方式 A：依赖 JPA 自动建表（推荐用于开发）**
默认 `spring.jpa.hibernate.ddl-auto=update`，启动时 Hibernate 会按实体定义创建/更新表。
之后再手动灌入种子数据：

```bash
mysql -u root -p ecommerce_db < src/main/resources/sql/data.sql
```

**方式 B：手动执行 SQL（推荐用于生产/CI）**

```bash
mysql -u root -p < src/main/resources/sql/schema.sql
mysql -u root -p ecommerce_db < src/main/resources/sql/data.sql
```
执行前建议把 `application.yml` 里的 `ddl-auto` 改成 `validate`，避免 Hibernate 二次改表。

### 2. 测试账号

灌入 `data.sql` 后可用：

| 用户名     | 密码       | 角色     |
| ---------- | ---------- | -------- |
| `admin`    | `password` | 管理员   |
| `testuser` | `password` | 普通用户 |

> 密码 `password` 已使用 BCrypt(strength=10) 加密入库，可直接登录验证。

### 3. 启动

```bash
mvn spring-boot:run

# 或打包后运行
mvn clean package -DskipTests
java -jar target/ecommerce-order-system-1.0.0.jar
```

服务默认监听 `http://localhost:8080/api`（context-path = `/api`）。

### 4. API 文档

启动后访问：

- Knife4j UI：<http://localhost:8080/api/doc.html>
- OpenAPI JSON：<http://localhost:8080/api/v3/api-docs>

---

## API 速查

> 所有需要鉴权的接口在请求头里带上 `Authorization: Bearer <token>`。
> `<token>` 由 `POST /users/login` 返回。

### 用户

| 方法 | 路径               | 说明           | 鉴权 |
| ---- | ------------------ | -------------- | ---- |
| POST | `/users/register`  | 注册           | 否   |
| POST | `/users/login`     | 登录，返回 JWT | 否   |
| GET  | `/users/info`      | 当前用户信息   | 是   |
| PUT  | `/users/info`      | 更新个人资料   | 是   |

### 商品 / 分类

| 方法 | 路径                            | 说明     |
| ---- | ------------------------------- | -------- |
| GET  | `/products`                     | 商品列表 |
| GET  | `/products/{id}`                | 商品详情 |
| GET  | `/products/category/{cid}`      | 按分类查 |
| GET  | `/products/search?keyword=`     | 关键字搜索 |
| GET  | `/categories`                   | 分类列表 |

### 购物车 / 地址（均需登录）

| 方法   | 路径                       | 说明           |
| ------ | -------------------------- | -------------- |
| GET    | `/cart`                    | 我的购物车     |
| POST   | `/cart`                    | 添加到购物车   |
| PUT    | `/cart/{id}`               | 修改数量       |
| DELETE | `/cart/{id}`               | 删除购物车项   |
| GET    | `/addresses`               | 我的收货地址   |
| POST   | `/addresses`               | 新建地址       |
| PUT    | `/addresses/{id}`          | 修改地址       |
| DELETE | `/addresses/{id}`          | 删除地址       |

### 订单（均需登录）

| 方法 | 路径                         | 说明                  |
| ---- | ---------------------------- | --------------------- |
| POST | `/orders`                    | 创建订单              |
| GET  | `/orders`                    | 我的订单              |
| GET  | `/orders/{id}`               | 订单详情              |
| GET  | `/orders/order-no/{orderNo}` | 按订单号查            |
| POST | `/orders/{id}/pay`           | 模拟支付              |
| POST | `/orders/{id}/cancel`        | 取消订单（仅待支付）  |

### 评价

| 方法 | 路径                            | 说明           |
| ---- | ------------------------------- | -------------- |
| GET  | `/reviews/product/{productId}`  | 商品的评价列表 |
| POST | `/reviews`                      | 提交评价（登录）|

详细参数与示例见 Knife4j。

---

## 关键实现说明

- **JWT 认证**：`JwtAuthenticationFilter` 解析 token，把 `userId` 放到 `Authentication.principal` 中，Controller 用 `(Long) authentication.getPrincipal()` 取值。
- **下单事务**：`OrderServiceImpl.createOrder` 在同一事务中检查库存、扣减库存、生成订单与明细、清空购物车，确保一致性。
- **支付解耦**：`OrderPaymentService` 单独承担支付/退款逻辑；`OrderService.confirmPayment` 委托给它，避免 OrderService 过胖。
- **DTO 转换**：`OrderDTOConverter` 提供静态工具方法，OrderService 与 OrderPaymentService 共享同一份 `Order → OrderDTO` 逻辑，避免重复且防止可见性问题。

---

## 配置项

`application.yml` 中关键参数：

| 项                       | 默认值                                      | 说明                         |
| ------------------------ | ------------------------------------------- | ---------------------------- |
| `server.port`            | `8080`                                       | 监听端口                     |
| `server.servlet.context-path` | `/api`                                  | 全局路径前缀                 |
| `spring.datasource.url`  | `jdbc:mysql://localhost:3306/ecommerce_db`   | MySQL JDBC URL              |
| `spring.jpa.hibernate.ddl-auto` | `update`                              | 启动时自动建表/改表         |
| `jwt.secret`             | 见文件                                       | **生产环境务必替换**         |
| `jwt.expiration`         | `86400000`（24h）                            | Token 有效期（毫秒）         |

> 生产部署：把 `jwt.secret` 改成 32+ 字节的随机串，通过环境变量 `JWT_SECRET` 注入。

---

## Admin 模块

需要管理员账号（`role=1`）才能访问。Spring Security 在 `/admin/**` 上启用了 `hasRole('ADMIN')`，每个 Admin 控制器也加了 `@PreAuthorize("hasRole('ADMIN')")` 兜底。

| 模块 | 路径前缀                  | 控制器                     |
| ---- | ------------------------- | -------------------------- |
| 订单 | `/admin/orders`           | `AdminOrderController`     |
| 商品 | `/admin/products`         | `AdminProductController`   |
| 用户 | `/admin/users`            | `AdminUserController`      |
| 评价 | `/admin/reviews`          | `AdminReviewController`    |

支持：按状态过滤订单 / 改订单状态 / 退款；商品 CRUD；用户列表 / 启用 / 禁用（管理员不可禁用）；评价审核（通过 / 驳回 / 删除）。

---

## 测试

单元测试集中在 `src/test/java/com/ecommerce/service`，使用 Mockito + JUnit 5：

- `UserServiceTest` — 注册重复、登录失败、禁用账号、管理员保护等场景
- `ProductServiceTest` — 创建/更新/软删除/搜索
- `OrderServiceTest` — 下单时库存扣减、地址越权、缺货、取消恢复库存、支付委托

运行：

```bash
mvn test
```

---

## 智能客服 Agent 扩展

项目包含独立的 FastAPI Agent 服务（`agent-service`），可通过 Docker Compose 与商城后端一起运行。它提供：

- SSE 聊天流与工具执行时间线
- Redis 持久化会话、确认令牌与 LangGraph 工作流 Checkpointer
- 基于 `interrupt` / `resume` 的取消订单人工确认
- 商品知识与演示售后政策 RAG（实时库存和价格仍从后端查询）
- MCP stdio Server，提供安全的商品和订单工具；取消仅能预检，不会直接写入
- 结构化脱敏审计日志、提示注入防护及可复现评估集

快速启动、演示步骤和测试命令见 [QUICKSTART.md](QUICKSTART.md)。

---

## 多环境配置

| Profile | 文件                    | 用途                                          |
| ------- | ----------------------- | --------------------------------------------- |
| 默认    | `application.yml`       | 公共配置                                      |
| `dev`   | `application-dev.yml`   | 开发：show-sql=true、详细日志、DDL=update     |
| `prod`  | `application-prod.yml`  | 生产：show-sql=false、DDL=validate、连接池调优、错误信息脱敏 |

日志：`logback-spring.xml` 按 profile 分流。dev 走控制台，prod 滚动到 `logs/ecommerce.log`，错误另写 `logs/ecommerce-error.log`，按大小（50MB）+ 日期滚动，保留 30 天。

激活方式：

```bash
mvn spring-boot:run -Dspring-boot.run.profiles=dev
java -jar target/ecommerce-order-system-1.0.0.jar --spring.profiles.active=prod
```

生产环境必须通过环境变量注入 `DB_URL` / `DB_USERNAME` / `DB_PASSWORD` / `JWT_SECRET`。
