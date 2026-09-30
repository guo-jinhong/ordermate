# API Design

## 1. Overview

This project contains two backend services:

- Java backend: Spring Boot e-commerce order system, mounted under `/api`.
- Agent backend: FastAPI customer-service Agent, mounted at the root path of port `8000`.

Recommended local addresses:

| Service | Base URL | Docs |
| --- | --- | --- |
| Agent service | `http://localhost:8000` | `http://localhost:8000/docs` |
| E-commerce backend | `http://localhost:8080/api` | `http://localhost:8080/api/doc.html` |

The frontend chat page calls the Agent service first. The Agent service then calls the Java backend through tool functions when it needs real business data such as products, cart items, or orders.

```mermaid
flowchart LR
    U["User / Browser"] --> A["FastAPI Agent service"]
    A -.->|"optional when REDIS_URL is configured"| R["Redis memory and confirmation tokens"]
    A --> K["Local knowledge base"]
    A --> L["LLM API or demo agent"]
    A --> B["Spring Boot e-commerce API"]
    B --> M["MySQL"]
```

## 2. Common Conventions

### 2.1 Response Envelope

The Java backend uses a unified response body:

```json
{
  "code": 200,
  "message": "success",
  "data": {}
}
```

The Agent service returns task-specific JSON models. For example, `/chat` returns:

```json
{
  "answer": "Here is the answer.",
  "tool_calls": [],
  "confirmation": null,
  "data": null,
  "reference": null
}
```

### 2.2 Authentication

Java protected APIs require a JWT in the request header:

```http
Authorization: Bearer <access_token>
```

The Agent service accepts the same token in the request body as `access_token`, then forwards it to the Java backend when calling protected tools.

### 2.3 Status Codes

| Code | Meaning | Typical Scenario |
| --- | --- | --- |
| `200` | Success | Query, login, chat, confirmation succeeded |
| `400` | Bad request | Invalid parameter or unsupported pending action |
| `401` | Unauthorized | Missing token or login failed |
| `403` | Forbidden | Non-admin user accesses admin API |
| `404` | Not found | Resource not found or confirmation token expired |
| `422` | Validation error | FastAPI/Pydantic request validation failed |
| `500` | Server error | Unexpected backend error |
| `502` | Upstream error | Agent failed to execute e-commerce API operation |
| `503` | Service unavailable | Live Agent mode enabled but model API key is missing |
| `429` | Rate limited | Per-IP request limit exceeded; see 2.5 |

### 2.4 Error Response Shapes

The Agent service returns **two** different error body shapes. A client must handle both.

Standard FastAPI error (`HTTPException`, including `422` validation errors):

```json
{ "detail": "Please log in first." }
```

Rate-limit error (`slowapi` handler, `429` only):

```json
{ "error": "rate_limited", "detail": "请求过于频繁，请稍后再试。" }
```

Note: `detail` exists in both shapes, but `error` appears **only** on `429`. Read `detail` first and fall back to a generic message; never assume `error` is present. On `422`, `detail` is an array of validation objects rather than a string, so coerce before rendering.

### 2.5 Rate Limits

| Scope | Limit | Key |
| --- | --- | --- |
| default (all routes) | `60/minute` | client IP |
| `/chat/stream` | `20/minute` | client IP |
| `/confirm` | `10/minute` | client IP |

Limits are keyed by `get_remote_address`. Behind a reverse proxy this resolves to the proxy address unless forwarded-header handling is configured, so a public deployment must also rate limit at the proxy layer.

### 2.6 API Versioning

The current project does not use `/api/v1` on the Agent side. If this project is upgraded for production, recommended paths are:

- `/api/v1/chat`
- `/api/v1/chat/stream`
- `/api/v1/auth/login`
- `/api/v1/confirm`
- `/api/v1/conversation/clear`

For the current demo, keep existing paths to avoid breaking the frontend.

## 3. Agent Service APIs

### 3.1 Health Check

```http
GET /health
```

Purpose: check whether the Agent service is alive and which mode is active.

Response:

```json
{
  "status": "ok",
  "model_configured": true,
  "agent_mode": "demo",
  "backend_base_url": "http://backend:8080/api"
}
```

Notes:

- `agent_mode=demo`: uses deterministic local demo logic, no model API key required.
- `agent_mode=live`: calls the configured LLM API.

### 3.2 Login Proxy

```http
POST /auth/login
Content-Type: application/json
```

Request:

```json
{
  "username": "testuser",
  "password": "password"
}
```

Response:

```json
{
  "access_token": "<jwt>",
  "token_type": "bearer"
}
```

Design note: the Agent service does not issue its own login token. It proxies login to the Java backend and returns the Java JWT, so all order/cart tools share the same business identity.

### 3.3 Normal Chat

```http
POST /chat
Content-Type: application/json
```

Request:

```json
{
  "message": "推荐 3000 元以内的手机",
  "session_id": "browser-session-001",
  "access_token": null
}
```

Response:

```json
{
  "answer": "可以考虑 Smartphone X ...",
  "tool_calls": [
    {
      "name": "search_products",
      "arguments": {
        "keyword": "手机"
      },
      "outcome": "success"
    }
  ],
  "confirmation": null,
  "data": [],
  "reference": null
}
```

Core behavior:

- Reads short-term conversation memory by `session_id + token fingerprint`.
- Adds structured state context such as last order ID or last product keyword.
- Lets the Agent choose tools.
- Saves the user and assistant turn back to memory.
- Redacts sensitive text before writing memory.

### 3.4 Streaming Chat

```http
POST /chat/stream
Content-Type: application/json
Accept: text/event-stream
```

Request:

```json
{
  "message": "查询我的订单",
  "session_id": "browser-session-001",
  "access_token": "<jwt>"
}
```

SSE frame format:

```text
event: <name>
data: <single-line JSON>

```

Every frame is produced by `_sse()` as `event: {name}\ndata: {json}\n\n`. There is no `id:` or `retry:` field, and `data` is always a single line.

Response headers sent by the endpoint:

```http
Content-Type: text/event-stream
Cache-Control: no-cache
X-Accel-Buffering: no
```

#### Event Reference

There are **10** event types. Emission order below is the order the server produces them.

| # | Event | Payload | When |
| --- | --- | --- | --- |
| 1 | `started` | `{"message": "正在理解你的问题"}` | Always, first frame |
| 2 | `progress` | `{"message": "Agent 正在处理"}` | Repeated every 0.75s while the task runs |
| 3 | `llm_trace` | `{"calls": [...]}` | Live mode only, and only when non-empty |
| 4 | `reference` | `{"type": "...", "value": "...", "source": "..."}` | Only when a context reference was resolved |
| 5 | `clarification` | `{"tool": "...", "message": "..."}` | Per tool call with `outcome == "clarification_needed"` |
| 6 | `tool_error` | `{"name": "...", "error": "..."}` | Per tool call with `outcome == "error"` |
| 7 | `tool` | `{"name": "...", "outcome": "...", "arguments": {}}` | **Every** tool call that ran |
| 8 | `confirmation_required` | `{"action": "cancel_order"}` | Only when a high-risk action is pending |
| 9 | `result` | full `ChatResponse` object | Always, terminal frame on success |
| 10 | `error` | `{"detail": "..."}` | On unhandled server exception; terminal frame on failure |

Example frames:

```text
event: started
data: {"message":"正在理解你的问题"}

event: reference
data: {"type":"order","value":"1","source":"上下文指代"}

event: tool
data: {"name":"get_my_orders","outcome":"success","arguments":{}}

event: result
data: {"answer":"...","tool_calls":[...],"confirmation":null,"data":[],"reference":null}
```

Critical behaviors for clients:

- **`tool` is emitted for every tool call, including calls that also emitted `clarification` or `tool_error`.** One tool call can therefore produce two frames (`5`+`7` or `6`+`7`). Do not treat `tool` as mutually exclusive with those.
- **`progress` repeats and carries no progress value.** It is a heartbeat, not a measurable percentage. Clients must render it idempotently.
- **`result` and `error` are mutually exclusive terminal frames.** Exactly one of them ends a run. If the stream closes without `result`, the client must treat the run as failed even if `error` was never received.
- **`error` does not carry an HTTP error status.** It arrives inside an already-`200` streaming response, so a client that only checks `response.ok` will silently render nothing.
- **An application-level failure before streaming starts** (for example `503` when no API key is configured, or `429` rate limiting) is returned as a normal JSON response with a non-2xx status, not as an SSE frame. Clients must check `response.ok` before reading the body as a stream.
- `llm_trace` is absent in `demo` mode and must be treated as optional by any client.

Design note: this endpoint is used by the frontend chat page. It improves user experience by showing the Agent execution timeline before the final answer is ready.

### 3.5 Confirm Pending Action

```http
POST /confirm
Content-Type: application/json
```

Request:

```json
{
  "session_id": "browser-session-001",
  "confirmation_token": "<confirmation_token>",
  "approved": true,
  "access_token": "<jwt>"
}
```

Response:

```json
{
  "status": "executed",
  "message": "订单已成功取消。",
  "data": {}
}
```

Used for high-risk operations.

#### Supported Confirmation Actions

The Agent creates a pending confirmation for any of the following actions, and `/confirm` dispatches on `confirmation.action`:

| Action | Arguments consumed | Successful message |
| --- | --- | --- |
| `cancel_order` | `order_id` | 订单 N 已成功取消。 |
| `refund_order` | `order_id`, `reason` (optional) | 订单 N 退款申请已提交。 |
| `update_cart` | `cart_id`, `quantity` | 购物车项 N 数量已修改为 M。 |
| `update_cart_items` | `items[]` (`cart_id`, `quantity`) | 已将 N 个购物车项的数量都修改为 M。 |
| `remove_from_cart` | `cart_id` | 购物车项 N 已删除。 |
| `clear_cart` | — | 购物车已清空。 |
| `create_order` | `product_id`, `quantity`, `address_id` (optional), `payment_method` (optional) | 订单已创建。 |
| `pay_order` | `order_id` | 订单 N 已完成支付确认。 |

#### Response Statuses

`ConfirmResponse.status` is one of:

| Status | Meaning | `data` |
| --- | --- | --- |
| `executed` | User approved and the write operation succeeded | Business payload from the Java API |
| `cancelled` | User rejected; **no data was modified** | `null` |

Note: `cancelled` is a **successful HTTP 200** response, not an error. Clients must branch on `status`, not on the HTTP code.

#### Failure Modes

| HTTP | Cause |
| --- | --- |
| `401` | No resolvable login token |
| `404` | Token invalid, expired, or already consumed |
| `400` | Unsupported action or invalid arguments (`ValueError`) |
| `502` | Java backend rejected the operation (`EcommerceApiError`) |
| `429` | Rate limited (`10/minute`) |

Safety design:

- The pending token is bound to session ID and login token fingerprint.
- The token is single-use.
- The token has a TTL.
- The actual write operation is executed only after explicit user confirmation.

### 3.6 Clear Conversation

```http
POST /conversation/clear
Content-Type: application/json
```

Request:

```json
{
  "session_id": "browser-session-001",
  "access_token": "<jwt>"
}
```

Response:

```json
{
  "status": "cleared",
  "cleared": true
}
```

Purpose: clear all memory and structured state under the given session.

## 4. Agent Tools

| Tool | Needs Login | Backend Dependency | Purpose |
| --- | --- | --- | --- |
| `search_knowledge_base` | No | Local knowledge files | Search product specs and after-sales policies |
| `search_products` | No | Java `/products/search` | Search real product data |
| `get_product_detail` | No | Java `/products/{id}` | Get real product detail |
| `get_cart` | Yes | Java `/shopping-cart` | Read user's cart |
| `get_my_orders` | Yes | Java `/orders` | Read user's order list |
| `get_order_detail` | Yes | Java `/orders/{id}` | Read order detail |
| `cancel_order` | Yes | Java `/orders/{id}/cancel` | Create confirmation first, then cancel after approval |

Tool execution rule:

```mermaid
flowchart TD
    Q["User asks a question"] --> C["Agent decides whether a tool is needed"]
    C -->|No tool| A["Generate answer directly"]
    C -->|Read tool| T["Call product/cart/order/knowledge tool"]
    C -->|Risky write tool| P["Create pending confirmation"]
    P --> U["User confirms or rejects"]
    U -->|Approve| W["Execute Java backend write API"]
    U -->|Reject| X["Cancel pending action"]
    T --> A
    W --> A
```

## 5. Java E-commerce APIs

The Java backend is mounted under:

```text
http://localhost:8080/api
```

### 5.1 User APIs

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| `POST` | `/users/register` | No | Register a new user |
| `POST` | `/users/login` | No | Login and return JWT |
| `GET` | `/users/info` | Yes | Get current user profile |
| `PUT` | `/users/info` | Yes | Update current user profile |

### 5.2 Product and Category APIs

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| `GET` | `/products` | No | List products |
| `GET` | `/products/{productId}` | No | Get product detail |
| `GET` | `/products/category/{categoryId}` | No | List products by category |
| `GET` | `/products/search?keyword=手机` | No | Search products |
| `GET` | `/categories` | No | List categories |

### 5.3 Cart APIs

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| `POST` | `/shopping-cart/add` | Yes | Add product to cart |
| `GET` | `/shopping-cart` | Yes | Get current user's cart |
| `PUT` | `/shopping-cart/{cartId}` | Yes | Update item quantity |
| `DELETE` | `/shopping-cart/{cartId}` | Yes | Delete one cart item |
| `DELETE` | `/shopping-cart` | Yes | Clear cart |

### 5.4 Order APIs

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| `POST` | `/orders` | Yes | Create order |
| `GET` | `/orders` | Yes | Get current user's orders |
| `GET` | `/orders/{orderId}` | Yes | Get order detail |
| `GET` | `/orders/order-no/{orderNo}` | Yes | Get order by order number |
| `POST` | `/orders/{orderId}/cancel` | Yes | Cancel unpaid order |
| `POST` | `/orders/{orderId}/pay` | Yes | Simulate payment |

### 5.5 Address APIs

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| `POST` | `/addresses` | Yes | Create address |
| `GET` | `/addresses` | Yes | List user's addresses |
| `GET` | `/addresses/{addressId}` | Yes | Get address detail |
| `PUT` | `/addresses/{addressId}` | Yes | Update address |
| `DELETE` | `/addresses/{addressId}` | Yes | Delete address |
| `POST` | `/addresses/{addressId}/set-default` | Yes | Set default address |

### 5.6 Review APIs

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| `POST` | `/reviews` | Yes | Create review |
| `GET` | `/reviews/product/{productId}` | No | List product reviews |
| `GET` | `/reviews` | No | List reviews |
| `GET` | `/reviews/{reviewId}` | No | Get review detail |
| `PUT` | `/reviews/{reviewId}` | Yes | Update review |
| `DELETE` | `/reviews/{reviewId}` | Yes | Delete review |
| `POST` | `/reviews/{reviewId}/like` | Yes | Like review |

### 5.7 Admin APIs

Admin APIs require `ROLE_ADMIN`.

| Module | Path Prefix | Description |
| --- | --- | --- |
| Orders | `/admin/orders` | Query all orders, update order status, handle refund |
| Products | `/admin/products` | Create, update, delete products |
| Users | `/admin/users` | List users, enable user, disable user |
| Reviews | `/admin/reviews` | Audit, reject, or delete reviews |

## 6. Frontend Integration Notes

### 6.1 Login Flow

1. Frontend calls `POST /auth/login`.
2. Frontend stores `access_token` in memory or local storage.
3. Frontend includes `access_token` in Agent requests.
4. Agent forwards it to Java backend as `Authorization: Bearer <token>`.

### 6.2 Chat Flow

For normal request-response chat:

```text
frontend -> POST /chat -> Agent -> tools/backend/LLM -> JSON response
```

For streaming chat:

```text
frontend -> POST /chat/stream -> SSE events -> render timeline and final answer
```

### 6.3 Common Integration Problems

| Problem | Reason | Fix |
| --- | --- | --- |
| `401 Unauthorized` | Missing or invalid token | Login again and pass `access_token` |
| `422 Validation Error` | Request body field is missing or invalid | Check Pydantic schema in `/docs` |
| `503 OPENAI_API_KEY is not configured` | Live mode has no API key | Use `AGENT_MODE=demo` or configure API key |
| Browser cannot call backend | CORS origin not allowed | Add frontend URL to `cors.allowed-origins` |
| No streaming effect | Frontend used normal JSON request | Use `fetch` stream or SSE-compatible client |

## 7. Interview Explanation

When explaining this API design in an interview, use this structure:

1. The Java service owns business data and transactional operations.
2. The Agent service owns conversation, tool orchestration, memory, and safety confirmation.
3. Process memory stores conversation state by default; Redis stores short-term memory, structured state, and pending confirmation tokens only when `REDIS_URL` is configured.
4. MySQL stores durable e-commerce data such as users, products, carts, and orders.
5. SSE is used for chat timeline streaming, while normal JSON APIs are used for login, confirmation, and backend business operations.
6. Risky write operations are not executed directly by the model. The Agent first creates a confirmation token, then executes only after the user approves.
