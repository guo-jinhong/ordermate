"""轻量级异步熔断器：失败次数达阈值后熔断，超时后半开探测。

不依赖 pybreaker，原生 async 友好，支持 LLM 调用和外部 API 调用的熔断保护。
"""
from __future__ import annotations

import asyncio
import logging
import time
from enum import Enum

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpenError(Exception):
    """熔断器处于 open 状态时抛出，上层应捕获并降级。"""


class AsyncCircuitBreaker:
    def __init__(
        self,
        name: str,
        *,
        failure_threshold: int = 5,
        recovery_timeout_seconds: float = 30.0,
        half_open_max_calls: int = 1,
        on_open_callback=None,
        alert_cooldown_seconds: float = 300.0,
    ) -> None:
        self._name = name
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout_seconds
        self._half_open_max = half_open_max_calls
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._opened_at: float | None = None
        self._half_open_calls = 0
        self._lock = asyncio.Lock()
        # STAB-2: 熔断器 open 告警回调 + 频率限制（默认 5 分钟内只告警一次）
        self._on_open_callback = on_open_callback
        self._alert_cooldown = alert_cooldown_seconds
        self._last_alert_at: float = 0.0

    @property
    def state(self) -> CircuitState:
        return self._state

    async def call(self, coro_func, *args, **kwargs):
        """调用异步函数，带熔断保护。coro_func 必须是返回 coroutine 的函数。"""
        # 状态检查（需要锁，因为多请求可能同时检查）
        async with self._lock:
            if self._state == CircuitState.OPEN:
                assert self._opened_at is not None
                if time.monotonic() - self._opened_at >= self._recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_calls = 0
                    logger.info("circuit %s -> half_open", self._name)
                else:
                    raise CircuitBreakerOpenError(f"circuit {self._name} is open")
            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_calls >= self._half_open_max:
                    raise CircuitBreakerOpenError(f"circuit {self._name} half_open saturated")
                self._half_open_calls += 1

        try:
            result = await coro_func(*args, **kwargs)
        except CircuitBreakerOpenError:
            raise
        except Exception:
            await self._on_failure()
            raise
        else:
            await self._on_success()
            return result

    async def _on_success(self) -> None:
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self._half_open_calls = 0
                logger.info("circuit %s -> closed (recovery success)", self._name)
            elif self._state == CircuitState.CLOSED:
                self._failure_count = 0

    async def _on_failure(self) -> None:
        async with self._lock:
            self._failure_count += 1
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                self._opened_at = time.monotonic()
                logger.warning("circuit %s -> open (half_open failed)", self._name)
            elif self._state == CircuitState.CLOSED and self._failure_count >= self._failure_threshold:
                self._state = CircuitState.OPEN
                self._opened_at = time.monotonic()
                logger.warning(
                    "circuit %s -> open (failures=%d)", self._name, self._failure_count
                )
                await self._trigger_alert()

    async def _trigger_alert(self) -> None:
        """STAB-2: 熔断器 open 时触发告警，带频率限制。"""
        if self._on_open_callback is None:
            return
        now = time.monotonic()
        if now - self._last_alert_at < self._alert_cooldown:
            return
        self._last_alert_at = now
        try:
            await self._on_open_callback(self._name, self._failure_count)
        except Exception as exc:
            logger.warning("circuit %s alert callback failed: %s", self._name, exc)
