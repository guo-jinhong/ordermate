"""Prometheus 指标埋点：QPS / 延迟 / 成功率 / 工具调用 / 知识库召回。"""
from __future__ import annotations

from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

# 接口请求
chat_requests_total = Counter(
    "agent_chat_requests_total",
    "Total chat requests",
    ["status"],  # success / error / rate_limited
)
chat_latency_seconds = Histogram(
    "agent_chat_latency_seconds",
    "Chat request latency",
    buckets=[0.1, 0.5, 1, 2, 5, 10, 20, 30],
)

# LLM 调用
llm_calls_total = Counter(
    "agent_llm_calls_total",
    "Total LLM calls",
    ["model", "outcome"],  # outcome: success / error / timeout
)
llm_latency_seconds = Histogram(
    "agent_llm_latency_seconds",
    "LLM call latency",
    buckets=[0.1, 0.5, 1, 2, 5, 10, 20],
)

# 工具调用
tool_calls_total = Counter(
    "agent_tool_calls_total",
    "Total tool calls",
    ["tool_name", "outcome"],  # outcome: success / error
)

# 知识库检索
kb_search_total = Counter(
    "agent_kb_search_total",
    "Total knowledge base searches",
    ["doc_type"],
)
kb_hit_count = Counter(
    "agent_kb_hit_total",
    "Knowledge base search hits (returned > 0 results)",
    ["doc_type"],
)

# 活跃会话数
active_sessions = Gauge(
    "agent_active_sessions",
    "Number of active sessions",
)


def metrics_text() -> bytes:
    return generate_latest()


def metrics_content_type() -> str:
    return CONTENT_TYPE_LATEST
