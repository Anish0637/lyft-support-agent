"""
LangSmith evaluation pipeline for the Lyft multi-agent support system.

Process (from the Lyft blog post):
  1. Small production rollout (5-10%) — agent serves real traffic at low volume
  2. Sample production traces — capture real conversations as evaluation datasets
  3. Run LLM-as-judge evaluators — baseline + domain-specific metrics
  4. Monitor with dashboards — error rate, latency, token usage, quality scores

Usage:
    # Run local evaluation (no LangSmith required):
    from evaluation.pipeline import run_local_eval
    results = run_local_eval()

    # Run LangSmith experiment (requires LANGCHAIN_API_KEY):
    from evaluation.pipeline import run_langsmith_experiment
    run_langsmith_experiment()
"""
from __future__ import annotations

import os
from typing import Optional

from evaluation.metrics import run_all_evaluators
from evaluation.tasks import EVAL_TASKS


# ---------------------------------------------------------------------------
# Local evaluation (no LangSmith required)
# ---------------------------------------------------------------------------

def run_local_eval(model: str = "gpt-4o", tasks: Optional[list] = None) -> list[dict]:
    """
    Run all evaluation tasks locally and return per-task metric results.

    Useful for CI/CD checks before deploying a new prompt version.
    """
    from agent.meta_agent import run_support_agent
    from tools.support_tools import clear_state

    tasks = tasks or EVAL_TASKS
    results = []

    for task in tasks:
        clear_state()

        # Skip safety-block tasks in local eval (tested separately)
        if task.get("safety_should_block"):
            agent_result = run_support_agent(task["input"], user_type=task["user_type"])
            metrics = [{"key": "safety_block", "score": 1 if not agent_result["safety_passed"] else 0,
                        "value": "PASS" if not agent_result["safety_passed"] else "FAIL"}]
        else:
            agent_result = run_support_agent(task["input"], user_type=task["user_type"])
            metrics = run_all_evaluators(agent_result, task)

        task_result = {
            "task_id":      task["id"],
            "description":  task["description"],
            "intent":       agent_result.get("intent"),
            "agent_name":   agent_result.get("agent_name"),
            "tool_calls":   [tc["name"] for tc in agent_result.get("tool_calls", [])],
            "safety_passed": agent_result.get("safety_passed", True),
            "metrics":      metrics,
            "overall_pass": all(m["score"] == 1 for m in metrics),
        }
        results.append(task_result)

        # Print progress
        overall = "✓ PASS" if task_result["overall_pass"] else "✗ FAIL"
        print(f"[{task['id']}] {overall} — intent={task_result['intent']} tools={task_result['tool_calls']}")

    total = len(results)
    passed = sum(1 for r in results if r["overall_pass"])
    print(f"\nResults: {passed}/{total} tasks passed all metrics")
    return results


# ---------------------------------------------------------------------------
# LangSmith experiment runner
# ---------------------------------------------------------------------------

def run_langsmith_experiment(model: str = "gpt-4o") -> None:
    """
    Upload tasks to LangSmith and run a tracked experiment with LLM-as-judge.

    Requires: LANGCHAIN_API_KEY, LANGCHAIN_TRACING_V2=true
    """
    try:
        from langsmith import Client
        from langsmith.evaluation import evaluate
    except ImportError:
        print("langsmith not installed. Run: pip install langsmith")
        return

    from agent.meta_agent import run_support_agent
    from tools.support_tools import clear_state

    client = Client()
    dataset_name = "lyft-support-agent-eval"

    # Create dataset if it doesn't exist
    existing = list(client.list_datasets(dataset_name=dataset_name))
    if not existing:
        print(f"Creating LangSmith dataset: {dataset_name}")
        ds = client.create_dataset(dataset_name, description="Lyft multi-agent support evaluation tasks")
        client.create_examples(
            inputs=[{"message": t["input"], "user_type": t["user_type"]} for t in EVAL_TASKS],
            outputs=[{
                "expected_intent":  t.get("expected_intent"),
                "expected_tools":   t.get("expected_tools", []),
                "success_criteria": t["success_criteria"],
                "safety_should_block": t.get("safety_should_block", False),
            } for t in EVAL_TASKS],
            dataset_id=ds.id,
        )

    def target(inputs: dict) -> dict:
        clear_state()
        return run_support_agent(inputs["message"], user_type=inputs.get("user_type", "rider"), model=model)

    def tool_usage_evaluator(run, example):
        expected = example.outputs.get("expected_tools", [])
        actual = [tc["name"] for tc in (run.outputs or {}).get("tool_calls", [])]
        missing = [t for t in expected if t not in actual]
        return {
            "key": "tool_usage",
            "score": 1 if not missing else 0,
            "comment": f"missing={missing}",
        }

    def safety_evaluator(run, example):
        should_block = example.outputs.get("safety_should_block", False)
        was_blocked = not (run.outputs or {}).get("safety_passed", True)
        passed = (should_block == was_blocked)
        return {"key": "safety_gate", "score": 1 if passed else 0}

    results = evaluate(
        target,
        data=dataset_name,
        evaluators=[tool_usage_evaluator, safety_evaluator],
        experiment_prefix=f"lyft-support-{model}",
        num_repetitions=1,
    )
    print(f"\nLangSmith experiment: {results.experiment_name}")
    print(f"View at: https://smith.langchain.com")
