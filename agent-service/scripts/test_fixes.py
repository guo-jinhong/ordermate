#!/usr/bin/env python3
"""Quick test for Chinese numeral and price extraction."""
from __future__ import annotations

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.demo_agent import DemoAgentService

# Test 1: Chinese numeral conversion
print("=== Test 1: Chinese numeral conversion ===")
print(f"四千 -> {DemoAgentService._chinese_to_number('四千')}")
print(f"三千 -> {DemoAgentService._chinese_to_number('三千')}")
print(f"五千 -> {DemoAgentService._chinese_to_number('五千')}")
print(f"两千 -> {DemoAgentService._chinese_to_number('两千')}")
print(f"三千五百 -> {DemoAgentService._chinese_to_number('三千五百')}")

# Test 2: Price extraction from Chinese text
print()
print("=== Test 2: Price extraction ===")
min_p, max_p, in_stock = DemoAgentService._extract_price_filters("四千以内的手机")
print(f"'四千以内的手机' -> min={min_p}, max={max_p}, in_stock={in_stock}")

min_p, max_p, in_stock = DemoAgentService._extract_price_filters("三千以内的耳机")
print(f"'三千以内的耳机' -> min={min_p}, max={max_p}, in_stock={in_stock}")

min_p, max_p, in_stock = DemoAgentService._extract_price_filters("四千以上的手机")
print(f"'四千以上的手机' -> min={min_p}, max={max_p}, in_stock={in_stock}")

min_p, max_p, in_stock = DemoAgentService._extract_price_filters("4000以内的手机")
print(f"'4000以内的手机' -> min={min_p}, max={max_p}, in_stock={in_stock}")

min_p, max_p, in_stock = DemoAgentService._extract_price_filters("有货的手机")
print(f"'有货的手机' -> min={min_p}, max={max_p}, in_stock={in_stock}")

# Test 3: Phone detection
print()
print("=== Test 3: Phone product detection ===")
test_phone = {"name": "iPhone 15 Pro", "description": "最新款智能手机", "categoryId": 101}
test_laptop = {"name": "华为 MateBook X Pro", "description": "高性能笔记本电脑", "categoryId": 102}
test_headphone = {"name": "AirPods Pro", "description": "无线蓝牙耳机", "categoryId": 103}
print(f"iPhone 15 Pro -> is_phone={DemoAgentService._is_phone_product(test_phone)}")
print(f"MateBook X Pro -> is_phone={DemoAgentService._is_phone_product(test_laptop)}")
print(f"AirPods Pro -> is_phone={DemoAgentService._is_phone_product(test_headphone)}")

# Test 4: Price safety net
print()
print("=== Test 4: Price safety net ===")
products = [
    {"id": 1, "name": "iPhone 15", "price": 8999},
    {"id": 2, "name": "Redmi 13C", "price": 799},
    {"id": 3, "name": "Phone X", "price": 2999},
    {"id": 4, "name": "Phone Ultra", "price": 6499},
]
filtered = DemoAgentService._filter_by_price_safety_net(products, None, 4000)
print(f"Price <= 4000: {[p['name'] for p in filtered]}")
filtered = DemoAgentService._filter_by_price_safety_net(products, 4000, None)
print(f"Price >= 4000: {[p['name'] for p in filtered]}")

# Summary
print()
print("=== Results ===")
all_ok = True

# Check Chinese numeral
if DemoAgentService._chinese_to_number("四千") != 4000.0:
    print("FAIL: '四千' did not convert to 4000")
    all_ok = False
if DemoAgentService._chinese_to_number("三千") != 3000.0:
    print("FAIL: '三千' did not convert to 3000")
    all_ok = False

# Check price extraction
_, max_p, _ = DemoAgentService._extract_price_filters("四千以内的手机")
if max_p != 4000.0:
    print(f"FAIL: '四千以内' max_price expected 4000, got {max_p}")
    all_ok = False

_, max_p, _ = DemoAgentService._extract_price_filters("3000以内")
if max_p != 3000.0:
    print(f"FAIL: '3000以内' max_price expected 3000, got {max_p}")
    all_ok = False

# Check phone detection
if not DemoAgentService._is_phone_product(test_phone):
    print("FAIL: iPhone should be detected as phone")
    all_ok = False
if DemoAgentService._is_phone_product(test_laptop):
    print("FAIL: MateBook should NOT be detected as phone")
    all_ok = False
if DemoAgentService._is_phone_product(test_headphone):
    print("FAIL: AirPods should NOT be detected as phone")
    all_ok = False

# Check price safety net
filtered = DemoAgentService._filter_by_price_safety_net(products, None, 4000)
if len(filtered) != 2 or filtered[0]["name"] != "Redmi 13C":
    print(f"FAIL: Price safety net returned wrong results: {[p['name'] for p in filtered]}")
    all_ok = False

if all_ok:
    print("ALL TESTS PASSED!")
else:
    print("SOME TESTS FAILED!")
    sys.exit(1)
