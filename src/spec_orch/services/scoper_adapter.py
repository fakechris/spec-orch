"""LiteLLM-backed ScoperAdapter — breaks a Mission into a wave-based DAG."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import time
import uuid
from typing import Any

from spec_orch.domain.models import (
    ExecutionPlan,
    Mission,
    PlanStatus,
    Wave,
    WorkPacket,
)
from spec_orch.services.litellm_profile import ResolvedLiteLLMProfile

_SCOPER_SYSTEM_PROMPT = """\
You are a technical scoper for SpecOrch.
Given a mission spec, break it into an execution plan with sequential waves.

Rules:
- Wave 0 is always "Contract Freeze / Scaffold" (interfaces, types, base tests).
- Later waves contain parallelizable work packets.
- The last wave is always "Integration / QA".
- Each work packet is an atomic task for a single coding agent.

Respond with JSON:
{
  "waves": [
    {
      "wave_number": 0,
      "description": "...",
      "work_packets": [
        {
          "packet_id": "unique-id",
          "title": "...",
          "spec_section": "section reference from the spec",
          "run_class": "feature|bug|refactor|spike|qa",
          "files_in_scope": ["path/to/file.py"],
          "files_out_of_scope": [],
          "depends_on": [],
          "acceptance_criteria": ["..."],
          "builder_prompt": "concise implementation instruction"
        }
      ]
    }
  ]
}
Do NOT include anything outside this JSON object.\
"""


class LiteLLMScoperAdapter:
    """Breaks a Mission spec into wave-based work packets using an LLM."""

    ADAPTER_NAME: str = "litellm_scoper"

    VALID_API_TYPES = ("anthropic", "openai")

    def __init__(
        self,
        *,
        model: str = "claude-sonnet-4-20250514",
        api_type: str = "anthropic",
        api_key: str | None = None,
        api_base: str | None = None,
        temperature: float = 0.3,
        max_retries: int = 2,
        retry_backoff_seconds: float = 1.0,
        model_chain: list[ResolvedLiteLLMProfile] | None = None,
        token_command: str | None = None,
        evidence_context: str | None = None,
        scoper_hints: str | None = None,
    ) -> None:
        if api_type not in self.VALID_API_TYPES:
            raise ValueError(f"api_type must be one of {self.VALID_API_TYPES}, got {api_type!r}")
        self.api_type = api_type
        self.model_chain = list(model_chain or [])
        if self.model_chain:
            primary = self.model_chain[0]
            self.model = primary.model
            self._static_api_key = primary.api_key or os.environ.get("SPEC_ORCH_LLM_API_KEY")
            self.api_base = primary.api_base or os.environ.get("SPEC_ORCH_LLM_API_BASE")
        else:
            if "/" in model:
                self.model = model
            else:
                self.model = f"{api_type}/{model}"
            self._static_api_key = api_key or os.environ.get("SPEC_ORCH_LLM_API_KEY")
            self.api_base = api_base or os.environ.get("SPEC_ORCH_LLM_API_BASE")
        self.temperature = temperature
        self.max_retries = max(0, max_retries)
        self.retry_backoff_seconds = max(0.0, retry_backoff_seconds)
        self._token_command = token_command
        self._evidence_context = evidence_context
        self._scoper_hints = scoper_hints

    @property
    def api_key(self) -> str | None:
        if self._token_command:
            return subprocess.check_output(
                shlex.split(self._token_command),
                text=True,
            ).strip()
        return self._static_api_key

    def scope(
        self,
        *,
        mission: Mission,
        codebase_context: dict[str, Any],
        context: Any | None = None,
    ) -> ExecutionPlan:
        try:
            import litellm
        except ImportError as exc:
            raise ImportError("litellm is required for LiteLLMScoperAdapter.") from exc

        spec_content = codebase_context.get("spec_content", "")
        file_tree = codebase_context.get("file_tree", "")

        user_msg = (
            f"## Mission: {mission.title}\n\n"
            f"### Spec\n```markdown\n{spec_content}\n```\n\n"
            f"### Acceptance Criteria\n"
            + "\n".join(f"- {c}" for c in mission.acceptance_criteria)
            + "\n\n### Constraints\n"
            + "\n".join(f"- {c}" for c in mission.constraints)
            + f"\n\n### Codebase Structure\n```\n{file_tree}\n```"
        )

        if context is not None:
            ctx_parts: list[str] = []
            learning = getattr(context, "learning", None)
            execution = getattr(context, "execution", None)
            if learning:
                hints = getattr(learning, "scoper_hints", [])
                if hints:
                    hint_lines = "\n".join(
                        f"- {h.get('hint', h) if isinstance(h, dict) else h}" for h in hints
                    )
                    ctx_parts.append(f"### Learned Planning Hints\n{hint_lines}")
                samples = getattr(learning, "similar_failure_samples", [])
                if samples:
                    lines = [
                        f"- {s.get('key', '?')}: {s.get('content', '')[:200]}" for s in samples[:3]
                    ]
                    ctx_parts.append("### Recent Failure Samples\n" + "\n".join(lines))
            if execution:
                vr = getattr(execution, "verification_results", None)
                if vr:
                    status = []
                    all_results = dict(getattr(vr, "step_results", {}))
                    if not all_results:
                        for k in ("lint", "typecheck", "test", "build"):
                            v = getattr(vr, f"{k}_passed", None)
                            if v is not None:
                                all_results[k] = v
                    for k, v in all_results.items():
                        status.append(f"- {k}: {'PASS' if v else 'FAIL'}")
                    if status:
                        ctx_parts.append("### Verification (previous run)\n" + "\n".join(status))
            if ctx_parts:
                user_msg += "\n\n## Orchestration Context\n\n" + "\n\n".join(ctx_parts)

        system_prompt = _SCOPER_SYSTEM_PROMPT
        if self._evidence_context:
            system_prompt += (
                "\n\nUse the following historical evidence to inform "
                "your decomposition decisions (e.g. isolate files that "
                "frequently cause deviations, allocate extra waves for "
                "areas with high failure rates):\n\n" + self._evidence_context
            )
        if self._scoper_hints:
            system_prompt += (
                "\n\nFollow these learned planning hints from historical "
                "analysis:\n\n" + self._scoper_hints
            )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ]
        profiles = self.model_chain or [self._default_profile()]
        last_exc: Exception | None = None
        for profile in profiles:
            if not profile.is_usable:
                continue
            kwargs: dict[str, Any] = {
                "model": profile.model,
                "messages": messages,
                "temperature": self.temperature,
            }
            if profile.api_key:
                kwargs["api_key"] = profile.api_key
            if profile.api_base:
                kwargs["api_base"] = profile.api_base

            attempt = 0
            while True:
                try:
                    response = litellm.completion(**kwargs)
                    return self._parse_response(response, mission)
                except Exception as exc:
                    last_exc = exc
                    if attempt < self.max_retries and _is_transient_litellm_error(exc):
                        attempt += 1
                        if self.retry_backoff_seconds > 0:
                            time.sleep(self.retry_backoff_seconds * attempt)
                        continue
                    if not _is_transient_litellm_error(exc):
                        raise
                    break
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("No scoper model profile configured")

    def _parse_response(
        self,
        response: Any,
        mission: Mission,
    ) -> ExecutionPlan:
        content = response.choices[0].message.content or ""

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            import re

            match = re.search(r"\{.*\}", content, re.DOTALL)
            parsed = json.loads(match.group()) if match else {"waves": []}

        waves: list[Wave] = []
        for w in parsed.get("waves", []):
            packets = []
            for p in w.get("work_packets", []):
                packets.append(
                    WorkPacket(
                        packet_id=p.get(
                            "packet_id",
                            f"wp-{uuid.uuid4().hex[:8]}",
                        ),
                        title=p.get("title", "Untitled"),
                        spec_section=p.get("spec_section", ""),
                        run_class=p.get("run_class", "feature"),
                        files_in_scope=p.get("files_in_scope", []),
                        files_out_of_scope=p.get("files_out_of_scope", []),
                        depends_on=p.get("depends_on", []),
                        acceptance_criteria=p.get("acceptance_criteria", []),
                        builder_prompt=p.get("builder_prompt", ""),
                    )
                )
            waves.append(
                Wave(
                    wave_number=w.get("wave_number", len(waves)),
                    description=w.get("description", ""),
                    work_packets=packets,
                )
            )

        return ExecutionPlan(
            plan_id=f"plan-{uuid.uuid4().hex[:8]}",
            mission_id=mission.mission_id,
            waves=waves,
            status=PlanStatus.DRAFT,
        )

    def _default_profile(self) -> ResolvedLiteLLMProfile:
        return ResolvedLiteLLMProfile(
            model=self.model,
            api_type=self.api_type,
            api_key=self.api_key or "",
            api_base=self.api_base or "",
            api_key_env="",
            api_base_env="",
            slot="primary",
        )


def _is_transient_litellm_error(exc: Exception) -> bool:
    if isinstance(exc, TimeoutError):
        return True
    message = str(exc).lower()
    transient_markers = (
        "overloaded_error",
        "rate limit",
        "rate_limit",
        "429",
        "529",
        "temporarily unavailable",
        "service unavailable",
        "server overloaded",
        "try again later",
    )
    fatal_markers = (
        "invalid x-api-key",
        "authentication_error",
        "unauthorized",
        "forbidden",
        "invalid api key",
        "missing_api_base",
    )
    if any(marker in message for marker in fatal_markers):
        return False
    return any(marker in message for marker in transient_markers)
