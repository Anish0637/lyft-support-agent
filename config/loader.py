"""Load configurable agents from JSON config files in config/agents/."""
from __future__ import annotations

import json
from pathlib import Path


def load_configurable_agents(config_dir: str | Path | None = None):
    """
    Scan config/agents/*.json and return a list of ConfigurableAgent instances.

    Each JSON file defines one self-serve agent:
    {
        "intent":       "driver_tax",
        "user_type":    "driver",
        "description":  "Handles driver tax questions",
        "tools":        ["get_driver_info", "get_driver_earnings", "create_support_ticket"],
        "prompt":       "You are a Lyft driver tax specialist..."
    }

    New agents are added by dropping a JSON file — no MLE code change required.
    """
    # Late import to avoid circular dependency (meta_agent → config.loader → configurable_agent)
    from agent.configurable_agent import AgentConfig, ConfigurableAgent

    if config_dir is None:
        config_dir = Path(__file__).parent / "agents"

    config_dir = Path(config_dir)
    agents: list[ConfigurableAgent] = []

    for json_file in sorted(config_dir.glob("*.json")):
        try:
            with open(json_file) as f:
                data = json.load(f)

            config = AgentConfig(
                intent=data["intent"],
                user_type=data["user_type"],
                description=data.get("description", ""),
                prompt=data["prompt"],
                tools=data.get("tools", []),
                metadata=data.get("metadata"),
            )
            agents.append(ConfigurableAgent(config))

        except Exception as e:
            print(f"[ConfigLoader] Skipping {json_file.name}: {e}")

    return agents
