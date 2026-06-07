"""
ConfigurableAgent — the self-serve agent layer.

Domain experts (ops, VoC leads, PMs) define new agents by writing a JSON config
and a prompt. No MLE code changes needed. The platform handles graph construction,
tool binding, and state management.

JSON config schema:
{
    "intent":       "driver_tax",          # unique slug — used as graph node name
    "user_type":    "driver",              # "rider" or "driver"
    "description":  "Handles tax questions",
    "prompt":       "You are a Lyft tax specialist...",
    "tools":        ["get_driver_info", "get_driver_earnings", "create_support_ticket"],
    "metadata":     {}                     # optional extra config
}
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from tools.support_tools import ALL_TOOLS, TOOL_REGISTRY


@dataclass
class AgentConfig:
    """Runtime config for a self-serve configurable agent."""

    intent: str
    user_type: str
    description: str
    prompt: str
    tools: list[str]
    metadata: Optional[dict] = field(default=None)


class ConfigurableAgent:
    """
    A runtime-configurable LangGraph ReAct agent.

    - Initialized from AgentConfig (loaded from JSON at startup)
    - Builds a create_react_agent graph with the specified tools and prompt
    - Registered in the meta agent as a subgraph node via get_node_fn()

    Example:
        config = AgentConfig(intent="driver_tax", ...)
        agent = ConfigurableAgent(config)
        meta_builder.add_node("driver_tax", agent.get_node_fn())
    """

    def __init__(self, config: AgentConfig):
        self.config = config

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _resolve_tools(self) -> list:
        resolved = [TOOL_REGISTRY[name] for name in self.config.tools if name in TOOL_REGISTRY]
        if not resolved:
            # Fallback: give the agent all tools rather than nothing
            return ALL_TOOLS
        return resolved

    def _build_graph(self, model: str = "gpt-4o"):
        llm = ChatOpenAI(
            model=model,
            temperature=0,
            api_key=os.environ["OPENAI_API_KEY"],
        )
        return create_react_agent(
            model=llm,
            tools=self._resolve_tools(),
            state_modifier=self.config.prompt,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_node_fn(self, model: str = "gpt-4o"):
        """
        Return a LangGraph node function for this configurable agent.

        The returned function is added to the meta agent's StateGraph:
            meta_builder.add_node(agent.config.intent, agent.get_node_fn())

        It receives the parent SupportState, invokes the subgraph, and returns
        only the *new* messages (everything the subagent added).
        """
        intent = self.config.intent

        def node_fn(state: dict) -> dict:
            graph = self._build_graph(model=model)
            result = graph.invoke({"messages": state["messages"]})
            new_messages = result["messages"][len(state["messages"]):]
            return {"messages": new_messages, "agent_name": intent}

        return node_fn

    def invoke(self, message: str, model: str = "gpt-4o") -> dict:
        """
        Direct invocation for testing/evaluation (bypasses the meta agent).

        Returns:
            {"tool_calls": [...], "final_response": "..."}
        """
        graph = self._build_graph(model=model)
        result = graph.invoke({"messages": [("human", message)]})

        tool_calls = []
        for msg in result["messages"]:
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_calls.append({"name": tc["name"], "args": tc["args"]})

        return {
            "tool_calls": tool_calls,
            "final_response": result["messages"][-1].content,
        }
