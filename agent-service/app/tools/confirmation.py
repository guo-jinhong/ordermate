from __future__ import annotations

import asyncio
import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any


@dataclass(frozen=True)
class PendingAction:
    token: str
    session_id: str
    action: str
    arguments: dict[str, Any]
    authorization_fingerprint: str
    expires_at: datetime


class ConfirmationStore:
    def __init__(self, ttl_minutes: int = 5) -> None:
        self._ttl = timedelta(minutes=ttl_minutes)
        self._pending: dict[str, PendingAction] = {}
        self._lock = asyncio.Lock()

    async def issue(
        self,
        session_id: str,
        action: str,
        arguments: dict[str, Any],
        authorization_fingerprint: str,
    ) -> PendingAction:
        pending = PendingAction(
            token=secrets.token_urlsafe(24),
            session_id=session_id,
            action=action,
            arguments=arguments,
            authorization_fingerprint=authorization_fingerprint,
            expires_at=datetime.now(UTC) + self._ttl,
        )
        async with self._lock:
            self._remove_expired()
            self._pending[pending.token] = pending
        return pending

    async def consume(
        self,
        token: str,
        session_id: str,
        authorization_fingerprint: str,
    ) -> PendingAction | None:
        async with self._lock:
            self._remove_expired()
            pending = self._pending.get(token)
            if (
                pending is None
                or pending.session_id != session_id
                or not secrets.compare_digest(
                    pending.authorization_fingerprint,
                    authorization_fingerprint,
                )
            ):
                return None
            return self._pending.pop(token)

    def _remove_expired(self) -> None:
        now = datetime.now(UTC)
        expired = [
            token
            for token, pending in self._pending.items()
            if pending.expires_at <= now
        ]
        for token in expired:
            self._pending.pop(token, None)


def fingerprint_access_token(access_token: str) -> str:
    """Bind confirmations to a login without retaining the JWT itself."""
    return hashlib.sha256(access_token.encode("utf-8")).hexdigest()
