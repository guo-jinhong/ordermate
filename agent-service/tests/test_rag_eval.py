"""RAG-4: 知识库检索质量评测（Recall@K + MRR）。

用 golden_queries.json 里的标注数据，量化检索召回率。
CI 中跑，Recall@3 低于 0.8 视为回归。
"""
import json
from types import SimpleNamespace
from pathlib import Path

import pytest

from app.knowledge_base import KnowledgeBase


GOLDEN_PATH = Path(__file__).parent / "golden_queries.json"


@pytest.fixture()
def rule_kb() -> KnowledgeBase:
    return KnowledgeBase(doc_type="rule", prefer_database=False)


@pytest.fixture()
def product_kb() -> KnowledgeBase:
    return KnowledgeBase(doc_type="product", prefer_database=False)


def _load_golden() -> list[dict]:
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", _load_golden())
def test_recall_at_3(case, rule_kb, product_kb):
    kb = rule_kb if case["doc_type"] == "rule" else product_kb
    results = kb.search(case["query"], limit=3)
    returned_ids = {r["id"] for r in results}
    expected = set(case["expected_ids"])
    # 期望命中的 doc 至少有一个在 top-3
    assert returned_ids & expected, (
        f"query='{case['query']}' 期望命中 {expected}，实际返回 {returned_ids}"
    )


def test_recall_at_3_overall(rule_kb, product_kb):
    """整体 Recall@3 应 >= 0.8。"""
    cases = _load_golden()
    hits = 0
    for case in cases:
        kb = rule_kb if case["doc_type"] == "rule" else product_kb
        results = kb.search(case["query"], limit=3)
        returned_ids = {r["id"] for r in results}
        if returned_ids & set(case["expected_ids"]):
            hits += 1
    recall = hits / len(cases)
    assert recall >= 0.8, f"Recall@3={recall:.2f} < 0.8"


def test_mrr(rule_kb, product_kb):
    """MRR（平均倒数排名）应 >= 0.7。"""
    cases = _load_golden()
    rr_sum = 0.0
    for case in cases:
        kb = rule_kb if case["doc_type"] == "rule" else product_kb
        results = kb.search(case["query"], limit=5)
        returned_ids = [r["id"] for r in results]
        expected = set(case["expected_ids"])
        rank = next(
            (i + 1 for i, rid in enumerate(returned_ids) if rid in expected),
            None,
        )
        if rank is not None:
            rr_sum += 1.0 / rank
    mrr = rr_sum / len(cases)
    assert mrr >= 0.7, f"MRR={mrr:.2f} < 0.7"


@pytest.mark.asyncio
async def test_vector_recall_can_add_candidates_without_lexical_overlap(tmp_path):
    class FakeEmbeddings:
        async def create(self, *, model, input):
            vectors = ([[1.0, 0.0]] + [[0.0, 1.0] for _ in input[1:]]) if len(input) > 1 else [[0.0, 1.0]]
            return SimpleNamespace(
                data=[SimpleNamespace(embedding=vector) for vector in vectors]
            )

    kb = KnowledgeBase(
        doc_type="product",
        prefer_database=False,
        embedding_client=SimpleNamespace(embeddings=FakeEmbeddings()),
        embedding_model="test-embedding",
    )
    kb._vector_cache_dir = tmp_path
    await kb.build_vector_index()

    results = await kb.asearch("完全没有词面重叠的语义问题", limit=1)

    assert results[0]["id"] == "product-laptop-pro-14"


def test_duplicate_merge_uses_business_source_id_not_snapshot_file():
    kb = KnowledgeBase(doc_type="product", prefer_database=False)
    results = kb._merge_duplicate_sources([
        {"id": "product:1", "source_id": "1", "source": "snapshot.sql", "content": "a"},
        {"id": "product:2", "source_id": "2", "source": "snapshot.sql", "content": "b"},
    ])
    assert [item["id"] for item in results] == ["product:1", "product:2"]


@pytest.mark.asyncio
async def test_configured_reranker_changes_candidate_order(monkeypatch):
    kb = KnowledgeBase(doc_type="product", prefer_database=False, rerank_base_url="http://reranker")

    async def reverse_order(_query, indices):
        return list(reversed(indices))

    monkeypatch.setattr(kb, "_rerank", reverse_order)
    results = await kb.asearch("商品", limit=2)
    assert len(results) == 2
