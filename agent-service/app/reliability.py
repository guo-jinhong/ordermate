"""请求执行边界：总超时、写入标记和同会话互斥。"""
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from hashlib import sha256
import asyncio
import logging
import secrets

from fastapi import HTTPException


@dataclass
class ExecutionState:
    write_attempted: bool = False


execution_state: ContextVar[ExecutionState | None] = ContextVar("execution_state", default=None)


def mark_write_attempt() -> None:
    state = execution_state.get()
    if state is not None:
        state.write_attempted = True


class SessionCoordinator:
    def __init__(self, redis=None, lease_seconds=90):
        self.redis = redis
        self.lease_seconds = lease_seconds
        self.active = set()

    @asynccontextmanager
    async def hold(self, session_id, access_token):
        key = "agent:session-lock:" + sha256(f"{session_id}:{access_token or ''}".encode()).hexdigest()
        owner = secrets.token_hex(16)
        if self.redis is None:
            if key in self.active:
                raise HTTPException(409, "当前会话正在处理，请等待本次操作结束。")
            self.active.add(key)
        else:
            try:
                acquired = await self.redis.set(key, owner, nx=True, ex=self.lease_seconds)
            except Exception as exc:
                raise HTTPException(503, "暂时无法保护本次操作，请稍后再试。") from exc
            if not acquired:
                raise HTTPException(409, "当前会话正在处理，请等待本次操作结束。")
        try:
            yield
        finally:
            if self.redis is None:
                self.active.discard(key)
            else:
                try:
                    await asyncio.wait_for(self.redis.eval("if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) end return 0", 1, key, owner), 3)
                except Exception:
                    # 释放失败由租期回收，不覆盖已经核实的业务结果。
                    logging.getLogger(__name__).warning("Session lock release failed; waiting for lease expiry")


@asynccontextmanager
async def request_budget(seconds):
    state = ExecutionState()
    token = execution_state.set(state)
    try:
        async with asyncio.timeout(seconds):
            yield state
    except TimeoutError as exc:
        message = "处理超时，操作结果暂时无法确认，请先查看购物车或订单，暂时不要重复提交。" if state.write_attempted else "处理超时，请稍后再试。"
        raise HTTPException(504, message) from exc
    finally:
        execution_state.reset(token)


class RedisDemoQuota:
    """原子共享额度及有租期的在途请求，不因工作进程退出永久占用名额。"""
    def __init__(self, redis, daily_limit, max_concurrent, lease_seconds=90):
        self.redis = redis
        self.daily_limit = daily_limit
        self.max_concurrent = max_concurrent
        self.lease_seconds = lease_seconds

    async def reserve(self):
        import time
        now = time.time()
        owner = secrets.token_hex(16)
        count_key = f"agent:quota:day:{int(now // 86400)}"
        result = await self.redis.eval("""
local used=tonumber(redis.call('get',KEYS[1]) or '0')
redis.call('zremrangebyscore',KEYS[2],'-inf',ARGV[1])
if used>=tonumber(ARGV[3]) then return 1 end
if redis.call('zcard',KEYS[2])>=tonumber(ARGV[4]) then return 2 end
redis.call('incr',KEYS[1]); redis.call('expire',KEYS[1],172800)
redis.call('zadd',KEYS[2],ARGV[2],ARGV[5]); redis.call('expire',KEYS[2],tonumber(ARGV[6]))
return 0
""", 2, count_key, "agent:quota:active", now, now + self.lease_seconds, self.daily_limit, self.max_concurrent, owner, self.lease_seconds)
        if result:
            raise HTTPException(429, "今日演示调用额度已用完。" if result == 1 else "当前演示请求较多，请稍后再试。")
        return owner

    async def release(self, owner=None):
        if owner:
            try:
                await asyncio.wait_for(self.redis.zrem("agent:quota:active", owner), 3)
            except Exception:
                # 名额有租期兜底，清理故障不能把成功回执变成失败。
                logging.getLogger(__name__).warning("Demo quota release failed; waiting for lease expiry")
