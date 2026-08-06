from __future__ import annotations

import pytest

from app import mcp_server


class FakeEcommerce:
    async def search_products(self, keyword: str):
        return [{"id": 2, "name": keyword}]

    async def get_order_detail(self, order_id: int, access_token: str):
        return {"id": order_id, "orderNo": "ORD-8", "status": 0, "finalAmount": 99}


@pytest.mark.asyncio
async def test_mcp_product_search_helper(monkeypatch):
    monkeypatch.setattr(mcp_server, "ecommerce", FakeEcommerce())
    assert await mcp_server.search_products_data("smartphone") == [{"id": 2, "name": "smartphone"}]


@pytest.mark.asyncio
async def test_mcp_cancellation_is_preflight_only(monkeypatch):
    monkeypatch.setattr(mcp_server, "ecommerce", FakeEcommerce())
    result = await mcp_server.cancellation_preflight_data(8, "jwt")
    assert result["status"] == "confirmation_required"
    assert "not executed" in result["message"]
