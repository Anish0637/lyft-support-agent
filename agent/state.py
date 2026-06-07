"""Shared state for the Lyft multi-agent support system."""
from __future__ import annotations

from typing import Optional

from langgraph.graph import MessagesState


class SupportState(MessagesState):
    """
    State shared across the meta agent and all subagents.

    Inherits:
        messages: Annotated[list, add_messages]  — full conversation history

    Added fields:
        user_type       — "rider" or "driver" (caller hint + LLM-refined)
        intent          — classified intent slug (e.g. "charge_dispute")
        agent_name      — which subagent handled the turn
        conversation_id — thread ID for checkpointing / LangSmith tracing
        safety_passed   — True if safety gate passed
        blocked_reason  — set when safety_passed=False
    """

    user_type: str
    intent: str
    agent_name: str
    conversation_id: str
    safety_passed: bool
    blocked_reason: Optional[str]
