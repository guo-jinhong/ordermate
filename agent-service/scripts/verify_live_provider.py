"""低成本验证 live 模型连通性及工具调用能力，不输出密钥或完整响应。"""
from __future__ import annotations

import asyncio

from openai import AsyncOpenAI

from app.config import Settings


async def main() -> int:
    settings = Settings.from_env()
    if not settings.openai_api_key or not settings.openai_base_url or not settings.openai_model:
        print("LIVE_CHECK=SKIP reason=missing_configuration")
        return 2

    client = AsyncOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        timeout=settings.request_timeout_seconds,
    )
    try:
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": "你必须调用提供的工具完成检查。"},
                {"role": "user", "content": "请执行连通性检查。"},
            ],
            tools=[{
                "type": "function",
                "function": {
                    "name": "ping",
                    "description": "连通性检查",
                    "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
                },
            }],
            max_tokens=128,
        )
        calls = response.choices[0].message.tool_calls or []
        ok = bool(calls and calls[0].function.name == "ping")
        print(f"LIVE_CHECK={'PASS' if ok else 'FAIL'} model={settings.openai_model} tool_call={ok}")
        return 0 if ok else 1
    except Exception as exc:
        status = getattr(exc, "status_code", "unknown")
        root = exc
        while root.__cause__ is not None:
            root = root.__cause__
        print(
            f"LIVE_CHECK=FAIL error={type(exc).__name__} status={status} "
            f"root={type(root).__name__}: {root}"
        )
        return 1
    finally:
        await client.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
