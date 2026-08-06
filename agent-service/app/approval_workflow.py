from __future__ import annotations

from typing import Any, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt


class ApprovalState(TypedDict, total=False):
    action: str
    arguments: dict[str, Any]
    approved: bool


def _await_human_approval(state: ApprovalState) -> ApprovalState:
    """Pause before a side effect; the resume value becomes `approved`."""
    approved = interrupt(
        {
            "action": state["action"],
            "arguments": state["arguments"],
            "message": "请确认是否执行该写操作。",
        }
    )
    return {"approved": bool(approved)}


class ApprovalWorkflow:
    """LangGraph HITL workflow with a checkpointer keyed by confirmation token."""

    def __init__(self, checkpointer: Any | None = None) -> None:
        self._build(checkpointer or InMemorySaver())

    def set_checkpointer(self, checkpointer: Any) -> None:
        """Switch to a durable saver after application startup initialization."""
        self._build(checkpointer)

    def _build(self, checkpointer: Any) -> None:
        builder = StateGraph(ApprovalState)
        builder.add_node("await_human_approval", _await_human_approval)
        builder.add_edge(START, "await_human_approval")
        builder.add_edge("await_human_approval", END)
        self._graph = builder.compile(checkpointer=checkpointer)

    async def start(self, thread_id: str, action: str, arguments: dict[str, Any]) -> None:
        await self._graph.ainvoke(
            {"action": action, "arguments": arguments},
            config=self._config(thread_id),
        )

    async def resume(self, thread_id: str, approved: bool) -> bool:
        result = await self._graph.ainvoke(
            Command(resume=approved), config=self._config(thread_id)
        )
        return bool(result.get("approved"))

    @staticmethod
    def _config(thread_id: str) -> dict[str, dict[str, str]]:
        return {"configurable": {"thread_id": f"approval:{thread_id}"}}
