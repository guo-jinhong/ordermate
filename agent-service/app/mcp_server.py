"""MCP server exposing e-commerce tools backed by local database."""
from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from app.clients.mysql_client import EcommerceApiError, EcommerceClient
from app.config import Settings
from app.database import get_repository

mcp = FastMCP("E-commerce Order MCP")
settings = Settings.from_env()
ecommerce = EcommerceClient()
repo = get_repository()


# ============================================================
# 数据访问层
# ============================================================

async def search_products_data(keyword: str) -> list[dict[str, Any]]:
    return await ecommerce.search_products(keyword)


async def product_detail_data(product_id: int) -> dict[str, Any]:
    return await ecommerce.get_product_detail(product_id)


async def order_list_data(access_token: str) -> list[dict[str, Any]]:
    _require_token(access_token)
    return await ecommerce.get_my_orders(access_token)


async def cancellation_preflight_data(order_id: int, access_token: str) -> dict[str, Any]:
    _require_token(access_token)
    order = await ecommerce.get_order_detail(order_id, access_token)
    if order.get("status") != 0:
        raise EcommerceApiError("Only unpaid orders can be prepared for cancellation.")
    return {
        "status": "confirmation_required",
        "order_id": order_id,
        "order_no": order.get("orderNo"),
        "final_amount": order.get("finalAmount"),
        "message": "Cancellation was not executed. Ask the user to confirm in the OrderMate UI.",
    }


def search_knowledge_data(query: str, limit: int = 3) -> list[dict[str, Any]]:
    """从数据库搜索知识库"""
    results = repo.search_knowledge(query)
    return results[:limit]


# ============================================================
# MCP 工具定义
# ============================================================

@mcp.tool()
async def search_products(keyword: str) -> list[dict[str, Any]]:
    """Search currently available products by keyword (Chinese or English)."""
    return await search_products_data(keyword)


@mcp.tool()
async def get_product_detail(product_id: int) -> dict[str, Any]:
    """Get one product's live details by numeric ID."""
    return await product_detail_data(product_id)


@mcp.tool()
def search_product_knowledge(query: str) -> list[dict[str, Any]]:
    """Search after-sales policies, refund rules, payment methods, and shipping info."""
    return search_knowledge_data(query)


@mcp.tool()
async def get_my_orders(access_token: str) -> list[dict[str, Any]]:
    """List the authenticated user's orders. A valid access token is required."""
    return await order_list_data(access_token)


@mcp.tool()
async def prepare_order_cancellation(order_id: int, access_token: str) -> dict[str, Any]:
    """Validate a cancellation request without executing it; a valid token is required."""
    return await cancellation_preflight_data(order_id, access_token)


def _require_token(access_token: str) -> None:
    if not access_token:
        raise ValueError("A user access token is required for this tool.")


if __name__ == "__main__":
    mcp.run(transport="stdio")
