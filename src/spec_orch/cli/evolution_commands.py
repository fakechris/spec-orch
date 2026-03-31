from __future__ import annotations

import contextlib
import json
from pathlib import Path
from typing import Any

import typer
import yaml

from spec_orch.cli import app
from spec_orch.cli._helpers import _build_planner_from_toml
from spec_orch.contract_core.contracts import (
    TaskContract,
    assess_risk_level,
    generate_contract_from_issue,
)
from spec_orch.services.fixture_issue_source import FixtureIssueSource

evidence_app = typer.Typer(help="Evidence analysis commands.")
app.add_typer(evidence_app, name="evidence")
harness_app = typer.Typer(help="Harness synthesis and rule management commands.")
app.add_typer(harness_app, name="harness")
prompt_app = typer.Typer(help="Prompt evolution and A/B testing commands.")
app.add_typer(prompt_app, name="prompt")
strategy_app = typer.Typer(help="Plan strategy evolution and scoper hints.")
app.add_typer(strategy_app, name="strategy")
policy_app = typer.Typer(help="Policy distiller — deterministic code policies.")
app.add_typer(policy_app, name="policy")
eval_app = typer.Typer(help="Harness eval — offline quality evaluation of historical runs.")
app.add_typer(eval_app, name="eval")
contract_app = typer.Typer(help="Task contract generation and management.")
app.add_typer(contract_app, name="contract")
evolution_app = typer.Typer(help="Evolution pipeline status and lifecycle management.")
app.add_typer(evolution_app, name="evolution")


# ---------------------------------------------------------------------------
# evidence commands
# ---------------------------------------------------------------------------


@evidence_app.command("summary")
def evidence_summary(
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Show aggregate pattern summary from historical run data."""
    from spec_orch.services.evidence_analyzer import EvidenceAnalyzer

    analyzer = EvidenceAnalyzer(repo_root)
    summary = analyzer.analyze()
    typer.echo(analyzer.format_summary(summary))


# ---------------------------------------------------------------------------
# harness commands
# ---------------------------------------------------------------------------


def _load_candidate_rules(input_file: Path) -> list[Any]:
    """Load CandidateRule objects from a YAML file."""
    from spec_orch.services.harness_synthesizer import CandidateRule

    raw = yaml.safe_load(input_file.read_text())
    if not isinstance(raw, dict) or not isinstance(raw.get("contracts"), list):
        typer.echo("No valid contracts list found in input file.", err=True)
        raise typer.Exit(1)

    candidates: list[CandidateRule] = []
    for c in raw["contracts"]:
        if not isinstance(c, dict) or "id" not in c or "name" not in c:
            typer.echo(f"Skipping malformed entry: {c!r}", err=True)
            continue
        candidates.append(
            CandidateRule(
                id=c["id"],
                name=c["name"],
                description=c.get("description", ""),
                severity=c.get("severity", "warning"),
                patterns=c.get("patterns", []),
                check_fields=c.get("check_fields", ["text"]),
            )
        )
    return candidates


@harness_app.command("synthesize")
def harness_synthesize(
    last_n: int = typer.Option(20, "--last-n", "-n", help="Number of recent runs to analyse."),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Write candidates YAML to file."
    ),
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Synthesize candidate compliance rules from recent failure patterns."""
    from spec_orch.services.harness_synthesizer import HarnessSynthesizer

    planner = _build_planner_from_toml(repo_root)

    synth = HarnessSynthesizer(repo_root, planner=planner)
    candidates = synth.synthesize(last_n=last_n)

    if not candidates:
        typer.echo("No candidate rules generated.")
        return

    yaml_str = synth.format_candidates_yaml(candidates)
    typer.echo(yaml_str)

    if output:
        output.write_text(yaml_str)
        typer.echo(f"Candidates written to {output}")


@harness_app.command("validate")
def harness_validate(
    input_file: Path = typer.Option(..., "--input", "-i", help="Path to candidates YAML file."),
    threshold: float = typer.Option(0.1, "--threshold", "-t", help="Max false positive rate."),
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Validate candidate rules from a YAML file against historical data."""
    from spec_orch.services.harness_synthesizer import RuleValidator

    candidates = _load_candidate_rules(input_file)
    validator = RuleValidator(repo_root)
    accepted, rejected = validator.validate(candidates, max_false_positive_rate=threshold)

    if accepted:
        typer.echo(f"Accepted ({len(accepted)}):")
        for r in accepted:
            typer.echo(f"  [{r.severity}] {r.id}: {r.name}")
    if rejected:
        typer.echo(f"Rejected ({len(rejected)}):")
        for r in rejected:
            typer.echo(f"  [{r.severity}] {r.id}: {r.name}")

    if not accepted and not rejected:
        typer.echo("No candidates to validate.")


@harness_app.command("apply")
def harness_apply(
    input_file: Path = typer.Option(..., "--input", "-i", help="Path to candidates YAML file."),
    contracts: Path = typer.Option(
        "compliance.contracts.yaml", "--contracts", "-c", help="Path to contracts YAML."
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview changes without modifying."),
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Apply validated rules to compliance.contracts.yaml."""
    from spec_orch.services.harness_synthesizer import RuleValidator

    candidates = _load_candidate_rules(input_file)

    validator = RuleValidator(repo_root)
    accepted, rejected = validator.validate(candidates)
    if rejected:
        typer.echo(f"Skipping {len(rejected)} invalid rule(s):", err=True)
        for r in rejected:
            typer.echo(f"  {r.id}: {r.name}", err=True)

    summary = validator.apply(accepted, contracts, dry_run=dry_run)
    typer.echo(summary)


# ---------------------------------------------------------------------------
# strategy commands
# ---------------------------------------------------------------------------


@strategy_app.command("status")
def strategy_status(
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Show current scoper hints."""
    from spec_orch.services.plan_strategy_evolver import PlanStrategyEvolver

    evolver = PlanStrategyEvolver(repo_root)
    hint_set = evolver.load_hints()

    if not hint_set.hints:
        typer.echo("No scoper hints found. Run 'spec-orch strategy analyze' to generate.")
        return

    if hint_set.analysis_summary:
        typer.echo(f"Summary: {hint_set.analysis_summary}")
    typer.echo(f"Hints ({len(hint_set.hints)}):")
    for h in hint_set.hints:
        active = " [active]" if h.is_active else " [inactive]"
        typer.echo(f"  {h.hint_id}{active} [{h.confidence}]: {h.text}")
        if h.evidence:
            typer.echo(f"    evidence: {h.evidence}")


@strategy_app.command("analyze")
def strategy_analyze(
    last_n: int = typer.Option(20, "--last-n", "-n", help="Number of recent runs to analyse."),
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Use LLM to analyze plan outcomes and generate scoper hints."""
    from spec_orch.services.plan_strategy_evolver import PlanStrategyEvolver

    planner = _build_planner_from_toml(repo_root)
    evolver = PlanStrategyEvolver(repo_root, planner=planner)
    result = evolver.analyze(last_n=last_n)

    if result is None:
        typer.echo("Could not generate hints. Check planner config and run data.")
        return

    typer.echo(f"Generated {len(result.hints)} hint(s):")
    for h in result.hints:
        typer.echo(f"  [{h.confidence}] {h.hint_id}: {h.text}")
    if result.analysis_summary:
        typer.echo(f"\nSummary: {result.analysis_summary}")


@strategy_app.command("inject-preview")
def strategy_inject_preview(
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Preview the text that would be injected into the scoper prompt."""
    from spec_orch.services.plan_strategy_evolver import PlanStrategyEvolver

    evolver = PlanStrategyEvolver(repo_root)
    text = evolver.format_hints_for_prompt()

    if not text:
        typer.echo("No active hints to inject.")
        return

    typer.echo(text)


# ---------------------------------------------------------------------------
# policy commands
# ---------------------------------------------------------------------------


@policy_app.command("list")
def policy_list(
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """List all registered policies."""
    from spec_orch.services.policy_distiller import PolicyDistiller

    distiller = PolicyDistiller(repo_root)
    policies = distiller.load_policies()

    if not policies:
        typer.echo("No policies found. Run 'spec-orch policy distill' to create one.")
        return

    for p in policies:
        active = " [active]" if p.is_active else " [inactive]"
        rate = f"{p.success_rate:.0%}" if p.total_executions > 0 else "n/a"
        typer.echo(f"  {p.policy_id}{active}: {p.name} ({p.total_executions} runs, {rate})")
        if p.description:
            typer.echo(f"    {p.description}")


@policy_app.command("candidates")
def policy_candidates(
    min_occurrences: int = typer.Option(3, "--min", "-m", help="Minimum occurrences."),
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Identify recurring task patterns that could become policies."""
    from spec_orch.services.policy_distiller import PolicyDistiller

    distiller = PolicyDistiller(repo_root)
    candidates = distiller.identify_candidates(min_occurrences=min_occurrences)

    if not candidates:
        typer.echo("No recurring patterns found.")
        return

    for c in candidates:
        typer.echo(f"  {c['pattern']}: {c['occurrences']} occurrences")
        if c.get("examples"):
            for ex in c["examples"]:
                typer.echo(f"    example: {ex}")


@policy_app.command("distill")
def policy_distill(
    task: str | None = typer.Option(None, "--task", "-t", help="Task description to distill."),
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Generate a deterministic policy for a recurring task."""
    from spec_orch.services.policy_distiller import PolicyDistiller

    planner = _build_planner_from_toml(repo_root)
    distiller = PolicyDistiller(repo_root, planner=planner)
    policy = distiller.distill(task_description=task)

    if policy is None:
        typer.echo("Could not generate a policy. Check planner config and task description.")
        return

    typer.echo(f"Created policy: {policy.policy_id}")
    typer.echo(f"  Name: {policy.name}")
    typer.echo(f"  Script: {policy.script_path}")
    if policy.estimated_savings:
        typer.echo(f"  Estimated savings: {policy.estimated_savings}")


@policy_app.command("run")
def policy_run(
    policy_id: str = typer.Option(..., "--policy", "-p", help="Policy ID to execute."),
    workspace: Path | None = typer.Option(None, "--workspace", "-w", help="Workspace directory."),
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Execute a policy script."""
    from spec_orch.services.policy_distiller import PolicyDistiller

    distiller = PolicyDistiller(repo_root)
    result = distiller.execute(policy_id, workspace=workspace)

    if result.get("succeeded"):
        typer.echo(f"Policy {policy_id} executed successfully.")
        if result.get("stdout"):
            typer.echo(result["stdout"])
    else:
        typer.echo(f"Policy {policy_id} failed: {result.get('error', 'unknown')}", err=True)
        if result.get("stderr"):
            typer.echo(result["stderr"], err=True)
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# prompt commands
# ---------------------------------------------------------------------------


@prompt_app.command("init")
def prompt_init(
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Initialize prompt history with the current builder prompt as v0."""
    from spec_orch.services.codex_exec_builder_adapter import PREAMBLE
    from spec_orch.services.prompt_evolver import PromptEvolver

    evolver = PromptEvolver(repo_root)
    v0 = evolver.initialize_from_current(PREAMBLE)
    typer.echo(f"Initialized prompt history with {v0.variant_id}")


@prompt_app.command("status")
def prompt_status(
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Show current prompt variant status and history."""
    from spec_orch.services.prompt_evolver import PromptEvolver

    evolver = PromptEvolver(repo_root)
    history = evolver.load_history()
    if not history:
        typer.echo("No prompt history found. Run 'spec-orch prompt init' first.")
        return

    for v in history:
        marker = " [ACTIVE]" if v.is_active else " [CANDIDATE]" if v.is_candidate else ""
        rate = f"{v.success_rate:.0%}" if v.total_runs > 0 else "n/a"
        typer.echo(f"  {v.variant_id}{marker}: {v.total_runs} runs, {rate} success")
        if v.rationale:
            typer.echo(f"    rationale: {v.rationale}")


@prompt_app.command("evolve")
def prompt_evolve(
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Use LLM to propose an improved builder prompt variant."""
    from spec_orch.services.prompt_evolver import PromptEvolver

    planner = _build_planner_from_toml(repo_root)
    evolver = PromptEvolver(repo_root, planner=planner)
    new_variant = evolver.evolve()

    if new_variant is None:
        typer.echo("Could not generate a new variant. Check planner config and prompt history.")
        return

    typer.echo(f"New candidate: {new_variant.variant_id}")
    typer.echo(f"Rationale: {new_variant.rationale}")
    if new_variant.target_improvements:
        typer.echo("Target improvements:")
        for imp in new_variant.target_improvements:
            typer.echo(f"  - {imp}")


@prompt_app.command("compare")
def prompt_compare(
    variant_a: str = typer.Option(..., "--a", help="First variant ID."),
    variant_b: str = typer.Option(..., "--b", help="Second variant ID."),
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Compare two prompt variants' performance."""
    from spec_orch.services.prompt_evolver import PromptEvolver

    evolver = PromptEvolver(repo_root)
    result = evolver.compare_variants(variant_a, variant_b)

    if result is None:
        typer.echo("Cannot compare: variants not found or insufficient run data.")
        return

    typer.echo(
        f"Winner: {result.winner_id} "
        f"({result.winner_success_rate:.0%} over {result.winner_runs} runs)"
    )
    typer.echo(
        f"Loser:  {result.loser_id} ({result.loser_success_rate:.0%} over {result.loser_runs} runs)"
    )
    typer.echo(f"Confidence: {result.confidence}")


@prompt_app.command("promote")
def prompt_promote(
    variant_id: str = typer.Option(..., "--variant", "-v", help="Variant ID to promote."),
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Promote a prompt variant to active."""
    from spec_orch.services.prompt_evolver import PromptEvolver

    evolver = PromptEvolver(repo_root)
    if evolver.promote_variant(variant_id):
        typer.echo(f"Promoted {variant_id} to active.")
    else:
        typer.echo(f"Variant {variant_id} not found.", err=True)
        raise typer.Exit(1)


@prompt_app.command("auto-promote")
def prompt_auto_promote(
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Auto-promote candidate if it outperforms the active variant."""
    from spec_orch.services.prompt_evolver import PromptEvolver

    evolver = PromptEvolver(repo_root)
    result = evolver.auto_promote_if_ready()

    if result is None:
        typer.echo("No candidate ready for comparison or no active variant.")
        return

    typer.echo(f"Winner: {result.winner_id} ({result.winner_success_rate:.0%})")
    typer.echo(f"Loser:  {result.loser_id} ({result.loser_success_rate:.0%})")
    active = evolver.get_active_prompt()
    if active:
        typer.echo(f"Active variant is now: {active.variant_id}")


# ---------------------------------------------------------------------------
# eval commands
# ---------------------------------------------------------------------------


@eval_app.command("run")
def eval_run(
    repo_root: Path = typer.Option(".", "--repo-root", "-r"),
    output: Path = typer.Option("eval_report.json", "--output", "-o", help="Output JSON path."),
    tag: list[str] = typer.Option(
        [], "--tag", "-t", help="Filter by tag=value (e.g. adapter=codex)."
    ),
    output_json: bool = typer.Option(False, "--json", help="Print JSON to stdout."),
) -> None:
    """Evaluate historical runs and produce a quality report."""
    from spec_orch.services.eval_runner import EvalRunner

    filter_tags: dict[str, str] = {}
    for t in tag:
        if "=" in t:
            k, v = t.split("=", 1)
            filter_tags[k.strip()] = v.strip()

    runner = EvalRunner(repo_root)
    report = runner.evaluate(filter_tags=filter_tags or None)
    runner.write_report(report, output)

    if output_json:
        typer.echo(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        typer.echo(
            f"Eval: {report.total} runs, {report.passed} passed, "
            f"{report.failed} failed — pass rate {report.pass_rate:.1%}"
        )
        if report.failure_breakdown:
            typer.echo("Failure breakdown:")
            for reason, count in sorted(report.failure_breakdown.items(), key=lambda x: -x[1]):
                typer.echo(f"  {reason}: {count}")
        if report.adapter_breakdown:
            typer.echo("Adapter breakdown:")
            for adapter, stats in sorted(report.adapter_breakdown.items()):
                total = stats.get("total", 0)
                ok = stats.get("passed", 0)
                rate = ok / total if total else 0
                typer.echo(f"  {adapter}: {ok}/{total} ({rate:.0%})")
        typer.echo(f"Report written to {output}")


@eval_app.command("compare")
def eval_compare(
    baseline: Path = typer.Argument(..., help="Baseline eval_report.json"),
    candidate: Path = typer.Argument(..., help="Candidate eval_report.json"),
) -> None:
    """Compare two eval reports (A/B or regression check)."""
    import json as _json

    def _load(p: Path) -> dict[str, Any]:
        data: dict[str, Any] = _json.loads(p.read_text(encoding="utf-8"))
        return data

    b = _load(baseline)
    c = _load(candidate)
    b_rate = b.get("pass_rate", 0)
    c_rate = c.get("pass_rate", 0)
    delta = c_rate - b_rate
    arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "=")

    typer.echo(f"Baseline:  {b.get('total', 0)} runs, pass rate {b_rate:.1%}")
    typer.echo(f"Candidate: {c.get('total', 0)} runs, pass rate {c_rate:.1%}")
    typer.echo(f"Delta:     {delta:+.1%} {arrow}")

    b_avr = b.get("avg_verification_rate", 0)
    c_avr = c.get("avg_verification_rate", 0)
    typer.echo(f"Avg verify: {b_avr:.1%} → {c_avr:.1%}")

    b_dev = b.get("avg_deviation_count", 0)
    c_dev = c.get("avg_deviation_count", 0)
    typer.echo(f"Avg deviations: {b_dev:.1f} → {c_dev:.1f}")

    eval_regression_threshold = -0.05
    if delta < eval_regression_threshold:
        typer.echo(f"⚠ Candidate regressed by more than {-eval_regression_threshold:.0%}")
        raise typer.Exit(1)


@eval_app.command("degradation")
def eval_degradation(
    repo_root: Path = typer.Option(".", "--repo-root", "-r"),
    recent: int = typer.Option(10, "--recent", help="Recent window size."),
    baseline: int = typer.Option(30, "--baseline", help="Baseline window size."),
    threshold: float = typer.Option(0.10, "--threshold", help="Regression threshold."),
    output: Path | None = typer.Option(None, "--output", "-o", help="Write JSON report."),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Detect quality degradation by comparing recent runs against baseline."""
    from spec_orch.services.degradation_detector import DegradationDetector

    detector = DegradationDetector(
        repo_root.resolve(),
        recent_window=recent,
        baseline_window=baseline,
        threshold=threshold,
    )
    report = detector.detect()

    if output:
        detector.write_report(report, output)

    if json_output:
        typer.echo(json.dumps(report.to_dict(), indent=2))
    elif not report.degraded:
        typer.echo(
            f"No degradation detected. "
            f"(baseline={report.baseline_runs} runs, recent={report.recent_runs} runs)"
        )
    else:
        typer.echo(f"⚠️  Degradation detected ({len(report.signals)} signal(s)):")
        for sig in report.signals:
            typer.echo(
                f"  - {sig.metric}: {sig.baseline_value:.3f} → {sig.recent_value:.3f} "
                f"(Δ={sig.delta:+.3f}, severity={sig.severity})"
            )

    if report.degraded:
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# contract commands
# ---------------------------------------------------------------------------


@contract_app.command("generate")
def contract_generate(
    issue_id: str = typer.Argument(help="Issue identifier (e.g. SPC-1)"),
    output: str = typer.Option("", help="Output file path (default: stdout)"),
    repo_root: str = typer.Option("", help="Repository root (default: cwd)"),
) -> None:
    """Generate a TaskContract from an issue definition."""
    root = Path(repo_root) if repo_root else Path.cwd()
    source = FixtureIssueSource(repo_root=root)
    issue = source.load(issue_id)
    contract = generate_contract_from_issue(issue)

    errors = contract.validate()
    if errors:
        for err in errors:
            typer.echo(f"  WARNING: {err}", err=True)

    data = contract.to_dict()
    content = yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)

    if output:
        Path(output).write_text(content)
        typer.echo(f"Contract written to {output}")
    else:
        typer.echo(content)


@contract_app.command("validate")
def contract_validate(
    path: str = typer.Argument(help="Path to contract YAML file"),
) -> None:
    """Validate a TaskContract YAML file."""
    data = yaml.safe_load(Path(path).read_text())
    contract = TaskContract.from_dict(data)
    errors = contract.validate()
    if errors:
        for err in errors:
            typer.echo(f"  ERROR: {err}", err=True)
        raise typer.Exit(1)
    typer.echo(f"Contract {contract.contract_id} is valid (risk: {contract.risk_level})")


@contract_app.command("assess-risk")
def contract_assess_risk(
    issue_id: str = typer.Argument(help="Issue identifier"),
    repo_root: str = typer.Option("", help="Repository root (default: cwd)"),
) -> None:
    """Assess the risk level of an issue for contract purposes."""
    root = Path(repo_root) if repo_root else Path.cwd()
    source = FixtureIssueSource(repo_root=root)
    issue = source.load(issue_id)
    risk = assess_risk_level(
        title=issue.title,
        summary=issue.summary,
        files_in_scope=list(issue.context.files_to_read),
        run_class=issue.run_class or "",
    )
    typer.echo(f"Issue {issue_id}: risk_level={risk}")


# ---------------------------------------------------------------------------
# evolution commands
# ---------------------------------------------------------------------------


@evolution_app.command("status")
def evolution_status(
    repo_root: Path = typer.Option(".", "--repo-root", "-r"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show evolution pipeline status: policy rules, recent activity, and proposals."""
    import tomllib as _tomllib

    from spec_orch.services.evolution_policy import EvolutionPolicy

    repo = repo_root.resolve()
    toml_path = repo / "spec-orch.toml"
    toml_data: dict[str, Any] = {}
    if toml_path.exists():
        with toml_path.open("rb") as f:
            toml_data = _tomllib.load(f)

    policy = EvolutionPolicy.from_toml(toml_data)

    log_path = repo / ".spec_orch_evolution" / "evolution_log.jsonl"
    recent_runs: list[dict[str, Any]] = []
    if log_path.exists():
        lines = log_path.read_text().strip().splitlines()
        for line in lines[-5:]:
            with contextlib.suppress(json.JSONDecodeError):
                recent_runs.append(json.loads(line))

    counter_path = repo / ".spec_orch_evolution" / "run_counter.json"
    current_count = 0
    if counter_path.exists():
        with contextlib.suppress(json.JSONDecodeError, OSError):
            current_count = json.loads(counter_path.read_text()).get("count", 0)

    status_data = {
        "global_min_runs": policy.global_min_runs,
        "current_run_count": current_count,
        "policy_rules": {
            name: {
                "enabled": rule.enabled,
                "min_runs": rule.min_runs,
                "trigger_on": rule.trigger_on,
                "threshold": rule.threshold,
            }
            for name, rule in policy.rules.items()
        },
        "recent_cycles": recent_runs,
    }

    if json_output:
        typer.echo(json.dumps(status_data, indent=2))
        return

    typer.echo(f"Evolution Pipeline Status (counter: {current_count}/{policy.global_min_runs})")
    typer.echo()

    if policy.rules:
        typer.echo("Policy Rules:")
        for name, rule in policy.rules.items():
            flag = "✅" if rule.enabled else "❌"
            typer.echo(
                f"  {flag} {name}: trigger_on={rule.trigger_on}, "
                f"min_runs={rule.min_runs}, threshold={rule.threshold}"
            )
    else:
        typer.echo("Policy Rules: (none configured, using defaults)")

    if recent_runs:
        typer.echo()
        typer.echo("Recent Cycles:")
        for entry in recent_runs:
            ts = entry.get("timestamp", "?")[:19]
            triggered = "triggered" if entry.get("triggered") else "skipped"
            errors = entry.get("errors", [])
            err_txt = f" ({len(errors)} error(s))" if errors else ""
            typer.echo(f"  [{ts}] {triggered}{err_txt}")
