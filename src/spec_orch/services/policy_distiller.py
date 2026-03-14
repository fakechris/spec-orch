"""Policy Distiller — convert recurring simple tasks into deterministic code.

For well-understood, repetitive tasks (e.g., "fix lint errors", "update
documentation") this module generates deterministic Python workflows that
execute without calling an LLM, reducing cost to near zero.

This mirrors the AutoHarness paper's finding that pure code policies can
outperform even the best LLMs on well-understood tasks.
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from spec_orch.services.evidence_analyzer import EvidenceAnalyzer

logger = logging.getLogger(__name__)

_POLICIES_DIR = "policies"
_POLICIES_INDEX = "policies_index.json"

_DISTILLER_SYSTEM_PROMPT = """\
You are a policy-distiller for an AI coding-agent orchestrator.

Given a recurring task pattern observed from historical runs, generate a
deterministic Python script that can handle the task without any LLM calls.

Requirements:
- The script must be self-contained and executable with `python script.py`.
- Use only standard library modules plus common tools (ruff, pytest, git).
- Include proper error handling and exit codes.
- The script should be idempotent when possible.
- Include a docstring describing what the policy does and when to apply it.

Respond with ONLY a JSON object:
{
  "policy_id": "kebab-case-id",
  "name": "Human-readable name",
  "description": "What this policy does",
  "trigger_patterns": ["regex patterns that identify when this policy applies"],
  "script": "the full Python script content",
  "estimated_savings": "brief description of cost/time savings"
}
"""


@dataclass
class Policy:
    """A distilled deterministic policy for a recurring task."""

    policy_id: str
    name: str
    description: str
    trigger_patterns: list[str] = field(default_factory=list)
    script_path: str = ""
    created_at: str = ""
    total_executions: int = 0
    successful_executions: int = 0
    is_active: bool = True
    estimated_savings: str = ""

    @property
    def success_rate(self) -> float:
        if self.total_executions == 0:
            return 0.0
        return self.successful_executions / self.total_executions


class PolicyDistiller:
    """Generate and manage deterministic code policies for recurring tasks."""

    def __init__(self, repo_root: Path, planner: Any | None = None) -> None:
        self._repo_root = repo_root
        self._planner = planner
        self._policies_dir = repo_root / _POLICIES_DIR
        self._index_path = repo_root / _POLICIES_INDEX

    def load_policies(self) -> list[Policy]:
        """Load the policy index from disk."""
        if not self._index_path.exists():
            return []

        try:
            data = json.loads(self._index_path.read_text())
        except (json.JSONDecodeError, OSError):
            logger.warning("Could not read policy index at %s", self._index_path)
            return []

        if not isinstance(data, list):
            return []

        policies: list[Policy] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            try:
                policies.append(
                    Policy(
                        policy_id=item["policy_id"],
                        name=item["name"],
                        description=item.get("description", ""),
                        trigger_patterns=item.get("trigger_patterns", []),
                        script_path=item.get("script_path", ""),
                        created_at=item.get("created_at", ""),
                        total_executions=item.get("total_executions", 0),
                        successful_executions=item.get("successful_executions", 0),
                        is_active=item.get("is_active", True),
                        estimated_savings=item.get("estimated_savings", ""),
                    )
                )
            except (KeyError, TypeError):
                logger.warning("Skipping malformed policy: %s", item)
        return policies

    def save_policies(self, policies: list[Policy]) -> None:
        """Persist the policy index to disk."""
        data = [asdict(p) for p in policies]
        self._index_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")

    def identify_candidates(self, min_occurrences: int = 3) -> list[dict[str, Any]]:
        """Identify recurring task patterns from historical data.

        Returns a list of pattern dicts with task descriptions and counts.
        """
        analyzer = EvidenceAnalyzer(self._repo_root)
        run_dirs = analyzer._collect_run_dirs()

        if not run_dirs:
            return []

        task_counts: dict[str, int] = {}
        task_examples: dict[str, list[str]] = {}

        for rd in run_dirs:
            report = analyzer._read_report(rd)
            if report is None:
                continue

            succeeded = report.get("mergeable", report.get("succeeded", False))
            if not succeeded:
                continue

            failed = report.get("failed_conditions", [])
            verification = report.get("verification", {})

            for check_name, check_data in verification.items():
                if not isinstance(check_data, dict):
                    continue
                if check_data.get("exit_code", 1) != 0:
                    continue
                cmd = check_data.get("command", "")
                if cmd:
                    pattern = f"fix-{check_name}"
                    task_counts[pattern] = task_counts.get(pattern, 0) + 1
                    task_examples.setdefault(pattern, []).append(cmd)

            if not failed:
                run_id = rd.name
                task_counts[run_id] = task_counts.get(run_id, 0) + 1

        candidates = []
        for pattern, count in task_counts.items():
            if count >= min_occurrences:
                candidates.append(
                    {
                        "pattern": pattern,
                        "occurrences": count,
                        "examples": task_examples.get(pattern, [])[:3],
                    }
                )

        candidates.sort(key=lambda x: x["occurrences"], reverse=True)
        return candidates

    def distill(self, task_description: str | None = None) -> Policy | None:
        """Use an LLM to generate a deterministic policy for a recurring task.

        If ``task_description`` is ``None``, the distiller picks the most
        common candidate from ``identify_candidates()``.
        """
        if self._planner is None:
            return None

        if task_description is None:
            candidates = self.identify_candidates(min_occurrences=2)
            if not candidates:
                return None
            task_description = (
                f"Pattern: {candidates[0]['pattern']} "
                f"(observed {candidates[0]['occurrences']} times). "
                f"Example commands: {candidates[0].get('examples', [])}"
            )

        user_msg = (
            "Task to distill into a deterministic policy:\n\n"
            f"{task_description}\n\n"
            "Generate a self-contained Python script for this task."
        )

        try:
            response = self._planner.brainstorm(
                conversation_history=[
                    {"role": "system", "content": _DISTILLER_SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                codebase_context="",
            )
        except Exception:
            logger.exception("LLM call failed during policy distillation")
            return None

        return self._parse_response(response)

    def _parse_response(self, response: Any) -> Policy | None:
        if not isinstance(response, str):
            logger.warning("Non-string LLM response: %s", type(response).__name__)
            return None

        text = response.strip()
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            logger.warning("Could not find JSON object in distiller response")
            return None

        try:
            obj = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            logger.warning("Failed to parse JSON from distiller response")
            return None

        if not isinstance(obj, dict) or "script" not in obj:
            return None

        policy_id = obj.get("policy_id", "unnamed-policy")
        self._policies_dir.mkdir(parents=True, exist_ok=True)
        script_path = self._policies_dir / f"{policy_id}.py"
        script_path.write_text(obj["script"])

        now = datetime.now(UTC).isoformat()
        policy = Policy(
            policy_id=policy_id,
            name=obj.get("name", policy_id),
            description=obj.get("description", ""),
            trigger_patterns=obj.get("trigger_patterns", []),
            script_path=str(script_path.relative_to(self._repo_root)),
            created_at=now,
            estimated_savings=obj.get("estimated_savings", ""),
        )

        policies = self.load_policies()
        existing_ids = {p.policy_id for p in policies}
        if policy_id in existing_ids:
            logger.info("Policy %s already exists, updating script", policy_id)
            for p in policies:
                if p.policy_id == policy_id:
                    p.script_path = str(script_path.relative_to(self._repo_root))
                    p.description = policy.description
                    break
        else:
            policies.append(policy)

        self.save_policies(policies)
        return policy

    def execute(self, policy_id: str, workspace: Path | None = None) -> dict[str, Any]:
        """Execute a policy script in the given workspace.

        Returns a result dict with ``succeeded``, ``exit_code``, ``stdout``,
        ``stderr`` keys.
        """
        policies = self.load_policies()
        target = None
        for p in policies:
            if p.policy_id == policy_id:
                target = p
                break

        if target is None:
            return {"succeeded": False, "error": f"Policy {policy_id} not found"}

        if not target.is_active:
            return {"succeeded": False, "error": f"Policy {policy_id} is inactive"}

        script = self._repo_root / target.script_path
        if not script.exists():
            return {"succeeded": False, "error": f"Script not found: {target.script_path}"}

        cwd = workspace or self._repo_root
        try:
            result = subprocess.run(
                ["python3", str(script)],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=300,
            )
            succeeded = result.returncode == 0

            target.total_executions += 1
            if succeeded:
                target.successful_executions += 1
            self.save_policies(policies)

            return {
                "succeeded": succeeded,
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        except subprocess.TimeoutExpired:
            target.total_executions += 1
            self.save_policies(policies)
            return {"succeeded": False, "error": "Script timed out after 300s"}
        except OSError as exc:
            return {"succeeded": False, "error": str(exc)}

    def match_policy(self, task_text: str) -> Policy | None:
        """Find an active policy whose trigger patterns match the task text.

        Returns the first matching policy, or ``None``.
        """
        import re

        for policy in self.load_policies():
            if not policy.is_active:
                continue
            for pattern in policy.trigger_patterns:
                try:
                    if re.search(pattern, task_text, re.IGNORECASE):
                        return policy
                except re.error:
                    continue
        return None
