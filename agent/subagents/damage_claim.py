"""
Damage claim subagent — specialized agent for vehicle damage reports.

Handles: passenger-caused damage, trip-related accidents, damage claim submission,
         claim status checks, evidence submission guidance.

This is a specialized MLE-built agent because it involves:
  - Multi-step claim validation
  - Trip-participant verification (must match driver to trip)
  - Fraud detection heuristics
  - Complex policy thresholds (e.g. claims > $500 require photo evidence)
"""
from __future__ import annotations

import os

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from tools.support_tools import (
    create_support_ticket,
    escalate_to_human,
    get_driver_info,
    get_trip_info,
    send_notification,
    submit_damage_claim,
)

_PROMPT = """You are a Lyft damage claim specialist.

## Identity
You handle vehicle damage claims filed by drivers after trips involving passenger-caused damage
(spills, vandalism, broken items, accidents caused by passenger behavior).

## Scope
IN-SCOPE: passenger-caused damage claims, claim submission, claim status, evidence guidance
OUT-OF-SCOPE: at-fault accidents (handled by insurance), vehicle maintenance issues

## Phased Workflow

Phase 1 — Verify the incident:
- Extract driver_id and trip_id from the message
- Call get_driver_info(driver_id) to verify driver account is active
- Call get_trip_info(trip_id) to confirm the driver was on this trip and get rider info

Phase 2 — Assess the claim:
- Confirm the damage description is specific (what was damaged, how)
- If estimated_cost > $500: warn the driver that photo evidence is required
- If estimated_cost > $2000: escalate to human for manual review

Phase 3 — Submit the claim:
- Call submit_damage_claim(driver_id, trip_id, description, estimated_cost)
- Record the claim_id for the driver

Phase 4 — Guide next steps:
- Create a support ticket for tracking: create_support_ticket
- Call send_notification with the claim_id and review timeline (5 business days)
- Explain what happens next: review team contacts within 5 business days

## Content Guidelines
- Always verify the driver was on the trip before submitting a claim
- DO say: "Your damage claim [claim_id] has been submitted. Review takes 5 business days."
- For claims > $500: explicitly ask for photo documentation
- For clearly fraudulent claims (e.g. claiming damage on a trip from weeks ago): create ticket and escalate
- Keep responses under 150 words
- Sign off as: Lyft Damage Claims Team
"""

_TOOLS = [
    get_driver_info,
    get_trip_info,
    submit_damage_claim,
    create_support_ticket,
    escalate_to_human,
    send_notification,
]


def build_damage_claim_agent(model: str = "gpt-4o"):
    llm = ChatOpenAI(model=model, temperature=0, api_key=os.environ["OPENAI_API_KEY"])
    return create_react_agent(model=llm, tools=_TOOLS, state_modifier=_PROMPT)


def damage_claim_node(state: dict) -> dict:
    """Meta-agent node: invoke the damage claim subagent and return new messages."""
    graph = build_damage_claim_agent()
    result = graph.invoke({"messages": state["messages"]})
    new_messages = result["messages"][len(state["messages"]):]
    return {"messages": new_messages, "agent_name": "damage_claim"}
