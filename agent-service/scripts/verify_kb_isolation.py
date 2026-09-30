"""验证 Phase 0/1 知识库分库 + 意图路由的售后噪声隔离效果。

对比同一批典型 query 在三种检索形态下的 top-3 结果：
  1. 单库全量（旧行为）        —— 售后问题会混入商品 chunk（噪声）
  2. 规则库 doc_type='rule'    —— 售后场景只检索规则（新行为）
  3. 商品库 doc_type='product' —— 商品场景只检索商品特征（新行为）

另附意图路由函数 route_knowledge_base 的断言检查。

用法（在 agent-service 目录下执行）:
    python -m scripts.build_product_kb      # 先生成商品特征 chunk
    python -m scripts.verify_kb_isolation   # 再跑隔离验证
"""

from __future__ import annotations

from app.database import Knowledge, SessionLocal, init_db
from app.knowledge_base import KnowledgeBase, route_knowledge_base

AFTERSALES_QUERIES = ["耳机可以退货吗", "退款多久到账", "换货流程是什么"]
PRODUCT_QUERIES = ["小米14的参数配置", "MacBook Pro 是什么芯片"]

ROUTING_CASES = [
    ("耳机可以退货吗", "rule"),      # 商品词+售后词混合 → 售后优先
    ("退款多久到账", "rule"),
    ("7天无理由退货政策", "rule"),
    ("运费怎么算", "rule"),
    ("小米14的参数配置", "product"),
    ("这款手机什么品牌", "product"),
    ("你好", "rule"),                # 默认兜底
]


def _fmt(matches: list[dict]) -> str:
    if not matches:
        return "(空)"
    return " | ".join(f"{m['doc_type']}:{m['title'][:14]}" for m in matches)


def _noise_count(matches: list[dict], expect: str) -> int:
    return sum(1 for m in matches if m["doc_type"] != expect)


def main() -> None:
    init_db()

    # ---------- 1. 意图路由断言 ----------
    failures = [
        (msg, want, route_knowledge_base(msg))
        for msg, want in ROUTING_CASES
        if route_knowledge_base(msg) != want
    ]
    for msg, want in ROUTING_CASES:
        status = "OK" if not any(f[0] == msg for f in failures) else "FAIL"
        print(f"[route] {status}  {msg} -> {route_knowledge_base(msg)} (期望 {want})")
    if failures:
        raise SystemExit("❌ 意图路由断言未通过")

    # ---------- 2. 库存统计 ----------
    with SessionLocal() as session:
        rules = session.query(Knowledge).filter(Knowledge.doc_type == "rule").count()
        products = session.query(Knowledge).filter(Knowledge.doc_type == "product").count()
    print(f"\n[kb] 规则知识 {rules} 条，商品特征 chunk {products} 条")
    if products == 0:
        raise SystemExit("❌ 商品特征 chunk 为 0，请先执行: python -m scripts.build_product_kb")

    # ---------- 3. 噪声隔离对比 ----------
    legacy = KnowledgeBase()                      # 旧行为：单库全量
    rule_kb = KnowledgeBase(doc_type="rule")      # 新行为：规则库
    product_kb = KnowledgeBase(doc_type="product")  # 新行为：商品库

    total_noise_before = 0
    total_noise_after = 0

    print("\n===== 售后场景（期望只命中规则）=====")
    for query in AFTERSALES_QUERIES:
        legacy_hits = legacy.search(query)
        rule_hits = rule_kb.search(query)
        noise_before = _noise_count(legacy_hits, "rule")
        noise_after = _noise_count(rule_hits, "rule")
        total_noise_before += noise_before
        total_noise_after += noise_after
        print(f"\nQ: {query}")
        print(f"  旧·单库: {_fmt(legacy_hits)}  [噪声 {noise_before}]")
        print(f"  新·规则库: {_fmt(rule_hits)}  [噪声 {noise_after}]")

    print("\n===== 商品场景（期望只命中商品特征）=====")
    for query in PRODUCT_QUERIES:
        legacy_hits = legacy.search(query)
        product_hits = product_kb.search(query)
        noise_before = _noise_count(legacy_hits, "product")
        noise_after = _noise_count(product_hits, "product")
        total_noise_before += noise_before
        total_noise_after += noise_after
        print(f"\nQ: {query}")
        print(f"  旧·单库: {_fmt(legacy_hits)}  [噪声 {noise_before}]")
        print(f"  新·商品库: {_fmt(product_hits)}  [噪声 {noise_after}]")

    print("\n===== 结论 =====")
    print(f"旧单库模式噪声片段总数: {total_noise_before}")
    print(f"分库+路由后噪声片段总数: {total_noise_after}")
    if total_noise_before > 0 and total_noise_after == 0:
        print("✅ 售后噪声隔离验证通过：分库后不再出现跨库检索噪声")
    else:
        raise SystemExit("❌ 隔离验证未通过，请检查分库数据与路由逻辑")


if __name__ == "__main__":
    main()
