from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.demo_agent import DemoAgentService
from app.security_guard import is_suspicious_instruction
from app.tools.confirmation import ConfirmationStore
from app.tools.registry import ToolRegistry


class EvalEcommerce:
    async def search_products(
        self,
        keyword: str,
        min_price: float | None = None,
        max_price: float | None = None,
        in_stock: bool | None = None,
        created_after: str | None = None,
    ):
        products = [
            {"id": 1, "name": "入门手机", "price": 1999, "stock": 10, "categoryId": 101},
            {"id": 2, "name": "旗舰手机", "price": 5999, "stock": 5, "categoryId": 101},
            {"id": 3, "name": "游戏手机", "price": 3999, "stock": 20, "categoryId": 101},
            {"id": 4, "name": "头戴耳机", "price": 1599, "stock": 50, "categoryId": 103},
            {"id": 5, "name": "入耳耳机", "price": 299, "stock": 200, "categoryId": 103},
        ]

        if keyword and keyword not in ("", "推荐"):
            keyword_lower = keyword.lower()
            products = [
                p for p in products
                if keyword_lower in p["name"].lower()
                or keyword_lower in str(p.get("categoryId", ""))
                or any(keyword_lower in str(v).lower() for v in p.values())
            ]

        if min_price is not None:
            products = [p for p in products if p["price"] >= min_price]
        if max_price is not None:
            products = [p for p in products if p["price"] <= max_price]
        if in_stock is True:
            products = [p for p in products if p["stock"] > 0]
        elif in_stock is False:
            products = [p for p in products if p["stock"] == 0]

        return products

    async def get_product_detail(self, product_id: int):
        products = {
            1: {"id": 1, "name": "入门手机", "price": 1999, "stock": 10, "categoryId": 101},
            2: {"id": 2, "name": "旗舰手机", "price": 5999, "stock": 5, "categoryId": 101},
            3: {"id": 3, "name": "游戏手机", "price": 3999, "stock": 20, "categoryId": 101},
            4: {"id": 4, "name": "头戴耳机", "price": 1599, "stock": 50, "categoryId": 103},
            5: {"id": 5, "name": "入耳耳机", "price": 299, "stock": 200, "categoryId": 103},
        }
        return products.get(product_id, {"id": product_id, "name": f"商品#{product_id}", "price": 0, "stock": 0})

    async def get_my_orders(self, access_token: str | None):
        return [{"id": 8, "orderNo": "ORD-8", "status": 0, "finalAmount": 99}]

    async def get_order_detail(self, order_id: int, access_token: str | None):
        return {"id": order_id, "orderNo": "ORD-8", "status": 0, "finalAmount": 99}

    async def get_cart(self, access_token: str | None):
        return []

    async def add_to_cart(self, product_id: int, quantity: int, access_token: str | None):
        return {"cart_id": 1, "product_id": product_id, "quantity": quantity}

    async def update_cart(self, cart_id: int, quantity: int, access_token: str | None):
        return {"cart_id": cart_id, "quantity": quantity}

    async def remove_from_cart(self, cart_id: int, access_token: str | None):
        return {"success": True}

    async def clear_cart(self, access_token: str | None):
        return {"success": True}

    async def create_order(self, product_id: int, quantity: int, address_id: int, payment_method: str, access_token: str | None):
        return {"id": 1, "orderNo": "ORD-NEW", "status": 0, "finalAmount": 999}

    async def pay_order(self, order_id: int, access_token: str | None):
        return {"id": order_id, "orderNo": "ORD-8", "status": 1}

    async def cancel_order(self, order_id: int, access_token: str | None):
        return {"id": order_id, "orderNo": "ORD-8", "status": 4}


CASES = json.loads((Path(__file__).parents[1] / "evals" / "demo_cases.json").read_text(encoding="utf-8"))


@pytest.mark.asyncio
@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
async def test_demo_agent_eval_suite(case):
    expected = case["expect"]
    if "prompt_injection" in case["name"]:
        assert is_suspicious_instruction(case["message"])
        return
    agent = DemoAgentService(ToolRegistry(EvalEcommerce(), ConfirmationStore()))
    result = await agent.chat(case["message"], session_id=f"eval-{case['name']}", access_token="eval-jwt" if case["authenticated"] else None)
    if "contains" in expected:
        assert expected["contains"] in result.answer
    assert result.tool_calls[0].name == expected["tool"]
    assert result.tool_calls[0].outcome == expected["outcome"]
    if expected.get("confirmation"):
        assert result.confirmation is not None
