from __future__ import annotations

import pytest

from app.approval_workflow import ApprovalWorkflow


@pytest.mark.asyncio
async def test_approval_workflow_interrupts_and_resumes_by_thread_id():
    workflow = ApprovalWorkflow()

    await workflow.start("confirmation-1", "cancel_order", {"order_id": 8})

    assert await workflow.resume("confirmation-1", True) is True
