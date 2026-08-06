from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.database import get_repository


_SYNONYMS: dict[str, list[str]] = {
    "退款": ["退款", "退钱", "退货", "售后", "refund", "return"],
    "售后": ["售后", "客服", "退换", "退款", "退货", "after-sales"],
    "取消": ["取消", "撤销", "取消订单", "cancel", "abort"],
    "订单": ["订单", "order", "购物", "购买"],
    "手机": ["手机", "smartphone", "phone", "移动电话"],
    "电脑": ["电脑", "laptop", "笔记本", "笔记本电脑", "pc"],
    "耳机": ["耳机", "headphones", "耳麦"],
    "库存": ["库存", "stock", "存货", "现货"],
    "价格": ["价格", "price", "多少钱", "费用"],
    "支付": ["支付", "payment", "付款", "结账"],
    "规则": ["规则", "政策", "policy", "说明", "条款"],
    "配置": ["配置", "参数", "规格", "spec", "configuration"],
    "确认": ["确认", "二次确认", "验证码", "确认卡"],
}


@dataclass
class _Document:
    id: str
    title: str
    content: str
    tags: list[str]
    source: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "_Document":
        return cls(
            id=str(data["id"]),
            title=str(data.get("title", "")),
            content=str(data.get("content", "")),
            tags=list(data.get("tags", [])),
            source=str(data.get("source", "")),
        )

    def all_text(self) -> str:
        return f"{self.title}\n{self.content}\n{' '.join(self.tags)}"


def _tokenize(text: str) -> list[str]:
    text = text.lower()
    tokens = re.findall(r"[a-z0-9_]+", text)
    chinese_chars = re.findall(r"[\u4e00-\u9fff]", text)
    chinese_bigrams = [
        chinese_chars[i] + chinese_chars[i + 1]
        for i in range(len(chinese_chars) - 1)
    ]
    return tokens + chinese_chars + chinese_bigrams


def _expand_query(query: str) -> list[str]:
    base_tokens = _tokenize(query)
    expanded = list(base_tokens)
    for token in set(base_tokens):
        if token in _SYNONYMS:
            expanded.extend(_SYNONYMS[token])
    return expanded


class KnowledgeBase:
    """
    知识库检索层
    
    优先从数据库读取，如果数据库没有数据则回退到本地 JSON 文件。
    使用 TF-IDF 评分进行文档检索。
    """

    def __init__(self, path: Path | None = None) -> None:
        self._repo = get_repository()
        self._documents: list[_Document] = []
        self._doc_count = 0
        self._df: dict[str, int] = {}
        self._doc_tokens: list[list[str]] = []
        self._title_tokens: list[set[str]] = []
        self._tag_tokens: list[set[str]] = []
        
        # 优先从数据库加载
        self._load_from_database()
        
        # 如果数据库没有数据，回退到 JSON 文件
        if not self._documents:
            self._load_from_json(path)
        
        if not self._documents:
            raise ValueError("knowledge base requires at least one document")
        
        self._build_index()

    def _load_from_database(self) -> None:
        """从数据库加载知识库"""
        try:
            results = self._repo.search_knowledge("", limit=500)
            for item in results:
                tags = []
                if item.get("category"):
                    tags.append(str(item["category"]))
                if item.get("keywords"):
                    tags.extend(item["keywords"].split())
                self._documents.append(_Document(
                    id=str(item["id"]),
                    title=item.get("title", ""),
                    content=item.get("content", ""),
                    tags=tags,
                    source="database",
                ))
            if self._documents:
                import logging
                logging.getLogger(__name__).info(
                    f"从数据库加载 {len(self._documents)} 条知识"
                )
        except Exception:
            pass  # 数据库不可用时回退到 JSON

    def _load_from_json(self, path: Path | None = None) -> None:
        """从 JSON 文件加载知识库"""
        source = path or Path(__file__).parent / "knowledge" / "documents.json"
        if source.exists():
            raw = json.loads(source.read_text(encoding="utf-8"))
            for item in raw:
                self._documents.append(_Document.from_dict(item))
            if self._documents:
                import logging
                logging.getLogger(__name__).info(
                    f"从 JSON 文件加载 {len(self._documents)} 条知识"
                )

    def _build_index(self) -> None:
        self._doc_count = len(self._documents)
        for doc in self._documents:
            title_set = set(_tokenize(doc.title))
            tag_set = set(_tokenize(" ".join(doc.tags)))
            tokens = _tokenize(doc.all_text())
            self._doc_tokens.append(tokens)
            self._title_tokens.append(title_set)
            self._tag_tokens.append(tag_set)
            for token in set(tokens):
                self._df[token] = self._df.get(token, 0) + 1

    @staticmethod
    def _tf(tokens: list[str]) -> dict[str, float]:
        if not tokens:
            return {}
        counts: dict[str, float] = {}
        for token in tokens:
            counts[token] = counts.get(token, 0.0) + 1.0
        total = len(tokens)
        return {token: count / total for token, count in counts.items()}

    def _idf(self, token: str) -> float:
        df = self._df.get(token, 0)
        return math.log((self._doc_count + 1) / (df + 1)) + 1.0

    def _score_document(self, query_tokens: list[str], doc_index: int) -> float:
        doc_tokens = self._doc_tokens[doc_index]
        if not doc_tokens:
            return 0.0

        tf = self._tf(doc_tokens)
        title_set = self._title_tokens[doc_index]
        tag_set = self._tag_tokens[doc_index]
        unique_query_tokens = set(query_tokens)

        score = 0.0
        for token in unique_query_tokens:
            if token not in tf:
                continue
            idf = self._idf(token)
            tf_val = tf[token]
            weight = 1.0
            if token in title_set:
                weight += 2.0
            if token in tag_set:
                weight += 1.5
            score += tf_val * idf * weight

        title_hits = sum(1 for token in unique_query_tokens if token in title_set)
        if title_hits > 0:
            score *= 1.0 + 0.3 * title_hits

        if unique_query_tokens & tag_set:
            score *= 1.2

        return score

    def search(self, query: str, limit: int = 3) -> list[dict[str, Any]]:
        if limit < 1:
            return []
        query = (query or "").strip()
        if not query:
            return []

        query_tokens = _expand_query(query)
        if not query_tokens:
            return []

        scored = [
            (idx, self._score_document(query_tokens, idx))
            for idx in range(self._doc_count)
        ]
        scored.sort(key=lambda item: item[1], reverse=True)

        results: list[dict[str, Any]] = []
        for idx, score in scored[:limit]:
            if score <= 0:
                break
            doc = self._documents[idx]
            results.append(
                {
                    "id": doc.id,
                    "title": doc.title,
                    "content": doc.content,
                    "source": doc.source,
                }
            )
        return results
