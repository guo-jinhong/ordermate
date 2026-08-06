from __future__ import annotations

import httpx
import pytest

from app.clients.ecommerce_client import EcommerceClient


@pytest.mark.asyncio
async def test_api_response_without_data_is_success(monkeypatch):
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={"code": 200, "message": "Product added to cart successfully"},
        )
    )
    client = EcommerceClient("http://backend.test/api")
    replacement = httpx.AsyncClient(
        base_url="http://backend.test/api",
        transport=transport,
    )
    await client._client.aclose()
    monkeypatch.setattr(client, "_client", replacement)

    try:
        result = await client.add_to_cart(2, 1, "jwt")
    finally:
        await client.close()

    assert result is None


@pytest.mark.asyncio
async def test_search_products_sends_created_after(monkeypatch):
    seen_params = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_params.update(dict(request.url.params))
        return httpx.Response(
            200,
            json={
                "code": 200,
                "message": "Success",
                "data": {"content": []},
            },
        )

    client = EcommerceClient("http://backend.test/api")
    replacement = httpx.AsyncClient(
        base_url="http://backend.test/api",
        transport=httpx.MockTransport(handler),
    )
    await client._client.aclose()
    monkeypatch.setattr(client, "_client", replacement)

    try:
        result = await client.search_products(
            "耳机",
            max_price=3000,
            in_stock=True,
            created_after="2026-07-01",
        )
    finally:
        await client.close()

    assert result == []
    assert seen_params["keyword"] == "耳机"
    assert seen_params["maxPrice"] == "3000"
    assert seen_params["inStock"] == "true"
    assert seen_params["createdAfter"] == "2026-07-01"
