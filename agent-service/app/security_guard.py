from __future__ import annotations

import re


_INJECTION_PATTERNS = (
    re.compile(r"(?i)ignore\s+(all\s+)?(previous|prior|system)\s+instructions"),
    re.compile(r"(?i)reveal\s+(the\s+)?(system\s+prompt|api\s*key|secret)"),
    re.compile(r"(?i)system\s+prompt|developer\s+message"),
    re.compile(r"忽略.{0,12}(之前|以上|系统).{0,12}(指令|规则)"),
    re.compile(r"(泄露|展示|输出).{0,12}(提示词|密钥|token|密码)"),
)


def is_suspicious_instruction(message: str) -> bool:
    """Conservative guard for attempts to override instructions or extract secrets."""
    return any(pattern.search(message) for pattern in _INJECTION_PATTERNS)
