"""服务端确认快照和操作结果日志；执行前占位，失败后绝不自动重放写入。"""
import asyncio
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.tools.confirmation import PendingAction


class OperationStore:
    def __init__(self, path, redis=None):
        self.path = path
        self.redis = redis
        if redis is None:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as db:
                db.execute("CREATE TABLE IF NOT EXISTS agent_operations (token TEXT PRIMARY KEY, record TEXT NOT NULL)")

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            db.execute("PRAGMA busy_timeout=5000")
            with db:
                yield db
        finally:
            db.close()

    async def put(self, pending):
        value = {"token": pending.token, "session_id": pending.session_id, "fingerprint": pending.authorization_fingerprint,
                 "action": pending.action, "arguments": pending.arguments, "expires_at": pending.expires_at.isoformat(),
                 "status": "prepared", "result": None, "updated_at": datetime.now(UTC).isoformat()}
        raw = json.dumps(value, ensure_ascii=False)
        if self.redis is not None:
            await self.redis.set("agent:operation:" + pending.token, raw, nx=True)
        else:
            def write():
                with self._connect() as db:
                    db.execute("INSERT OR IGNORE INTO agent_operations VALUES (?,?)", (pending.token, raw))
            await asyncio.to_thread(write)

    async def get(self, token):
        if self.redis is not None:
            raw = await self.redis.get("agent:operation:" + token)
        else:
            def read():
                with self._connect() as db:
                    row = db.execute("SELECT record FROM agent_operations WHERE token=?", (token,)).fetchone()
                    return row[0] if row else None
            raw = await asyncio.to_thread(read)
        return json.loads(raw) if raw else None

    async def transition(self, token, expected, status, result=None):
        """SQLite 写事务或 Redis CAS，多个进程只允许一个执行者占位。"""
        if self.redis is not None:
            key = "agent:operation:" + token
            raw = await self.redis.get(key)
            if not raw:
                return False
            value = json.loads(raw)
            if value["status"] not in expected:
                return False
            value.update(status=status, result=result, updated_at=datetime.now(UTC).isoformat())
            return bool(await self.redis.eval("if redis.call('get',KEYS[1])==ARGV[1] then redis.call('set',KEYS[1],ARGV[2]); return 1 end return 0", 1, key, raw, json.dumps(value, ensure_ascii=False)))
        def write():
            with self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute("SELECT record FROM agent_operations WHERE token=?", (token,)).fetchone()
                if not row:
                    return False
                value = json.loads(row[0])
                if value["status"] not in expected:
                    return False
                value.update(status=status, result=result, updated_at=datetime.now(UTC).isoformat())
                db.execute("UPDATE agent_operations SET record=? WHERE token=?", (json.dumps(value, ensure_ascii=False), token))
                return True
        return await asyncio.to_thread(write)

    async def cancel_prepared(self, session_id, fingerprint):
        """清理当前身份的待确认快照，保留已受理及已执行操作的结果。"""
        result = {"status": "cancelled", "message": "会话已清空，本次待确认操作已取消。", "data": None}
        if self.redis is not None:
            cancelled = 0
            async for key in self.redis.scan_iter(match="agent:operation:*"):
                raw = await self.redis.get(key)
                if not raw:
                    continue
                value = json.loads(raw)
                if value["session_id"] == session_id and value["fingerprint"] == fingerprint:
                    cancelled += int(await self.transition(value["token"], {"prepared"}, "cancelled", result))
            return cancelled
        def write():
            cancelled = 0
            with self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                rows = db.execute(
                    "SELECT token, record FROM agent_operations WHERE json_extract(record,'$.session_id')=? "
                    "AND json_extract(record,'$.fingerprint')=? AND json_extract(record,'$.status')='prepared'",
                    (session_id, fingerprint),
                ).fetchall()
                for token, raw in rows:
                    value = json.loads(raw)
                    value.update(status="cancelled", result=result, updated_at=datetime.now(UTC).isoformat())
                    db.execute("UPDATE agent_operations SET record=? WHERE token=?", (json.dumps(value, ensure_ascii=False), token))
                    cancelled += 1
            return cancelled
        return await asyncio.to_thread(write)

    async def has_unresolved_purchase(self, fingerprint, product_id, quantity):
        def matches(value):
            args = value["arguments"]
            return (value["fingerprint"] == fingerprint and value["action"] == "create_order"
                    and value["status"] in {"accepted", "processing", "unknown"}
                    and str(args.get("product_id")) == str(product_id)
                    and str(args.get("quantity")) == str(quantity))
        if self.redis is not None:
            async for key in self.redis.scan_iter(match="agent:operation:*"):
                raw = await self.redis.get(key)
                if raw and matches(json.loads(raw)):
                    return True
            return False
        def read():
            with self._connect() as db:
                rows = db.execute("SELECT record FROM agent_operations WHERE json_extract(record,'$.fingerprint')=? "
                                  "AND json_extract(record,'$.action')='create_order' "
                                  "AND json_extract(record,'$.status') IN ('accepted','processing','unknown')",
                                  (fingerprint,))
                return any(matches(json.loads(row[0])) for row in rows)
        return await asyncio.to_thread(read)

    async def cleanup(self, retention_days=7, *, now=None):
        """仅删除过期终态；未知及已受理操作保留，清理与确认竞争使用 CAS/事务。"""
        now = now or datetime.now(UTC)
        cutoff = now - timedelta(days=retention_days)
        def classify(raw):
            value = json.loads(raw)
            if value["status"] == "prepared" and datetime.fromisoformat(value["expires_at"]) <= now:
                value.update(status="cancelled", updated_at=now.isoformat(), result={
                    "status": "cancelled", "message": "本次确认已过期，未执行操作。", "data": None})
            elif value["status"] in {"executed", "failed", "cancelled"}:
                # 旧记录没有完成时间，保守从首次维护起计时，不能直接删除。
                if "updated_at" not in value:
                    value["updated_at"] = now.isoformat()
                elif datetime.fromisoformat(value["updated_at"]) <= cutoff:
                    return None
            return json.dumps(value, ensure_ascii=False)
        if self.redis is not None:
            removed = 0
            async for key in self.redis.scan_iter(match="agent:operation:*"):
                raw = await self.redis.get(key)
                if not raw:
                    continue
                if isinstance(raw, bytes):
                    raw = raw.decode()
                replacement = classify(raw)
                if replacement is None:
                    removed += int(await self.redis.eval(
                        "if redis.call('get',KEYS[1])==ARGV[1] then return redis.call('del',KEYS[1]) end return 0",
                        1, key, raw))
                elif replacement != raw:
                    await self.redis.eval("if redis.call('get',KEYS[1])==ARGV[1] then redis.call('set',KEYS[1],ARGV[2]); return 1 end return 0",
                                          1, key, raw, replacement)
            return removed
        def write():
            removed = 0
            with self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                for token, raw in db.execute("SELECT token, record FROM agent_operations").fetchall():
                    replacement = classify(raw)
                    if replacement is None:
                        db.execute("DELETE FROM agent_operations WHERE token=?", (token,))
                        removed += 1
                    elif replacement != raw:
                        db.execute("UPDATE agent_operations SET record=? WHERE token=?", (replacement, token))
            return removed
        return await asyncio.to_thread(write)


class JournaledConfirmations:
    def __init__(self, delegate, operations):
        self.delegate = delegate
        self.operations = operations

    async def issue(self, session_id, action, arguments, authorization_fingerprint):
        pending = await self.delegate.issue(session_id, action, arguments, authorization_fingerprint)
        # 由服务端生成，模型及客户端不能选择或替换此键。
        arguments = {**pending.arguments, "_operation_id": pending.token}
        if action == "create_order":
            arguments["idempotency_key"] = pending.token
        pending = replace(pending, arguments=arguments)
        await self.operations.put(pending)
        return pending

    async def consume(self, token, session_id, authorization_fingerprint):
        value = await self.operations.get(token)
        if not value or value["session_id"] != session_id or value["fingerprint"] != authorization_fingerprint:
            return None
        if value["status"] != "prepared" or datetime.fromisoformat(value["expires_at"]) <= datetime.now(UTC):
            return None
        # 重启丢失内存令牌后，仍可恢复未过期的服务端持久化确认快照。
        if not await self.operations.transition(token, {"prepared"}, "accepted"):
            return None
        await self.delegate.consume(token, session_id, authorization_fingerprint)
        return PendingAction(token, session_id, value["action"], value["arguments"], authorization_fingerprint, datetime.fromisoformat(value["expires_at"]))
