"""
Agent Builder API routes — internal tool for domain experts.

GET    /api/agents              — list all configurable agents
GET    /api/agents/{intent}     — get a single agent config
POST   /api/agents              — create a new agent (writes JSON file)
PUT    /api/agents/{intent}     — update an existing agent
DELETE /api/agents/{intent}     — delete an agent
POST   /api/agents/lint         — lint a prompt + config (returns errors)
POST   /api/agents/test         — test an agent config with a sample message
GET    /api/agents/tools        — list all available tools that can be assigned
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

from api.models import (
    AgentConfig,
    LintIssue,
    LintRequest,
    LintResponse,
    TestAgentRequest,
    TestAgentResponse,
    ToolCallInfo,
)

router = APIRouter()

AGENTS_DIR = Path(__file__).parent.parent.parent / "config" / "agents"
AGENTS_DIR.mkdir(parents=True, exist_ok=True)

AVAILABLE_TOOLS = [
    "get_rider_info",
    "get_trip_info",
    "process_refund",
    "get_driver_info",
    "get_driver_earnings",
    "submit_damage_claim",
    "create_support_ticket",
    "escalate_to_human",
    "send_notification",
    "update_account",
]


def _load_config(intent: str) -> dict:
    path = AGENTS_DIR / f"{intent}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Agent '{intent}' not found")
    with open(path) as f:
        return json.load(f)


@router.get("/tools")
def list_tools():
    """Return all tools that can be assigned to configurable agents."""
    return {"tools": AVAILABLE_TOOLS}


@router.get("")
def list_agents():
    """List all configurable agents from config/agents/."""
    agents = []
    for f in sorted(AGENTS_DIR.glob("*.json")):
        try:
            with open(f) as fp:
                data = json.load(fp)
            agents.append({
                "intent":      data.get("intent"),
                "user_type":   data.get("user_type"),
                "description": data.get("description", ""),
                "tools":       data.get("tools", []),
                "file":        f.name,
            })
        except Exception:
            continue
    return {"agents": agents, "count": len(agents)}


@router.get("/{intent}")
def get_agent(intent: str):
    """Get a single agent config by intent slug."""
    return _load_config(intent)


@router.post("")
def create_agent(config: AgentConfig):
    """
    Create a new configurable agent.

    Validates intent slug uniqueness, runs static lint, then writes JSON.
    In production: opens a Git PR instead of writing directly.
    """
    path = AGENTS_DIR / f"{config.intent}.json"
    if path.exists():
        raise HTTPException(status_code=409, detail=f"Agent '{config.intent}' already exists. Use PUT to update.")

    # Run lint before saving
    from ci.prompt_linter import PromptLinter
    linter = PromptLinter()
    errors = linter.lint(config.prompt, config.model_dump(), run_llm_checks=False)
    hard_errors = [e for e in errors if e.severity == "error"]
    if hard_errors:
        raise HTTPException(
            status_code=422,
            detail={"message": "Prompt lint failed", "errors": [{"rule": e.rule, "message": e.message} for e in hard_errors]},
        )

    with open(path, "w") as f:
        json.dump(config.model_dump(exclude_none=True), f, indent=2)

    return {"status": "created", "intent": config.intent, "file": path.name}


@router.put("/{intent}")
def update_agent(intent: str, config: AgentConfig):
    """Update an existing agent config."""
    _load_config(intent)  # raises 404 if not found

    from ci.prompt_linter import PromptLinter
    linter = PromptLinter()
    errors = linter.lint(config.prompt, config.model_dump(), run_llm_checks=False)
    hard_errors = [e for e in errors if e.severity == "error"]
    if hard_errors:
        raise HTTPException(
            status_code=422,
            detail={"message": "Prompt lint failed", "errors": [{"rule": e.rule, "message": e.message} for e in hard_errors]},
        )

    path = AGENTS_DIR / f"{intent}.json"
    with open(path, "w") as f:
        json.dump(config.model_dump(exclude_none=True), f, indent=2)

    return {"status": "updated", "intent": intent}


@router.delete("/{intent}")
def delete_agent(intent: str):
    """Delete a configurable agent config file."""
    path = AGENTS_DIR / f"{intent}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Agent '{intent}' not found")
    path.unlink()
    return {"status": "deleted", "intent": intent}


@router.post("/lint")
def lint_prompt(req: LintRequest):
    """
    Lint a prompt + config and return structured errors and warnings.

    Called live (debounced) from the Agent Builder UI as the PM types.
    Static checks only — no LLM cost — so it's fast enough for live feedback.
    """
    from ci.prompt_linter import PromptLinter
    linter = PromptLinter()
    errors = linter.lint(req.prompt, req.config, run_llm_checks=False)

    issues = [
        LintIssue(severity=e.severity, rule=e.rule, message=e.message, line=e.line)
        for e in errors
    ]
    return LintResponse(
        passed=all(i.severity != "error" for i in issues),
        errors=[i for i in issues if i.severity == "error"],
        warnings=[i for i in issues if i.severity == "warning"],
    )


@router.post("/test")
def test_agent(req: TestAgentRequest):
    """
    Test a configurable agent config with a sample message.

    Lets domain experts preview how their prompt performs before saving.
    The config does NOT need to be saved first — it's tested from the form data.
    """
    import os
    from agent.configurable_agent import AgentConfig as CoreAgentConfig, ConfigurableAgent
    from tools.support_tools import clear_state

    if not os.environ.get("OPENAI_API_KEY"):
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not configured on server")

    clear_state()
    try:
        core_config = CoreAgentConfig(
            intent=req.config.intent,
            user_type=req.config.user_type,
            description=req.config.description,
            prompt=req.config.prompt,
            tools=req.config.tools,
        )
        agent = ConfigurableAgent(core_config)
        result = agent.invoke(req.message)
        return TestAgentResponse(
            tool_calls=[ToolCallInfo(name=tc["name"], args=tc["args"]) for tc in result["tool_calls"]],
            final_response=result["final_response"],
        )
    except Exception as e:
        return TestAgentResponse(tool_calls=[], final_response="", error=str(e))
