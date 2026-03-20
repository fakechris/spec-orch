from __future__ import annotations

import json
from pathlib import Path

import typer

from spec_orch.cli import app
from spec_orch.cli._helpers import (
    _build_gate_input_from_report,
    _load_gate_policy,
)
from spec_orch.services.workspace_service import WorkspaceService

compliance_app = typer.Typer(help="Compliance evaluation commands.")
app.add_typer(compliance_app, name="compliance")

gate_app = typer.Typer(help="Gate evaluation commands.")
app.add_typer(gate_app, name="gate")


# ---------------------------------------------------------------------------
# compliance commands
# ---------------------------------------------------------------------------


@compliance_app.command("evaluate")
def compliance_evaluate(
    events_file: Path = typer.Argument(
        ...,
        help="Path to builder events JSONL or report.json.",
    ),
    contracts: Path = typer.Option(
        "compliance.contracts.yaml",
        "--contracts",
        "-c",
        help="Path to compliance contracts YAML.",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Write compliance_report.json to this path.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output as JSON.",
    ),
) -> None:
    """Evaluate builder events against compliance contracts."""
    from spec_orch.domain.models import BuilderEvent
    from spec_orch.services.compliance_engine import (
        ConfigurableComplianceEngine,
    )

    engine = ConfigurableComplianceEngine.from_yaml(contracts)

    events: list[BuilderEvent] = []
    if not events_file.exists():
        typer.echo(f"Warning: events file not found: {events_file}", err=True)
    else:
        skipped = 0
        for line in events_file.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
                kind = raw.get("kind") or raw.get("method") or raw.get("type", "")
                text = raw.get("text") or raw.get("excerpt") or ""
                if not text and "item" in raw:
                    text = str(raw["item"])
                events.append(
                    BuilderEvent(
                        timestamp=raw.get("timestamp", ""),
                        kind=kind,
                        text=text,
                    )
                )
            except json.JSONDecodeError:
                skipped += 1
                continue
        if skipped:
            typer.echo(
                f"Warning: {skipped} malformed line(s) skipped",
                err=True,
            )

    report = engine.evaluate(events)

    if output:
        report.save(output)
        typer.echo(f"Report saved to {output}")

    if json_output:
        typer.echo(json.dumps(report.to_dict(), indent=2))
    else:
        status = "COMPLIANT" if report.compliant else "NON-COMPLIANT"
        typer.echo(f"Status: {status}")
        typer.echo(f"Errors: {report.error_count}  Warnings: {report.warning_count}")
        for r in report.results:
            icon = "✅" if r.passed else ("❌" if r.severity == "error" else "⚠️")
            typer.echo(f"  {icon} [{r.severity}] {r.contract_name}")
            for v in r.violations[:3]:
                excerpt = v.get("excerpt", v.get("text", ""))[:80]
                typer.echo(f"     → {excerpt}")


@compliance_app.command("list-contracts")
def compliance_list_contracts(
    contracts: Path = typer.Option(
        "compliance.contracts.yaml",
        "--contracts",
        "-c",
        help="Path to compliance contracts YAML.",
    ),
) -> None:
    """List all configured compliance contracts."""
    from spec_orch.services.compliance_engine import load_contracts

    loaded = load_contracts(contracts)
    if not loaded:
        typer.echo("No contracts found.")
        return
    for c in loaded:
        typer.echo(f"  [{c.severity}] {c.id}: {c.name}")
        if c.description:
            typer.echo(f"    {c.description.strip()[:100]}")


# ---------------------------------------------------------------------------
# gate commands
# ---------------------------------------------------------------------------


@gate_app.command("evaluate")
def gate_evaluate(
    issue_id: str = typer.Argument(default="", help="Issue ID to evaluate gate for."),
    repo_root: Path = typer.Option(".", "--repo-root", "-r"),
    policy: Path = typer.Option(
        "gate.policy.yaml", "--policy", "-p", help="Path to gate.policy.yaml."
    ),
    profile: str = typer.Option(
        "", "--profile", help="Gate profile to apply (e.g. daemon, ci, strict)."
    ),
    report_file: Path | None = typer.Option(
        None, "--report", help="Path to report.json (overrides issue workspace)."
    ),
    output_json: bool = typer.Option(False, "--json", help="Output in JSON format."),
) -> None:
    """Evaluate the gate for an issue or report file."""
    from spec_orch.services.gate_service import GateService

    gate_policy = _load_gate_policy(policy, profile)
    svc = GateService(policy=gate_policy)

    if not issue_id and report_file is None:
        typer.echo("provide an issue_id or --report")
        raise typer.Exit(1)

    if report_file is not None:
        result_file = Path(report_file)
    else:
        ws = WorkspaceService(repo_root=Path(repo_root))
        workspace = ws.issue_workspace_path(issue_id)
        result_file = workspace / "report.json"

    if not result_file.exists():
        typer.echo(f"report not found: {result_file}")
        raise typer.Exit(1)

    data = json.loads(result_file.read_text())
    gate_input = _build_gate_input_from_report(data)
    verdict = svc.evaluate(gate_input)
    auto_merge = svc.should_auto_merge(gate_input)

    if output_json:
        typer.echo(
            json.dumps(
                {
                    "issue_id": issue_id or data.get("issue_id", ""),
                    "mergeable": verdict.mergeable,
                    "failed_conditions": verdict.failed_conditions,
                    "auto_merge": auto_merge,
                    "profile": profile or "default",
                },
                indent=2,
            )
        )
        return

    label = issue_id or result_file.parent.name
    typer.echo(f"{label}: mergeable={verdict.mergeable}")
    if verdict.failed_conditions:
        typer.echo(f"  blocked: {', '.join(verdict.failed_conditions)}")
    else:
        typer.echo("  all conditions passed")
    typer.echo(f"  auto_merge: {gate_policy.auto_merge} (would_trigger={auto_merge})")
    if profile:
        typer.echo(f"  profile: {profile}")


@gate_app.command("show-policy")
def gate_show_policy(
    policy: Path = typer.Option(
        "gate.policy.yaml", "--policy", "-p", help="Path to gate.policy.yaml."
    ),
    profile: str = typer.Option("", "--profile", help="Apply a profile before showing."),
    output_json: bool = typer.Option(False, "--json", help="Output in JSON format."),
) -> None:
    """Print the current gate policy."""
    from spec_orch.services.gate_service import GateService

    gate_policy = _load_gate_policy(policy, profile)
    svc = GateService(policy=gate_policy)

    if output_json:
        typer.echo(json.dumps(svc.describe_as_dict(), indent=2))
    else:
        typer.echo(svc.describe_policy())
        if profile:
            typer.echo(f"\n  (profile '{profile}' applied)")


@gate_app.command("list-conditions")
def gate_list_conditions(
    policy: Path = typer.Option(
        "gate.policy.yaml", "--policy", "-p", help="Path to gate.policy.yaml."
    ),
) -> None:
    """List all known gate conditions and their status."""
    from spec_orch.services.gate_service import ALL_KNOWN_CONDITIONS

    gate_policy = _load_gate_policy(policy, "")
    for cond in sorted(ALL_KNOWN_CONDITIONS):
        status = "required" if cond in gate_policy.required_conditions else "optional"
        typer.echo(f"  {cond:25s} [{status}]")


@gate_app.command("profiles")
def gate_list_profiles(
    policy: Path = typer.Option(
        "gate.policy.yaml", "--policy", "-p", help="Path to gate.policy.yaml."
    ),
) -> None:
    """List available gate profiles."""
    gate_policy = _load_gate_policy(policy, "")
    profiles = gate_policy.available_profiles()
    if not profiles:
        typer.echo("no profiles defined")
        return
    for pname in profiles:
        pcfg = gate_policy.profiles[pname]
        disables = pcfg.get("disable", [])
        enables = pcfg.get("enable", [])
        am = pcfg.get("auto_merge", "inherit")
        parts = []
        if disables:
            parts.append(f"disable=[{','.join(disables)}]")
        if enables:
            parts.append(f"enable=[{','.join(enables)}]")
        parts.append(f"auto_merge={am}")
        typer.echo(f"  {pname:15s} {' '.join(parts)}")
