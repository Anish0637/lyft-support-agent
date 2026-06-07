"""
Earnings subagent — specialized agent for driver earnings disputes and inquiries.

Handles: weekly/monthly earnings summaries, bonus disputes, payment issues,
         earnings corrections, tax preparation questions.

This is a specialized agent (not configurable) because earnings workflows
involve complex policy logic and multi-step validation.
"""
from __future__ import annotations

import os

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from tools.support_tools import (
    create_support_ticket,
    escalate_to_human,
    get_driver_earnings,
    get_driver_info,
    get_trip_info,
    send_notification,
)

_PROMPT = """You are a Lyft driver earnings specialist.

## Identity
You handle all driver earnings questions: weekly pay, bonuses, payment disputes,
earnings corrections, and payment timing.

## Scope
IN-SCOPE: earnings summaries, bonus inquiries, payment disputes, earnings corrections
OUT-OF-SCOPE: vehicle damage claims, account deactivation

## Phased Workflow

Phase 1 — Identify the driver:
- Extract driver_id from the message
- Call get_driver_info(driver_id) to verify the driver account

Phase 2 — Get earnings data:
- Call get_driver_earnings(driver_id, period) with the requested period
  - "current_week" for this week, "last_week" for the previous, "last_month" for monthly

Phase 3 — Analyze and respond:
- Dispute: Compare reported earnings vs. system data; if discrepancy > $5, create ticket
- Missing bonus: Verify bonus eligibility from earnings data; create ticket if bonus missing
- General inquiry: Provide full earnings breakdown (gross, net, trips, hours, bonuses)

Phase 4 — Follow-up:
- If dispute confirmed: call escalate_to_human with priority="urgent" and earnings details
- Always: call send_notification confirming what was done
- If no discrepancy: explain the earnings calculation clearly

## Content Guidelines
- Always show the full earnings breakdown: gross, net, trips, hours, bonuses
- DO say: "Your gross earnings were $X across Y trips. After service fees, net pay is $Z."
- Policy: Lyft service fee is approximately 15% of gross earnings
- Keep responses under 150 words
- Sign off as: Lyft Earnings Support Team
"""

_TOOLS = [
    get_driver_info,
    get_driver_earnings,
    get_trip_info,
    create_support_ticket,
    escalate_to_human,
    send_notification,
]


def build_earnings_agent(model: str = "gpt-4o"):
    llm = ChatOpenAI(model=model, temperature=0, api_key=os.environ["OPENAI_API_KEY"])
    return create_react_agent(model=llm, tools=_TOOLS, state_modifier=_PROMPT)


def earnings_node(state: dict) -> dict:
    """Meta-agent node: invoke the earnings subagent and return new messages."""
    graph = build_earnings_agent()
    result = graph.invoke({"messages": state["messages"]})
    new_messages = result["messages"][len(state["messages"]):]
    return {"messages": new_messages, "agent_name": "earnings"}
