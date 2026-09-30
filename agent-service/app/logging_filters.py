"""日志脱敏过滤器：防止 API Key、密码、Token 等敏感信息写入日志。"""
from __future__ import annotations

import logging
import re

# sk- 开头的 API Key
_SK_PATTERN = re.compile(r"sk-[A-Za-z0-9_-]{8,}")

# URL 里的密码：scheme://user:password@host
_URL_PASSWORD_PATTERN = re.compile(r"(://[^:]+:)[^@\s]+(@)")

# 敏感字段名
_SENSITIVE_KEYS = (
    "api_key", "api-key", "apikey",
    "password", "passwd", "pwd",
    "secret", "token",
    "access_token", "access-token",
    "refresh_token", "refresh-token",
    "authorization", "jwt",
    "private_key", "private-key",
)


def _redact_text(text: str) -> str:
    if not text:
        return text
    # 1. sk- API Key
    text = _SK_PATTERN.sub("sk-***", text)
    # 2. URL 密码
    text = _URL_PASSWORD_PATTERN.sub(lambda m: m.group(1) + "***" + m.group(2), text)
    # 3. 敏感字段的 key=value 或 key: value
    lower = text.lower()
    for key in _SENSITIVE_KEYS:
        idx = 0
        while True:
            pos = lower.find(key, idx)
            if pos < 0:
                break
            # 找到 key 后面的分隔符 : 或 =
            sep_pos = pos + len(key)
            while sep_pos < len(text) and text[sep_pos] in " \t\"'":
                sep_pos += 1
            if sep_pos >= len(text) or text[sep_pos] not in ":=":
                idx = pos + len(key)
                continue
            # 跳过分隔符和空白/引号
            val_start = sep_pos + 1
            while val_start < len(text) and text[val_start] in " \t\"'":
                val_start += 1
            if val_start >= len(text):
                break
            # 找到 value 结束位置
            quote = text[val_start - 1] if text[val_start - 1] in "\"'" else None
            if quote:
                val_end = text.find(quote, val_start)
                if val_end < 0:
                    val_end = len(text)
            else:
                val_end = val_start
                while val_end < len(text) and text[val_end] not in " \t,;}\n":
                    val_end += 1
            if val_end - val_start >= 4:
                text = text[:val_start] + "***" + text[val_end:]
                lower = text.lower()
            idx = val_start + 3
    return text


class RedactingFilter(logging.Filter):
    """对所有日志记录做脱敏，确保敏感值不落盘。"""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = _redact_text(str(record.msg))
            if record.args:
                record.args = tuple(
                    _redact_text(str(a)) if isinstance(a, str) else a
                    for a in record.args
                )
        except Exception:
            pass
        return True


def install_redacting_filter(logger: logging.Logger | None = None) -> None:
    """把脱敏过滤器挂到指定 logger（默认 root logger）。"""
    target = logger or logging.getLogger()
    if not any(isinstance(f, RedactingFilter) for f in target.filters):
        target.addFilter(RedactingFilter())


import random as _random


class SamplingFilter(logging.Filter):
    """OBS-1: 对高频详细日志（如 LLM 输入输出）按概率采样，避免日志爆炸。

    默认采样率 10%（0.1）。ERROR 及以上级别不采样，全部记录。
    """

    def __init__(self, sample_rate: float = 0.1, *keywords: str) -> None:
        super().__init__()
        self._sample_rate = max(0.0, min(1.0, sample_rate))
        self._keywords = keywords or ("llm", "model", "embedding", "prompt")

    def filter(self, record: logging.LogRecord) -> bool:
        # ERROR 及以上全部记录
        if record.levelno >= logging.ERROR:
            return True
        # 非目标关键词的日志全部记录
        msg_lower = str(record.msg).lower()
        if not any(kw in msg_lower for kw in self._keywords):
            return True
        # 目标关键词日志按采样率记录
        return _random.random() < self._sample_rate


def install_sampling_filter(sample_rate: float = 0.1, logger: logging.Logger | None = None) -> None:
    """把采样过滤器挂到指定 logger（默认 root logger）。"""
    target = logger or logging.getLogger()
    if not any(isinstance(f, SamplingFilter) for f in target.filters):
        target.addFilter(SamplingFilter(sample_rate))
