from __future__ import annotations

import inspect
import logging
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any, TypeVar, cast

from spec_orch.acceptance_core.calibration import (
    FixtureGraduationStage,
    append_fixture_graduation_event,
    build_fixture_graduation_event,
    load_fixture_graduation_events,
    qualifies_for_fixture_candidate,
    write_fixture_candidate_seed,
)
from spec_orch.acceptance_core.models import build_acceptance_judgments
from spec_orch.acceptance_runtime.graph_registry import graph_definition_for
from spec_orch.acceptance_runtime.runner import run_acceptance_graph
from spec_orch.domain.models import (
    AcceptanceCampaign,
    AcceptanceReviewResult,
    RoundArtifacts,
    RoundSummary,
)
from spec_orch.services.acceptance.browser_evidence import collect_playwright_browser_evidence
from spec_orch.services.io import atomic_write_json

logger = logging.getLogger(__name__)
T = TypeVar("T")


class AcceptancePipeline:
    """Owns acceptance evaluation flow for supervised mission rounds.

    Tranche 1 extraction keeps artifact/campaign construction in the host
    orchestrator, but moves the acceptance execution flow and side effects out
    of the main coordinator.
    """

    def __init__(
        self,
        *,
        repo_root: Path,
        acceptance_evaluator: Any | None,
        acceptance_filer: Any | None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.acceptance_evaluator = acceptance_evaluator
        self.acceptance_filer = acceptance_filer

    def run(
        self,
        *,
        host: Any,
        mission_id: str,
        round_id: int,
        round_dir: Path,
        worker_results: list[tuple[Any, Any]],
        artifacts: RoundArtifacts,
        summary: RoundSummary,
        chain_root: Path,
        chain_id: str,
        round_span_id: str,
    ) -> AcceptanceReviewResult | None:
        if self.acceptance_evaluator is None:
            return None
        acceptance_artifacts = host._build_acceptance_artifacts(
            mission_id=mission_id,
            round_id=round_id,
            artifacts=artifacts,
            summary=summary,
        )
        campaign = host._build_acceptance_campaign(
            mission_id=mission_id,
            artifacts=acceptance_artifacts,
        )
        routing_decision = host._build_acceptance_routing_decision(
            mission_id=mission_id,
            artifacts=acceptance_artifacts,
        )
        browser_evidence = self.collect_browser_evidence(
            host=host,
            mission_id=mission_id,
            round_id=round_id,
            round_dir=round_dir,
            campaign=campaign,
        )
        if browser_evidence is not None:
            acceptance_artifacts["browser_evidence"] = browser_evidence
        try:
            graph_trace = self.run_graph_trace(
                mission_id=mission_id,
                round_id=round_id,
                round_dir=round_dir,
                campaign=campaign,
                routing_decision=routing_decision,
                acceptance_artifacts=acceptance_artifacts,
                chain_root=chain_root,
                chain_id=chain_id,
                round_span_id=round_span_id,
            )
        except Exception as exc:
            logger.exception(
                "Acceptance graph trace failed for %s round %s",
                mission_id,
                round_id,
            )
            acceptance_artifacts["graph_trace_error"] = str(exc)
        else:
            if graph_trace:
                acceptance_artifacts.update(graph_trace)
        try:
            result = cast(
                AcceptanceReviewResult | None,
                self._call_runtime_chain_aware(
                    self.acceptance_evaluator.evaluate_acceptance,
                    mission_id=mission_id,
                    round_id=round_id,
                    round_dir=round_dir,
                    worker_results=worker_results,
                    artifacts=acceptance_artifacts,
                    repo_root=self.repo_root,
                    campaign=campaign,
                    chain_root=chain_root,
                    chain_id=chain_id,
                    span_id=f"{round_span_id}:acceptance-review",
                    parent_span_id=round_span_id,
                ),
            )
        except Exception:
            logger.exception("Acceptance evaluation failed for %s round %s", mission_id, round_id)
            return None
        if result is None:
            return None
        if self.acceptance_filer is not None:
            try:
                result = self.acceptance_filer.apply(
                    result,
                    mission_id=mission_id,
                    round_id=round_id,
                )
            except Exception as exc:
                result = self.mark_filing_failure(result, str(exc))
        atomic_write_json(round_dir / "acceptance_review.json", result.to_dict())
        judgments = build_acceptance_judgments(result)
        try:
            from spec_orch.services.memory.service import get_memory_service

            memory = get_memory_service(repo_root=self.repo_root)
            memory.record_acceptance_judgments(
                mission_id=mission_id,
                round_id=round_id,
                judgments=judgments,
            )
            self.record_fixture_candidate_graduations(
                mission_id=mission_id,
                source_record_id=f"acceptance:round-{round_id}",
                judgments=judgments,
                review=result,
                memory=memory,
            )
        except Exception:
            logger.warning(
                "Failed to record acceptance judgments to memory",
                extra={"mission_id": mission_id, "round_id": round_id},
                exc_info=True,
            )
        return result

    def run_graph_trace(
        self,
        *,
        mission_id: str,
        round_id: int,
        round_dir: Path,
        campaign: AcceptanceCampaign,
        routing_decision: Any,
        acceptance_artifacts: dict[str, Any],
        chain_root: Path,
        chain_id: str,
        round_span_id: str,
    ) -> dict[str, Any]:
        if self.acceptance_evaluator is None:
            return {}
        step_invoker = getattr(self.acceptance_evaluator, "invoke_acceptance_graph_step", None)
        if not callable(step_invoker):
            return {}
        try:
            from spec_orch.services.memory.service import get_memory_service

            memory = get_memory_service(repo_root=self.repo_root)
        except Exception:
            memory = None
        graph = graph_definition_for(routing_decision.graph_profile)
        observability_root = (
            self.repo_root
            / "docs"
            / "specs"
            / mission_id
            / "operator"
            / "observability"
            / f"round-{round_id:02d}-acceptance-graph"
        )
        trace = run_acceptance_graph(
            base_dir=round_dir,
            run_id=f"acceptance-{routing_decision.graph_profile.value}",
            graph=graph,
            mission_id=mission_id,
            round_id=round_id,
            goal=campaign.goal,
            target=f"mission:{mission_id}",
            evidence=acceptance_artifacts,
            compare_overlay=routing_decision.compare_overlay,
            invoke=lambda system_prompt, user_prompt: step_invoker(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            ),
            chain_root=chain_root,
            chain_id=chain_id,
            span_id=f"{round_span_id}:acceptance-graph",
            parent_span_id=round_span_id,
            observability_root=observability_root,
            memory_service=memory,
        )
        normalized: dict[str, Any] = {"graph_profile": trace["graph_profile"]}
        graph_run_path = Path(trace["graph_run"])
        if graph_run_path.is_absolute():
            try:
                normalized["graph_run"] = str(graph_run_path.relative_to(self.repo_root))
            except ValueError:
                normalized["graph_run"] = str(graph_run_path)
        else:
            normalized["graph_run"] = str(graph_run_path)

        step_artifacts: list[str] = []
        for item in trace.get("step_artifacts", []):
            path = Path(item)
            if path.is_absolute():
                try:
                    step_artifacts.append(str(path.relative_to(self.repo_root)))
                except ValueError:
                    step_artifacts.append(str(path))
            else:
                step_artifacts.append(str(path))
        normalized["step_artifacts"] = step_artifacts
        normalized["graph_transitions"] = [
            str(item) for item in trace.get("graph_transitions", []) if str(item).strip()
        ]
        normalized["final_transition"] = str(trace.get("final_transition", "") or "")
        return normalized

    def collect_browser_evidence(
        self,
        *,
        host: Any,
        mission_id: str,
        round_id: int,
        round_dir: Path,
        campaign: AcceptanceCampaign,
    ) -> dict[str, Any] | None:
        try:
            return collect_playwright_browser_evidence(
                mission_id=mission_id,
                round_id=round_id,
                round_dir=round_dir,
                paths=host._acceptance_browser_routes(campaign),
                interaction_plans=campaign.interaction_plans,
            )
        except Exception:
            logger.exception(
                "Acceptance browser evidence collection failed for %s round %s",
                mission_id,
                round_id,
            )
            return None

    @staticmethod
    def mark_filing_failure(
        result: AcceptanceReviewResult,
        error: str,
    ) -> AcceptanceReviewResult:
        if result.issue_proposals:
            proposals = [
                replace(proposal, filing_status="failed", filing_error=error)
                for proposal in result.issue_proposals
            ]
            return replace(result, issue_proposals=proposals)
        return replace(
            result,
            artifacts={**result.artifacts, "filing_error": error},
        )

    def record_fixture_candidate_graduations(
        self,
        *,
        mission_id: str,
        source_record_id: str,
        judgments: list[Any],
        review: AcceptanceReviewResult,
        memory: Any,
    ) -> None:
        reviewed_findings = memory.get_reviewed_acceptance_findings(top_k=200)
        existing_events = load_fixture_graduation_events(self.repo_root, mission_id)
        existing_markers = {
            str(
                event.get("dedupe_key") or event.get("finding_id") or event.get("judgment_id") or ""
            )
            for event in existing_events
            if isinstance(event, dict)
        }
        for judgment in judgments:
            candidate = getattr(judgment, "candidate", None)
            if candidate is None:
                continue
            repeat_count = self.fixture_candidate_repeat_count(
                judgment=judgment,
                reviewed_findings=reviewed_findings,
            )
            if not qualifies_for_fixture_candidate(judgment, repeat_count=repeat_count):
                continue
            marker = str(
                candidate.dedupe_key or candidate.finding_id or judgment.judgment_id or ""
            ).strip()
            if marker and marker in existing_markers:
                continue
            payload = build_fixture_graduation_event(
                mission_id=mission_id,
                judgment=judgment,
                stage=FixtureGraduationStage.FIXTURE_CANDIDATE,
                source_record_id=source_record_id,
                repeat_count=repeat_count,
                review_artifacts=review.artifacts if isinstance(review.artifacts, dict) else {},
            )
            append_fixture_graduation_event(
                self.repo_root,
                mission_id=mission_id,
                judgment_id=str(payload["judgment_id"]),
                finding_id=str(payload.get("finding_id") or ""),
                stage=FixtureGraduationStage.FIXTURE_CANDIDATE,
                summary=str(payload["summary"]),
                source_record_id=str(payload["source_record_id"]),
                evidence_refs=list(payload.get("evidence_refs", [])),
                repeat_count=int(payload.get("repeat_count", 0)),
                dedupe_key=str(payload.get("dedupe_key") or ""),
                baseline_ref=str(payload.get("baseline_ref") or ""),
                graph_profile=str(payload.get("graph_profile") or ""),
                graph_run=str(payload.get("graph_run") or ""),
                step_artifacts=list(payload.get("step_artifacts", [])),
                graph_transitions=list(payload.get("graph_transitions", [])),
                final_transition=str(payload.get("final_transition") or ""),
                workflow_tuning_notes=list(payload.get("workflow_tuning_notes", [])),
                route=str(payload.get("route") or ""),
                origin_step=str(payload.get("origin_step") or ""),
                promotion_test=str(payload.get("promotion_test") or ""),
            )
            write_fixture_candidate_seed(
                self.repo_root,
                mission_id=mission_id,
                event=payload,
                review_payload=review.to_dict(),
            )
            if marker:
                existing_markers.add(marker)

    @staticmethod
    def fixture_candidate_repeat_count(
        *,
        judgment: Any,
        reviewed_findings: list[dict[str, Any]],
    ) -> int:
        candidate = getattr(judgment, "candidate", None)
        if candidate is None:
            return 0
        dedupe_key = str(candidate.dedupe_key or "").strip()
        if dedupe_key:
            count = sum(1 for item in reviewed_findings if item.get("dedupe_key") == dedupe_key)
            if count > 1:
                return count
        route = str(candidate.route or "").strip()
        baseline_ref = str(candidate.baseline_ref or "").strip()
        if route or baseline_ref:
            count = 0
            for item in reviewed_findings:
                if route and item.get("route") != route:
                    continue
                if baseline_ref and item.get("baseline_ref") != baseline_ref:
                    continue
                count += 1
            if count:
                return count
        return 1

    @staticmethod
    def _call_runtime_chain_aware(func: Callable[..., T], /, **kwargs: Any) -> T:
        signature = inspect.signature(func)
        supported_kwargs = {
            name: value for name, value in kwargs.items() if name in signature.parameters
        }
        return func(**supported_kwargs)
