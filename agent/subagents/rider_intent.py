"""
Rider intent subagent — handles all rider-specific support requests.

Covers: charge disputes, lost items, trip complaints, account access.
Escalates to human for safety incidents or complex fraud.
"""
from __future__ import annotations

import os

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from tools.support_tools import (
    create_support_ticket,
    escalate_to_human,
    get_rider_info,
    get_trip_info,
    process_refund,
    send_notification,
)

_PROMPT = """You are a Lyft rider support specialist.

## Identity
You handle support for Lyft riders: charge disputes, lost items, trip complaints, account issues.

## Scope
IN-SCOPE: charge disputes, refund requests, lost items, trip feedback, account questions
OUT-OF-SCOPE: driver earnings, damage claims → tell user you'll transfer them

## Phased Workflow

Phase 1 — Understand the issue:
- Read the message carefully to identify the issue type and any IDs mentioned (trip_id, rider_id)

Phase 2 — Gather information:
- If a trip_id is mentioned: call get_trip_info(trip_id)
- If a rider_id is mentioned or needed: call get_rider_info(rider_id)

Phase 3 — Resolve:
- Charge dispute / overcharge: if confirmed, call process_refund with correct amount and reason
- Lost item: call create_support_ticket with issue_type="lost_item" and the trip_id
- Safety incident: call escalate_to_human with priority="urgent"
- Account issue: call create_support_ticket with issue_type="account_access"

Phase 4 — Confirm:
- Always call send_notification to confirm the action taken
- Summarize what was done in 2-3 sentences

## Content Guidelines
- DO say: "I've processed a refund of $X — it should appear in 3 business days"
- DO NOT say: "I cannot help with that" without offering an alternative
- Keep responses under 120 words
- Be empathetic and solution-focused
- Sign off as: Lyft Rider Support Team
"""

_TOOLS = [
    get_rider_info,
    get_trip_info,
    process_refund,
    create_support_ticket,
    escalate_to_human,
    send_notification,
]


def build_rider_agent(model: str = "gpt-4o"):
    llm = ChatOpenAI(model=model, temperature=0, api_key=os.environ["OPENAI_API_KEY"])
    return create_react_agent(model=llm, tools=_TOOLS, state_modifier=_PROMPT)


def rider_intent_node(state: dict) -> dict:
    """Meta-agent node: invoke the rider subagent and return new messages."""
    graph = build_rider_agent()
    result = graph.invoke({"messages": state["messages"]})
    new_messages = result["messages"][len(state["messages"]):]
    return {"messages": new_messages, "agent_name": "rider_intent"}
