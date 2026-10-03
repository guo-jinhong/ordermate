# OrderMate Vue 前端重构方案

> **文档用途**：本文件是新增 Vue 前端的**实施规范**。实施以可运行的纵向闭环为优先；凡是本文件已定义的接口、类型、目录职责与验收标准，执行者不得自行发明或改动。
>
> **配套文档**：`docs/frontend-showcase.md` 说明"为什么这样设计"（视觉与演示叙事），本文件说明"怎么实现"。两者必须同步更新，不得互相矛盾。
>
> **权威契约来源优先级**（出现分歧时以此为准）：
> 1. `agent-service/app/main.py` 与 `agent-service/app/schemas.py` 的实际代码
> 2. `agent-service/app/static/app.js` 的实际处理逻辑
> 3. `docs/api-design.md`（已于本次修正，见 1.4）
>
> **状态**：待实施。

---

## 1. 背景、目标与非目标

### 1.1 背景

现有前端位于 `agent-service/app/static/`，由 FastAPI 以静态资源方式提供：

| 文件 | 行数 | 体积 |
| --- | ---: | ---: |
| `app.js` | 1552 | 64.8 KB |
| `styles.css` | 2532 | 60.7 KB |
| `index.html` | 359 | 16.3 KB |

该实现功能完整：客户/开发者双视角、SSE 执行时间线、递归脱敏、请求取消防旧流回写、无障碍支持（跳转链接、`aria-live`、方向键切视角、Esc 关抽屉、`prefers-reduced-motion`、Windows 高对比度）。它**不是半成品**，重构的理由是工程化能力与演示观感，不是功能缺失。

### 1.2 目标

1. 新增 `frontend/` 目录，实现 Vue 3 + Vite + TypeScript 前端，作为公网演示的主入口。
2. 通过 TypeScript 类型契约把后端 Pydantic 模型镜像到前端，形成可讲解的前后端契约设计。
3. 组件化拆分，使双视角、结果卡片、确认流程、Inspector 各自独立可测。
4. 补齐前端工程化能力：类型、组件测试、构建产物契约测试、依赖方向约束。
5. 公网部署时保持与原生版本一致的视觉与交互，且不引入新的安全风险。

### 1.3 非目标

- **不做 SSR / Nuxt**。纯 SPA，静态产物。
- **不做 i18n**。界面语言固定为简体中文。
- **不引入商品图片或任何外部静态资源**。沿用现有约束：商品卡片只渲染业务接口返回的真实字段。
- **不改动 `agent-service` 的业务编排与电商规则**。允许在 Vue 接入前完成一项必要的传输层修正：`/chat/stream` 必须在创建 `StreamingResponse` 前完成登录令牌校验，使失效登录能以标准 `401` 返回，而不是在 `200` SSE 流中退化为通用 `error`。
- **不删除 `agent-service/app/static/`**。原生前端保留为兜底与对照实现。
- **不修改 `agent-service/tests/test_frontend_contract.py`**。它继续守护原生页面，必须保持通过。

### 1.4 本次已修正的契约偏差

在编写本方案时比对代码与 `docs/api-design.md`，发现三处偏差并已修正文档：

| 偏差 | 原文档 | 实际代码 |
| --- | --- | --- |
| SSE 事件数量 | 只列了 4 个（`started`/`progress`/`tool`/`result`） | 实际有 **10 个** |
| 确认动作范围 | "仅对 `cancel_order` 创建待确认" | 实际 **8 个**动作（见 2.6） |
| 错误响应格式 | 未提及 | 实际有**两种**错误体，且 `429` 与其余不同 |

修正已写入 `docs/api-design.md` 的 2.4、2.5、3.4、3.5 节。

### 1.5 原生前端已存在、Vue 版应一并修正的缺口

以下问题在现有实现中存在。Vue 版**应修正**，且必须写进测试，避免回归：

| # | 缺口 | 位置 | 处理方式 |
| --- | --- | --- | --- |
| G1 | `refund_order` 没有确认卡片展示配置，会落到默认分支 | `app.js` 926–974 | 补齐 `refund_order` 的展示信息 |
| G2 | `refund_order` 不在 `resultDataKind` 的工具名列表中，只能靠字段嗅探 | `app.js` 1140–1146 | 补入对应工具名列表 |
| G3 | `update_cart_items` 不在购物车工具名列表中 | `app.js` 1140 | 补入 |
| G4 | 无法识别的 `data` 会**静默隐藏**结果区，用户看不到任何反馈 | `app.js` 1103 | 改为 `raw` 分支渲染（见 6.4） |

> **注意 G4 是行为变更，不是保持现状。** 现有实现遇到不认识的数据结构时直接把结果区隐藏，Vue 版改为显式渲染"未识别数据"折叠块。理由：静默丢弃会让人误以为 Agent 没有返回结果，而面试演示中恰好要展示 Agent 的原始返回。此变更需在 `frontend-showcase.md` 中同步说明。

---

## 2. 权威后端契约

**本章内容为照抄内容，执行者不得推测或简化。** 所有端点均挂载在 Agent 服务根路径（本机 `http://localhost:8000`）。

### 2.1 端点总表

| 方法 | 路径 | 请求模型 | 响应模型 | 限流 |
| --- | --- | --- | --- | --- |
| `GET` | `/health` | — | `HealthResponse` | 60/min |
| `POST` | `/auth/login` | `LoginRequest` | `LoginResponse` | 60/min |
| `POST` | `/auth/session` | Authorization 请求头；兼容旧 `AuthSessionRequest` | `AuthSessionResponse` | 60/min |
| `POST` | `/chat` | `ChatRequest` | `ChatResponse` | 60/min |
| `POST` | `/chat/stream` | `ChatRequest` | SSE 流 | **20/min** |
| `POST` | `/conversation/clear` | `ClearConversationRequest` | `ClearConversationResponse` | 60/min |
| `POST` | `/confirm` | `ConfirmRequest` | `ConfirmResponse` | **10/min** |
| `GET` | `/admin/config` | — | `RuntimeConfigResponse` | 60/min |
| `POST` | `/admin/config` | — | — | 60/min |
| `POST` | `/admin/knowledge/reload` | — | `ReloadKnowledgeResponse` | 60/min |
| `GET` | `/metrics` | — | Prometheus 文本 | 60/min |

`/admin/*` 需要管理员令牌（`require_admin_token` 依赖），**公网 demo 模式不暴露**，前端不实现对应界面。

Agent 服务当前同时支持 `Authorization: Bearer <token>` 与请求体 `access_token`，且请求头优先。Vue 版统一使用 **Authorization 请求头**；请求体字段仅作为兼容旧前端的后端契约保留，不在新代码中形成第二套令牌传递路径。登录接口 `/auth/login` 不携带 token，仅提交用户名和密码。

### 2.2 SSE 事件表（`POST /chat/stream`）

帧格式由 `_sse()` 产生，固定为 `event: <name>\ndata: <单行JSON>\n\n`。无 `id:`、无 `retry:`。

响应头：

```http
Content-Type: text/event-stream
Cache-Control: no-cache
X-Accel-Buffering: no
```

**共 10 个事件，按服务端产生顺序：**

| # | 事件 | 载荷 | 触发条件 |
| --- | --- | --- | --- |
| 1 | `started` | `{ message: string }` | 总是，首帧 |
| 2 | `progress` | `{ message: string }` | 任务运行期间每 0.75s 重复 |
| 3 | `llm_trace` | `{ calls: unknown[] }` | 仅 live 模式且非空 |
| 4 | `reference` | `ReferenceResolution` | 仅当解析出上下文指代 |
| 5 | `clarification` | `{ tool: string; message: string \| null }` | 工具 `outcome === "clarification_needed"` |
| 6 | `tool_error` | `{ name: string; error: string \| null }` | 工具 `outcome === "error"` |
| 7 | `tool` | `{ name: string; outcome: string; arguments: Record<string, unknown> }` | **每个执行过的工具** |
| 8 | `confirmation_required` | `{ action: ConfirmationAction }` | 存在待确认高风险动作 |
| 9 | `result` | 完整 `ChatResponse` | 总是，成功时的终止帧 |
| 10 | `error` | `{ detail: string }` | 服务端未捕获异常，失败时的终止帧 |

**必须实现的 6 条客户端行为：**

1. **`tool` 对每个工具都会发出，包括同时产生 `clarification` 或 `tool_error` 的调用。** 一次工具调用可能产生两帧（`5`+`7` 或 `6`+`7`），因此 `tool` 与它们**不是互斥关系**。
2. **`progress` 会重复且不含进度值。** 它是心跳，不是百分比。渲染必须幂等。
3. **`result` 与 `error` 是互斥的终止帧**，一次运行恰好以其中之一结束。**若流结束但未收到 `result`，必须按失败处理**，即使从未收到 `error`。
4. **`error` 不携带 HTTP 错误码。** 它出现在已经是 `200` 的流式响应内部。只检查 `response.ok` 的客户端会静默渲染空白。
5. **流开始前的应用级失败**（如未配置 Key 的 `503`、限流的 `429`）以**普通 JSON 响应**返回非 2xx 状态，**不是** SSE 帧。必须先用 `response.ok` 判断，再按流读取。
6. **`llm_trace` 在 demo 模式下不存在**，必须按可选处理。

**接入前置修正：**当前实现是在 SSE 生成器开始执行后才调用 `resolve_access_token`。这会导致失效令牌先收到 `200` 和 `started`，随后只收到通用 `error`，前端无法可靠触发重新登录。实现 Vue 前端前，必须把令牌解析和校验移动到返回 `StreamingResponse` 之前；校验失败直接返回普通 JSON `401`。该改动只修正传输层错误语义，不改变 Agent 业务逻辑。

### 2.3 错误契约

服务端有**两种**错误响应体，前端必须都处理：

```jsonc
// 标准 FastAPI 错误（HTTPException、422 校验失败）
{ "detail": "Please log in first." }

// 限流错误（slowapi 处理器，仅 429）
{ "error": "rate_limited", "detail": "请求过于频繁，请稍后再试。" }
```

- `detail` 在两种形态中都存在；`error` **仅在 429 出现**。
- `422` 时 `detail` 是**校验对象数组**而非字符串，渲染前必须先归一化为字符串。

状态码语义见 `docs/api-design.md` 2.3。

### 2.4 限流

| 范围 | 限制 |
| --- | --- |
| 默认（全部路由） | `60/minute` |
| `/chat/stream` | `20/minute` |
| `/confirm` | `10/minute` |

按客户端 IP 计数。**反向代理后该 IP 会退化为代理地址**，所以公网部署必须在 Nginx 层再加限流（见第 10 章）。

前端要求：`429` 必须给出明确文案（"请求过于频繁，请稍后再试"），并**禁用发送按钮进行短时退避**，不得静默重试。

### 2.5 `data` 字段多态与嗅探规则

`ChatResponse.data` 的类型是 `unknown`（后端为 `Any`）。前端通过**两步**判定渲染类型，顺序不可颠倒：

**第一步：按工具名判定**（取 `tool_calls` 中最后一个有 `name` 的调用）

| 工具名 | 判定类型 |
| --- | --- |
| `get_cart` `add_to_cart` `update_cart` **`update_cart_items`** `remove_from_cart` `clear_cart` | `cart` |
| `get_my_orders` `get_order_detail` `cancel_order` **`refund_order`** `create_order` `pay_order` | `order` |
| `search_products` `get_product_detail` | `product` |

（加粗项是 1.5 要求补齐的缺口。`refund_order` 后端存在但原实现未列入。）

**第二步：按字段嗅探**（仅当第一步无法判定时）。记录需要先归一化：数组直接用；`{ content: [...] }` 取 `content`；单个对象包成单元素数组。

```
isOrderRecord  : item.orderNo 存在
isCartRecord   : 无 orderNo 且 ( cartId 存在
                               或 ( productId && quantity && typeof productName === 'string' ) )
isProductRecord: 无 orderNo 且 非 cart 且 typeof item.name === 'string' 且 item 自身有 price 属性
```

判定顺序固定为 `order → cart → product`。两者都无法判定时进入 `raw` 分支。

**所有字段在 TS 中一律为可选**，渲染层必须容忍缺失：价格缺失显示"价格待确认"，库存缺失显示"库存待确认"，**任何情况下不得编造数值或规格**。这是本项目的硬约束。

### 2.6 高风险动作与确认流程

`Confirmation.action` 共 **8 个**：

| 动作 | 参数 | 成功文案 |
| --- | --- | --- |
| `cancel_order` | `order_id` | 订单 N 已成功取消。 |
| `refund_order` | `order_id`, `reason?` | 订单 N 退款申请已提交。 |
| `update_cart` | `cart_id`, `quantity` | 购物车项 N 数量已修改为 M。 |
| `update_cart_items` | `items[]`(`cart_id`,`quantity`) | 已将 N 个购物车项的数量都修改为 M。 |
| `remove_from_cart` | `cart_id` | 购物车项 N 已删除。 |
| `clear_cart` | — | 购物车已清空。 |
| `create_order` | `product_id`,`quantity`,`address_id?`,`payment_method?` | 订单已创建。 |
| `pay_order` | `order_id` | 订单 N 已完成支付确认。 |

`ConfirmResponse.status` 只有两个取值：

| status | 含义 | HTTP |
| --- | --- | --- |
| `executed` | 已确认并执行成功 | 200 |
| `cancelled` | 用户拒绝，**数据未被修改** | 200 |

> **`cancelled` 是 HTTP 200 的成功响应，不是错误。** 前端必须按 `status` 分支，不能按 HTTP 码分支。

`/confirm` 失败模式：`401` 未登录、`404` 令牌无效/过期/已用、`400` 动作不支持或参数非法、`502` Java 后端拒绝、`429` 限流。

安全约束（后端已实现，前端不得削弱）：令牌绑定 `session_id` + 登录令牌指纹、一次性、有 TTL、仅在用户显式确认后执行写操作。

---

## 3. 技术选型与工程约定

### 3.1 依赖清单

| 依赖 | 用途 |
| --- | --- |
| `vue` | 框架 |
| `pinia` | 状态管理 |
| `vite` + `@vitejs/plugin-vue` | 构建 |
| `typescript` + `vue-tsc` | 类型检查 |
| `vitest` + `@vue/test-utils` + `jsdom` | 测试 |

**不引入**：`vue-router`（单路由）、`axios`（用原生 `fetch`）、任何 UI 组件库、任何 CSS 框架、任何图标库、任何外部字体。

不引入 `axios` 的理由要能讲清楚：SSE 需要 `fetch` + `ReadableStream`，既然流式请求必须手写，再引一个 HTTP 客户端只会造成两套请求路径。

### 3.2 TypeScript 严格模式

`tsconfig.json` 必须开启：

```jsonc
{
  "strict": true,
  "noUncheckedIndexedAccess": true,
  "exactOptionalPropertyTypes": true,
  "noImplicitOverride": true,
  "noFallthroughCasesInSwitch": true,
  "verbatimModuleSyntax": true
}
```

`npm run build` 必须先跑 `vue-tsc --noEmit`。**类型错误一律视为构建失败**，不得用 `any` 或 `@ts-ignore` 绕过。后端返回的数据在进入类型系统前必须经过类型守卫。

### 3.3 依赖方向（单向，禁止反向 import）

```
views → components → stores → api → lib/http
                 ↘ composables ↗
                          ↓
                        types（叶子，不依赖任何业务模块）
```

| 层 | 允许 import | 禁止 |
| --- | --- | --- |
| `types/` | 无 | 任何业务模块 |
| `lib/` | `types/` | `stores`、`components`、`api` |
| `api/` | `types/`、`lib/http` | `stores`、`components` |
| `stores/` | `types/`、`api/`、`lib/` | `components` |
| `composables/` | `types/`、`lib/`、`stores/` | `components` |
| `components/` | `types/`、`lib/`、`stores/`、`composables/` | 兄弟组件之外的 `views/` |
| `views/` | 全部 | — |

**`components/` 不得直接调用 `api/`。** 所有网络请求经由 `stores/` 或 `composables/`。

### 3.4 命名与代码约定

- 组件文件 `PascalCase.vue`；`lib`/`api`/`stores` 用小写文件名。
- 组件用 `<script setup lang="ts">`，props 用 `defineProps<Props>()`，事件用 `defineEmits<Emits>()`。
- 组件内样式一律 `<style scoped>`，禁止新增全局样式（全局只允许 `styles/tokens.css` 与 `styles/base.css`）。
- 禁止在组件里写 `document.querySelector`。所有 DOM 操作交给 Vue。
- 禁止把 token、密码、完整载荷写进 `console.log`。
- 文案中的中文标点、术语与现有前端保持一致（"购物车项"、"价格待确认"、"订单编号"）。

---

## 4. 目录结构与文件职责

```
frontend/
├── index.html                    # Vite 入口，lang="zh-CN"，含 app-init-error 兜底
├── package.json
├── vite.config.ts                # dev 代理 + @ 别名
├── tsconfig.json  tsconfig.node.json  env.d.ts
└── src/
    ├── main.ts                   # createApp + createPinia + 挂载
    ├── App.vue                   # 仅承载 <AppShell />
    ├── styles/
    │   ├── tokens.css            # 设计令牌（唯一变量来源）
    │   └── base.css              # reset、排版、reduced-motion、高对比度
    ├── types/
    │   ├── api.ts                # 1:1 镜像 schemas.py
    │   ├── stream.ts             # StreamEvent 判别联合
    │   ├── results.ts            # ProductRecord / CartRecord / OrderRecord / ResultPayload
    │   └── chat.ts               # 消息模型 ChatMessage / AssistantMessage
    ├── lib/
    │   ├── http.ts               # fetchJson：错误体归一化 + token 注入
    │   ├── sse.ts                # 纯函数：SSE 分片解析器（可单测，无 DOM 依赖）
    │   ├── session.ts            # sessionId 生成/持久化/轮换（sessionStorage）
    │   ├── guards.ts             # isOrderRecord / isCartRecord / isProductRecord / resolveResultPayload
    │   ├── redact.ts             # redactSensitive 递归脱敏（Inspector 用）
    │   ├── format.ts             # formatCurrency / formatDateTime / finiteAmount / finitePositiveInteger
    │   ├── labels.ts             # toolBusinessLabel / toolStatusCopy / confirmationPresentation / 空结果文案
    │   └── reference.ts          # removeCredentialQueryParameters 等 URL 清洗
    ├── api/
    │   ├── auth.ts               # login / restoreSession
    │   ├── chat.ts               # sendChat / streamChat / confirmAction / clearConversation
    │   └── system.ts             # fetchHealth
    ├── stores/
    │   ├── session.ts            # 登录态、token、username、sessionId、pendingAction
    │   ├── chat.ts               # messages、当前 run、confirmation 状态、发送中标志
    │   ├── view.ts               # viewMode('customer'|'developer')、抽屉开关
    │   └── inspector.ts          # 事件时间线、耗时、SSE 连接状态
    ├── composables/
    │   ├── useChatStream.ts      # SSE 编排 + AbortController + 防旧流回写
    │   ├── useHealthPoll.ts      # /health 轮询
    │   ├── useMediaQuery.ts      # 响应式断点
    │   ├── useFocusRestore.ts    # 抽屉焦点陷阱与恢复
    │   └── useSrAnnounce.ts      # aria-live 播报
    ├── components/
    │   ├── shell/                # AppShell / AppSidebar / AppTopbar / ViewSwitch / ShellBackdrop
    │   ├── chat/                 # ChatWorkspace / WelcomeState / MessageList / UserMessage
    │   │                         # AssistantMessage / SystemNotice / StreamingStatus
    │   │                         # ReferenceBar / ComposerBox
    │   ├── results/              # ResultList / ProductCard / CartCard / CartSummary
    │   │                         # OrderCard / OrderItemRow / EmptyResult / RawResult
    │   ├── confirm/              # ConfirmationCard / ConfirmFacts / OperationResult
    │   ├── inspector/            # AgentInspector / InspectorRunHeader / InspectorMetrics
    │   │                         # InspectorTimeline / InspectorEventItem / InspectorFooter
    │   └── common/               # StatusPill / SrAnnouncer
    └── views/
        └── ChatView.vue          # 组装三栏布局
```

**关键文件职责说明：**

- `lib/sse.ts` 必须是**纯函数解析器**，输入 `string` 输出 `StreamEvent[]` 与剩余缓冲，不触碰 `fetch`、不触碰 DOM。这样跨 chunk 边界的行为才能被完整单测。
- `lib/labels.ts` 集中所有中文文案映射，是 1.5 中 G1 缺口的修复点。
- `stores/inspector.ts` 与 `stores/chat.ts` 分离：Inspector 是调试视角的独立数据流，即便用户从未切到调试视角，工具事件仍要完整记录。
- `components/results/RawResult.vue` 是 G4 的落点，渲染未识别数据的折叠 JSON 视图。

---

## 5. 类型契约

**本章代码可直接复制使用，执行者不得改写字段名。**

### 5.1 `types/api.ts`（镜像 `schemas.py`）

```ts
// ---------- /auth/login ----------
export interface LoginRequest {
  username: string
  password: string
}

export interface LoginResponse {
  access_token: string
  token_type: string
}

// ---------- /auth/session ----------
/** 旧前端兼容请求体；Vue 版只发送 Authorization 请求头。 */
export interface AuthSessionRequest {
  access_token: string
}

export interface AuthSessionResponse {
  authenticated: boolean
  username: string | null
}

// ---------- /chat, /chat/stream ----------
export interface ChatRequest {
  message: string
  session_id: string
  access_token?: string | null
}

export type ToolOutcome = 'success' | 'error' | 'clarification_needed' | (string & {})

export interface ToolCallRecord {
  name: string
  arguments: Record<string, unknown>
  outcome: ToolOutcome
  result_message?: string | null
}

export interface ReferenceResolution {
  type: string
  value: string
  source: string
}

export type ConfirmationAction =
  | 'cancel_order'
  | 'refund_order'
  | 'update_cart'
  | 'update_cart_items'
  | 'remove_from_cart'
  | 'clear_cart'
  | 'create_order'
  | 'pay_order'

export interface Confirmation {
  token: string
  action: ConfirmationAction
  description: string
  arguments: Record<string, unknown>
}

export interface ChatResponse {
  answer: string
  tool_calls: ToolCallRecord[]
  confirmation: Confirmation | null
  data: unknown
  reference: ReferenceResolution | null
}

// ---------- /conversation/clear ----------
export interface ClearConversationRequest {
  session_id: string
  access_token?: string | null
}

export interface ClearConversationResponse {
  status: string
  cleared: boolean
}

// ---------- /confirm ----------
export interface ConfirmRequest {
  session_id: string
  confirmation_token: string
  approved: boolean
  access_token?: string | null
}

export type ConfirmStatus = 'executed' | 'cancelled'

export interface ConfirmResponse {
  status: ConfirmStatus
  message: string
  data: unknown
}

// ---------- /health ----------
export interface HealthResponse {
  status: string
  model_configured: boolean
  agent_mode: string
  backend_base_url: string
  checks?: Record<string, string>
}

// ---------- /admin/config ----------
export interface RuntimeConfigResponse {
  force_demo: boolean
  disabled_tools: string[]
  max_tool_rounds: number | null
}
```

### 5.2 `types/stream.ts`（10 个 SSE 事件）

```ts
import type {
  ChatResponse,
  ConfirmationAction,
  ReferenceResolution,
  ToolOutcome,
} from './api'

export interface SseStarted {
  message: string
}

export interface SseProgress {
  message: string
}

export interface SseLlmTrace {
  calls: unknown[]
}

export interface SseClarification {
  tool: string
  message: string | null
}

export interface SseToolError {
  name: string
  error: string | null
}

export interface SseTool {
  name: string
  outcome: ToolOutcome
  arguments: Record<string, unknown>
}

export interface SseConfirmationRequired {
  action: ConfirmationAction
}

export interface SseError {
  detail: string
}

export type StreamEvent =
  | { type: 'started'; data: SseStarted }
  | { type: 'progress'; data: SseProgress }
  | { type: 'llm_trace'; data: SseLlmTrace }
  | { type: 'reference'; data: ReferenceResolution }
  | { type: 'clarification'; data: SseClarification }
  | { type: 'tool_error'; data: SseToolError }
  | { type: 'tool'; data: SseTool }
  | { type: 'confirmation_required'; data: SseConfirmationRequired }
  | { type: 'result'; data: ChatResponse }
  | { type: 'error'; data: SseError }
```

### 5.3 `types/results.ts`（记录与判别联合）

```ts
export interface ProductRecord {
  id?: number | string | null
  name?: string | null
  price?: number | string | null
  stock?: number | string | null
  status?: number | string | null
  description?: string | null
  categoryId?: number | string | null
}

export interface CartRecord {
  cartId?: number | string | null
  productId?: number | string | null
  productName?: string | null
  price?: number | string | null
  quantity?: number | string | null
}

export interface OrderItemRecord {
  productId?: number | string | null
  productName?: string | null
  quantity?: number | string | null
  unitPrice?: number | string | null
  totalPrice?: number | string | null
}

export interface OrderRecord {
  id?: number | string | null
  orderNo?: string | null
  status?: number | string | null
  paymentStatus?: number | string | null
  createdAt?: string | null
  items?: OrderItemRecord[]
  totalAmount?: number | string | null
  discountAmount?: number | string | null
  finalAmount?: number | string | null
}

/** 商品搜索的匹配依据，来自 search_products / get_product_detail 的入参 */
export interface ProductSearchContext {
  keyword?: string
  max_price?: number | string
  min_price?: number | string
  in_stock?: boolean
  [key: string]: unknown
}

export type ResultKind = 'product' | 'cart' | 'order'

export type ResultPayload =
  | { kind: 'product'; items: ProductRecord[]; context: ProductSearchContext }
  | { kind: 'cart'; items: CartRecord[] }
  | { kind: 'order'; items: OrderRecord[] }
  | { kind: 'empty'; emptyKind: ResultKind }
  | { kind: 'raw'; value: unknown }
  | { kind: 'none' }
```

`kind: 'raw'` 对应 1.5 的 G4；`kind: 'none'` 表示后端未返回 `data`，两种情况都不渲染结果区标题。

### 5.4 `types/chat.ts`（消息模型）

```ts
import type { Confirmation, ReferenceResolution } from './api'
import type { ResultPayload } from './results'

export type MessageStatusTone = 'loading' | 'success' | 'warning' | 'error'

export interface MessageStatus {
  text: string
  tone: MessageStatusTone
}

export interface PromptAction {
  prompt: string
  label: string
  authRequired: boolean
}

export type RunPhase = 'connecting' | 'streaming' | 'done' | 'error' | 'cancelled'

export type ConfirmationPhase =
  | 'pending'
  | 'submitting'
  | 'executed'
  | 'cancelled'
  | 'failed'

export interface UserMessage {
  id: string
  role: 'user'
  text: string
  at: number
}

export interface SystemNotice {
  id: string
  role: 'system'
  text: string
  at: number
}

/**
 * 一条助手消息是若干可选块的容器，不是一段文字。
 * text / status / reference / results / confirmation 各自独立，可任意缺失。
 */
export interface AssistantMessage {
  id: string
  role: 'assistant'
  /** 与本次运行绑定，用于防止旧流的写回污染新会话 */
  runId: string
  at: number
  text: string
  status: MessageStatus | null
  reference: ReferenceResolution | null
  results: ResultPayload
  confirmation: Confirmation | null
  confirmationPhase: ConfirmationPhase
  confirmationResult: { message: string; data: unknown } | null
  streamPhase: RunPhase
}

export type ChatMessage = UserMessage | AssistantMessage | SystemNotice
```

---

## 6. 状态与数据流

### 6.1 单向数据流

```
组件事件 → store action → api/ → lib/http → 后端
                ↑                              │
                └──── 结果写入 store state ←───┘
                            ↓
                    组件响应式重渲染
```

组件**不持有业务状态**，只持有纯 UI 状态（展开/折叠、输入框草稿）。典型反例是把消息列表放在 `ChatWorkspace.vue` 的 `ref` 里——必须放 store。

### 6.2 `stores/session.ts`

```ts
state: {
  accessToken: string | null      // sessionStorage: ordermate_token
  username: string | null         // sessionStorage: ordermate_username
  sessionId: string               // sessionStorage: ordermate_session
  authStatus: 'anonymous' | 'checking' | 'authenticated'
  pendingAction: { prompt: string; label: string } | null
}
getters: {
  isAuthenticated
}
actions: {
  login(username, password)          // POST /auth/login
  restore()                          // POST /auth/session，失败则 clear()
  clear()                            // 清 token + username，保留 sessionId
  rotateSession()                    // 生成新 sessionId 并持久化
  requestLoginForAction(prompt, label)
  consumePendingAction()
}
```

**持久化策略（安全约束，不得改动）：**

- token 存 **`sessionStorage`**，不存 `localStorage`。`sessionStorage` 是 per-tab 隔离的，浏览器关闭即清除，且天然支持"多个面试官各自独立会话"。
- 启动时调用 `lib/reference.ts` 的 `removeCredentialQueryParameters()`，清除 URL 中的 `username` / `password` / `access_token` / `token` 参数，用 `history.replaceState` 重写地址且不新增历史记录。
- `clear()` 清除 token、username、`authStatus` 与 `pendingAction`，**不清 `sessionId`**，这样可以保留匿名会话的上下文。

### 6.3 `stores/chat.ts`

```ts
state: {
  messages: ChatMessage[]
  activeRunId: string | null
  sending: boolean
  lastError: string | null
  backoffUntil: number | null      // 429 退避
}
getters: {
  hasConversation
  latestAssistant
}
actions: {
  send(text)                 // 追加用户消息 → 建助手占位消息 → 调 useChatStream
  cancel(reason)
  applyStreamEvent(runId, event)
  finalizeRun(runId, response)
  failRun(runId, message)
  confirm(approved)          // POST /confirm
  clearConversation()        // POST /conversation/clear + 重置消息
}
```

**防旧流回写（核心不变量）：** 每个 action 接收 `runId`。写入 state 前必须校验 `runId === this.activeRunId`，不匹配则**直接丢弃**。新建会话、退出登录、切换视角都不改变这条规则。此不变量必须有单测覆盖。

### 6.4 `lib/guards.ts` 的解析入口

```ts
export function normalizeResultRecords(data: unknown): unknown[]
export function isOrderRecord(item: unknown): item is OrderRecord
export function isCartRecord(item: unknown): item is CartRecord
export function isProductRecord(item: unknown): item is ProductRecord

/**
 * 两步判定：先按工具名，再按字段嗅探。
 * 无法判定时返回 { kind: 'raw', value }，data 为 null/undefined 时返回 { kind: 'none' }。
 */
export function resolveResultPayload(
  data: unknown,
  toolCalls: ToolCallRecord[],
): ResultPayload
```

`resolveResultPayload` 是 G1–G4 四个缺口的统一修复点。实现要求：

- 工具名列表必须包含 `update_cart_items` 与 `refund_order`（G1/G2/G3）。
- 判定顺序固定 `order → cart → product`。
- 判定不出类型时返回 `raw`，**绝不返回 `none`**（G4）。`none` 只用于 `data` 为空。

---

## 7. `useChatStream` 行为规范

这是整个前端最容易出错的地方，行为必须逐条实现。

### 7.1 接口

```ts
export interface UseChatStream {
  send(input: {
    message: string
    sessionId: string
    accessToken: string | null
    runId: string
  }): Promise<ChatResponse | null>
  cancel(reason?: 'user' | 'rotate'): void
  phase: Ref<RunPhase>
  events: Ref<StreamEvent[]>
  cancelReason: Ref<'user' | 'rotate' | null>
}

export function useChatStream(
  onEvent: (runId: string, event: StreamEvent) => void,
): UseChatStream
```

### 7.2 必须实现的行为

1. **必须用 `fetch` + `response.body.getReader()`。** `EventSource` 只支持 GET，而 `/chat/stream` 是 POST，不可用。
2. **必须用 `AbortController`。** `send()` 开始时创建，`cancel()` 调用 `abort()`。组件卸载时也要 abort。
3. **解析委托给 `lib/sse.ts` 的纯函数**，不得在 composable 内联解析逻辑。分片边界处理：
   - 累积 `buffer`，按 `/\r?\n\r?\n/` 切帧，**最后一段留回 buffer**（它可能是半帧）。
   - 流结束时若 buffer 仍有非空内容，也要作为一帧处理。
   - 每个 `data:` 行要支持多行拼接（服务端目前是单行，但协议允许多行，属防御性实现）。
4. **`response.ok` 必须先检查。** 非 2xx 时按 JSON 读取并抛错，错误体可能是 `{detail}` 或 `{error, detail}` 两种形态（见 2.3）。`422` 时 `detail` 是数组，需归一化。
5. **`error` 事件必须抛异常**，不能静默吞掉，也不能当作正常结束。
6. **未收到 `result` 就结束流 = 失败。** 抛"流式响应意外结束"。
7. **`cancel()` 后不得再写 state。** abort 会导致 `send()` 抛 `AbortError`，必须捕获并按 `cancelReason` 区分处理，**不当作错误展示**。
8. **`progress` 事件不得累积到 `events` 之外**。时间线只保留有信息量的事件；`progress` 只更新当前状态文案。若全量保留 `progress`（每 0.75s 一条），长回答会产生上百条记录。
9. **`tool` 事件必须每次都记录**，即使同一工具已产生 `tool_error` 或 `clarification`。
10. **超时保护**：整个请求设置上限（建议 120s），超时按失败处理并给出"响应超时"文案，避免公网下无限挂起。

### 7.3 状态机

```
idle → connecting → streaming → done
                        ├──────→ error
                        └──────→ cancelled
```

`done` 仅在收到 `result` 时进入。`cancelled` 由 `cancel()` 触发。任何其他结束方式都进 `error`。

---

## 8. 组件清单

每个组件下方标注数据来源与关键要求。`props` 为必填，除非标 `?`。

### 8.1 `shell/`

| 组件 | props | emits | 要求 |
| --- | --- | --- | --- |
| `AppShell.vue` | — | — | 承载三栏骨架，`data-view` 属性由 `view` store 驱动 |
| `AppSidebar.vue` | — | — | 账号区、新建会话、快捷功能、服务状态、安全说明 |
| `AppTopbar.vue` | — | — | 品牌、`ViewSwitch`、在线状态 |
| `ViewSwitch.vue` | `modelValue: 'customer' \| 'developer'` | `update:modelValue` | `role="tablist"`，支持左右方向键切换 |
| `ShellBackdrop.vue` | `open: boolean` | `close` | 移动端抽屉遮罩 |

### 8.2 `chat/`

| 组件 | props | emits | 要求 |
| --- | --- | --- | --- |
| `ChatWorkspace.vue` | — | — | 无消息时渲染 `WelcomeState`，否则 `MessageList`；底部固定 `ComposerBox` |
| `WelcomeState.vue` | — | `prompt(text)` | 4 张能力卡片；未登录时标注需登录的能力 |
| `MessageList.vue` | `messages: ChatMessage[]` | `prompt`, `confirm` | 按 `role` 分发；新消息到达时滚动到底部（仅当用户已在底部附近） |
| `UserMessage.vue` | `message: UserMessage` | — | 纯文本渲染，**不使用 `v-html`** |
| `AssistantMessage.vue` | `message: AssistantMessage` | `prompt`, `confirm` | 依次渲染 `StreamingStatus` / `ReferenceBar` / `ResultList` / `ConfirmationCard`，各自独立可缺 |
| `SystemNotice.vue` | `message: SystemNotice` | — | 居中弱化样式 |
| `StreamingStatus.vue` | `status: MessageStatus \| null`, `phase: RunPhase` | — | 流式期间显示 loading 动效；`prefers-reduced-motion` 下改为静态 |
| `ReferenceBar.vue` | `reference: ReferenceResolution` | — | 展示"已找到相关订单/商品"的指代解析结果 |
| `ComposerBox.vue` | `disabled: boolean`, `sending: boolean` | `send(text)`, `cancel` | 自适应高度；Enter 发送、Shift+Enter 换行；发送中变为取消按钮 |

### 8.3 `results/`

| 组件 | props | emits | 要求 |
| --- | --- | --- | --- |
| `ResultList.vue` | `payload: ResultPayload` | `prompt` | 按 `kind` 分发；`none` 不渲染 |
| `ProductCard.vue` | `product: ProductRecord`, `context: ProductSearchContext` | `prompt` | 库存三态（有货/暂时缺货/库存待确认/已下架）；匹配依据最多 3 条；**不得显示任何图片** |
| `CartCard.vue` | `item: CartRecord` | `prompt` | 数量/小计缺失时显示"—"/"金额待确认" |
| `CartSummary.vue` | `items: CartRecord[]` | `prompt` | 合计仅在全部小计可计算时显示"合计"，否则"已知金额" |
| `OrderCard.vue` | `order: OrderRecord` | `prompt` | 仅 `status === 0` 时显示取消按钮 |
| `OrderItemRow.vue` | `item: OrderItemRecord` | — | `totalPrice` 缺失时用 `unitPrice × quantity` 兜底 |
| `EmptyResult.vue` | `kind: ResultKind` | `prompt` | 三种空态文案与引导按钮 |
| `RawResult.vue` | `value: unknown` | — | **G4**：折叠展示未识别数据，标注"未识别的数据结构" |

金额与数量的格式化必须走 `lib/format.ts`：`finiteAmount`（`>= 0` 才算有效）、`finitePositiveInteger`（正整数才算有效）、`formatCurrency`（`zh-CN` / `CNY` / 0 位小数）。**无效值一律降级为文案，不得显示 `NaN`、`undefined`、`null`。**

### 8.4 `confirm/`

| 组件 | props | emits | 要求 |
| --- | --- | --- | --- |
| `ConfirmationCard.vue` | `confirmation: Confirmation`, `phase: ConfirmationPhase`, `result: {...} \| null` | `confirm(approved: boolean)` | `role="alertdialog"`、`aria-modal="false"`、`aria-labelledby` 指向标题 |
| `ConfirmFacts.vue` | `action: ConfirmationAction`, `args: Record<string, unknown>` | — | 按动作生成事实清单（如 `clear_cart` 显示"影响范围：当前购物车全部商品"） |
| `OperationResult.vue` | `phase`, `message`, `data` | — | `executed` / `cancelled` / `failed` 三种呈现；`cancelled` **不得显示为错误色** |

`ConfirmationCard` 要求：

- 必须覆盖**全部 8 个动作**的展示配置（修复 G1），未知动作降级为通用展示，不崩溃。
- 提交中禁用两个按钮，防止重复提交（后端令牌一次性，重复提交会得到 `404`）。
- `executed` 后卡片变为只读结果，不可再次操作。

### 8.5 `inspector/`

| 组件 | props | emits | 要求 |
| --- | --- | --- | --- |
| `AgentInspector.vue` | — | — | 仅调试视角渲染；中屏为右侧抽屉 |
| `InspectorRunHeader.vue` | `title: string`, `state: string`, `query: string` | — | 当前运行概览 |
| `InspectorMetrics.vue` | `elapsedMs: number`, `toolCount: number` | — | 标注"浏览器观测时长"，**不得声称是服务端耗时** |
| `InspectorTimeline.vue` | `events: StreamEvent[]` | — | 有序时间线 |
| `InspectorEventItem.vue` | `event: StreamEvent`, `elapsedMs: number` | — | 展示工具名、状态、脱敏入参 |
| `InspectorFooter.vue` | `sseStatus`, `model`, `sessionId` | — | SSE 空闲/流式中/完成状态 |

Inspector 要求：

- 工具名映射到业务语言（`toolBusinessLabel`），不直接暴露内部函数名给客户视角。
- **所有载荷经 `lib/redact.ts` 递归脱敏**：`password`、`token`、`access_token`、`authorization`、`cookie`、`api_key`、`secret` 等键名不区分大小写匹配，命中则替换为 `"[已脱敏]"`。
- 客户端观测时长必须明确标注口径，与服务端逐工具耗时区分（服务端目前不提供该字段）。
- 客户视角下 **Inspector 不渲染**，但事件记录不停。

### 8.6 `common/`

| 组件 | props | 要求 |
| --- | --- | --- |
| `StatusPill.vue` | `tone`, `text` | 状态标签 |
| `SrAnnouncer.vue` | — | 全局 `aria-live="polite"` 区域，由 `useSrAnnounce` 写入 |

---

## 9. 样式与设计令牌

### 9.1 令牌策略

**唯一变量来源是 `styles/tokens.css`。** 现有 `styles.css` 中新旧两套变量并存（旧的 `--ink` / `--deep` / `--paper` / `--line` / `--muted` / `--danger` / `--accent`，新的 `--color-*` 语义体系）。Vue 版**只保留 `--color-*` 与功能令牌**，统一命名，不再保留旧别名。

需要覆盖的令牌类别：

| 类别 | 示例 |
| --- | --- |
| 颜色 | `--color-canvas`、`--color-surface`、`--color-surface-raised`、`--color-ink`、`--color-muted`、`--color-line`、`--color-primary`、`--color-ai`、`--color-success`、`--color-warning`、`--color-danger` 及各自 `-soft` / `-hover` 变体 |
| 深色面板 | `--color-navy`、`--color-navy-raised`、`--color-on-dark`、`--color-on-dark-muted` |
| 间距 | `--space-1` 至 `--space-10` |
| 圆角 | `--radius-sm/md/lg/xl/pill` |
| 字号 | `--text-xs/sm/base/lg/xl/2xl` |
| 行高 | `--leading-tight/normal/relaxed` |
| 字体 | `--font-sans`、`--font-display`、`--font-mono` |
| 阴影 | `--shadow-sm/md/lg`、`--shadow-focus` |
| 动效 | `--duration-fast/normal`、`--ease-standard` |
| 控件 | `--control-height-sm/md` |

视觉风格**保持现有**：深海军蓝 + 冷白 + 科技蓝 + AI 紫。不重新设计视觉，只做令牌归一化与组件化。

### 9.2 布局

三栏结构（与现有实现一致）：

```
┌──────────┬────────────────────────────┬──────────────┐
│ Sidebar  │  Topbar                    │              │
│ (账号/   ├────────────────────────────┤ Inspector    │
│  快捷/   │  Workspace                 │ (仅调试视角) │
│  状态)   │  ├ 消息列表 / 欢迎态        │              │
│          │  └ Composer (固定底部)      │              │
└──────────┴────────────────────────────┴──────────────┘
```

响应式断点（沿用 `styles.css` 现有行为，数值已核对）：

| 断点 | 行为 |
| --- | --- |
| `> 1100px` | 三栏并排，Inspector 常驻（调试视角） |
| `≤ 1100px` | Inspector 变为绝对定位的右侧抽屉，宽度 `min(380px, 92vw)`，调试视角出现遮罩 |
| `≤ 900px` | Sidebar 变为 `fixed` 抽屉（`translateX(-100%)`），显示汉堡按钮，两种遮罩共用 |
| `≤ 680px` | 顶栏压缩至 68px，隐藏 eyebrow 与在线状态 |

### 9.3 无障碍（既有要求，不得退化）

- 跳转链接 `href="#workspace"`。
- `aria-live="polite"` 播报异步状态（回复完成、错误、登录变化）。
- 视角切换用 `role="tablist"` + 方向键，`tabindex` 管理。
- Esc 关闭抽屉并**恢复焦点到触发按钮**。
- 粗指针设备（`pointer: coarse`）关键触控目标高度 ≥ 44px。
- `@media (prefers-reduced-motion: reduce)` 关闭动效。
- 支持 Windows 高对比度模式（`forced-colors`）。
- 焦点可见：统一的 `--shadow-focus` 焦点环，禁止 `outline: none` 而无替代。

### 9.4 体积约束

原生前端继续沿用 `test_frontend_contract.py` 的 **160 KiB** 限制；该数字不直接套用到包含 Vue runtime 与 Pinia 的新产物。

Vue 版采用两级预算：

- Phase 0 构建空壳后记录 JS、CSS 的 Vite 生产构建基线。
- 首次实施暂定 JS + CSS 的**未 gzip 生产文件**合计不超过 **220 KiB**，gzip 合计不超过 **75 KiB**；Phase 0 结束时根据实测基线冻结最终阈值。

若超过预算，先排查误引入依赖、重复样式和无法 tree-shake 的导入。阈值如需调整，必须在构建报告中说明新增体积来自哪些功能，不能静默放宽。

---

## 10. 部署接入

### 10.1 开发环境

`vite.config.ts`：

```ts
server: {
  port: 5173,
  proxy: {
    '/health': 'http://localhost:8000',
    '/auth': 'http://localhost:8000',
    '/chat': 'http://localhost:8000',
    '/confirm': 'http://localhost:8000',
    '/conversation': 'http://localhost:8000',
  },
}
```

前端所有请求使用**相对路径**（`baseURL = ''`），于是开发与生产**代码零差异**，不需要 `.env.production`，也不需要配置 CORS。

> 因为选择了单路由（无 `vue-router`），应用所有页面都在 `/`，**不存在 SPA 深链接回退问题**，Nginx 配置比标准 SPA 更简单。

### 10.2 生产环境（Nginx）

Nginx 托管 `frontend/dist`，并精确反代 API。`limit_req_zone` 必须定义在 `http` 上下文，不能放进 `server`。嵌套路由使用前缀匹配，避免 `/auth/login`、`/auth/session`、`/conversation/clear` 被 SPA fallback 错误返回为 `index.html`：

```nginx
http {
    limit_req_zone $binary_remote_addr zone=chat:10m rate=30r/m;
    limit_req_zone $binary_remote_addr zone=global:10m rate=120r/m;

    server {
        listen 80;
        server_name your-domain.example;

        root /srv/ordermate/frontend/dist;
        index index.html;

        location = /chat/stream {
            limit_req zone=chat burst=5 nodelay;
            proxy_pass http://127.0.0.1:8000;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_buffering off;
            proxy_cache off;
            proxy_read_timeout 300s;
        }

        location = /chat {
            limit_req zone=global burst=40 nodelay;
            proxy_pass http://127.0.0.1:8000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        }

        location ^~ /auth/ {
            limit_req zone=global burst=40 nodelay;
            proxy_pass http://127.0.0.1:8000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        }

        location = /confirm {
            limit_req zone=global burst=40 nodelay;
            proxy_pass http://127.0.0.1:8000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        }

        location ^~ /conversation/ {
            limit_req zone=global burst=40 nodelay;
            proxy_pass http://127.0.0.1:8000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        }

        location = /health {
            limit_req zone=global burst=40 nodelay;
            proxy_pass http://127.0.0.1:8000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        }

        location = /index.html {
            add_header Cache-Control "no-cache, no-store, must-revalidate";
        }

        location /assets/ {
            add_header Cache-Control "public, max-age=31536000, immutable";
        }

        location / {
            try_files $uri /index.html;
        }
    }
}
```

要点：

- `proxy_buffering off` 与 `proxy_read_timeout 300s` 是 SSE 生效的必要条件。
- **`X-Real-IP` / `X-Forwarded-For` 必须转发**，同时 Uvicorn 只信任 Nginx 所在地址的代理头；不得无条件信任公网传入的伪造头。否则后端按 IP 限流会退化成代理地址或被绕过。
- `index.html` 禁止缓存；Vite 带 hash 的 `/assets/` 使用长期 immutable 缓存。
- `/admin/*` 与 `/metrics` 不配置公网反代；仅由内网运维访问。
- `dist` 不含任何外部字体或图片资源，因此 CSP 可以设得很紧。

### 10.3 Docker Compose 变更

新增 `frontend` 构建阶段，并由独立 Nginx 容器提供 `dist`、反代 Agent API。开发阶段仍由 Vite 代理，不修改现有原生前端入口；部署接入在最终交付阶段一次完成。

`docs/deployment.md` 需同步补充：前端构建命令、Nginx 站点配置、限流参数、SSE 验证步骤。

### 10.4 公网运行策略（已定）

| 项 | 决策 |
| --- | --- |
| 运行模式 | 公网 `AGENT_MODE=demo`；`live` 仅管理员本地使用 |
| 模型成本 | demo 模式零模型成本，无 Key 泄露风险 |
| 会话隔离 | `session_id` 仅隔离 Agent 对话、引用和确认状态，不代表 Java 业务数据隔离 |
| 业务数据隔离 | 公网发布前必须二选一：为访客分配独立演示账号/数据，或禁用共享账号的写操作 |
| 写操作 | 本地面试演示保留完整写能力；公网只有完成业务数据隔离后才开放，定时重置只能清理数据，不能替代隔离 |
| 管理接口 | `/admin/*` 不在 Nginx 中反代，公网不可达 |
| 兜底方案 | 面试现场另备本地 `docker compose` + Cloudflare Tunnel |

若将来需要定时重置演示数据，应另建专用脚本，并在重置前后打印当前订单数以便核验。

> **发布门禁：**若仍使用共享 `testuser`，Vue 公网页面只能开放匿名查询和只读演示。购物车、下单、支付、取消、退款等写操作不得仅依赖 `session_id` 宣称隔离。

---

## 11. 测试与验收标准

### 11.1 四层测试

| 层 | 工具 | 覆盖对象 | 数量下限 |
| --- | --- | --- | --- |
| 纯函数单测 | Vitest | `lib/sse.ts`、`lib/guards.ts`、`lib/redact.ts`、`lib/format.ts` | 每个导出函数至少 1 例 |
| 组件测试 | Vitest + `@vue/test-utils` | `ProductCard`、`CartCard`、`OrderCard`、`ConfirmationCard`、`AssistantMessage`、`RawResult` | 每组件至少 2 例 |
| 编排测试 | Vitest | `useChatStream`、`stores/chat` | 见 11.2 |
| 构建产物契约 | Vitest（node 环境） | `dist/` 产物 | 见 11.3 |

### 11.2 必须有测试覆盖的行为（逐条对应前文规范）

**`lib/sse.ts`：**
1. 单帧解析。
2. 事件被切在任意位置时仍能正确解析（跨 chunk 边界）。
3. 一次 chunk 含多帧。
4. 流结束时有残留 buffer。
5. `data` 为多行时正确拼接。
6. 非法 JSON 抛出明确错误。
7. 未知事件名不崩溃（向前兼容新事件）。

**`lib/guards.ts`：**
8. 工具名优先于字段嗅探。
9. `update_cart_items` 判定为 `cart`（G3）。
10. `refund_order` 判定为 `order`（G2）。
11. `order → cart → product` 顺序：同时具备 `orderNo` 与商品特征时判为订单。
12. 无法识别时返回 `raw`，**不返回 `none`**（G4）。
13. `data` 为 `null`/`undefined` 时返回 `none`。
14. `{ content: [...] }` 包装被正确解包。

**`lib/redact.ts`：**
15. 嵌套对象与数组中的敏感键被递归脱敏。
16. 键名大小写不敏感（`Access_Token` 也要命中）。
17. 原始对象不被修改（纯函数）。

**`lib/format.ts`：**
18. `null` / `undefined` / `""` / `NaN` / `"abc"` 一律降级为文案，不产生 `NaN`。
19. 负金额按无效处理（`finiteAmount` 要求 `>= 0`）。
20. 小数数量按无效处理（`finitePositiveInteger` 要求正整数）。

**`useChatStream`：**
21. 正常流：依次收到 `started`/`tool`/`result`，`phase` 终态为 `done`。
22. 收到 `error` 事件时抛异常，`phase` 为 `error`。
23. **流结束但无 `result` 时判定为失败**（2.2 第 3 条）。
24. 非 2xx 响应被正确识别，且 `{detail}` 与 `{error, detail}` 两种错误体都能解析。
25. `422` 的数组型 `detail` 归一化为字符串。
26. `cancel()` 后不再写入 state，且不展示为错误。
27. `tool_error` 之后同一个 `tool` 事件仍被记录（2.2 第 1 条）。

**`stores/chat`：**
28. **旧 `runId` 的事件被丢弃**（防旧流回写）。
29. `confirm()` 在 `phase === 'submitting'` 时不可重入。
30. `ConfirmResponse.status === 'cancelled'` 时消息**不标记为错误**（2.6）。

### 11.3 构建产物契约测试

新增 `frontend/tests/dist-contract.test.ts`，在 `npm run build` 之后运行：

- `dist/index.html` 不含任何 `http://` / `https://` 外部资源引用。
- 产物中不含 `data:image` 以外的图片引用（本项目无图片）。
- JS + CSS 的生产文件合计与 gzip 合计均不超过 9.4 节冻结后的预算；测试输出实际大小与相对 Phase 0 基线的增量。
- 产物中不出现 `api_key`、`secret`、`password` 字面量（防止误打包配置）。

`agent-service/tests/test_frontend_contract.py` **保持原样并继续通过**，它守护的是 `agent-service/app/static`。

### 11.4 完成定义（DoD）

一个任务只有同时满足以下条件才算完成：

1. `npm run build` 通过且 `vue-tsc --noEmit` 无错误。
2. 该任务新增/修改的文件对应的测试全部通过。
3. `npm run test` 全绿，无跳过、无 `.only`。
4. 未引入第 3.1 节清单之外的依赖。
5. 依赖方向符合 3.3，无反向 import。
6. 无 `any`、无 `@ts-ignore`、无 `console.log`。
7. 该任务涉及的文案与现有前端一致。

### 11.5 手工验收清单

- [ ] 客户视角看不到任何工具名或内部参数。
- [ ] 调试视角能看到完整时间线，且敏感字段显示为 `[已脱敏]`。
- [ ] 未登录时点击购物车/订单能力，引导登录并在登录后继续原操作。
- [ ] 搜索商品后卡片显示匹配依据与库存状态，**无图片**。
- [ ] 取消订单时出现确认卡片，拒绝后显示"数据没有被修改"且不为错误色。
- [ ] 流式过程中点"取消"，界面立即停止且不残留转圈状态。
- [ ] 新建会话后，上一个会话的迟到响应**不污染**新会话。
- [ ] 键盘可完成：切视角、发消息、确认/拒绝、关闭抽屉并恢复焦点。
- [ ] `prefers-reduced-motion` 下无动画。
- [ ] 移动端宽度下侧栏与 Inspector 均为抽屉，可 Esc 关闭。

### 11.6 原生版 / Vue 版功能等价验收记录

| 能力 | 自动化证据 | 真实浏览器状态 |
| --- | --- | --- |
| 健康状态、登录与恢复 | API、Session Store、Topbar/Sidebar 测试通过 | 待 Java + Agent 环境验收 |
| 登录后续办 | 必须再次选择“继续执行/暂不继续”，Sidebar 测试通过 | 待真实登录验收 |
| SSE 对话、停止与防旧流回写 | `useChatStream`、Chat Store 测试通过 | 待真实流式响应验收 |
| 商品、购物车和订单卡片 | 结果守卫及业务卡片组件测试通过 | 待真实业务数据验收 |
| 8 类高风险确认 | 状态机、确认卡及取消中性色测试通过 | 待真实一次性令牌验收 |
| 开发者 Inspector | 完整时间线、业务名称、递归脱敏测试通过 | 待真实 SSE 时间线验收 |
| 新建会话 | Session/Chat Store 清理与旧运行隔离测试通过 | 待服务端会话清理验收 |
| 响应式与无障碍 | Shell、焦点、读屏、CSS 偏好测试通过 | 待 Chrome 键盘/读屏/移动宽度验收 |

当前有意差异：Vue 版不提供写死演示密码的“一键填入”按钮；高风险“取消订单”不放在全局快捷入口，改由订单卡或自然语言发起；文案与快捷问题经过精简，但对应业务能力保留。Vue 版尚未切换公网主入口，原生前端继续作为回退版本。

本表只把自动化验证标记为完成。由于 Java、Agent 与 Vue 服务未运行，真实浏览器列不得提前勾选。

---

## 12. 任务拆分与执行顺序

### 12.1 拆分原则

1. **先修接入前置问题，再写 UI。** SSE 鉴权语义、令牌传递方式和生产反代路由未确认前，不进入组件开发。
2. **先纵向闭环，后横向铺组件。** 第一版必须先跑通健康检查、登录、SSE 对话和文本结果，避免目录齐全但主流程不可用。
3. **每个阶段都必须可运行、可演示、可回退**，原生前端始终保留。
4. 类型与纯函数公开签名冻结后再扩展结果卡片；发现契约偏差必须同步更新本文档。
5. 公网部署是独立发布门禁，不能用前端完成代替业务数据隔离与安全验收。

### 12.2 Phase 0 — 接入前置与基础契约（已完成）

| 任务 | 文件 | 交付物 |
| --- | --- | --- |
| P0-1 SSE 鉴权前置 | `agent-service/app/main.py` 及对应测试 | 失效 token 在流开始前返回 JSON `401`；有效请求行为不变 |
| P0-2 脚手架 | `frontend/package.json`、Vite/TS 配置、入口文件 | 开发服务器与生产构建可运行；记录空壳 raw/gzip 体积基线 |
| P0-3 类型与协议 | `src/types/**`、`src/lib/http.ts`、`src/lib/sse.ts` | 请求头令牌策略、错误归一化、SSE 分片解析测试通过 |
| P0-4 基础纯函数 | `src/lib/format.ts`、`redact.ts`、`guards.ts`、`session.ts`、`reference.ts`、`labels.ts` | 第 11.2 节中对应纯函数测试通过 |

**Phase 0 完成标志**：记录空壳构建体积并冻结 `types/`、`lib/` 的公开签名。此后变更必须同步修订本文档和测试。

### 12.3 Phase 1 — 最小纵向闭环（代码与自动验证已完成）

本阶段只实现一条从浏览器到 Agent 的完整路径：

- `/health` 状态展示。
- 登录、恢复登录与退出；统一使用 Authorization 请求头。
- 输入问题、消费 `/chat/stream`、显示 `started/progress/result/error`。
- 文本回答与 `raw` 结果兜底。
- AbortController 取消、防旧 `runId` 回写、新建会话。
- 最小可用的桌面与移动布局。

验收：使用 demo 模式可以从空白浏览器完成“打开页面 → 登录 → 提问 → 流式收到回答 → 新建会话”，并通过 `useChatStream` 与 store 的核心测试。此时即使尚无业务卡片，也必须是可运行产品。

当前状态：代码、自动化测试、生产构建和开发入口 HTTP 验证已完成；进入下一阶段前仍建议在 Java 与 Agent 服务同时运行时走一遍上述浏览器人工路线，作为环境级联调确认。

### 12.4 Phase 2 — 业务结果与确认闭环（代码与自动验证已完成）

- 实现商品、购物车、订单与 `RawResult` 卡片。
- 覆盖 G1–G4，字段缺失时降级显示，不编造规格。
- 实现 8 个高风险动作的确认、拒绝、过期和失败状态。
- `cancelled` 显示为正常拒绝结果，不使用错误色。
- 完成客户视角的主要手工演示路线与组件测试。

### 12.5 Phase 3 — 双视角与质量完善（自动化质量已完成，待浏览器等价验收）

- 实现开发者视角、Inspector、时间线与递归脱敏。
- 完成三栏/抽屉响应式、键盘操作、焦点恢复、读屏播报、减少动效和高对比度支持。
- 跑完第 11 章的纯函数、组件、编排和构建产物测试。
- 对照原生前端完成一次功能等价验收，记录有意差异。

当前结论（2026-09-28）：前三项代码与自动化验收已经完成，原生版/Vue 版等价矩阵及有意差异已记录。当前为 **40 个测试文件 / 141 项常规测试**和 **5 项构建产物契约测试**全部通过；JS + CSS 合计 raw `154.99 kB`、gzip `49.91 kB`，未超过冻结预算。真实登录、SSE、业务数据、一次性确认令牌、响应式抽屉和读屏器仍需浏览器环境验收；完成前不把 Phase 3 标记为全部完成。

### 12.6 Phase 4 — 部署与公网发布门禁

- 增加 Nginx 容器和前端构建阶段，按 10.2 验证所有 API 路由与 SSE 不缓冲。
- 验证代理头信任范围、限流、缓存策略以及 `/admin/*`、`/metrics` 不可从公网访问。
- 完成业务数据隔离方案；未完成时，公网共享账号保持只读。
- 更新 `docs/deployment.md`、README、架构文档和演示文档，明确 Vue 主入口与原生兜底入口。
- 验证回滚：移除或停止 Vue/Nginx 后，原生 FastAPI 页面仍可访问。

### 12.7 关键路径

```text
接入前置与契约 → 最小纵向闭环 → 业务卡片与确认 → Inspector/无障碍/测试 → 部署与公网门禁
```

不得跳过 Phase 1 直接批量创建所有组件。Phase 1 是最早的可演示里程碑，Phase 4 是唯一允许切换公网主入口的阶段。

### 12.8 风险与应对

| 风险 | 影响 | 应对 |
| --- | --- | --- |
| Phase 0 契约不完整 | 后续各层自行猜测类型，产生返工 | 冻结前用第 5 章逐字核对；冻结后改动必须回写本文件 |
| `useChatStream` 的防旧流逻辑写错 | 演示时出现"上一条回答串台" | 11.2 第 26、28 项为强制测试，不得省略 |
| 组件测试缺位 | 新前端零覆盖，面试提问答不上 | 11.1 的组件测试为 DoD 硬性条件 |
| 两套前端并存导致文档矛盾 | 面试官发现文档与仓库不符 | Phase 4 必须同步 `frontend-showcase.md`、README 与架构文档 |
| 构建产物超过冻结预算 | 首屏加载变慢或误引入依赖 | 对比 Phase 0 基线，检查 raw/gzip 增量后再决定是否调整预算 |
| 共享账号被当成数据隔离 | 不同访客互相修改购物车和订单 | 公网采用独立演示数据，未完成前禁止共享账号写操作 |
| 公网限流误伤或被绕过 | 一个用户耗尽配额，或伪造代理头绕过限制 | Nginx 转发真实 IP，Uvicorn 只信任 Nginx 地址，按 10.2 验证 |

---

## 附录 A：冻结记录

> Phase 0 完成后，将 `types/` 与 `lib/` 的最终公开签名记录于此，作为后续变更的对照基线。

### 2026-09-26：类型与基础库签名冻结

类型契约已冻结：

- `types/api.ts`：后端请求/响应、8 个 `ConfirmationAction`、工具调用与健康检查类型。
- `types/stream.ts`：10 个 SSE 事件的 `StreamEvent` 判别联合。
- `types/results.ts`：商品、购物车、订单以及 `empty` / `raw` / `none` 结果联合。
- `types/chat.ts`：用户、助手、系统消息及运行/确认状态。

基础库公开入口已冻结：

```ts
fetchJson<T>(input, options): Promise<T>
normalizeErrorDetail(payload, status?): string
parseSseChunk(buffer, chunk, flush?): SseParseResult
flushSseBuffer(buffer): StreamEvent[]
ensureSessionId(storage?, factory?): string
rotateSessionId(storage?, factory?): string
readStoredAuth(storage?): StoredAuth
persistAuth(accessToken, username, storage?): void
clearStoredAuth(storage?): void
finiteAmount(value): number | null
finitePositiveInteger(value): number | null
formatCurrency(value, fallback?): string
formatDateTime(value, fallback?): string
redactSensitive(value): unknown
normalizeResultRecords(data): unknown[]
isOrderRecord / isCartRecord / isProductRecord
resolveResultPayload(data, toolCalls): ResultPayload
sanitizeCredentialUrl(href): SanitizedCredentialUrl
removeCredentialQueryParameters(href?, replaceState?): boolean
toolBusinessLabel / toolStatusCopy / confirmationPresentation / emptyResultCopy
```

冻结时验证：`vue-tsc` 通过，Vitest **10 个文件 / 45 项测试**通过，Vite 生产构建通过。后续如需改变公开签名，必须同时更新本节、调用方和对应测试。

### 2026-09-26：全局样式基础完成

- `styles/tokens.css` 已成为颜色、字体、间距、圆角、阴影、动效和控件尺寸的唯一变量来源，不保留旧变量别名。
- `styles/base.css` 已统一基础重置、键盘焦点、跳转链接、触屏控件尺寸、减少动效和强制高对比度规则。
- `App.vue` 已移除硬编码的全局样式，组件样式只消费设计令牌。
- 完成时验证：`vue-tsc` 通过，Vitest **11 个文件 / 48 项测试**通过，Vite 生产构建通过。

### 2026-09-26：API 适配层完成

- `api/auth.ts`、`api/system.ts`、`api/chat.ts` 已覆盖健康检查、登录、会话恢复、普通/流式聊天、确认和清理会话。
- Vue 请求统一使用相对路径；除登录凭据外，token 只通过 `Authorization` 请求头传递，兼容字段 `access_token` 不进入 Vue 请求体。
- `/auth/session` 已支持无 token 请求体的 Authorization 恢复方式，同时保留原生前端的旧请求体兼容能力。
- 完成时验证：`vue-tsc` 通过，Vitest **14 个文件 / 55 项测试**通过，Vite 生产构建通过；后端会话恢复定向测试 **2 项**通过。

### 2026-09-26：会话状态层完成

- `stores/session.ts` 已实现登录、启动恢复、退出、会话 ID 轮换以及待登录动作的一次性消费。
- 已存 token 启动时进入 `checking`，只有 `/auth/session` 校验成功后才进入 `authenticated`。
- 登录失败保留待继续操作；退出或 token 失效清除认证信息，但保留当前 `sessionId`。
- 完成时验证：`vue-tsc` 通过，Vitest **15 个文件 / 60 项测试**通过，Vite 生产构建通过。

### 2026-09-26：基础视图与健康状态完成

- `stores/view.ts` 已实现客户/开发者视角切换和侧栏开关，侧栏与调试视图保持互斥。
- `composables/useHealthPoll.ts` 已实现挂载时立即检查、默认 30 秒轮询、失败状态、手动恢复、请求防重入和卸载清理。
- 健康状态区分 `checking`、`online`、`offline`，并保留最近一次成功的健康详情供后续界面展示。
- 完成时验证：`vue-tsc` 通过，Vitest **17 个文件 / 67 项测试**通过，Vite 生产构建通过。

### 2026-09-26：最小纵向闭环实现完成

- `useChatStream` 已覆盖非 2xx 错误、SSE 终止语义、无结果异常、AbortController 取消和进度事件去噪。
- `stores/chat.ts` 已实现消息运行、新旧 `runId` 隔离、限流退避、取消请求和新建会话；`stores/inspector.ts` 已记录脱敏事件时间线。
- Vue 页面已接通健康状态、登录/恢复/退出、快捷问题、消息输入、流式状态、文本回答、`RawResult` 兜底和 Inspector。
- 已完成三栏桌面布局，以及 `1100px` Inspector 抽屉、`900px` 侧栏抽屉和 `680px` 顶栏压缩。
- 开发服务器入口实测返回 HTTP `200`；生产产物 JS `96.63 kB`（gzip `37.34 kB`）、CSS `15.71 kB`（gzip `3.57 kB`），低于既定预算。
- 完成时验证：`vue-tsc` 通过，Vitest **22 个文件 / 84 项测试**通过，Vite 生产构建通过；无 `any`、`@ts-ignore`、`console.log`。

### 2026-09-27：业务结果阶段第一步完成

- `ResultList.vue` 已覆盖 `product`、`cart`、`order`、`empty`、`raw`、`none` 全部分支，并接入助手消息。
- `EmptyResult.vue` 已实现商品、购物车、订单三类空状态及下一步问题，事件可回传聊天 Store。
- 完整业务卡片实现前，三类已识别结果只展示真实身份字段，不提前编造价格、库存或状态。
- 完成时验证：`vue-tsc` 通过，Vitest **24 个文件 / 91 项测试**通过，Vite 生产构建通过；生产 JS `99.62 kB`（gzip `38.11 kB`）、CSS `17.43 kB`（gzip `3.76 kB`）。

### 2026-09-27：商品、购物车与订单卡片完成

- `ProductCard.vue` 已实现价格降级、四态库存、最多三条匹配依据、详情和登录后继续加入购物车。
- `CartCard.vue` 与 `CartSummary.vue` 已实现安全数量/小计计算，并严格区分完整“合计”和部分“已知金额”。
- `OrderCard.vue` 与 `OrderItemRow.vue` 已实现订单/支付状态、商品明细、金额拆分，以及仅待支付订单可取消。
- 结果操作统一使用 `PromptAction`，由 `ChatWorkspace` 集中处理登录要求；业务卡片不直接调用 API。
- 完成时验证：`vue-tsc` 通过，Vitest **29 个文件 / 104 项测试**通过，Vite 生产构建通过；生产 JS `108.58 kB`（gzip `40.62 kB`）、CSS `25.25 kB`（gzip `4.69 kB`）。

### 2026-09-27：确认状态逻辑完成

- `stores/chat.ts` 已实现 `pending → submitting → executed/cancelled/failed` 状态机，并只允许最新待确认助手消息提交。
- `submitting` 阶段拒绝重复请求；`executed` 会按确认动作重新解析业务结果，`cancelled` 保持正常结果且不写入错误状态。
- `401` 会清除失效登录，`404` 进入不可重试的失败终态，`429` 同步触发发送退避。
- 确认请求统一携带 `session_id`、一次性确认令牌和 Authorization token，不会通过业务请求体传递登录 token。
- 完成时验证：`vue-tsc` 通过，Vitest **29 个文件 / 108 项测试**通过，Vite 生产构建通过；生产 JS `109.58 kB`（gzip `40.84 kB`）、CSS `25.25 kB`（gzip `4.69 kB`）。

### 2026-09-27：确认界面与交互闭环完成

- 新增 `ConfirmationCard.vue`、`ConfirmFacts.vue` 和 `OperationResult.vue`，覆盖全部 8 类高风险动作及未知动作安全降级。
- 确认、拒绝事件已从助手消息贯通到 `chat.confirm()`；提交中双按钮禁用，避免重复执行。
- 执行成功、主动取消和执行失败使用独立终态；其中 `cancelled` 为中性色，并明确提示数据未修改。
- 完成时验证：`vue-tsc` 通过，Vitest **32 个文件 / 126 项测试**通过，Vite 生产构建通过；生产 JS `115.58 kB`（gzip `42.63 kB`）、CSS `29.37 kB`（gzip `5.16 kB`）。
- Phase 2 的代码与自动化验收完成；真实 Java + Agent 环境的浏览器演示仍按手工验收路线执行。

### 2026-09-27：构建产物契约完成

- 新增独立 `test:dist` 门禁，要求先完成生产构建，不影响日常组件测试。
- 自动验证生产入口无外部资源、无图片依赖、无内嵌凭据配置，且只生成 HTML、CSS 和 JavaScript 文件。
- JS + CSS 最新合计 raw `150.60 kB`、gzip `48.90 kB`，相对 Phase 0 分别增加 `38.26 kB` 与 `7.99 kB`，均低于冻结预算。
- `npm run validate` 已串联构建、**40 个文件 / 141 项常规测试**和 **1 个文件 / 5 项产物契约测试**，本次全部通过。
- 真实 Java + Agent 服务当时未运行，环境级浏览器验收仍保留为独立待办，不以静态验证代替。

### 2026-09-27：Phase 3 Inspector 完善

- Inspector 现在记录包括 `progress` 在内的完整 SSE 时间线，并显示当前问题、SSE 状态、业务步骤数、模型和会话信息。
- 工具名统一映射为业务语言；工具参数继续经过递归脱敏，界面不直接展示内部工具名。
- 时长明确标注为“浏览器观测时长”，每个事件显示相对运行开始时间，避免误解为服务端逐工具耗时。
- 新增 Inspector 组件测试，并扩展 Store 与标签测试。

### 2026-09-27：Phase 3 键盘焦点管理完成

- 新增 `useFocusRestore`，移动端侧栏和中屏 Inspector 抽屉打开后进入面板，Tab/Shift+Tab 不会逃出当前抽屉。
- Esc、遮罩和面板关闭按钮关闭抽屉后，焦点精确恢复到原触发控件。
- `ViewSwitch` 的左右方向键、Home、End 现在同步更新选中状态与真实 DOM 焦点。
- 新增 AppShell 与 ViewSwitch 组件测试；全量验证结果为 **35 个文件 / 132 项常规测试**及 **5 项产物契约测试**全部通过。

### 2026-09-27：Phase 3 读屏播报完善

- 新增统一聊天播报编排，覆盖回复完成、回答停止、生成失败、出现待确认操作，以及确认执行、取消和失败终态。
- 全局 `SrAnnouncer` 使用原子化 polite status；确认结果移除重复 live region，避免同一结果被读屏器朗读两次。
- 消息列表滚动改为能力检测，测试环境及不支持 `scrollTo` 的旧浏览器可安全降级。
- 全量验证结果为 **35 个文件 / 133 项常规测试**及 **5 项产物契约测试**全部通过。

### 2026-09-27：Phase 3 Shell 测试与等价验收准备完成

- 新增 Sidebar、Topbar 与全局读屏区域测试，覆盖健康状态、受限快捷操作、关闭事件和 live region 语义。
- 修复 Vue 登录后自动续办与原生版不一致的问题：登录成功后必须由用户明确选择“继续执行”或“暂不继续”。
- 第 11.6 节已记录原生版/Vue 版的等价能力、自动化证据、真实浏览器待验收项和有意差异。
- 全量验证结果为 **40 个文件 / 141 项常规测试**及 **5 项产物契约测试**全部通过；Phase 3 剩余工作仅为启动完整环境后的浏览器等价验收。

## 附录 B：与 `frontend-showcase.md` 的分工

| 文档 | 回答的问题 | 读者 |
| --- | --- | --- |
| `frontend-showcase.md` | 为什么这样设计？面试怎么讲？ | 面试官、访客 |
| `frontend-vue-plan.md`（本文件） | 怎么实现？谁做什么？验收标准？ | 执行者（人或 AI） |

两份文档**必须保持一致**。任何影响视觉、交互或工程决策的变更，都要同时更新两份。
