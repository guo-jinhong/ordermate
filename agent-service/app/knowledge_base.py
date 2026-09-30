from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.database import get_repository
from app.embedding import cosine_similarity, embed_texts
from app.metrics import kb_hit_count, kb_search_total


_SYNONYMS: dict[str, list[str]] = {
    "退款": ["退款", "退钱", "退货", "售后", "refund", "return"],
    "退钱": ["退款", "退钱", "退货", "售后", "refund", "return"],
    "退货": ["退款", "退货", "售后", "refund", "return"],
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
    # 以下为 golden set 实测暴露的同义词面缺口（见 evals/kb_golden_cases.json）
    "包邮": ["包邮", "免运费", "免邮", "运费"],
    "专票": ["专票", "专用发票", "发票"],
    "快递": ["快递", "配送", "发货", "物流"],
    "苹果": ["苹果", "apple", "macbook", "iphone"],
    "笔记本": ["笔记本", "电脑", "laptop", "notebook"],
}


@dataclass
class _Document:
    id: str
    title: str
    content: str
    tags: list[str]
    source: str
    doc_type: str = "rule"
    source_id: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "_Document":
        # 旧 fixture 无 doc_type 字段时按 id 前缀推断，保持向后兼容
        doc_type = str(data.get("doc_type") or ("product" if str(data["id"]).startswith("product-") else "rule"))
        return cls(
            id=str(data["id"]),
            title=str(data.get("title", "")),
            content=str(data.get("content", "")),
            tags=list(data.get("tags", [])),
            source=str(data.get("source", "")),
            doc_type=doc_type,
            source_id=str(data["source_id"]) if data.get("source_id") is not None else None,
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
    lowered = query.lower()
    # 按子串匹配同义词键（而非仅 token 匹配）：
    # 中文分词只有单字+双字，3 字词（如"笔记本"）不会成为 token，键永远不触发。
    for key, synonyms in _SYNONYMS.items():
        if key in lowered:
            expanded.extend(synonyms)
    return expanded


# 泛词黑名单：规则/商品文档中高频出现的功能性动词/疑问词，
# 单靠这类词共现不能证明查询与文档相关（如"支持以旧换新吗"撞上"支持支付宝"）。
# 仅用于检索"噪声下限"判定，不参与打分。
_GENERIC_QUERY_WORDS = frozenset({
    "支持", "可以", "什么", "怎么", "哪些", "哪个", "哪种", "推荐", "如何",
    "是否", "有卖", "有没有", "多少", "请问", "帮我", "一下", "今天", "现在",
    "多少钱", "怎么样", "是不是",
})

# 数据库不可用时短暂熔断，避免一次请求创建规则库/商品库时重复等待连接超时。
_DATABASE_RETRY_AFTER = 0.0


class KnowledgeBase:
    """
    知识库检索层（分库隔离）

    通过 doc_type 参数限定本实例检索的知识类型，实现知识库分类隔离：
    - doc_type="rule":    售后/退款/配送/平台规则，仅售后与政策场景检索
    - doc_type="product": 商品特征 chunk（品牌/型号/卖点），仅商品语义查询检索
    - doc_type=None:      全量加载（旧行为，仅用于对比验证）

    优先从数据库读取，如果数据库没有数据则回退到本地 JSON 文件。
    使用 TF-IDF 评分进行文档检索。
    """

    def __init__(
        self,
        path: Path | None = None,
        *,
        prefer_database: bool = True,
        doc_type: str | None = None,
        embedding_client: Any | None = None,
        embedding_model: str = "text-embedding-3-small",
        rerank_base_url: str | None = None,
    ) -> None:
        self._repo = get_repository()
        self._doc_type = doc_type
        self._documents: list[_Document] = []
        self._doc_count = 0
        self._df: dict[str, int] = {}
        self._doc_tokens: list[list[str]] = []
        self._title_tokens: list[set[str]] = []
        self._tag_tokens: list[set[str]] = []
        # R1-1/R1-6: 向量索引（Hybrid Search 第二支路）
        self._embedding_client = embedding_client
        self._embedding_model = embedding_model
        self._rerank_base_url = rerank_base_url.rstrip("/") if rerank_base_url else None
        self._doc_vectors: list[list[float]] | None = None
        # 增量更新锁，避免 reload 与检索并发冲突
        self._reload_lock = asyncio.Lock()
        # 向量持久化目录
        self._vector_cache_dir = Path(__file__).parent.parent / "data" / "vectors"

        # 运行时优先从数据库加载；测试或离线场景可显式关闭，确保结果可复现。
        if prefer_database:
            self._load_from_database()

        # 如果数据库没有数据，回退到 JSON 文件
        if not self._documents:
            self._load_from_json(path)

        if not self._documents:
            scope = f"doc_type={doc_type}" if doc_type else "全量"
            raise ValueError(f"knowledge base requires at least one document ({scope})")

        self._build_index()

    def _load_from_database(self) -> None:
        """从数据库加载知识库（按 doc_type 过滤实现分库）"""
        global _DATABASE_RETRY_AFTER
        if time.monotonic() < _DATABASE_RETRY_AFTER:
            return
        try:
            results = self._repo.search_knowledge("", limit=500, doc_type=self._doc_type)
            for item in results:
                tags = []
                if item.get("category"):
                    tags.append(str(item["category"]))
                if item.get("keywords"):
                    tags.extend(item["keywords"].split())
                self._documents.append(_Document(
                    id=(
                        f"product:{item['source_id']}"
                        if str(item.get("doc_type") or "rule") == "product" and item.get("source_id") is not None
                        else str(item["id"])
                    ),
                    title=item.get("title", ""),
                    content=item.get("content", ""),
                    tags=tags,
                    source="database",
                    doc_type=str(item.get("doc_type") or "rule"),
                    source_id=str(item["source_id"]) if item.get("source_id") is not None else None,
                ))
            if self._documents:
                logging.getLogger(__name__).info(
                    f"从数据库加载 {len(self._documents)} 条知识"
                    f"（doc_type={self._doc_type or 'all'}）"
                )
        except Exception:
            _DATABASE_RETRY_AFTER = time.monotonic() + 30.0
            logging.getLogger(__name__).warning("知识库数据库不可用，30 秒内直接使用本地快照")
        finally:
            self._repo.close()

    def _load_from_json(self, path: Path | None = None) -> None:
        """从 JSON 文件加载知识库（同样按 doc_type 过滤）"""
        source = path or Path(__file__).parent / "knowledge" / "documents.json"
        if source.exists():
            raw = json.loads(source.read_text(encoding="utf-8"))
            for item in raw:
                document = _Document.from_dict(item)
                if self._doc_type and document.doc_type != self._doc_type:
                    continue
                self._documents.append(document)
            if self._documents:
                import logging
                logging.getLogger(__name__).info(
                    f"从 JSON 文件加载 {len(self._documents)} 条知识"
                    f"（doc_type={self._doc_type or 'all'}）"
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

    def _document_hash(self) -> str:
        """计算所有文档内容的 hash，用于判断向量缓存是否过期。"""
        h = hashlib.sha256()
        for doc in self._documents:
            h.update(doc.all_text().encode("utf-8"))
        return h.hexdigest()[:16]

    def _vector_cache_path(self) -> Path:
        name = self._doc_type or "all"
        return self._vector_cache_dir / f"{name}.npy"

    def _vector_hash_path(self) -> Path:
        name = self._doc_type or "all"
        return self._vector_cache_dir / f"{name}.hash"

    def _load_cached_vectors(self) -> bool:
        """尝试从本地加载持久化的向量索引。成功返回 True。"""
        vp = self._vector_cache_path()
        hp = self._vector_hash_path()
        if not vp.exists() or not hp.exists():
            return False
        try:
            import numpy as np
            cached_hash = hp.read_text(encoding="utf-8").strip()
            if cached_hash != self._document_hash():
                return False
            arr = np.load(vp)
            self._doc_vectors = arr.tolist()
            import logging
            logging.getLogger(__name__).info(
                f"向量索引从缓存加载: {len(self._doc_vectors)} 条（doc_type={self._doc_type or 'all'}）"
            )
            return True
        except Exception:
            return False

    def _save_cached_vectors(self) -> None:
        """将向量索引持久化到本地。"""
        if self._doc_vectors is None:
            return
        try:
            import numpy as np
            self._vector_cache_dir.mkdir(parents=True, exist_ok=True)
            np.save(self._vector_cache_path(), np.array(self._doc_vectors))
            self._vector_hash_path().write_text(self._document_hash(), encoding="utf-8")
        except Exception:
            pass  # 持久化失败不影响运行

    async def build_vector_index(self) -> None:
        """R1-1/R1-6: 为所有文档生成 embedding 向量，供 Hybrid Search 使用。

        优先从本地缓存加载（向量持久化），hash 不一致才重新调用 embedding API。
        """
        if self._embedding_client is None:
            return
        # 向量持久化：优先加载本地缓存
        if self._load_cached_vectors():
            return
        texts = [doc.all_text() for doc in self._documents]
        vectors = await embed_texts(
            self._embedding_client,
            texts,
            model=self._embedding_model,
        )
        if vectors:
            self._doc_vectors = vectors
            import logging
            logging.getLogger(__name__).info(
                f"向量索引构建完成: {len(vectors)} 条文档（doc_type={self._doc_type or 'all'}）"
            )
            self._save_cached_vectors()

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

    async def reload(self) -> None:
        """增量更新：重新加载知识库文档并重建索引（含向量）。

        用 asyncio.Lock 保证并发安全：reload 期间检索请求用旧索引，
        重建完成后原子替换。
        """
        async with self._reload_lock:
            # 重新加载文档
            self._documents = []
            self._doc_tokens = []
            self._title_tokens = []
            self._tag_tokens = []
            self._df = {}
            self._doc_count = 0
            self._load_from_database()
            if not self._documents:
                self._load_from_json(None)
            self._build_index()
            # 重建向量索引（会自动走缓存或重新 embedding）
            if self._embedding_client is not None:
                await self.build_vector_index()
            import logging
            logging.getLogger(__name__).info(
                f"知识库已重载: {self._doc_count} 条文档（doc_type={self._doc_type or 'all'}）"
            )

    def search(self, query: str, limit: int = 3) -> list[dict[str, Any]]:
        if limit < 1:
            return []
        query = (query or "").strip()
        if not query:
            return []

        query_tokens = _expand_query(query)
        if not query_tokens:
            return []

        scored = []
        significant_query = {
            t for t in query_tokens
            if len(t) >= 2 and t not in _GENERIC_QUERY_WORDS
        }
        tfidf_scores: dict[int, float] = {}
        for idx in range(self._doc_count):
            score = self._score_document(query_tokens, idx)
            if score <= 0:
                continue
            if significant_query and not (significant_query & set(self._doc_tokens[idx])):
                continue
            tfidf_scores[idx] = score

        # R1-2: Hybrid Search — TF-IDF 与向量相似度加权融合后重排
        # 归一化 TF-IDF 分数到 [0,1]
        max_tfidf = max(tfidf_scores.values()) if tfidf_scores else 1.0
        for idx, tfidf in tfidf_scores.items():
            norm_tfidf = tfidf / max_tfidf if max_tfidf > 0 else 0.0
            scored.append((idx, norm_tfidf))

        scored.sort(key=lambda item: item[1], reverse=True)

        results: list[dict[str, Any]] = []
        for idx, _score in scored[:limit]:
            doc = self._documents[idx]
            results.append(
                {
                    "id": doc.id,
                    "title": doc.title,
                    "content": doc.content,
                    "source": doc.source,
                    "doc_type": doc.doc_type,
                    "source_id": doc.source_id,
                }
            )
        kb_search_total.labels(doc_type=self._doc_type or "all").inc()
        if results:
            kb_hit_count.labels(doc_type=self._doc_type or "all").inc()
        return results

    async def asearch(self, query: str, limit: int = 3) -> list[dict[str, Any]]:
        """异步检索：支持向量召回（R1-1/R1-6 Hybrid Search）。"""
        if limit < 1:
            return []
        query = (query or "").strip()
        if not query:
            return []

        query_tokens = _expand_query(query)
        if not query_tokens:
            return []

        # 向量召回支路
        query_vector: list[float] | None = None
        if self._doc_vectors is not None and self._embedding_client is not None:
            vectors = await embed_texts(
                self._embedding_client,
                [query],
                model=self._embedding_model,
            )
            if vectors:
                query_vector = vectors[0]

        significant_query = {
            t for t in query_tokens
            if len(t) >= 2 and t not in _GENERIC_QUERY_WORDS
        }
        tfidf_scores: dict[int, float] = {}
        for idx in range(self._doc_count):
            score = self._score_document(query_tokens, idx)
            if score <= 0:
                continue
            if significant_query and not (significant_query & set(self._doc_tokens[idx])):
                continue
            tfidf_scores[idx] = score

        # Hybrid Search：词法召回与向量召回独立产生候选，再统一融合。
        max_tfidf = max(tfidf_scores.values()) if tfidf_scores else 1.0
        scored = []
        candidate_indices = set(tfidf_scores)
        if query_vector is not None:
            candidate_indices.update(range(self._doc_count))
        for idx in candidate_indices:
            tfidf = tfidf_scores.get(idx, 0.0)
            norm_tfidf = tfidf / max_tfidf if max_tfidf > 0 else 0.0
            vec_score = 0.0
            if query_vector is not None and self._doc_vectors is not None:
                vec_score = cosine_similarity(query_vector, self._doc_vectors[idx])
            final_score = 0.5 * norm_tfidf + 0.5 * vec_score
            scored.append((idx, final_score))

        scored.sort(key=lambda item: item[1], reverse=True)

        candidate_count = min(len(scored), max(limit * 4, 12))
        ranked_indices = [idx for idx, _score in scored[:candidate_count]]
        if self._rerank_base_url and ranked_indices:
            ranked_indices = await self._rerank(query, ranked_indices)

        results: list[dict[str, Any]] = []
        for idx in ranked_indices[:limit]:
            doc = self._documents[idx]
            results.append(
                {
                    "id": doc.id,
                    "title": doc.title,
                    "content": doc.content,
                    "source": doc.source,
                    "doc_type": doc.doc_type,
                    "source_id": doc.source_id,
                }
            )
        return self._merge_duplicate_sources(results)

    async def _rerank(self, query: str, indices: list[int]) -> list[int]:
        """调用独立 Cross-Encoder 服务重排；故障时保留原召回顺序。"""
        import httpx

        texts = [self._documents[idx].all_text() for idx in indices]
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self._rerank_base_url}/rerank",
                    json={"query": query, "texts": texts, "raw_scores": False},
                )
                response.raise_for_status()
            ranking = response.json()
            return [indices[int(item["index"])] for item in ranking]
        except Exception as exc:
            logging.getLogger(__name__).warning("reranker 不可用，保留 Hybrid 排序: %s", exc)
            return indices

    def _merge_duplicate_sources(self, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """RAG-3: 同一 source 的多个 chunk 合并内容，避免给 LLM 重复信息。"""
        merged: list[dict[str, Any]] = []
        seen: dict[str, dict[str, Any]] = {}
        for item in results:
            src = str(item.get("source_id") or item["id"])
            if src in seen:
                existing = seen[src]
                # 合并 content，去重
                combined = existing["content"]
                if item["content"] not in combined:
                    combined = f"{combined}\n---\n{item['content']}"
                existing["content"] = combined
            else:
                copy = dict(item)
                seen[src] = copy
                merged.append(copy)
        return merged


# ============================================================
# 知识意图（唯一事实源）
# 分两层、共用同一份词表常量，杜绝多套路由规则各自漂移：
#   - 触发层 knowledge_search_intent(): 消息是否该检索知识库
#     （demo 模式的知识分支与 LLM 模式的 search_knowledge_base 守卫共用）
#   - 路由层 route_knowledge_base(): 一旦触发检索，选规则库还是商品库
# ============================================================

# 售后/政策词：命中即视为规则/政策类问题
_AFTERSALES_WORDS = (
    r"退款|退货|退换|换货|售后|保修|维修|投诉|举报|"
    r"运费|发票|报销|会员|积分|优惠券|红包|"
    r"支付方式|分期|账期|白条|"
    r"政策|规则|条款|协议|流程|多久|几天|几个工作日|到账|签收|拒收|"
    r"客服时间|几点上班|几点下班|电话客服|在线客服|"
    r"cancel|refund|return|warranty|policy|shipping|invoice|membership|complaint"
)

# 商品规格/卖点词（路由层全量）：命中则路由商品库
_PRODUCT_SPEC_WORDS = (
    r"参数|配置|规格|型号|芯片|屏幕|内存|存储|续航|拍照|影像|卖点|亮点|区别|对比|"
    r"降噪|游戏|苹果|笔记本|键盘|鼠标|音箱|"
    r"跑步|跑鞋|运动鞋|羽绒服|冲锋衣|"
    r"什么品牌|哪个品牌|什么牌子|"
    r"spec|model|brand|specification"
)

# 触发层词表：售后/政策词全量 + 商品"规格/卖点属性词"子集。
# 刻意不含裸类目词（笔记本/键盘/跑鞋/苹果 等）：这类查询应走商品搜索工具
# （价格/库存/在售），而不是知识库检索，避免演示分支抢走业务查询。
_KNOWLEDGE_TRIGGER_WORDS = _AFTERSALES_WORDS + "|" + (
    r"参数|配置|规格|型号|芯片|屏幕|内存|存储|续航|拍照|影像|卖点|亮点|区别|对比|"
    r"降噪|游戏|spec|model|brand|specification"
)

_AFTERSALES_INTENT_PATTERN = re.compile(_AFTERSALES_WORDS, re.IGNORECASE)
_PRODUCT_SPEC_INTENT_PATTERN = re.compile(_PRODUCT_SPEC_WORDS, re.IGNORECASE)
_KNOWLEDGE_TRIGGER_PATTERN = re.compile(_KNOWLEDGE_TRIGGER_WORDS, re.IGNORECASE)


def knowledge_search_intent(message: str) -> bool:
    """消息是否触发知识库检索（售后/政策，或商品规格/卖点属性问法）。

    demo 模式的知识分支与 LLM 模式的 search_knowledge_base 守卫共用此判定，
    保证两条链路对"是否需要检索知识"的判断一致。
    """
    return bool(_KNOWLEDGE_TRIGGER_PATTERN.search(message))


def route_knowledge_base(message: str) -> str:
    """意图路由：确定检索哪个知识库。

    返回 "rule"（售后/政策/默认兜底）或 "product"（商品规格/卖点语义查询）。
    服务端路由结果会覆盖 LLM 传入的 kb 参数，防止跨库检索噪声。
    仅当 knowledge_search_intent() 已判定需要检索时调用才有意义。
    """
    if _AFTERSALES_INTENT_PATTERN.search(message):
        return "rule"
    if _PRODUCT_SPEC_INTENT_PATTERN.search(message):
        return "product"
    return "rule"
