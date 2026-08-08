from __future__ import annotations

import pytest

from app.knowledge_base import KnowledgeBase
from app.tools.confirmation import ConfirmationStore
from app.tools.registry import ToolRegistry


def test_knowledge_base_retrieves_after_sales_policy():
    matches = KnowledgeBase(prefer_database=False).search("refund after-sales")
    assert matches
    assert matches[0]["id"] == "after-sales-refund"


@pytest.mark.asyncio
async def test_knowledge_base_is_available_as_agent_tool():
    registry = ToolRegistry(
        object(),
        ConfirmationStore(),
        knowledge_base=KnowledgeBase(prefer_database=False),
    )
    result = await registry.execute(
        "search_knowledge_base", {"query": "Smartphone X specifications"}, session_id="s1", access_token=None
    )
    assert result.outcome == "success"
    assert result.output["data"][0]["id"] == "product-smartphone-x"
