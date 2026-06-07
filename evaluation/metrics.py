"""
LLM-as-judge evaluation metrics for the Lyft multi-agent support system.

Baseline metrics applied to EVERY agent (from the Lyft blog post):
  1. task_completion   — did the agent successfully complete the request?
  2. hallucination     — did the agent make up facts not supported by tool results?
  3. tool_usage        — did the agent call the correct tools in the right order?
  4. policy_adherence  — did the agent follow the support policies?
  5. tone              — was the response professional and empathetic?

All evaluators return binary Pass/Fail (True/False) — not numeric scores.
Binary outputs are more actionable and consistent than 1-5 scores.
"""
from __future__ import annotations

import os
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI


# ---------------------------------------------------------------------------
# Shared judge LLM
# ---------------------------------------------------------------------------

def _get_judge_llm():
    return ChatOpenAI(
        model="gpt-4o",
        temperature=0,
        api_key=os.environ.get("OPENAI_API_KEY", ""),
    )


def _judge(prompt: str) -> bool:
    """Ask the LLM judge and return True (PASS) or False (FAIL)."""
    llm = _get_judge_llm()
    response = llm.invoke([
        SystemMessage(content="You are an objective evaluator. Respond with exactly PASS or FAIL."),
        HumanMessage(content=prompt),
    ]).content.strip().upper()
    return response.startswith("PASS")


# ---------------------------------------------------------------------------
# Metric 1: Task completion
# ---------------------------------------------------------------------------

def evaluate_task_completion(result: dict, task: dict) -> dict:
    """Did the agent successfully complete the stated task?"""
    prompt = f"""Evaluate whether the agent successfully completed the following support task.

Task description: {task['description']}
Success criteria: {task['success_criteria']}

Agent's final response:
{result.get('final_response', '')}

Tools used: {[tc['name'] for tc in result.get('tool_calls', [])]}

Did the agent successfully complete the task? Answer PASS or FAIL."""

    passed = _judge(prompt)
    return {
        "key": "task_completion",
        "score": 1 if passed else 0,
        "value": "PASS" if passed else "FAIL",
        "comment": f"Task: {task['description']}",
    }


# ---------------------------------------------------------------------------
# Metric 2: Hallucination detection
# ---------------------------------------------------------------------------

def evaluate_hallucination(result: dict, task: dict) -> dict:
    """Did the agent make up facts not supported by tool results?"""
    tool_calls_str = str(result.get("tool_calls", []))
    response = result.get("final_response", "")

    prompt = f"""Evaluate whether the agent's response contains hallucinated facts.

A hallucination is any specific factual claim in the response that was NOT returned
by a tool call (e.g. making up a refund amount, a trip date, or a driver name that
was never retrieved).

Tool calls made: {tool_calls_str}
Agent response: {response}

Does the response appear free of hallucinations? Answer PASS (no hallucinations) or FAIL (contains hallucinations)."""

    passed = _judge(prompt)
    return {
        "key": "hallucination",
        "score": 1 if passed else 0,
        "value": "PASS" if passed else "FAIL",
    }


# ---------------------------------------------------------------------------
# Metric 3: Tool usage correctness
# ---------------------------------------------------------------------------

def evaluate_tool_usage(result: dict, task: dict) -> dict:
    """Did the agent call the expected tools?"""
    expected = task.get("expected_tools", [])
    actual = [tc["name"] for tc in result.get("tool_calls", [])]

    missing = [t for t in expected if t not in actual]
    passed = len(missing) == 0

    return {
        "key": "tool_usage",
        "score": 1 if passed else 0,
        "value": "PASS" if passed else "FAIL",
        "comment": f"Expected: {expected}. Actual: {actual}. Missing: {missing}",
    }


# ---------------------------------------------------------------------------
# Metric 4: Policy adherence
# ---------------------------------------------------------------------------

def evaluate_policy_adherence(result: dict, task: dict) -> dict:
    """Did the agent follow Lyft's support policies?"""
    prompt = f"""Evaluate whether the Lyft support agent followed company policies.

Key policies:
- Never process a refund without first verifying the trip with get_trip_info
- Never give specific tax or legal advice
- Escalate safety incidents to human agents with priority="urgent"
- For damage claims > $500, mention photo evidence is required
- Always be professional and empathetic

Task: {task['description']}
Tools used: {[tc['name'] for tc in result.get('tool_calls', [])]}
Agent response: {result.get('final_response', '')}

Did the agent follow the policies? Answer PASS or FAIL."""

    passed = _judge(prompt)
    return {
        "key": "policy_adherence",
        "score": 1 if passed else 0,
        "value": "PASS" if passed else "FAIL",
    }


# ---------------------------------------------------------------------------
# Metric 5: Tone and empathy
# ---------------------------------------------------------------------------

def evaluate_tone(result: dict, task: dict) -> dict:
    """Was the response professional, empathetic, and appropriately concise?"""
    response = result.get("final_response", "")
    if not response:
        return {"key": "tone", "score": 0, "value": "FAIL", "comment": "Empty response"}

    prompt = f"""Evaluate the tone and professionalism of this customer support response.

The response should be:
- Empathetic and acknowledging of the customer's concern
- Professional (no informal slang, no defensive language)
- Concise (under ~200 words)
- Clear about what action was taken

Response to evaluate:
{response}

Is the tone appropriate? Answer PASS or FAIL."""

    passed = _judge(prompt)
    return {
        "key": "tone",
        "score": 1 if passed else 0,
        "value": "PASS" if passed else "FAIL",
    }


# ---------------------------------------------------------------------------
# All baseline evaluators
# ---------------------------------------------------------------------------

BASELINE_EVALUATORS = [
    evaluate_task_completion,
    evaluate_hallucination,
    evaluate_tool_usage,
    evaluate_policy_adherence,
    evaluate_tone,
]


def run_all_evaluators(result: dict, task: dict) -> list[dict]:
    """Run all baseline evaluators and return a list of metric results."""
    metrics = []
    for evaluator in BASELINE_EVALUATORS:
        try:
            metric = evaluator(result, task)
            metrics.append(metric)
        except Exception as e:
            metrics.append({
                "key": evaluator.__name__,
                "score": 0,
                "value": "ERROR",
                "comment": str(e),
            })
    return metrics
