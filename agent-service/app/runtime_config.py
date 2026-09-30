"""运行时动态配置（降级开关）：通过 Redis 存储，支持热切换，无需重启服务。

支持的配置项：
- force_demo: bool           强制 demo 模式（不调用 LLM），用于 LLM 故障时降级
- disabled_tools: list[str]  禁用的工具名称列表
- max_tool_rounds: int       覆盖最大工具调用轮数
"""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_REDIS_KEY = "agent:runtime_config"
_DEFAULTS: dict[str, Any] = {
    "force_demo": False,
    "disabled_tools": [],
    "max_tool_rounds": None,
}


class RuntimeConfig:
    def __init__(self, redis_client: Any | None = None) -> None:
        self._redis = redis_client
        self._cache: dict[str, Any] = dict(_DEFAULTS)

    async def load(self) -> dict[str, Any]:
        if self._redis is None:
            return dict(self._cache)
        try:
            raw = await self._redis.get(_REDIS_KEY)
            if raw:
                data = json.loads(raw)
                self._cache.update(data)
        except Exception as exc:
            logger.warning("runtime config load failed: %s", exc)
        return dict(self._cache)

    async def save(self, overrides: dict[str, Any]) -> dict[str, Any]:
        # 只允许已知配置项
        valid = {k: v for k, v in overrides.items() if k in _DEFAULTS}
        self._cache.update(valid)
        if self._redis is not None:
            try:
                await self._redis.set(_REDIS_KEY, json.dumps(self._cache))
            except Exception as exc:
                logger.warning("runtime config save failed: %s", exc)
        return dict(self._cache)

    def get(self, key: str, default: Any = None) -> Any:
        return self._cache.get(key, default)

    @property
    def force_demo(self) -> bool:
        return bool(self._cache.get("force_demo", False))

    @property
    def disabled_tools(self) -> list[str]:
        return list(self._cache.get("disabled_tools", []))

    @property
    def max_tool_rounds(self) -> int | None:
        return self._cache.get("max_tool_rounds")
