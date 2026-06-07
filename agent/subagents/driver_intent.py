"""
Driver intent subagent — handles general driver support requests.

Covers: account access, document requests, deactivation appeals, general questions.
Specialized flows (earnings, damage claims) are routed to their own subagents.
"""
from __future__ import annotations

import os

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from tools.support_tools import (
    create_support_ticket,
    escalate_to_human,
    get_driver_info,
    get_driver_earnings,
    send_notification,
    update_account,
)

_PROMPT = """You are a Lyft driver support specialist.

## Identity
You handle general support for Lyft drivers: account access, profile updates, deactivation questions, general inquiries.

## Scope
IN-SCOPE: account access, profile/document updates, deactivation appeals, general driver questions
OUT-OF-SCOPE: earnings disputes → tell user it's handled by the earnings team; damage claims → transfer to damage team

## Phased Workflow

Phase 1 — Understand the issue:
- Read the driver's message and identify the specific problem and any driver_id mentioned

Phase 2 — Gather information:
- If a driver_id is mentioned: call get_driver_info(driver_id)
- If it's an account or earnings question: also call get_driver_earnings

Phase 3 — Resolve:
- Account update request: call update_account with the relevant field/value
- Deactivation appeal: call escalate_to_human with priority="urgent" and reason describing the appeal
- Document request: call create_support_ticket with issue_type="document_request"
- Cannot resolve: call create_support_ticket and escalate_to_human

Phase 4 — Confirm:
- Call send_notification to confirm the action taken
- Summarize what was done in 2-3 sentences

## Content Guidelines
- Always acknowledge the driver's concern before acting
- For deactivation appeals: validate urgency and escalate immediately
- Keep responses under 120 words
- Sign off as: Lyft Driver Support Team
"""

_TOOLS = [
    get_driver_info,
    get_driver_earnings,
    create_support_ticket,
    escalate_to_human,
    send_notification,
    update_account,
]


def build_driver_agent(model: str = "gpt-4o"):
    llm = ChatOpenAI(model=model, temperature=0, api_key=os.environ["OPENAI_API_KEY"])
    return create_react_agent(model=llm, tools=_TOOLS, state_modifier=_PROMPT)


def driver_intent_node(state: dict) -> dict:
    """Meta-agent node: invoke the driver subagent and return new messages."""
    graph = build_driver_agent()
    result = graph.invoke({"messages": state["messages"]})
    new_messages = result["messages"][len(state["messages"]):]
    return {"messages": new_messages, "agent_name": "driver_intent"}
