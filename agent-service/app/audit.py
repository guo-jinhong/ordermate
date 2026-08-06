from __future__ import annotations

import json
import logging
import time
from typing import Any

from app.conversation_memory import redact_sensitive_text


class AuditLogger:
    """Structured, redacted operational events; never log plaintext credentials."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger("agent.audit")

    def emit(self, event: str, **fields: Any) -> None:
        safe = {"event": event, "timestamp_ms": int(time.time() * 1000)}
        safe.update(
            {
                key: self._redact(value)
                for key, value in fields.items()
                if key.lower() not in {"access_token", "password", "authorization"}
            }
        )
        self._logger.info(json.dumps(safe, ensure_ascii=False, default=str))

    @staticmethod
    def _redact(value: Any) -> Any:
        if isinstance(value, str):
            return redact_sensitive_text(value)
        if isinstance(value, dict):
            return {key: AuditLogger._redact(item) for key, item in value.items() if key.lower() not in {"access_token", "password", "authorization"}}
        if isinstance(value, list):
            return [AuditLogger._redact(item) for item in value]
        return value
