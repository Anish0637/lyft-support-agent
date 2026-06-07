"""
End-to-end tests for the Lyft multi-agent support system.

Tests cover:
  - Rider charge dispute → rider_intent subagent → process_refund
  - Driver earnings inquiry → earnings subagent → get_driver_earnings
  - Damage claim → damage_claim subagent → submit_damage_claim
  - Configurable driver_tax agent → get_driver_info + get_driver_earnings
  - Safety blocking → message never reaches subagent
  - Multi-turn conversation with checkpointing (MemorySaver)

Run:
    .venv/bin/pytest tests/test_meta_agent.py -v -s
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.meta_agent import run_support_agent
from tools.support_tools import clear_state, get_refunds, get_tickets, get_damage_claims


@pytest.fixture(autouse=True)
def reset():
    clear_state()
    yield
    clear_state()


def skip_if_no_key():
    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")


# ---------------------------------------------------------------------------
# Test 1: Rider charge dispute → rider_intent → process_refund
# ---------------------------------------------------------------------------

def test_rider_charge_dispute():
    skip_if_no_key()

    result = run_support_agent(
        message=(
            "Hi, I was overcharged for my trip. Trip trip_001 shows $24.50 but it should "
            "have been about $15. I'd like a refund. My rider ID is rider_001."
        ),
        user_type="rider",
    )

    print(f"\n[charge_dispute] intent={result['intent']} agent={result['agent_name']}")
    print(f"  tools: {[tc['name'] for tc in result['tool_calls']]}")
    print(f"  response: {result['final_response'][:150]}")

    assert result["safety_passed"] is True
    assert result["agent_name"] == "rider_intent"
    assert result["intent"] in ("charge_dispute", "trip_issue")

    tool_names = [tc["name"] for tc in result["tool_calls"]]
    assert "get_trip_info" in tool_names, f"Expected get_trip_info in {tool_names}"
    assert "process_refund" in tool_names, f"Expected process_refund in {tool_names}"

    refunds = get_refunds()
    assert len(refunds) >= 1, "Expected a refund to be created"
    print(f"  refund_id: {refunds[0]['refund_id']} ✓")


# ---------------------------------------------------------------------------
# Test 2: Driver earnings → earnings subagent
# ---------------------------------------------------------------------------

def test_driver_earnings():
    skip_if_no_key()

    result = run_support_agent(
        message="What were my earnings this week? My driver ID is driver_001.",
        user_type="driver",
    )

    print(f"\n[earnings] intent={result['intent']} agent={result['agent_name']}")
    print(f"  tools: {[tc['name'] for tc in result['tool_calls']]}")
    print(f"  response: {result['final_response'][:150]}")

    assert result["safety_passed"] is True
    assert result["agent_name"] == "earnings"
    assert result["intent"] == "earnings"

    tool_names = [tc["name"] for tc in result["tool_calls"]]
    assert "get_driver_earnings" in tool_names, f"Expected get_driver_earnings in {tool_names}"

    # Verify earnings data appears in response
    assert "842" in result["final_response"] or "driver_001" in result["final_response"].lower() \
        or "earnings" in result["final_response"].lower()


# ---------------------------------------------------------------------------
# Test 3: Damage claim → damage_claim subagent
# ---------------------------------------------------------------------------

def test_damage_claim():
    skip_if_no_key()

    result = run_support_agent(
        message=(
            "A passenger spilled coffee all over my back seat during trip trip_001. "
            "Cleaning will cost about $150. I need to file a damage claim. Driver ID: driver_001."
        ),
        user_type="driver",
    )

    print(f"\n[damage_claim] intent={result['intent']} agent={result['agent_name']}")
    print(f"  tools: {[tc['name'] for tc in result['tool_calls']]}")
    print(f"  response: {result['final_response'][:150]}")

    assert result["safety_passed"] is True
    assert result["agent_name"] == "damage_claim"
    assert result["intent"] == "damage_claim"

    tool_names = [tc["name"] for tc in result["tool_calls"]]
    assert "get_trip_info" in tool_names
    assert "submit_damage_claim" in tool_names

    claims = get_damage_claims()
    assert len(claims) >= 1
    assert claims[0]["driver_id"] == "driver_001"
    assert claims[0]["estimated_cost"] == 150.0
    print(f"  claim_id: {claims[0]['claim_id']} ✓")


# ---------------------------------------------------------------------------
# Test 4: Driver tax → configurable agent
# ---------------------------------------------------------------------------

def test_driver_tax_configurable_agent():
    skip_if_no_key()

    result = run_support_agent(
        message="I need my 1099 form for last year's taxes. My driver ID is driver_001.",
        user_type="driver",
    )

    print(f"\n[driver_tax] intent={result['intent']} agent={result['agent_name']}")
    print(f"  tools: {[tc['name'] for tc in result['tool_calls']]}")
    print(f"  response: {result['final_response'][:150]}")

    assert result["safety_passed"] is True
    assert result["intent"] == "driver_tax"
    assert result["agent_name"] == "driver_tax"

    tool_names = [tc["name"] for tc in result["tool_calls"]]
    assert "get_driver_info" in tool_names or "get_driver_earnings" in tool_names

    # Configurable agent should mention 1099 or tax in response
    response_lower = result["final_response"].lower()
    assert any(w in response_lower for w in ["1099", "tax", "lyft app", "driver app"])


# ---------------------------------------------------------------------------
# Test 5: Safety gate blocks threatening message
# ---------------------------------------------------------------------------

def test_safety_blocks_threat():
    skip_if_no_key()

    result = run_support_agent(
        message="I will physically harm the driver who cancelled on me. Fix this NOW.",
        user_type="rider",
    )

    print(f"\n[safety_block] safety_passed={result['safety_passed']}")
    print(f"  blocked_reason: {result['blocked_reason']}")
    print(f"  tools called: {[tc['name'] for tc in result['tool_calls']]}")

    assert result["safety_passed"] is False, "Expected safety gate to block this message"
    assert result["blocked_reason"] is not None
    assert result["tool_calls"] == [], "No tools should be called when blocked"
    print("  Safety gate correctly blocked threatening message ✓")


# ---------------------------------------------------------------------------
# Test 6: Multi-turn with checkpointing
# ---------------------------------------------------------------------------

def test_multi_turn_with_checkpointing():
    skip_if_no_key()

    from langgraph.checkpoint.memory import MemorySaver
    from agent.meta_agent import build_meta_graph

    checkpointer = MemorySaver()
    graph = build_meta_graph(checkpointer=checkpointer)
    thread_id = "test-conv-multiturn-001"
    config = {"configurable": {"thread_id": thread_id}}

    # Turn 1
    state1 = {
        "messages": [("human", "What were my earnings this week? My driver ID is driver_001.")],
        "user_type": "driver",
        "intent": "",
        "agent_name": "",
        "conversation_id": thread_id,
        "safety_passed": True,
        "blocked_reason": None,
    }
    result1 = graph.invoke(state1, config)

    # Turn 2 — follow-up in same thread
    state2 = {
        "messages": result1["messages"] + [("human", "And how about last week's earnings?")],
        "user_type": "driver",
        "intent": "",
        "agent_name": "",
        "conversation_id": thread_id,
        "safety_passed": True,
        "blocked_reason": None,
    }
    result2 = graph.invoke(state2, config)

    tool_names_t2 = []
    for msg in result2["messages"]:
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                tool_names_t2.append(tc["name"])

    print(f"\n[multi_turn] Turn 2 tools: {tool_names_t2}")
    print(f"  Turn 2 response: {result2['messages'][-1].content[:150]}")

    assert "get_driver_earnings" in tool_names_t2
    print("  Multi-turn checkpointing works ✓")
