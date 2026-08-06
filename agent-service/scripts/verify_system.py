#!/usr/bin/env python3
"""
电商助手数据库连接验证脚本
检查 MySQL 连接、Java API 连接、商品数据是否就绪
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Ensure project root is in path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
os.chdir(project_root)

# Load .env
env_path = project_root / ".env"
if env_path.exists():
    print(f"[INFO] Loading env from {env_path}")
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key] = value
else:
    print("[WARN] No .env file found")


def check_mysql():
    """检查 MySQL 数据库连接"""
    print("\n" + "=" * 50)
    print("[CHECK 1] MySQL 数据库连接")
    print("=" * 50)

    try:
        import pymysql
        conn = pymysql.connect(
            host=os.getenv("MYSQL_HOST", "127.0.0.1"),
            port=int(os.getenv("MYSQL_PORT", "3306")),
            user=os.getenv("MYSQL_USER", "root"),
            password=os.getenv("MYSQL_PASSWORD", "123456"),
            database=os.getenv("MYSQL_DATABASE", "ecommerce_db"),
            charset="utf8mb4",
        )
        print("[OK] MySQL 连接成功")

        cursor = conn.cursor()

        # 检查 products 表
        cursor.execute("SELECT COUNT(*) FROM products")
        product_count = cursor.fetchone()[0]
        print(f"  - 商品数量: {product_count}")

        # 检查是否有增强数据 (id >= 126)
        cursor.execute("SELECT COUNT(*) FROM products WHERE id >= 126")
        enhanced_count = cursor.fetchone()[0]
        if enhanced_count > 0:
            print(f"  - 增强数据: 已加载 ({enhanced_count} 条新商品)")
        else:
            print(f"  - 增强数据: ⚠️  未加载 (建议运行 enhance_business_demo_data.sql)")

        # 检查库存状态
        cursor.execute("SELECT COUNT(*) FROM products WHERE stock > 0")
        in_stock = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM products WHERE stock = 0")
        out_of_stock = cursor.fetchone()[0]
        print(f"  - 有货商品: {in_stock}, 无货商品: {out_of_stock}")

        # 检查订单
        cursor.execute("SELECT COUNT(*) FROM orders")
        order_count = cursor.fetchone()[0]
        print(f"  - 订单数量: {order_count}")

        # 检查用户
        cursor.execute("SELECT COUNT(*) FROM users")
        user_count = cursor.fetchone()[0]
        print(f"  - 用户数量: {user_count}")

        # 查看商品价格分布
        cursor.execute("SELECT MIN(price), MAX(price), AVG(price) FROM products WHERE status = 1")
        min_p, max_p, avg_p = cursor.fetchone()
        if min_p is not None:
            print(f"  - 价格区间: ¥{min_p:.2f} - ¥{max_p:.2f} (平均 ¥{avg_p:.2f})")

        # 检查是否有 status 字段
        cursor.execute("SHOW COLUMNS FROM products LIKE 'status'")
        status_col = cursor.fetchone()
        if status_col:
            cursor.execute("SELECT COUNT(*) FROM products WHERE status = 1")
            active = cursor.fetchone()[0]
            print(f"  - 在售商品: {active}")

        cursor.close()
        conn.close()
        return True
    except ImportError:
        print("[FAIL] pymysql 未安装。运行: pip install pymysql")
        return False
    except Exception as e:
        print(f"[FAIL] MySQL 连接失败: {e}")
        return False


def check_java_api():
    """检查 Java 后端 API 连接"""
    print("\n" + "=" * 50)
    print("[CHECK 2] Java 后端 API")
    print("=" * 50)

    import httpx
    base_url = os.getenv("ECOMMERCE_API_BASE_URL", "http://localhost:8080/api")

    try:
        client = httpx.Client(base_url=base_url, timeout=5)
        response = client.get("/products/search", params={"keyword": "", "size": 3})
        if response.status_code == 200:
            data = response.json()
            print(f"[OK] Java API 连接成功 ({response.status_code})")
            products = data.get("data", {})
            if isinstance(products, dict):
                content = products.get("content", [])
                print(f"  - API 返回 {len(content)} 个商品")
                for p in content[:3]:
                    print(f"    - #{p.get('id')} {p.get('name')} ¥{p.get('price')} 库存:{p.get('stock')}")
            elif isinstance(products, list):
                print(f"  - API 返回 {len(products)} 个商品")
            return True
        else:
            print(f"[FAIL] Java API 返回异常状态码: {response.status_code}")
            print(f"  响应: {response.text[:200]}")
            return False
    except httpx.ConnectError:
        print(f"[FAIL] 无法连接到 Java 后端 ({base_url})")
        print("  请确保 Java Spring Boot 应用正在运行")
        return False
    except Exception as e:
        print(f"[FAIL] API 检查失败: {e}")
        return False


def check_search_filters():
    """检查搜索筛选功能"""
    print("\n" + "=" * 50)
    print("[CHECK 3] 搜索筛选功能")
    print("=" * 50)

    import httpx
    base_url = os.getenv("ECOMMERCE_API_BASE_URL", "http://localhost:8080/api")

    try:
        client = httpx.Client(base_url=base_url, timeout=5)

        # 测试关键词搜索
        response = client.get("/products/search", params={"keyword": "手机", "size": 5})
        data = response.json()
        products = data.get("data", {})
        content = products.get("content", []) if isinstance(products, dict) else []
        print(f"  关键词'手机': 返回 {len(content)} 个商品")

        # 测试价格筛选
        response = client.get("/products/search", params={"keyword": "手机", "minPrice": "4000", "size": 5})
        data = response.json()
        products = data.get("data", {})
        content = products.get("content", []) if isinstance(products, dict) else []
        print(f"  价格>=4000的手机: 返回 {len(content)} 个商品")
        for p in content:
            print(f"    - #{p.get('id')} {p.get('name')} ¥{p.get('price')}")

        # 测试库存筛选
        response = client.get("/products/search", params={"keyword": "", "inStock": "true", "size": 3})
        data = response.json()
        products = data.get("data", {})
        content = products.get("content", []) if isinstance(products, dict) else []
        print(f"  有货商品: 返回 {len(content)} 个商品")

        print("[OK] 搜索筛选功能正常")
        return True
    except httpx.ConnectError:
        print("[SKIP] Java 后端未运行，跳过搜索筛选检查")
        return False
    except Exception as e:
        print(f"[FAIL] 搜索筛选检查失败: {e}")
        return False


def check_agent_config():
    """检查 Agent 配置"""
    print("\n" + "=" * 50)
    print("[CHECK 4] Agent 配置")
    print("=" * 50)

    checks = [
        ("ECOMMERCE_BACKEND", os.getenv("ECOMMERCE_BACKEND", "未设置")),
        ("ECOMMERCE_API_BASE_URL", os.getenv("ECOMMERCE_API_BASE_URL", "未设置")),
        ("DB_TYPE", os.getenv("DB_TYPE", "未设置")),
        ("MYSQL_HOST", os.getenv("MYSQL_HOST", "未设置")),
        ("MYSQL_DATABASE", os.getenv("MYSQL_DATABASE", "未设置")),
        ("AGENT_MODE", os.getenv("AGENT_MODE", "未设置")),
        ("OPENAI_MODEL", os.getenv("OPENAI_MODEL", "未设置")),
    ]

    for key, value in checks:
        print(f"  {key} = {value}")

    backend = os.getenv("ECOMMERCE_BACKEND", "api")
    if backend == "api":
        print("\n  [MODE] API 模式: Agent → HTTP → Java 后端 → MySQL (推荐)")
    elif backend == "mysql":
        print("\n  [MODE] 直连模式: Agent → SQLAlchemy → MySQL (需要 schema 匹配)")

    return True


def main():
    print("=" * 50)
    print("  电商助手 - 系统连接验证")
    print("=" * 50)

    results = {
        "mysql": check_mysql(),
        "java_api": check_java_api(),
        "search_filters": check_search_filters(),
        "agent_config": check_agent_config(),
    }

    print("\n" + "=" * 50)
    print("验证结果汇总")
    print("=" * 50)

    for name, ok in results.items():
        status = "✅" if ok else "❌"
        print(f"  {status} {name}")

    all_ok = all(results.values())
    if all_ok:
        print("\n🎉 所有检查通过！系统可以正常使用。")
        print("   用户下单 → Agent → Java API → MySQL 实时记录")
    else:
        print("\n⚠️  部分检查未通过，请查看上方日志。")
        if not results["mysql"]:
            print("   → 请确保 MySQL 正在运行，且账号密码正确")
        if not results["java_api"]:
            print("   → 请确保 Java Spring Boot 后端正在运行 (端口 8080)")
        if not results["search_filters"]:
            print("   → Java 后端未运行，搜索筛选功能暂不可用")

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
