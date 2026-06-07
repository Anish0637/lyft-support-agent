"""
Meta agent — the top-level LangGraph router for Lyft's multi-agent support system.

Architecture (from the Lyft blog post):
  - A meta agent acts as a stateful router
  - Classifies intent → dispatches to specialized or configurable subagent
  - Safety checks run BEFORE every LLM reasoning step
  - Configurable agents are loaded from JSON config at startup

Graph flow:
  START → safety → classify → [rider_intent | driver_intent | earnings |
                                damage_claim | <configurable agents>] → END

Separate router instances run for riders and drivers (user_type hint).
"""
from __future__ import annotations

import os
import uuid
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from agent.safety import run_safety_check
from agent.state import SupportState
from agent.subagents.damage_claim import damage_claim_node
from agent.subagents.driver_intent import driver_intent_node
from agent.subagents.earnings import earnings_node
from agent.subagents.rider_intent import rider_intent_node

# ---------------------------------------------------------------------------
# Intent classification
# ---------------------------------------------------------------------------

_CLASSIFY_SYSTEM = """You are an intent classifier for Lyft's customer support system.

Classify the support request and return JSON with exactly these fields:
  - user_type: "rider" or "driver"
  - intent: one of the exact values below

Intent values:
  charge_dispute   — rider disputing a charge or requesting a refund
  lost_item        — rider lost something in a Lyft vehicle
  trip_issue       — rider complaint about a specific trip experience
  account_access   — user cannot access their account
  earnings         — driver asking about earnings, pay, bonuses, or payment timing
  damage_claim     — driver reporting vehicle damage caused by a passenger
  driver_tax       — driver asking about tax documents, 1099, or deductions
  charge_review    — detailed review of a specific charge or billing breakdown
  rider_general    — other rider support not covered above
  driver_general   — other driver support not covered above

Return ONLY the JSON object, no explanation."""


class _IntentResult(BaseModel):
    user_type: str
    intent: str


# Maps intent slug → StateGraph node name
_INTENT_TO_NODE: dict[str, str] = {
    "charge_dispute": "rider_intent",
    "lost_item":      "rider_intent",
    "trip_issue":     "rider_intent",
    "rider_general":  "rider_intent",
    "account_access": "driver_intent",
    "driver_general": "driver_intent",
    "earnings":       "earnings",
    "damage_claim":   "damage_claim",
    # configurable agents — registered at build time:
    "driver_tax":     "driver_tax",
    "charge_review":  "charge_review",
    "rider_general_configurable": "rider_general",
}


def _classify_node(state: SupportState) -> dict:
    """
    LLM-based intent classification node.

    Uses gpt-4o with structured output. Falls back to keyword matching
    if the LLM call fails, so the system never fully breaks.
    """
    if not state.get("safety_passed", True):
        return {}  # skip classification if safety blocked

    messages = state.get("messages", [])
    last = messages[-1] if messages else None
    content = last.content if last and hasattr(last, "content") else ""

    try:
        llm = ChatOpenAI(
            model="gpt-4o",
            temperature=0,
            api_key=os.environ["OPENAI_API_KEY"],
        )
        result: _IntentResult = llm.with_structured_output(_IntentResult).invoke([
            SystemMessage(content=_CLASSIFY_SYSTEM),
            HumanMessage(content=content),
        ])
        intent = result.intent
        user_type = result.user_type

    except Exception:
        # Keyword fallback — keeps the system running if LLM is unavailable
        c = content.lower()
        if any(w in c for w in ["earn", "pay", "wage", "bonus", "income", "weekly pay"]):
            intent, user_type = "earnings", "driver"
        elif any(w in c for w in ["damage", "spill", "scratch", "dent", "accident"]):
            intent, user_type = "damage_claim", "driver"
        elif any(w in c for w in ["refund", "overcharg", "wrong charge", "charge dispute"]):
            intent, user_type = "charge_dispute", "rider"
        elif any(w in c for w in ["lost", "left behind", "forgot", "left my"]):
            intent, user_type = "lost_item", "rider"
        elif any(w in c for w in ["1099", "tax", "deduction", "w-2"]):
            intent, user_type = "driver_tax", "driver"
        elif any(w in c for w in ["review my charge", "explain charge", "billing breakdown"]):
            intent, user_type = "charge_review", "rider"
        else:
            user_type = state.get("user_type", "rider")
            intent = "driver_general" if user_type == "driver" else "rider_general"

    node = _INTENT_TO_NODE.get(intent, "rider_intent")
    return {"intent": intent, "user_type": user_type, "agent_name": node}


def _route_from_classify(state: SupportState) -> str:
    """Conditional edge: return the node name to route to after classification."""
    if not state.get("safety_passed", True):
        return "__end__"
    intent = state.get("intent", "rider_general")
    return _INTENT_TO_NODE.get(intent, "rider_intent")


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_meta_graph(checkpointer=None):
    """
    Build and compile the top-level LangGraph StateGraph.

    Specialized subagents (MLE-built):
      rider_intent, driver_intent, earnings, damage_claim

    Configurable subagents (loaded from config/agents/*.json):
      driver_tax, charge_review, rider_general (+ any future additions)

    The configurable agents are dynamically discovered and registered here,
    meaning a PM can add a new agent by dropping a JSON file — no code change.
    """
    from config.loader import load_configurable_agents  # late import avoids circularity

    builder = StateGraph(SupportState)

    # ── Core nodes ─────────────────────────────────────────────────────────
    builder.add_node("safety",       run_safety_check)
    builder.add_node("classify",     _classify_node)

    # ── Specialized subagent nodes ─────────────────────────────────────────
    builder.add_node("rider_intent", rider_intent_node)
    builder.add_node("driver_intent", driver_intent_node)
    builder.add_node("earnings",     earnings_node)
    builder.add_node("damage_claim", damage_claim_node)

    # ── Configurable subagent nodes (self-serve) ───────────────────────────
    configurable_agents = load_configurable_agents()
    configurable_node_names: list[str] = []
    for agent in configurable_agents:
        builder.add_node(agent.config.intent, agent.get_node_fn())
        configurable_node_names.append(agent.config.intent)

    # ── Edges ──────────────────────────────────────────────────────────────
    builder.add_edge(START, "safety")
    builder.add_edge("safety", "classify")

    # Build the full routing map (specialized + configurable)
    routing_map: dict[str, str | object] = {
        "rider_intent":  "rider_intent",
        "driver_intent": "driver_intent",
        "earnings":      "earnings",
        "damage_claim":  "damage_claim",
        "__end__":       END,
    }
    routing_map.update({name: name for name in configurable_node_names})

    builder.add_conditional_edges("classify", _route_from_classify, routing_map)

    # All subagent nodes terminate at END
    for node_name in ["rider_intent", "driver_intent", "earnings", "damage_claim"] + configurable_node_names:
        builder.add_edge(node_name, END)

    return builder.compile(checkpointer=checkpointer)


# ---------------------------------------------------------------------------
# Public run API
# ---------------------------------------------------------------------------

def run_support_agent(
    message: str,
    user_type: str = "rider",
    conversation_id: Optional[str] = None,
    checkpointer=None,
) -> dict:
    """
    Run the full multi-agent support system for a single turn.

    Args:
        message:         Incoming support message from the user.
        user_type:       "rider" or "driver" — hint used if LLM classification fails.
        conversation_id: Thread ID for multi-turn checkpointing.
        checkpointer:    LangGraph checkpointer (MemorySaver or DynamoDBSaver).

    Returns:
        {
            "tool_calls":     [{"name": ..., "args": ...}, ...],
            "final_response": "...",
            "intent":         "earnings",
            "safety_passed":  True,
            "blocked_reason": None,
            "agent_name":     "earnings",
            "conversation_id": "...",
        }
    """
    graph = build_meta_graph(checkpointer=checkpointer)

    conv_id = conversation_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": conv_id}} if checkpointer else {}

    initial_state = {
        "messages":        [("human", message)],
        "user_type":       user_type,
        "intent":          "",
        "agent_name":      "",
        "conversation_id": conv_id,
        "safety_passed":   True,
        "blocked_reason":  None,
    }

    result = graph.invoke(initial_state, config)

    # Collect tool call trajectory from all AIMessages
    tool_calls: list[dict] = []
    for msg in result.get("messages", []):
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                tool_calls.append({"name": tc["name"], "args": tc["args"]})

    final_msg = result.get("messages", [])[-1] if result.get("messages") else None
    final_response = final_msg.content if final_msg and hasattr(final_msg, "content") else ""

    return {
        "tool_calls":      tool_calls,
        "final_response":  final_response,
        "intent":          result.get("intent"),
        "safety_passed":   result.get("safety_passed", True),
        "blocked_reason":  result.get("blocked_reason"),
        "agent_name":      result.get("agent_name"),
        "conversation_id": conv_id,
    }
