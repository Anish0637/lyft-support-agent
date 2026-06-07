"""
Tests for ConfigurableAgent and the config loader.

Verifies:
  - JSON configs load correctly
  - ConfigurableAgent builds a working LangGraph graph
  - Direct invocation returns tool calls + response
  - Invalid config is skipped gracefully
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.configurable_agent import AgentConfig, ConfigurableAgent
from config.loader import load_configurable_agents
from tools.support_tools import clear_state


@pytest.fixture(autouse=True)
def reset():
    clear_state()
    yield
    clear_state()


def skip_if_no_key():
    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def test_load_configurable_agents():
    """All 3 JSON configs in config/agents/ should load without error."""
    agents = load_configurable_agents()
    assert len(agents) >= 3, f"Expected at least 3 configurable agents, got {len(agents)}"

    intents = [a.config.intent for a in agents]
    assert "driver_tax" in intents, f"driver_tax not found in {intents}"
    assert "charge_review" in intents
    assert "rider_general" in intents

    for agent in agents:
        assert agent.config.prompt, f"Prompt empty for {agent.config.intent}"
        assert agent.config.tools, f"Tools empty for {agent.config.intent}"
    print(f"  Loaded {len(agents)} configurable agents: {intents} ✓")


def test_load_from_custom_dir():
    """Loader should work with a custom config directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = {
            "intent": "test_agent",
            "user_type": "rider",
            "description": "Test agent",
            "tools": ["get_rider_info"],
            "prompt": "You are a test agent with scope: IN-SCOPE: testing. WORKFLOW: 1. Test. GUIDELINES: Be accurate. IDENTITY: tester.",
        }
        with open(Path(tmpdir) / "test_agent.json", "w") as f:
            json.dump(config, f)

        agents = load_configurable_agents(config_dir=tmpdir)
        assert len(agents) == 1
        assert agents[0].config.intent == "test_agent"
    print("  Custom dir loading ✓")


def test_invalid_json_skipped(capsys):
    """Invalid JSON file should be skipped with a warning, not crash the loader."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(Path(tmpdir) / "bad.json", "w") as f:
            f.write("{ invalid json }")

        agents = load_configurable_agents(config_dir=tmpdir)
        assert agents == [], "Expected empty list when all configs are invalid"
    print("  Invalid JSON gracefully skipped ✓")


# ---------------------------------------------------------------------------
# ConfigurableAgent graph building
# ---------------------------------------------------------------------------

def test_build_configurable_graph():
    """ConfigurableAgent should build a LangGraph with agent + tools nodes."""
    skip_if_no_key()
    config = AgentConfig(
        intent="test_rider",
        user_type="rider",
        description="Test",
        prompt="You are a test support agent. IDENTITY: tester. SCOPE: testing. WORKFLOW: 1. test. GUIDELINES: be helpful.",
        tools=["get_rider_info", "create_support_ticket"],
    )
    agent = ConfigurableAgent(config)
    graph = agent._build_graph()
    assert "agent" in graph.nodes
    assert "tools" in graph.nodes
    print(f"  Graph nodes: {list(graph.nodes.keys())} ✓")


def test_get_node_fn_returns_callable():
    """get_node_fn() should return a callable that accepts a state dict."""
    config = AgentConfig(
        intent="test_node",
        user_type="driver",
        description="Test",
        prompt="Test prompt. IDENTITY: tester. SCOPE: test. WORKFLOW: 1. test. GUIDELINES: test.",
        tools=["get_driver_info"],
    )
    agent = ConfigurableAgent(config)
    fn = agent.get_node_fn()
    assert callable(fn)
    print("  get_node_fn() returns callable ✓")


# ---------------------------------------------------------------------------
# ConfigurableAgent invocation
# ---------------------------------------------------------------------------

def test_driver_tax_agent_invoke():
    """driver_tax configurable agent should call get_driver_info and get_driver_earnings."""
    skip_if_no_key()

    agents = load_configurable_agents()
    tax_agent = next((a for a in agents if a.config.intent == "driver_tax"), None)
    assert tax_agent is not None, "driver_tax agent not found"

    result = tax_agent.invoke(
        "I need my 1099 form for last year. My driver ID is driver_001."
    )

    print(f"\n[driver_tax] tools: {[tc['name'] for tc in result['tool_calls']]}")
    print(f"  response: {result['final_response'][:150]}")

    tool_names = [tc["name"] for tc in result["tool_calls"]]
    assert "get_driver_info" in tool_names or "get_driver_earnings" in tool_names

    response_lower = result["final_response"].lower()
    assert any(w in response_lower for w in ["1099", "tax", "lyft app", "driver app", "january"])
    print("  driver_tax configurable agent ✓")


def test_charge_review_agent_invoke():
    """charge_review configurable agent should look up trip and explain charge."""
    skip_if_no_key()

    agents = load_configurable_agents()
    review_agent = next((a for a in agents if a.config.intent == "charge_review"), None)
    assert review_agent is not None, "charge_review agent not found"

    result = review_agent.invoke(
        "Can you explain why trip trip_003 cost $35? Rider ID is rider_001."
    )

    print(f"\n[charge_review] tools: {[tc['name'] for tc in result['tool_calls']]}")
    print(f"  response: {result['final_response'][:150]}")

    tool_names = [tc["name"] for tc in result["tool_calls"]]
    assert "get_trip_info" in tool_names
    print("  charge_review configurable agent ✓")
