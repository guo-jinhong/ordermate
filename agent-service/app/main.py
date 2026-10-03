from __future__ import annotations

import asyncio
import json
import os
import time
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from openai import AsyncOpenAI
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from redis.asyncio import Redis, from_url

from app.business_fields import purchase_request
from app.operation_store import OperationStore, JournaledConfirmations
from app.reliability import SessionCoordinator, RedisDemoQuota, request_budget, mark_write_attempt
from app.agent import AgentService
from app.audit import AuditLogger
from app.circuit_breaker import AsyncCircuitBreaker
from app.approval_workflow import ApprovalWorkflow
from app.clients.ecommerce_client import EcommerceApiError, EcommerceClient
from app.clients.mysql_client import EcommerceClient as MysqlEcommerceClient
from app.conversation_memory import ConversationMemoryStore
from app.conversation_state import ConversationStateStore
from app.redis_stores import (
    RedisConfirmationStore,
    RedisConversationMemoryStore,
    RedisConversationStateStore,
)
from app.cart_operations import execute_cart_mutation
from app.config import Settings
from app.demo_agent import DemoAgentService
from app.embedding import get_embedding_client
from app.knowledge_base import KnowledgeBase
from app.metrics import chat_latency_seconds, chat_requests_total, metrics_content_type, metrics_text
from app.runtime_config import RuntimeConfig
from app.logging_filters import install_redacting_filter, install_sampling_filter
from app.tracing import TraceIdFormatter, get_trace_id, install_trace_id_filter, new_trace_id, set_trace_id
from app.business_feedback import abandoned_action_reply, customer_error_reply
from app.schemas import (
    AuthSessionRequest,
    AuthSessionResponse,
    ChatRequest,
    ChatResponse,
    ClearConversationRequest,
    ClearConversationResponse,
    ConfirmRequest,
    ConfirmResponse,
    HealthResponse,
    LoginRequest,
    LoginResponse,
    ReloadKnowledgeResponse,
    RuntimeConfigResponse,
)
from app.tools.confirmation import ConfirmationStore, fingerprint_access_token
from app.tools.registry import ToolRegistry


class VersionedStaticFiles(StaticFiles):
    """Cache versioned assets aggressively while keeping bare asset URLs fresh."""

    async def get_response(self, path: str, scope: dict[str, Any]):
        response = await super().get_response(path, scope)
        query = parse_qs(scope.get("query_string", b"").decode("ascii", errors="ignore"))
        response.headers["Cache-Control"] = (
            "public, max-age=31536000, immutable"
            if query.get("v")
            else "no-cache, must-revalidate"
        )
        return response


logger = logging.getLogger(__name__)


class PublicDemoQuota:
    """Single-process cap for a temporary, local public demo."""

    def __init__(self, daily_limit: int, max_concurrent: int):
        self.daily_limit = daily_limit
        self.max_concurrent = max_concurrent
        self.day = int(time.time() // 86400)
        self.used = 0
        self.active = 0
        self.lock = asyncio.Lock()

    async def reserve(self) -> None:
        async with self.lock:
            day = int(time.time() // 86400)
            if day != self.day:
                self.day = day
                self.used = 0
            if self.used >= self.daily_limit:
                raise HTTPException(status_code=429, detail="今日演示调用额度已用完。")
            if self.active >= self.max_concurrent:
                raise HTTPException(status_code=429, detail="当前演示请求较多，请稍后再试。")
            self.used += 1
            self.active += 1

    async def release(self, owner=None) -> None:
        async with self.lock:
            self.active = max(0, self.active - 1)


def _rate_limit_handler(request, exc):  # noqa: ARG001
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=429,
        content={"error": "rate_limited", "detail": "请求过于频繁，请稍后再试。"},
    )


# 后端-3: 依赖注入函数（从 app.state 取组件，测试时可用 dependency_overrides 替换）
def get_ecommerce(request: Request):
    return request.app.state.ecommerce


def get_confirmations(request: Request):
    return request.app.state.confirmations


def get_runtime_config(request: Request):
    return request.app.state.runtime_config


def get_agent(request: Request):
    return request.app.state.agent


def create_app(
    settings: Settings | None = None,
    *,
    model_client: Any | None = None,
    ecommerce_client: Any | None = None,
    redis_client: Redis | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    settings.validate_for_production()
    if settings.chat_timeout_seconds <= 0 or settings.read_retry_budget_seconds <= 0:
        raise ValueError("Request time budgets must be positive")
    if settings.public_demo:
        if settings.resolved_agent_mode() != "live":
            raise RuntimeError("PUBLIC_DEMO requires AGENT_MODE=live")
        if model_client is None and not settings.openai_api_key:
            raise RuntimeError("PUBLIC_DEMO requires a configured live model")
        if settings.demo_chat_daily_limit < 1 or settings.demo_chat_max_concurrent < 1:
            raise RuntimeError("Demo chat limits must be positive")
        if not settings.demo_allowed_users:
            raise RuntimeError("PUBLIC_DEMO requires DEMO_ALLOWED_USERS")
    install_redacting_filter()  # 全局日志脱敏，防止密钥落盘
    install_trace_id_filter()  # 全链路 trace_id 注入
    install_sampling_filter(sample_rate=0.1)  # OBS-1: LLM 详细日志 10% 采样

    # OBS-1: 日志级别从环境变量读取，默认 INFO；生产环境不低于 INFO
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.getLogger().setLevel(log_level)
    # uvicorn 日志同步级别
    logging.getLogger("uvicorn").setLevel(log_level)
    logging.getLogger("uvicorn.access").setLevel(log_level)

    # 统一日志格式：包含 trace_id，便于全链路追踪
    _formatter = TraceIdFormatter(
        "%(asctime)s [%(trace_id)s] %(levelname)s %(name)s: %(message)s"
    )
    for _handler in logging.getLogger().handlers:
        _handler.setFormatter(_formatter)

    # 根据配置选择电商后端
    # D1-1: 生产环境强制走 API，禁止直连数据库（避免两套数据源不一致）
    if ecommerce_client is None:
        backend = settings.ecommerce_backend.lower()
        force_api = os.getenv("APP_ENV", "dev").lower() in {"prod", "production"}
        if backend in {"database", "mysql", "direct"} and not force_api:
            ecommerce = MysqlEcommerceClient()
            logger.warning(
                "Using direct DB backend (mode: %s) — 仅限开发环境，生产环境必须用 api 模式",
                backend,
            )
        else:
            ecommerce = EcommerceClient(
                settings.ecommerce_api_base_url,
                settings.request_timeout_seconds,
                retry_budget_seconds=settings.read_retry_budget_seconds,
            )
            logger.info("Using HTTP API backend for ecommerce")
    else:
        ecommerce = ecommerce_client
    redis = redis_client
    if redis is None and settings.redis_url:
        redis = from_url(settings.redis_url, decode_responses=True, socket_timeout=3, socket_connect_timeout=3)
    if redis is None:
        confirmations = ConfirmationStore(ttl_seconds=settings.confirmation_ttl_seconds)
        memory = ConversationMemoryStore(
            max_messages=settings.conversation_max_messages,
            ttl_seconds=settings.conversation_ttl_seconds,
        )
    else:
        confirmations = RedisConfirmationStore(redis, ttl_seconds=settings.confirmation_ttl_seconds)
        memory = RedisConversationMemoryStore(
            redis,
            max_messages=settings.conversation_max_messages,
            ttl_seconds=settings.conversation_ttl_seconds,
        )
    operations = OperationStore(settings.operation_db_path, redis)
    confirmations = JournaledConfirmations(confirmations, operations)
    coordinator = SessionCoordinator(redis, lease_seconds=max(90, int(settings.chat_timeout_seconds) + 30))
    # R1-1/R1-6: Embedding 客户端（无 Key 时为 None，降级到纯 TF-IDF）
    embedding_client = get_embedding_client(
        settings.embedding_api_key,
        settings.embedding_base_url,
    )
    # 知识库分库注入：规则库与商品库隔离
    rule_kb = KnowledgeBase(
        doc_type="rule",
        embedding_client=embedding_client,
        embedding_model=settings.embedding_model,
        rerank_base_url=settings.rerank_base_url,
    )
    product_kb = KnowledgeBase(
        doc_type="product",
        embedding_client=embedding_client,
        embedding_model=settings.embedding_model,
        rerank_base_url=settings.rerank_base_url,
    )
    registry = ToolRegistry(
        ecommerce,
        confirmations,
        rule_knowledge_base=rule_kb,
        product_knowledge_base=product_kb,
        public_readonly=settings.public_readonly,
    )
    registry.operations = operations
    registry.memory = memory
    audit = AuditLogger()
    approval_workflow = ApprovalWorkflow()
    runtime_config = RuntimeConfig(redis_client=redis)

    if redis is None:
        state_store = ConversationStateStore(
            ttl_seconds=settings.conversation_ttl_seconds,
        )
    else:
        state_store = RedisConversationStateStore(
            redis,
            ttl_seconds=settings.conversation_ttl_seconds,
        )

    agent_mode = settings.resolved_agent_mode()

    fallback_model_client: Any | None = None
    if model_client is None and agent_mode == "live" and settings.openai_api_key:
        client_options: dict[str, Any] = {"api_key": settings.openai_api_key}
        if settings.openai_base_url:
            client_options["base_url"] = settings.openai_base_url
        model_client = AsyncOpenAI(**client_options)
        # fallback 模型：主模型失败/熔断时自动切换
        if settings.openai_fallback_model:
            fb_options: dict[str, Any] = {
                "api_key": settings.openai_fallback_api_key or settings.openai_api_key,
            }
            if settings.openai_fallback_base_url:
                fb_options["base_url"] = settings.openai_fallback_base_url
            fallback_model_client = AsyncOpenAI(**fb_options)

    # STAB-2: LLM 熔断器告警回调（通过 webhook 发送，未配置则只记日志）
    alert_webhook_url = os.getenv("ALERT_WEBHOOK_URL")

    async def _send_circuit_alert(name: str, failure_count: int) -> None:
        msg = f"[熔断告警] {name} 熔断器已触发（连续失败 {failure_count} 次）"
        logger.warning(msg)
        if not alert_webhook_url:
            return
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5) as ac:
                await ac.post(alert_webhook_url, json={"text": msg})
        except Exception as exc:
            logger.warning("告警 webhook 发送失败: %s", exc)

    llm_breaker = AsyncCircuitBreaker("llm", on_open_callback=_send_circuit_alert)

    demo_agent = DemoAgentService(
        registry,
        state_store=state_store,
        approval_workflow=approval_workflow,
    )
    live_agent: AgentService | None = None
    if model_client is not None:
        live_agent = AgentService(
            model_client,
            registry,
            model=settings.openai_model,
            max_tool_rounds=settings.max_tool_rounds,
            memory=memory,
            state_store=state_store,
            approval_workflow=approval_workflow,
            confirmed_action_executor=lambda action, arguments, access_token, session_id: _execute_confirmed_action(
                ecommerce, registry, session_id, action, arguments, access_token
            ),
            fallback_model_client=fallback_model_client,
            fallback_model=settings.openai_fallback_model,
            llm_circuit_breaker=llm_breaker,
        )
        agent = live_agent
        active_mode = "live"
    elif agent_mode == "demo":
        agent = demo_agent
        active_mode = "demo"
    else:
        agent = None
        active_mode = "live"

    runtime_state: dict[str, Any] = {
        "serving_mode": active_mode,
        "fallback_reason": None,
        "fallback_at": None,
    }

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        async def maintain_operations():
            while True:
                try:
                    await operations.cleanup(settings.operation_retention_days)
                except Exception:
                    logger.exception("Operation log maintenance failed")
                await asyncio.sleep(3600)

        # R1-1/R1-6: 启动时构建知识库向量索引（失败不影响启动，降级到 TF-IDF）
        try:
            await rule_kb.build_vector_index()
            await product_kb.build_vector_index()
        except Exception as exc:
            logger.warning("向量索引构建失败，降级到 TF-IDF: %s", exc)
        workflow_saver = None
        if settings.redis_url:
            from langgraph.checkpoint.redis.aio import AsyncRedisSaver

            workflow_saver = AsyncRedisSaver(settings.redis_url)
            await workflow_saver.asetup()
            approval_workflow.set_checkpointer(workflow_saver)
        # DB-2: 启动会话过期清理后台任务（仅内存版 store）
        if hasattr(state_store, "start_cleanup_task"):
            await state_store.start_cleanup_task()
        maintenance = asyncio.create_task(maintain_operations())
        try:
            yield
        finally:
            maintenance.cancel()
            try:
                await maintenance
            except asyncio.CancelledError:
                pass
        # DB-2: 停止会话清理任务
        if hasattr(state_store, "stop_cleanup_task"):
            await state_store.stop_cleanup_task()

        # STAB-1: 优雅关闭——等待进行中的请求完成（最长 30s），然后关闭资源
        import time as _time
        shutdown_deadline = _time.monotonic() + 30
        # 关闭 LLM 客户端（释放 httpx 连接池）
        for mc in (model_client, fallback_model_client):
            if mc is not None:
                try:
                    await mc.close()
                except Exception:
                    pass

        close = getattr(ecommerce, "close", None)
        if close is not None:
            await close()
        if redis is not None and redis is not redis_client:
            await redis.aclose()
        if workflow_saver is not None:
            workflow_redis = getattr(workflow_saver, "redis", None)
            close_workflow_redis = getattr(workflow_redis, "aclose", None)
            if close_workflow_redis is not None:
                await close_workflow_redis()

    app = FastAPI(
        title="E-commerce Customer Service Agent",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.agent = agent
    app.state.ecommerce = ecommerce
    app.state.operations = operations
    app.state.coordinator = coordinator
    app.state.confirmations = confirmations
    app.state.runtime_config = runtime_config
    demo_quota = (
        (RedisDemoQuota(redis, settings.demo_chat_daily_limit, settings.demo_chat_max_concurrent, coordinator.lease_seconds) if redis is not None else PublicDemoQuota(settings.demo_chat_daily_limit, settings.demo_chat_max_concurrent))
        if settings.public_demo else None
    )
    app.state.demo_quota = demo_quota
    # RAG-1: 知识库实例存到 app.state，供 /admin/knowledge/reload 端点调用
    app.state.rule_kb = rule_kb
    app.state.product_kb = product_kb

    # SEC-1: CORS 白名单（生产环境必须配置具体域名，禁止 *）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[] if settings.public_demo else settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"], storage_uri=settings.redis_url or "memory://")
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)

    # SEC-2: 请求体大小限制（1MB），防止大 payload 打挂服务
    MAX_REQUEST_SIZE = 1 * 1024 * 1024

    @app.middleware("http")
    async def request_size_limit_middleware(request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_REQUEST_SIZE:
            from fastapi import JSONResponse
            return JSONResponse(
                status_code=413,
                content={"error": "payload_too_large", "detail": "请求体超过 1MB 限制"},
            )
        return await call_next(request)

    @app.middleware("http")
    async def trace_id_middleware(request, call_next):
        # 从 header 取 trace_id（支持跨服务传递），没有则生成
        tid = request.headers.get("x-trace-id") or new_trace_id()
        set_trace_id(tid)
        response = await call_next(request)
        response.headers["X-Trace-Id"] = tid
        return response

    @app.middleware("http")
    async def api_version_middleware(request, call_next):
        """后端-1: 接口版本化。/api/v1/xxx 自动重写到 /xxx，新旧路径共存。"""
        path = request.scope.get("path", "")
        if path.startswith("/api/v1/"):
            request.scope["path"] = path[len("/api/v1"):]
            request.scope["raw_path"] = request.scope["path"].encode("utf-8")
        return await call_next(request)

    if settings.public_demo:
        public_routes = {
            ("GET", "/"),
            ("GET", "/index.html"),
            ("GET", "/health"),
            ("GET", "/cart"),
            ("POST", "/auth/login"),
            ("POST", "/auth/session"),
            ("POST", "/chat"),
            ("POST", "/chat/stream"),
            ("POST", "/confirm"),
            ("POST", "/conversation/clear"),
        }

        @app.middleware("http")
        async def public_demo_gate(request: Request, call_next):
            path = request.url.path
            allowed_asset = request.method == "GET" and (path.startswith("/assets/") or path.startswith("/operations/"))
            if not allowed_asset and (request.method, path) not in public_routes:
                return JSONResponse(status_code=404, content={"detail": "Not Found"})
            return await call_next(request)

    def require_demo_user(user: Any) -> None:
        if settings.public_demo:
            username = user.get("username") if isinstance(user, dict) else None
            if username not in settings.demo_allowed_users:
                raise HTTPException(status_code=403, detail="此账号无演示访问权限。")

    async def get_current_user(
        authorization: str | None = Header(default=None),
    ) -> str | None:
        """可选鉴权：从 Authorization header 读取 Bearer Token 并校验。

        无 header 时返回 None（匿名访问），body 里的 access_token 由各路由自行兜底。
        """
        token: str | None = None
        if authorization and authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()
        if not token:
            return None
        try:
            user = await ecommerce.get_current_user(token)
        except EcommerceApiError:
            raise HTTPException(status_code=401, detail="登录状态无效或已失效，请重新登录。")
        require_demo_user(user)
        return token

    async def require_admin_token(
        x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    ) -> None:
        """SEC-3: /admin 接口鉴权。生产环境未配置 ADMIN_TOKEN 时拒绝访问。"""
        import os
        is_prod = os.getenv("APP_ENV", "dev").lower() not in {"dev", "development", "local", "test"}
        if is_prod and not settings.admin_token:
            raise HTTPException(status_code=503, detail="Admin 接口未配置 ADMIN_TOKEN，拒绝访问")
        if settings.admin_token:
            if not x_admin_token or x_admin_token != settings.admin_token:
                raise HTTPException(status_code=401, detail="无效的 Admin Token")
        # 开发环境未配置 ADMIN_TOKEN 时放行，方便调试

    async def resolve_access_token(
        header_token: str | None,
        body_token: str | None,
    ) -> str | None:
        """统一解析有效 token：优先 header，回退 body，并对 body token 做一次校验。"""
        if header_token:
            return header_token
        if not body_token:
            return None
        try:
            user = await ecommerce.get_current_user(body_token)
        except EcommerceApiError:
            raise HTTPException(status_code=401, detail="登录状态无效或已失效，请重新登录。")
        require_demo_user(user)
        return body_token

    static_dir = Path(__file__).resolve().parent / "static"
    vue_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
    if settings.public_demo:
        if not (vue_dist / "index.html").is_file() or not (vue_dist / "assets").is_dir():
            raise RuntimeError("Vue build missing: run npm run build in frontend first")
        app.mount("/assets", StaticFiles(directory=vue_dist / "assets"), name="vue-assets")
    else:
        app.mount("/static", VersionedStaticFiles(directory=static_dir), name="static")

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(
            (vue_dist if settings.public_demo else static_dir) / "index.html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    if settings.public_demo:
        app.add_api_route("/index.html", index, methods=["GET"], include_in_schema=False)

    # 前端写操作后的只读同步，复用当前用户鉴权和账号权限。
    @app.get("/cart")
    async def cart_snapshot(token: str | None = Depends(get_current_user)):
        if not token:
            raise HTTPException(status_code=401, detail="请先登录。")
        try:
            return await ecommerce.get_cart(token)
        except EcommerceApiError as exc:
            raise HTTPException(status_code=502, detail="购物车暂时无法读取，请刷新后重试。") from exc

    @app.get("/health", response_model=HealthResponse, response_model_exclude_none=True)
    async def health(deep: bool = False):
        """健康检查。deep=true 时探测 Redis / 后端 API / LLM 连通性。"""
        if settings.public_demo:
            deep = False
        checks: dict[str, str] = {"app": "ok"}
        if deep:
            # Redis 连通性
            if redis is not None:
                try:
                    await redis.ping()
                    checks["redis"] = "ok"
                except Exception as exc:
                    checks["redis"] = f"error: {exc}"
            else:
                checks["redis"] = "not_configured"
            # 后端 API 连通性：使用公开只读接口，鉴权失败不再掩盖真实 5xx。
            try:
                await ecommerce.search_products("__health_probe__")
                checks["backend"] = "ok"
            except Exception as exc:
                checks["backend"] = f"error: {type(exc).__name__}"
            # LLM 连通性（live 模式才检查）
            if active_mode == "live":
                checks["llm"] = "ok" if live_agent is not None else "not_configured"
            else:
                checks["llm"] = "demo_mode"
            checks["embedding"] = (
                "configured" if embedding_client is not None else "disabled"
            )
        accepted = {"ok", "not_configured", "demo_mode", "configured", "disabled"}
        all_ok = all(v in accepted for v in checks.values())
        if active_mode == "live" and live_agent is None:
            all_ok = False
        if runtime_state["serving_mode"] == "demo_fallback":
            all_ok = False
        result = {
            "status": "ok" if all_ok else "degraded",
            "model_configured": live_agent is not None,
            "agent_mode": active_mode,
            "serving_mode": runtime_state["serving_mode"],
            "llm_provider": "openai-compatible" if live_agent is not None else None,
            "llm_model": settings.openai_model if live_agent is not None and not settings.public_demo else None,
            "embedding_mode": "external" if embedding_client is not None else "lexical",
            "fallback_reason": runtime_state["fallback_reason"],
            "backend_base_url": "" if settings.public_demo else settings.ecommerce_api_base_url,
            # 公共聊天开放，个人数据和写操作由工具层校验登录。
            "public_demo": settings.public_demo,
            "chat_login_required": False,
        }
        if deep:
            result["checks"] = checks
        return result

    @app.get("/admin/config", response_model=RuntimeConfigResponse, dependencies=[Depends(require_admin_token)])
    async def get_admin_config():
        """P1-4: 读取运行时配置（降级开关）。"""
        return await runtime_config.load()

    @app.post("/admin/config", dependencies=[Depends(require_admin_token)])
    async def update_admin_config(overrides: dict):
        """P1-4: 更新运行时配置，支持热切换。"""
        return await runtime_config.save(overrides)

    @app.post("/admin/knowledge/reload", response_model=ReloadKnowledgeResponse, dependencies=[Depends(require_admin_token)])
    async def reload_knowledge_base(request: Request):
        """RAG-1: 增量更新知识库（重新加载文档并重建索引）。"""
        from fastapi import HTTPException
        try:
            await app.state.rule_kb.reload()
            await app.state.product_kb.reload()
            return {"ok": True, "rule_count": app.state.rule_kb._doc_count, "product_count": app.state.product_kb._doc_count}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"知识库重载失败: {exc}") from exc

    @app.get("/metrics")
    async def prometheus_metrics():
        """O1-1: Prometheus 指标端点。"""
        from fastapi import Response
        return Response(content=metrics_text(), media_type=metrics_content_type())

    @app.post("/auth/login", response_model=LoginResponse)
    async def login(request: LoginRequest) -> LoginResponse:
        if settings.public_demo and request.username not in settings.demo_allowed_users:
            raise HTTPException(status_code=403, detail="此账号无演示访问权限。")
        try:
            token = await ecommerce.login(request.username, request.password)
        except EcommerceApiError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        return LoginResponse(access_token=token)

    @app.post("/auth/session", response_model=AuthSessionResponse)
    async def auth_session(
        request: AuthSessionRequest | None = None,
        token: str | None = Depends(get_current_user),
    ) -> AuthSessionResponse:
        resolved_token = token or (request.access_token if request is not None else None)
        if not resolved_token:
            raise HTTPException(status_code=401, detail="登录状态无效或已失效。")
        try:
            user = await ecommerce.get_current_user(resolved_token)
        except EcommerceApiError as exc:
            raise HTTPException(status_code=401, detail="登录状态无效或已失效。") from exc
        require_demo_user(user)
        username = user.get("username") if isinstance(user, dict) else None
        return AuthSessionResponse(username=username)

    @app.post("/chat", response_model=ChatResponse)
    @limiter.limit("20/minute")
    async def chat(request: Request, chat_request: ChatRequest, token: str | None = Depends(get_current_user)) -> ChatResponse:
        if agent is None:
            raise HTTPException(
                status_code=503,
                detail="OPENAI_API_KEY is not configured.",
            )
        start = time.monotonic()
        try:
            resolved_token = await resolve_access_token(token, chat_request.access_token)
            chat_request.access_token = resolved_token
            if demo_quota is not None:
                lease = await demo_quota.reserve()
            try:
                result, _llm_trace = await run_chat(chat_request)
            finally:
                if demo_quota is not None:
                    await demo_quota.release(lease)
            chat_requests_total.labels(status="success").inc()
            chat_latency_seconds.observe(time.monotonic() - start)
            return result
        except HTTPException as he:
            chat_requests_total.labels(status="error").inc()
            chat_latency_seconds.observe(time.monotonic() - start)
            raise he
        except Exception as exc:
            logger.exception("Unhandled Agent error")
            chat_requests_total.labels(status="error").inc()
            chat_latency_seconds.observe(time.monotonic() - start)
            raise HTTPException(
                status_code=500,
                detail="暂时无法处理您的请求，请稍后再试。",
            ) from exc

    async def run_chat(request: ChatRequest) -> tuple[ChatResponse, list[dict]]:
        with purchase_request(request.message):
            return await run_chat_guarded(request)

    async def run_chat_guarded(request: ChatRequest) -> tuple[ChatResponse, list[dict]]:
        async with coordinator.hold(request.session_id, request.access_token), request_budget(settings.chat_timeout_seconds) as execution:
            try:
                return await run_chat_once(request)
            except HTTPException:
                raise
            except Exception as exc:
                if execution.write_attempted:
                    raise HTTPException(502, "本次处理未完成，请先查询购物车或订单核实操作结果，暂时不要重复提交。") from exc
                raise

    async def run_chat_once(request: ChatRequest) -> tuple[ChatResponse, list[dict]]:
        audit.emit("chat_started", session_id=request.session_id, message=request.message)
        await runtime_config.load()
        selected_agent = demo_agent if runtime_config.force_demo and not settings.public_demo else agent
        llm_trace: list[dict] = []
        try:
            result = await selected_agent.chat(
                request.message,
                session_id=request.session_id,
                access_token=request.access_token,
            )
            if isinstance(selected_agent, AgentService):
                llm_trace = selected_agent.collect_llm_trace()
                runtime_state.update(
                    serving_mode="live",
                    fallback_reason=None,
                    fallback_at=None,
                )
            elif runtime_config.force_demo:
                runtime_state.update(serving_mode="forced_demo", fallback_reason=None)
        except Exception:
            # 仅在模型调用内部切换备用模型；禁止业务流程失败后重放整条请求。
            raise
        if result.reference is not None:
            audit.emit(
                "reference_resolved",
                session_id=request.session_id,
                reference_type=result.reference.type,
                reference_value=result.reference.value,
                source=result.reference.source,
            )
        if result.confirmation is not None:
            await approval_workflow.start(
                result.confirmation.token,
                result.confirmation.action,
                result.confirmation.arguments,
            )
            audit.emit("confirmation_created", action=result.confirmation.action)
        audit.emit(
            "chat_completed",
            session_id=request.session_id,
            tool_calls=[call.model_dump() for call in result.tool_calls],
        )
        return result, llm_trace

    @app.post("/chat/stream")
    @limiter.limit("20/minute")
    async def chat_stream(request: Request, chat_request: ChatRequest, token: str | None = Depends(get_current_user)) -> StreamingResponse:
        """SSE-compatible chat endpoint with safe, user-visible execution events."""
        if agent is None:
            raise HTTPException(status_code=503, detail="OPENAI_API_KEY is not configured.")

        # 鉴权必须在返回 StreamingResponse 之前完成：失效 token 应得到标准 HTTP 401，
        # 而不是在 200 SSE 流中退化为通用 error 事件，否则前端无法可靠触发重新登录。
        resolved_token = await resolve_access_token(token, chat_request.access_token)
        chat_request.access_token = resolved_token
        if demo_quota is not None:
            lease = await demo_quota.reserve()

        async def events():
            task = None
            try:
                # 首个事件发出时断开，也归还演示名额。
                yield _sse("started", {"message": "正在理解您的问题"})
                task = asyncio.create_task(run_chat(chat_request))
                while not task.done():
                    yield _sse("progress", {"message": "正在为您处理"})
                    await asyncio.sleep(0.75)
                result, llm_trace = await task
                if llm_trace:
                    yield _sse("llm_trace", {"calls": llm_trace})
                if result.reference is not None:
                    yield _sse("reference", result.reference.model_dump())
                for call in result.tool_calls:
                    if call.outcome == "clarification_needed":
                        yield _sse(
                            "clarification",
                            {
                                "tool": call.name,
                                "message": call.result_message,
                            },
                        )
                    elif call.outcome == "error":
                        yield _sse(
                            "tool_error",
                            {
                                "name": call.name,
                                "error": customer_error_reply(call.result_message),
                            },
                        )
                    yield _sse(
                        "tool",
                        {
                            "name": call.name,
                            "outcome": call.outcome,
                            "arguments": call.arguments,
                        },
                    )
                if result.confirmation is not None:
                    yield _sse("confirmation_required", {"action": result.confirmation.action})
                yield _sse("result", result.model_dump())
            except HTTPException as exc:
                yield _sse("error", {"detail": exc.detail, "status": exc.status_code})
            except Exception:
                logger.exception("Unhandled streaming Agent error")
                yield _sse(
                    "error",
                    {"detail": "暂时无法处理您的请求，请稍后再试。"},
                )
            finally:
                if task is not None and not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                if demo_quota is not None:
                    await demo_quota.release(lease)

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/conversation/clear", response_model=ClearConversationResponse)
    async def clear_conversation(
        request: Request,
        clear_request: ClearConversationRequest,
        token: str | None = Depends(get_current_user),
    ) -> ClearConversationResponse:
        resolved = await resolve_access_token(token, clear_request.access_token)
        async with coordinator.hold(clear_request.session_id, resolved), request_budget(settings.chat_timeout_seconds):
            pending_cancelled = await operations.cancel_prepared(clear_request.session_id, fingerprint_access_token(resolved)) if resolved else 0
            memory_cleared = int(await memory.clear(clear_request.session_id, resolved))
            state_cleared = int(await state_store.clear(clear_request.session_id, resolved))
        return ClearConversationResponse(
            status="cleared",
            cleared=memory_cleared > 0 or state_cleared > 0 or pending_cancelled > 0,
        )

    @app.post("/confirm", response_model=ConfirmResponse)
    @limiter.limit("10/minute")
    async def confirm(request: Request, confirm_request: ConfirmRequest, token: str | None = Depends(get_current_user)) -> ConfirmResponse:
        resolved_token = await resolve_access_token(token, confirm_request.access_token)
        if not resolved_token:
            raise HTTPException(status_code=401, detail="请先登录后再确认操作。")

        async with coordinator.hold(confirm_request.session_id, resolved_token), request_budget(settings.chat_timeout_seconds):
            return await confirm_once(confirm_request, resolved_token)

    async def confirm_once(confirm_request, resolved_token):
        previous = await operations.get(confirm_request.confirmation_token)
        if previous and previous["session_id"] == confirm_request.session_id and previous["fingerprint"] == fingerprint_access_token(resolved_token):
            if previous["status"] != "prepared":
                return await operation_response(previous, resolved_token)
        pending = await confirmations.consume(
            confirm_request.confirmation_token,
            confirm_request.session_id,
            fingerprint_access_token(resolved_token),
        )
        if pending is None:
            raise HTTPException(
                status_code=404,
                detail="本次确认已失效、过期或已使用，请重新发起操作。",
            )
        # 按钮与文字确认共享令牌，消费后同步清除会话中的待确认状态。
        confirmation_state = await state_store.get(confirm_request.session_id, resolved_token)
        if confirmation_state.pending_confirmation_token == pending.token:
            confirmation_state.clear_confirmation()
            await state_store.save(confirm_request.session_id, resolved_token, confirmation_state)
        await approval_workflow.resume(pending.token, confirm_request.approved, action=pending.action, arguments=pending.arguments)
        # 重启后以持久化确认快照和本次审批为依据。
        if not confirm_request.approved:
            audit.emit("confirmation_rejected", action=pending.action)
            response = ConfirmResponse(status="cancelled", message=abandoned_action_reply(pending.action))
            await operations.transition(pending.token, {"accepted"}, "cancelled", response.model_dump())
            return response

        # 公网只读模式：拦截确认执行的写操作
        if registry.is_write_disabled(pending.action):
            await operations.transition(pending.token, {"accepted"}, "failed", {"status": "failed", "message": registry.write_restriction_message()})
            raise HTTPException(
                status_code=403,
                detail=registry.write_restriction_message(),
            )

        try:
            data, message = await _execute_confirmed_action(
                ecommerce,
                registry,
                confirm_request.session_id,
                pending.action,
                pending.arguments,
                resolved_token,
            )
        except EcommerceApiError as exc:
            if exc.result_unknown:
                return ConfirmResponse(status="unknown", message=str(exc))
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        if pending.action == "remove_from_cart" and isinstance(data, list):
            confirmation_state.record_cart_items(data)
            await state_store.save(confirm_request.session_id, resolved_token, confirmation_state)
        return ConfirmResponse(
            status="executed",
            message=message,
            data=data,
        )

    async def operation_response(value, access_token):
        if value["result"] is not None and value["status"] in {"executed", "cancelled", "failed"}:
            return ConfirmResponse(**value["result"])
        if value["action"] == "create_order" and value["status"] in {"accepted", "processing", "unknown"}:
            try:
                data = await ecommerce.get_order_by_intent(value["token"], access_token)
                if not isinstance(data, dict) or not data.get("id"):
                    raise EcommerceApiError("未取得可核实的订单回执。")
                response = ConfirmResponse(status="executed", message="已核实，本次订单已创建。", data=data)
                recovered = await operations.transition(value["token"], {"accepted", "processing", "unknown"}, "executed", response.model_dump())
                if recovered:
                    await memory.record_operations(value["session_id"], access_token, ["create_order"])
                return response
            except (EcommerceApiError, AttributeError):
                pass
        if value["action"] in {"pay_order", "cancel_order"} and value["status"] in {"processing", "unknown"}:
            try:
                order_id = value["arguments"]["order_id"]
                data = await ecommerce.get_order_detail(order_id, access_token)
                _verify_order_receipt(registry, data, order_id)
                verified = (value["action"] == "pay_order" and data.get("paymentStatus") == 1
                            or value["action"] == "cancel_order" and data.get("status") == 4)
                if verified:
                    message = "已核实，订单已取消。" if value["action"] == "cancel_order" else "已核实，演示支付已完成，本次不会真实扣款。"
                    response = ConfirmResponse(status="executed", message=message, data=data)
                    recovered = await operations.transition(value["token"], {"accepted", "processing", "unknown"}, "executed", response.model_dump())
                    if recovered:
                        await memory.record_operations(value["session_id"], access_token, [value["action"]])
                    return response
            except (EcommerceApiError, AttributeError):
                pass
        return ConfirmResponse(status="unknown", message="本次操作仍在处理或结果待核实，请查询购物车或订单，暂时不要重复提交。")

    @app.get("/operations/{operation_id}", response_model=ConfirmResponse)
    async def operation_status(operation_id: str, session_id: str, token: str | None = Depends(get_current_user)):
        if not token:
            raise HTTPException(401, "请先登录后再查询操作结果。")
        async with coordinator.hold(session_id, token), request_budget(settings.chat_timeout_seconds):
            value = await operations.get(operation_id)
            if not value or value["session_id"] != session_id or value["fingerprint"] != fingerprint_access_token(token):
                raise HTTPException(404, "找不到本次操作。")
            if value["status"] == "prepared":
                return ConfirmResponse(status="prepared", message="本次操作尚未确认。")
            return await operation_response(value, token)

    return app


app = create_app()


def _sse(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _execute_confirmed_action(ecommerce, registry, session_id, action, arguments, access_token):
    operation_id = arguments.get("_operation_id")
    operations = getattr(registry, "operations", None)
    if registry.is_write_disabled(action):
        message = registry.write_restriction_message()
        if operation_id and operations:
            await operations.transition(operation_id, {"accepted"}, "failed", {"status": "failed", "message": message})
        raise EcommerceApiError(message)
    if operation_id and operations:
        if not await operations.transition(operation_id, {"accepted"}, "processing"):
            raise EcommerceApiError("本次操作已受理，请查询操作结果，勿重复提交。", result_unknown=True)
    mark_write_attempt()
    try:
        data, message = await _execute_confirmed_action_once(ecommerce, registry, session_id, action, arguments, access_token)
    except BaseException as exc:
        if operation_id and operations:
            unknown = isinstance(exc, (asyncio.CancelledError, TimeoutError)) or not isinstance(exc, (EcommerceApiError, ValueError)) or getattr(exc, "result_unknown", False)
            status = "unknown" if unknown else "failed"
            response = {"status": status, "message": "本次操作结果待核实，请勿重复提交。" if unknown else str(exc)}
            await asyncio.shield(operations.transition(operation_id, {"processing"}, status, response))
        raise
    if operation_id and operations:
        await operations.transition(operation_id, {"processing"}, "executed", {"status": "executed", "message": message, "data": data})
    memory = getattr(registry, "memory", None)
    if memory:
        await memory.record_operations(session_id, access_token, [action])
    return data, message


async def _execute_confirmed_action_once(
    ecommerce: Any,
    registry: ToolRegistry,
    session_id: str,
    action: str,
    arguments: dict[str, Any],
    access_token: str,
) -> tuple[Any, str]:
    try:
        return await _perform_confirmed_action(ecommerce, registry, session_id, action, arguments, access_token)
    except EcommerceApiError as exc:
        if not exc.result_unknown:
            raise
        # 回执丢失后只查询；创建订单的模糊结果也进入短期防重保护。
        if action == "create_order":
            await registry.record_created_order(session_id, access_token, arguments["product_id"], arguments["quantity"])
        try:
            if action in {"cancel_order", "pay_order"}:
                order = await ecommerce.get_order_detail(arguments["order_id"], access_token)
                _verify_order_receipt(registry, order, arguments["order_id"])
                if action == "cancel_order" and order.get("status") == 4:
                    return order, f"已确认，订单 {order.get('orderNo') or arguments['order_id']} 已取消。"
                if action == "pay_order" and order.get("paymentStatus") == 1:
                    return order, f"已确认，订单 {order.get('orderNo') or arguments['order_id']} 演示支付已完成，本次不会真实扣款。"
            elif action == "clear_cart":
                cart = await ecommerce.get_cart(access_token)
                if cart == []:
                    # 当前为空只能说明读取时的事实，不能证明本次未知写入已经完成。
                    raise EcommerceApiError("当前购物车为空，但本次清空结果仍待核实，暂时不要重复提交。", result_unknown=True)
            elif action == "create_order":
                # 同一账号可被多人使用，不能把新出现的相似订单冒认为本次订单。
                key = arguments.get("idempotency_key")
                if key:
                    order = await ecommerce.get_order_by_intent(key, access_token)
                    if isinstance(order, dict) and order.get("id"):
                        return order, "已核实，本次订单已创建。"
        except Exception:
            pass
        next_step = "请查看我的订单核实，勿重复下单。" if action == "create_order" else "请查询当前状态核实，勿重复提交。"
        raise EcommerceApiError(f"本次操作结果暂时无法确认。{next_step}", result_unknown=True) from exc


async def _perform_confirmed_action(
    ecommerce: Any,
    registry: ToolRegistry,
    session_id: str,
    action: str,
    arguments: dict[str, Any],
    access_token: str,
) -> tuple[Any, str]:
    if action == "cancel_order":
        data = await ecommerce.cancel_order(arguments["order_id"], access_token)
        _verify_order_receipt(registry, data, arguments["order_id"])
        order_no = data.get("orderNo") if isinstance(data, dict) else None
        return data, f"订单 {order_no or arguments.get('order_no') or '当前订单'} 已成功取消。"
    if action == "refund_order":
        data = await ecommerce.refund_order(
            arguments["order_id"], access_token, arguments.get("reason")
        )
        return data, f"订单 {arguments['order_id']} 退款申请已提交。"
    if action in {"update_cart", "update_cart_items", "remove_from_cart"}:
        return await execute_cart_mutation(ecommerce, action, arguments, access_token)
    if action == "clear_cart":
        data = await ecommerce.clear_cart(access_token)
        return data, "购物车已清空。"
    if action == "create_order":
        data = await ecommerce.create_order(
            arguments["product_id"],
            arguments["quantity"],
            arguments["address_id"],
            arguments.get("payment_method", "DEMO"),
            access_token,
            **({"idempotency_key": arguments["idempotency_key"]} if arguments.get("idempotency_key") else {}),
        )
        if not isinstance(data, dict) or not data.get("id"):
            raise EcommerceApiError("未取得有效订单回执，请查询订单核实，勿重复下单。", result_unknown=True)
        await registry.record_created_order(
            session_id,
            access_token,
            arguments["product_id"],
            arguments["quantity"],
        )
        product_name = arguments.get("product_name") or "该商品"
        order_no = data.get("orderNo") if isinstance(data, dict) else None
        order_text = f"，订单号：{order_no}" if order_no else ""
        return data, f"下单成功{order_text}。商品：「{product_name}」× {arguments['quantity']} 件。"
    if action == "pay_order":
        data = await ecommerce.pay_order(arguments["order_id"], access_token)
        _verify_order_receipt(registry, data, arguments["order_id"])
        order_no = data.get("orderNo") if isinstance(data, dict) else None
        return data, f"订单 {order_no or arguments.get('order_no') or '当前订单'} 演示支付已完成，本次不会真实扣款。"
    raise ValueError(f"Unsupported pending action: {action}")


def _verify_order_receipt(registry, data, order_id):
    try:
        if not isinstance(data, dict) or data.get("id") is None:
            raise EcommerceApiError("缺少订单回执。")
        registry._verify_entity_id(data, order_id, "订单")
    except EcommerceApiError as exc:
        # 写入已发送，错订单或空回执只能只读核实，不能当作成功或安全重试。
        raise EcommerceApiError("订单操作回执不完整或不匹配，请查询订单核实，勿重复提交。", result_unknown=True) from exc
