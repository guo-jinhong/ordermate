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


# 知识库文档注入检测：检索结果可能被恶意构造为指令载体
_CHUNK_INJECTION_PATTERNS = (
    re.compile(r"(?i)(ignore|disregard|forget)\s+(all\s+)?(previous|prior|above|system|initial)\s+(instructions?|rules?|prompts?|context)"),
    re.compile(r"(?i)you\s+are\s+now\s+(an?\s+)?(new|different|unrestricted)"),
    re.compile(r"(?i)(reveal|show|display|print|output|leak)\s+(the\s+)?(system\s+prompt|developer\s+message|hidden\s+instruction)"),
    re.compile(r"忽略.{0,15}(以上|之前|先前|系统|上面|所有).{0,15}(指令|规则|提示|约束|要求)"),
    re.compile(r"(忽略|无视|忘记|推翻).{0,10}(规则|约束|指令|限制)"),
    re.compile(r"你现在是.{0,30}(客服|助手|系统|管理员|root)"),
    re.compile(r"(泄露|展示|输出|打印|显示).{0,12}(系统提示词|隐藏指令|内部规则|密钥|token)"),
    re.compile(r"(?i)act\s+as\s+if"),
)


def is_injected_chunk(text: str) -> bool:
    """Detect prompt-injection attempts embedded in retrieved knowledge chunks."""
    if not text:
        return False
    return any(pattern.search(text) for pattern in _CHUNK_INJECTION_PATTERNS)


def strip_injection_markers(text: str) -> str:
    """Replace injection-bearing chunk content with a safe placeholder."""
    if is_injected_chunk(text):
        return "[已过滤：该知识库片段包含可疑指令，已阻止注入]"
    return text
