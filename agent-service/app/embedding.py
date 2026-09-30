"""文本向量化封装：调用 OpenAI Embedding API 生成文本向量。

用于知识库 Hybrid Search 的向量召回支路。如果没有配置 API Key，
返回 None 由调用方降级到纯 TF-IDF 检索。
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# 向量维度（text-embedding-3-small）
_EMBEDDING_DIM = 1536
def get_embedding_client(
    api_key: str | None,
    base_url: str | None = None,
) -> Any | None:
    """获取独立的 Embedding 客户端。

    Embedding 不复用聊天模型的 Key/Base URL，避免把 OpenAI Embedding
    模型错误发送到仅提供 Chat/Responses API 的供应商。
    """
    if not api_key or api_key in {"sk-demo", "test-key", "your-api-key-here"}:
        return None
    try:
        from openai import AsyncOpenAI
    except ImportError:
        return None
    kwargs: dict[str, Any] = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    return AsyncOpenAI(**kwargs)


async def embed_texts(
    client: Any,
    texts: list[str],
    *,
    model: str,
) -> list[list[float]] | None:
    """批量生成文本向量。失败返回 None（调用方降级）。"""
    if not texts:
        return []
    try:
        resp = await client.embeddings.create(model=model, input=texts)
        return [item.embedding for item in resp.data]
    except Exception as exc:
        logger.warning("embedding 生成失败，降级到 TF-IDF: %s", exc)
        return None


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """计算两个向量的余弦相似度。"""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
