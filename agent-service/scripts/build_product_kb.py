"""从商品表生成商品特征 chunk，写入知识库（doc_type='product'）。

商品知识库只存语义特征（品牌/型号/类目/卖点摘要），不存价格库存——
实时数据永远以业务表和商品查询工具为准（分库约定见 update_knowledge.sql 头注释）。

用法（在 agent-service 目录下执行）:
    python -m scripts.build_product_kb            # 全量重建商品特征 chunk
    python -m scripts.build_product_kb --dry-run  # 只打印，不写库
"""

from __future__ import annotations

import argparse

from app.database import Knowledge, Product, SessionLocal, init_db

# 品牌 -> 匹配词（商品名/描述命中即归属该品牌；顺序即优先级）
BRAND_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Apple": ("iphone", "macbook", "airpods", "苹果"),
    "华为": ("华为", "huawei", "freebuds"),
    "小米": ("小米", "xiaomi", "红米", "redmi"),
    "OPPO": ("oppo",),
    "vivo": ("vivo",),
    "联想": ("联想", "拯救者", "thinkpad", "lenovo"),
    "戴尔": ("戴尔", "dell", "xps"),
    "索尼": ("索尼", "sony"),
    "Bose": ("bose", "quietcomfort"),
    "罗技": ("罗技", "logitech", "mx "),
    "飞利浦": ("飞利浦", "philips"),
    "戴森": ("戴森", "dyson"),
    "Nike": ("nike",),
    "Adidas": ("adidas",),
    "李宁": ("李宁",),
    "安踏": ("安踏",),
    "北面": ("北脸", "北面", "the north face"),
    "始祖鸟": ("始祖鸟", "arc'teryx", "arcteryx"),
}


def extract_brand(name: str, description: str) -> str:
    haystack = f"{name} {description}".lower()
    for brand, keywords in BRAND_KEYWORDS.items():
        if any(keyword in haystack for keyword in keywords):
            return brand
    return "其他"


def build_chunk(product: Product) -> Knowledge:
    """一个商品生成一条特征 chunk（单品维度切片）。"""
    brand = extract_brand(product.name, product.description or "")
    title = f"{product.name}（{product.category}）"
    content = (
        f"{product.name}，品牌：{brand}，类目：{product.category}。"
        f"产品卖点：{product.description}。"
        f"实时价格与库存以商品查询为准（商品ID：{product.id}）。"
    )
    keywords = " ".join(
        part for part in (product.name, brand, product.category, product.description) if part
    )
    return Knowledge(
        doc_type="product",
        category="product",
        title=title,
        content=content,
        keywords=keywords[:500],
        source_id=product.id,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="生成商品特征 chunk 到知识库")
    parser.add_argument("--dry-run", action="store_true", help="只打印将写入的 chunk，不落库")
    args = parser.parse_args()

    init_db()
    with SessionLocal() as session:
        products = session.query(Product).order_by(Product.id.asc()).all()
        chunks = [build_chunk(p) for p in products]

        if args.dry_run:
            for chunk in chunks:
                print(f"[dry-run] source_id={chunk.source_id} {chunk.title}")
                print(f"          {chunk.content}")
            print(f"共 {len(chunks)} 条商品特征 chunk（未写入）")
            return

        deleted = (
            session.query(Knowledge)
            .filter(Knowledge.doc_type == "product")
            .delete(synchronize_session=False)
        )
        session.add_all(chunks)
        session.commit()
        print(f"✅ 重建商品知识 chunk：删除旧 {deleted} 条，写入 {len(chunks)} 条")


if __name__ == "__main__":
    main()
