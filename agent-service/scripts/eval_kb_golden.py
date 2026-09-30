"""知识问答 golden set 评测（检索层基线测量）。

度量对象是"分库检索链路"本身（Phase 0/1 产物），不依赖 LLM，可复现：
  1. 意图路由准确率：route_knowledge_base() 与用例期望路由的一致性
  2. 命中率：在期望库中 search(message, limit=3) 是否命中期望 chunk
  3. 缺口分类：按用例预判的 gap 分组统计，区分"检索缺陷"与"内容层缺口"

用法（agent-service 目录下）:
    python -m scripts.eval_kb_golden            # 全量评测
    python -m scripts.eval_kb_golden p01 e02    # 只跑指定用例（id 或类别）
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from app.knowledge_base import KnowledgeBase, route_knowledge_base  # noqa: E402

CASES_PATH = Path(__file__).resolve().parents[1] / "evals" / "kb_golden_cases.json"
SEARCH_LIMIT = 3
MIN_ROUTE_ACCURACY = 1.0
MIN_POSITIVE_RECALL = 0.85
MIN_NEGATIVE_PRECISION = 1.0


def load_cases() -> list[dict]:
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))


def evaluate_case(case: dict, rule_kb: KnowledgeBase, product_kb: KnowledgeBase) -> dict:
    message = case["message"]
    actual_route = route_knowledge_base(message)
    kb = product_kb if actual_route == "product" else rule_kb
    hits = kb.search(message, limit=SEARCH_LIMIT)
    # 文档 ID 是稳定标识，不假定必须为整数；数据库旧数据和 JSON 新数据均可评测。
    hit_ids = [str(h["id"]) for h in hits]
    titles = [h["title"] for h in hits]

    expect_hits = [str(value) for value in (case.get("expect_hits") or [])]
    expect_route = case.get("expect_route")
    route_ok = actual_route == expect_route

    if expect_hits:
        hit_ok = any(eid in hit_ids for eid in expect_hits)
    else:
        # negative 用例：期望检索返回空（不硬凑）
        hit_ok = len(hit_ids) == 0

    return {
        "id": case["id"],
        "category": case.get("category", ""),
        "message": message,
        "gap": case.get("gap", "none"),
        "expect_route": expect_route,
        "actual_route": actual_route,
        "route_ok": route_ok,
        "expect_hits": expect_hits,
        "hit_ids": hit_ids,
        "hit_titles": titles,
        "hit_ok": hit_ok,
    }


def summarize(results: list[dict]) -> bool:
    total = len(results)
    route_ok = sum(1 for r in results if r["route_ok"])
    # positive（有期望命中）与 negative（期望为空）分开统计
    positives = [r for r in results if r["expect_hits"]]
    negatives = [r for r in results if not r["expect_hits"]]
    pos_hit = sum(1 for r in positives if r["hit_ok"])
    neg_clean = sum(1 for r in negatives if r["hit_ok"])
    route_accuracy = route_ok / total if total else 0.0
    positive_recall = pos_hit / len(positives) if positives else 1.0
    negative_precision = neg_clean / len(negatives) if negatives else 1.0

    print("=" * 72)
    print(f"知识检索 golden set 基线  |  共 {total} 条用例")
    print(f"  意图路由准确率  : {route_ok}/{total} ({route_ok / total:.0%})")
    if positives:
        print(f"  positive 命中率 : {pos_hit}/{len(positives)} ({pos_hit / len(positives):.0%})  @top{SEARCH_LIMIT}")
    if negatives:
        print(f"  negative 空结果 : {neg_clean}/{len(negatives)} ({neg_clean / len(negatives):.0%})  （不应硬凑）")
    print("-" * 72)

    # 按 gap 分组的 positive 命中率：none 失败 = 检索缺陷；其余 = 内容层缺口
    print("按用例预判缺口分组（positive 命中率，gap 说明见 kb_golden_cases.json）：")
    for gap in ["none", "semantic", "synonym", "routing"]:
        group = [r for r in positives if r["gap"] == gap]
        if not group:
            continue
        ok = sum(1 for r in group if r["hit_ok"])
        label = {
            "none": "词面应命中(检索缺陷候选)",
            "semantic": "语义/内容缺口",
            "synonym": "同义词面缺口",
            "routing": "路由意图词表缺口",
        }[gap]
        print(f"    [{gap:>10}] {ok}/{len(group)}  {label}")
    print("-" * 72)

    print("失败明细（route 路由 / hit 命中 任一失败列出）：")
    for r in results:
        if r["route_ok"] and r["hit_ok"]:
            continue
        route_mark = " " if r["route_ok"] else "✗"
        hit_mark = " " if r["hit_ok"] else "✗"
        exp_route = r["expect_route"] or "-"
        print(
            f"  [{r['id']}] {r['message']}"
        )
        print(
            f"      route {route_mark} 期望={exp_route:<8} 实际={r['actual_route']:<8}"
            f" | hit {hit_mark} 期望={r['expect_hits'] or '空'}"
        )
        print(f"      命中: {r['hit_ids']} {r['hit_titles']}")
    print("=" * 72)
    passed = (
        route_accuracy >= MIN_ROUTE_ACCURACY
        and positive_recall >= MIN_POSITIVE_RECALL
        and negative_precision >= MIN_NEGATIVE_PRECISION
    )
    print(
        "QUALITY GATE: " + ("PASS" if passed else "FAIL")
        + f" (route>={MIN_ROUTE_ACCURACY:.0%}, recall@{SEARCH_LIMIT}>={MIN_POSITIVE_RECALL:.0%}, negative>={MIN_NEGATIVE_PRECISION:.0%})"
    )
    return passed


def main(argv: list[str]) -> int:
    rule_kb = KnowledgeBase(doc_type="rule", prefer_database=False)
    product_kb = KnowledgeBase(doc_type="product", prefer_database=False)

    cases = load_cases()
    if argv:
        wanted = set(argv)
        cases = [c for c in cases if c["id"] in wanted or c["category"] in wanted]
        if not cases:
            print(f"没有匹配的用例: {argv}")
            return 2

    results = [evaluate_case(c, rule_kb, product_kb) for c in cases]
    return 0 if summarize(results) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
