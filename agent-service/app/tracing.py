"""全链路 trace_id 管理：contextvar 存储 + logging.Filter 自动注入。"""
from __future__ import annotations

import logging
import uuid
from contextvars import ContextVar

# 当前请求的 trace_id，异步上下文隔离
_trace_id_var: ContextVar[str] = ContextVar("trace_id", default="-")


def get_trace_id() -> str:
    return _trace_id_var.get()


def set_trace_id(trace_id: str) -> None:
    _trace_id_var.set(trace_id)


def new_trace_id() -> str:
    return uuid.uuid4().hex[:16]


class TraceIdFilter(logging.Filter):
    """把当前上下文的 trace_id 注入到每条日志记录。"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = get_trace_id()
        return True


def install_trace_id_filter(logger: logging.Logger | None = None) -> None:
    target = logger or logging.getLogger()
    if not any(isinstance(f, TraceIdFilter) for f in target.filters):
        target.addFilter(TraceIdFilter())


class TraceIdFormatter(logging.Formatter):
    """日志格式化器：确保 record 始终有 trace_id 属性（默认 "-"）。"""

    def format(self, record: logging.LogRecord) -> str:
        if not hasattr(record, "trace_id"):
            record.trace_id = get_trace_id()
        return super().format(record)
