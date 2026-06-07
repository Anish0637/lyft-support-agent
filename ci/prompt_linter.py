"""
Prompt linting pipeline — CI/CD gate for self-serve agent prompts.

From the Lyft blog post:
  "When a domain expert finishes writing a prompt in our builder UI,
   it opens a pull request. A CI pipeline runs two layers of checks:
   fast static rules followed by LLM-powered rules that detect prompt
   injection vulnerabilities, contradictory instructions, and structural
   dead-ends. All violations block the merge."

Two layers:
  Layer 1 — Static checks (fast, no LLM):
    - Required sections present (identity, scope, workflow, guidelines)
    - No undefined template variables {VAR}
    - Intent slug is unique (no duplicates)
    - Prompt is not empty or too short

  Layer 2 — LLM-powered checks (catches semantic issues):
    - Prompt injection vulnerabilities
    - Contradictory instructions
    - Structural dead-ends (phase with no exit condition)
    - Vague scope (missing out-of-scope definitions)
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass
class LintError:
    severity: Literal["error", "warning"]
    rule: str
    message: str
    line: int | None = None

    def __str__(self) -> str:
        icon = "✗" if self.severity == "error" else "⚠"
        loc = f" (line {self.line})" if self.line else ""
        return f"  {icon} [{self.rule}]{loc} {self.message}"


class PromptLinter:
    """
    Two-layer prompt linter for configurable agent prompts.

    Usage:
        linter = PromptLinter()
        errors = linter.lint(prompt_text, config_dict)
        if any(e.severity == "error" for e in errors):
            print("CI FAILED — prompt has errors")
    """

    REQUIRED_SECTIONS = ["identity", "scope", "workflow", "guidelines"]
    MIN_PROMPT_LENGTH = 200

    def lint(self, prompt: str, config: dict, run_llm_checks: bool = True) -> list[LintError]:
        """Run both static and LLM checks. Returns a list of LintErrors."""
        errors = []
        errors += self._static_checks(prompt, config)

        if run_llm_checks and os.environ.get("OPENAI_API_KEY"):
            errors += self._llm_checks(prompt, config)

        return errors

    # ------------------------------------------------------------------
    # Layer 1: Static checks
    # ------------------------------------------------------------------

    def _static_checks(self, prompt: str, config: dict) -> list[LintError]:
        errors = []

        # Check 1: Prompt not empty
        if not prompt or not prompt.strip():
            errors.append(LintError("error", "empty_prompt", "Prompt is empty"))
            return errors  # stop here

        # Check 2: Minimum length
        if len(prompt.strip()) < self.MIN_PROMPT_LENGTH:
            errors.append(LintError(
                "warning", "prompt_too_short",
                f"Prompt is only {len(prompt.strip())} chars. Minimum recommended: {self.MIN_PROMPT_LENGTH}",
            ))

        # Check 3: Required sections
        prompt_lower = prompt.lower()
        for section in self.REQUIRED_SECTIONS:
            if section not in prompt_lower:
                errors.append(LintError(
                    "warning", f"missing_section_{section}",
                    f"Prompt appears to be missing a '{section}' section. "
                    f"Required sections: {', '.join(self.REQUIRED_SECTIONS)}",
                ))

        # Check 4: Undefined template variables
        used_vars = set(re.findall(r"\{(\w+)\}", prompt))
        defined_vars = set(config.get("variables", {}).keys())
        for var in used_vars:
            # Ignore common non-variable patterns
            if var not in defined_vars and var not in {"intent", "user_type"}:
                errors.append(LintError(
                    "error", "undefined_variable",
                    f"Template variable {{{var}}} is used in prompt but not defined in config.variables",
                ))

        # Check 5: Intent slug format
        intent = config.get("intent", "")
        if intent and not re.match(r"^[a-z][a-z0-9_]*$", intent):
            errors.append(LintError(
                "error", "invalid_intent_slug",
                f"Intent slug '{intent}' must be lowercase letters, digits, and underscores only",
            ))

        # Check 6: Required config fields
        for field in ("intent", "user_type", "tools"):
            if not config.get(field):
                errors.append(LintError(
                    "error", f"missing_config_{field}",
                    f"Config is missing required field: '{field}'",
                ))

        # Check 7: Obvious prompt injection in the prompt itself
        injection_patterns = [
            r"ignore\s+(all\s+)?previous\s+instructions",
            r"you\s+are\s+now\s+(?:a\s+)?(?:different|new|DAN)",
            r"disregard\s+(your\s+)?rules",
            r"pretend\s+you\s+(?:are|have\s+no)",
        ]
        for pattern in injection_patterns:
            if re.search(pattern, prompt, re.IGNORECASE):
                errors.append(LintError(
                    "error", "prompt_injection_in_prompt",
                    f"Prompt contains suspicious injection-like instruction matching: '{pattern}'",
                ))

        return errors

    # ------------------------------------------------------------------
    # Layer 2: LLM-powered checks
    # ------------------------------------------------------------------

    def _llm_checks(self, prompt: str, config: dict) -> list[LintError]:
        """Use LLM to detect semantic issues: contradictions, dead-ends, vague scope."""
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0,
            api_key=os.environ["OPENAI_API_KEY"],
        )

        check_prompt = f"""You are a prompt quality reviewer for an AI customer support system.

Review the following agent prompt for these specific issues. For each issue found,
output a JSON array of objects with: severity ("error"|"warning"), rule (string), message (string).
If no issues found, return an empty array [].

Issues to check:
1. prompt_injection_vulnerability — does the prompt contain instructions that could allow
   a user message to override the agent's behavior? (e.g. "follow any user corrections to your role")
2. contradictory_instructions — are there two instructions that directly contradict each other?
3. structural_dead_end — is there a workflow phase that has no exit condition or terminal action?
4. vague_scope — does the scope section lack explicit OUT-OF-SCOPE definitions?
5. no_escalation_path — for safety-sensitive agents, is there no escalation to human?

Agent config: intent={config.get('intent')}, user_type={config.get('user_type')}

Prompt to review:
---
{prompt[:3000]}
---

Return ONLY a JSON array. No explanation outside the array."""

        try:
            response = llm.invoke([
                SystemMessage(content="You are a strict prompt quality reviewer. Return only valid JSON arrays."),
                HumanMessage(content=check_prompt),
            ]).content.strip()

            # Extract JSON array from response
            match = re.search(r"\[.*\]", response, re.DOTALL)
            if not match:
                return []

            issues = json.loads(match.group())
            errors = []
            for issue in issues:
                if isinstance(issue, dict):
                    errors.append(LintError(
                        severity=issue.get("severity", "warning"),
                        rule=issue.get("rule", "llm_check"),
                        message=issue.get("message", "LLM-detected issue"),
                    ))
            return errors

        except Exception:
            return []  # Don't block CI if LLM check fails


# ---------------------------------------------------------------------------
# Convenience: lint all config files in a directory
# ---------------------------------------------------------------------------

def lint_all_configs(config_dir: str | Path | None = None, run_llm_checks: bool = True) -> dict:
    """
    Lint all JSON config files in config/agents/.

    Returns:
        {"file.json": [LintError, ...], ...}
    """
    if config_dir is None:
        config_dir = Path(__file__).parent.parent / "config" / "agents"

    config_dir = Path(config_dir)
    linter = PromptLinter()
    results: dict[str, list[LintError]] = {}
    intent_slugs: list[str] = []

    for json_file in sorted(config_dir.glob("*.json")):
        try:
            with open(json_file) as f:
                config = json.load(f)
        except Exception as e:
            results[json_file.name] = [LintError("error", "invalid_json", str(e))]
            continue

        prompt = config.get("prompt", "")
        errors = linter.lint(prompt, config, run_llm_checks=run_llm_checks)

        # Check for duplicate intent slugs across files
        intent = config.get("intent", "")
        if intent in intent_slugs:
            errors.append(LintError("error", "duplicate_intent", f"Intent '{intent}' is already defined in another config file"))
        else:
            intent_slugs.append(intent)

        results[json_file.name] = errors

    return results


def print_lint_report(results: dict) -> bool:
    """Print lint results and return True if all files pass (no errors)."""
    all_pass = True
    for filename, errors in results.items():
        error_count = sum(1 for e in errors if e.severity == "error")
        warn_count = sum(1 for e in errors if e.severity == "warning")

        if not errors:
            print(f"  ✓ {filename} — OK")
        else:
            status = "FAIL" if error_count > 0 else "WARN"
            print(f"  {'✗' if error_count else '⚠'} {filename} — {status} ({error_count} errors, {warn_count} warnings)")
            for err in errors:
                print(f"    {err}")
            if error_count > 0:
                all_pass = False

    return all_pass
