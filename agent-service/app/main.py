from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from openai import AsyncOpenAI
from redis.asyncio import Redis, from_url

from app.agent import AgentService
from app.audit import AuditLogger
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
from app.config import Settings
from app.demo_agent import DemoAgentService
from app.schemas import (
    ChatRequest,
    ChatResponse,
    ClearConversationRequest,
    ClearConversationResponse,
    ConfirmRequest,
    ConfirmResponse,
    HealthResponse,
    LoginRequest,
    LoginResponse,
)
from app.tools.confirmation import ConfirmationStore, fingerprint_access_token
from app.tools.registry import ToolRegistry


logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    *,
    model_client: Any | None = None,
    ecommerce_client: Any | None = None,
    redis_client: Redis | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()

    # 根据配置选择电商后端
    if ecommerce_client is None:
        if settings.ecommerce_backend == "database":
            ecommerce = MysqlEcommerceClient()
            logger.info(f"Using {settings.db_type} backend for ecommerce")
        else:
            ecommerce = EcommerceClient(
                settings.ecommerce_api_base_url,
                settings.request_timeout_seconds,
            )
            logger.info("Using HTTP API backend for ecommerce")
    else:
        ecommerce = ecommerce_client
    redis = redis_client
    if redis is None and settings.redis_url:
        redis = from_url(settings.redis_url, decode_responses=True)
    if redis is None:
        confirmations = ConfirmationStore()
        memory = ConversationMemoryStore(
            max_messages=settings.conversation_max_messages,
            ttl_seconds=settings.conversation_ttl_seconds,
        )
    else:
        confirmations = RedisConfirmationStore(redis)
        memory = RedisConversationMemoryStore(
            redis,
            max_messages=settings.conversation_max_messages,
            ttl_seconds=settings.conversation_ttl_seconds,
        )
    registry = ToolRegistry(ecommerce, confirmations)
    audit = AuditLogger()
    approval_workflow = ApprovalWorkflow()

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

    if model_client is None and agent_mode == "live" and settings.openai_api_key:
        client_options: dict[str, Any] = {"api_key": settings.openai_api_key}
        if settings.openai_base_url:
            client_options["base_url"] = settings.openai_base_url
        model_client = AsyncOpenAI(**client_options)

    if model_client is not None:
        agent = AgentService(
            model_client,
            registry,
            model=settings.openai_model,
            max_tool_rounds=settings.max_tool_rounds,
            memory=memory,
            state_store=state_store,
            confirmed_action_executor=lambda action, arguments, access_token: _execute_confirmed_action(
                ecommerce, action, arguments, access_token
            ),
        )
        active_mode = "live"
    elif agent_mode == "demo":
        agent = DemoAgentService(registry, state_store=state_store)
        active_mode = "demo"
    else:
        agent = None
        active_mode = "live"

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        workflow_saver = None
        if settings.redis_url:
            from langgraph.checkpoint.redis.aio import AsyncRedisSaver

            workflow_saver = AsyncRedisSaver(settings.redis_url)
            await workflow_saver.asetup()
            approval_workflow.set_checkpointer(workflow_saver)
        yield
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
    static_dir = Path(__file__).resolve().parent / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            model_configured=agent is not None,
            agent_mode=active_mode,
            backend_base_url=settings.ecommerce_api_base_url,
        )

    @app.post("/auth/login", response_model=LoginResponse)
    async def login(request: LoginRequest) -> LoginResponse:
        try:
            token = await ecommerce.login(request.username, request.password)
        except EcommerceApiError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        return LoginResponse(access_token=token)

    @app.post("/chat", response_model=ChatResponse)
    async def chat(request: ChatRequest) -> ChatResponse:
        if agent is None:
            raise HTTPException(
                status_code=503,
                detail="OPENAI_API_KEY is not configured.",
            )
        try:
            return await run_chat(request)
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("Unhandled Agent error")
            raise HTTPException(
                status_code=500,
                detail="Agent 执行时遇到内部错误，请稍后重试或换个问法。",
            ) from exc

    async def run_chat(request: ChatRequest) -> ChatResponse:
        audit.emit("chat_started", session_id=request.session_id, message=request.message)
        result = await agent.chat(
            request.message,
            session_id=request.session_id,
            access_token=request.access_token,
        )
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
        return result

    @app.post("/chat/stream")
    async def chat_stream(request: ChatRequest) -> StreamingResponse:
        """SSE-compatible chat endpoint with safe, user-visible execution events."""
        if agent is None:
            raise HTTPException(status_code=503, detail="OPENAI_API_KEY is not configured.")

        async def events():
            yield _sse("started", {"message": "正在理解你的问题"})
            task = asyncio.create_task(
                run_chat(request)
            )
            try:
                while not task.done():
                    yield _sse("progress", {"message": "Agent 正在处理"})
                    await asyncio.sleep(0.75)
                result = await task
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
                                "error": call.result_message,
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
            except Exception:
                logger.exception("Unhandled streaming Agent error")
                yield _sse(
                    "error",
                    {"detail": "Agent 执行时遇到内部错误，请稍后重试或换个问法。"},
                )
            finally:
                if not task.done():
                    task.cancel()

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/conversation/clear", response_model=ClearConversationResponse)
    async def clear_conversation(
        request: ClearConversationRequest,
    ) -> ClearConversationResponse:
        memory_cleared = await memory.clear_session(request.session_id)
        state_cleared = await state_store.clear_session(request.session_id)
        return ClearConversationResponse(
            status="cleared",
            cleared=memory_cleared > 0 or state_cleared > 0,
        )

    @app.post("/confirm", response_model=ConfirmResponse)
    async def confirm(request: ConfirmRequest) -> ConfirmResponse:
        if not request.access_token:
            raise HTTPException(status_code=401, detail="Please log in first.")

        pending = await confirmations.consume(
            request.confirmation_token,
            request.session_id,
            fingerprint_access_token(request.access_token),
        )
        if pending is None:
            raise HTTPException(
                status_code=404,
                detail="Confirmation is invalid, expired, or already used.",
            )
        if not await approval_workflow.resume(
            request.confirmation_token, request.approved
        ):
            audit.emit("confirmation_rejected", action=pending.action)
            return ConfirmResponse(status="cancelled", message="已放弃本次操作，数据没有被修改。")

        try:
            data, message = await _execute_confirmed_action(
                ecommerce, pending.action, pending.arguments, request.access_token
            )
        except EcommerceApiError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        return ConfirmResponse(
            status="executed",
            message=message,
            data=data,
        )

    return app


app = create_app()


def _sse(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _execute_confirmed_action(
    ecommerce: Any,
    action: str,
    arguments: dict[str, Any],
    access_token: str,
) -> tuple[Any, str]:
    if action == "cancel_order":
        data = await ecommerce.cancel_order(arguments["order_id"], access_token)
        return data, f"订单 {arguments['order_id']} 已成功取消。"
    if action == "update_cart":
        data = await ecommerce.update_cart(
            arguments["cart_id"], arguments["quantity"], access_token
        )
        return data, f"购物车项 {arguments['cart_id']} 数量已修改为 {arguments['quantity']}。"
    if action == "update_cart_items":
        results = []
        for item in arguments["items"]:
            data = await ecommerce.update_cart(
                item["cart_id"], item["quantity"], access_token
            )
            results.append({"cart_id": item["cart_id"], "quantity": item["quantity"], "data": data})
        return results, f"已将 {len(results)} 个购物车项的数量都修改为 {arguments['quantity']}。"
    if action == "remove_from_cart":
        data = await ecommerce.remove_from_cart(arguments["cart_id"], access_token)
        return data, f"购物车项 {arguments['cart_id']} 已删除。"
    if action == "clear_cart":
        data = await ecommerce.clear_cart(access_token)
        return data, "购物车已清空。"
    if action == "create_order":
        data = await ecommerce.create_order(
            arguments["product_id"],
            arguments["quantity"],
            arguments.get("address_id", 1),
            arguments.get("payment_method", "DEMO"),
            access_token,
        )
        return data, "订单已创建。"
    if action == "pay_order":
        data = await ecommerce.pay_order(arguments["order_id"], access_token)
        return data, f"订单 {arguments['order_id']} 已完成支付确认。"
    raise ValueError(f"Unsupported pending action: {action}")
