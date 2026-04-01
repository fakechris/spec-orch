from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import typer

from spec_orch.cli import app
from spec_orch.cli._helpers import (
    _build_planner_from_toml,
    _print_check_report,
    _print_preflight,
    _run_preflight,
)
from spec_orch.services.fixture_issue_source import FixtureIssueSource
from spec_orch.services.io import atomic_write_json
from spec_orch.services.litellm_profile import resolve_role_litellm_settings
from spec_orch.services.model_probe import probe_model_compliance

config_app = typer.Typer()
app.add_typer(config_app, name="config")


@app.command("preflight")
def preflight_cmd(
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
    try_llm: bool = typer.Option(
        False, "--try-llm", help="Send a test request to verify LLM connectivity."
    ),
) -> None:
    """Pre-launch health check: dependencies, config, env, and connectivity."""
    root = Path(repo_root).resolve()
    report = _run_preflight(root, try_llm=try_llm)
    report_path = root / ".spec_orch" / "preflight.json"

    if json_output:
        typer.echo(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        _print_preflight(report, report_path)

    if report["summary"]["fail"] > 0:
        raise typer.Exit(1)


@app.command("doctor")
def doctor_cmd(
    config: Path = typer.Option(
        "spec-orch.toml", "--config", "-c", help="Path to spec-orch.toml config file."
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
    fix_hints: bool = typer.Option(False, "--fix-hints", help="Show fix commands."),
) -> None:
    """Comprehensive health check (superset of config check)."""
    from spec_orch.services.doctor import Doctor

    doc = Doctor(config_path=config)
    health_path = doc.write_health_file()

    if json_output:
        import json as _json

        data = doc.to_json()
        typer.echo(_json.dumps(data, indent=2))
        summary = data.get("summary", {})
        if isinstance(summary, dict) and summary.get("fail", 0) > 0:
            raise typer.Exit(1)
        return

    checks = doc.run_all()
    counts = {"pass": 0, "warn": 0, "fail": 0}
    for check in checks:
        counts[check.status] += 1
        line = f"[{check.status.upper()}] {check.name}: {check.message}"
        typer.echo(line)
        if fix_hints and check.fix_hint:
            typer.echo(f"       fix: {check.fix_hint}")
    typer.echo(f"Doctor: {counts['pass']} pass, {counts['warn']} warn, {counts['fail']} fail")
    typer.echo(f"Health report: {health_path}")
    if counts["fail"] > 0:
        raise typer.Exit(1)


@app.command("selftest")
def selftest_cmd(
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Run end-to-end smoke test using a fixture issue (plan through gate)."""
    root = Path(repo_root).resolve()

    report = _run_preflight(root)
    if report["summary"]["fail"] > 0:
        typer.echo("Selftest aborted: preflight has failures. Run 'spec-orch preflight' first.")
        raise typer.Exit(1)

    fixture_dir = root / ".spec_orch_runs" / "__selftest__"
    fixture_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []

    def _step(name: str, fn: Any) -> bool:
        try:
            fn()
            results.append({"step": name, "status": "pass"})
            return True
        except Exception as exc:
            results.append({"step": name, "status": "fail", "error": str(exc)})
            return False

    fixture_src = FixtureIssueSource(repo_root=root)
    fixture_issue = None

    def load_fixture() -> None:
        nonlocal fixture_issue
        fixtures_dir = root / "fixtures" / "issues"
        if not fixtures_dir.is_dir():
            raise RuntimeError(f"No fixture issues found. Create {fixtures_dir} with JSON files.")
        json_files = sorted(fixtures_dir.glob("*.json"))
        if not json_files:
            raise RuntimeError(f"No fixture issues found in {fixtures_dir}.")
        issue_id = json_files[0].stem
        fixture_issue = fixture_src.load(issue_id)

    _step("load_fixture", load_fixture)

    if fixture_issue is not None:
        planner = _build_planner_from_toml(root)
        if planner is not None:

            def plan_step() -> None:
                planner.brainstorm(
                    conversation_history=[
                        {"role": "user", "content": f"Analyze: {fixture_issue.title}"}
                    ],
                    codebase_context="selftest",
                )

            _step("planner_call", plan_step)
        else:
            results.append(
                {"step": "planner_call", "status": "skip", "error": "planner not configured"}
            )

    from spec_orch.services.doctor import Doctor

    doc = Doctor(config_path=root / "spec-orch.toml")
    _step("doctor", lambda: doc.run_all())

    counts = {"pass": 0, "fail": 0, "skip": 0}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    selftest_report = {"steps": results, "summary": counts}
    report_dir = root / ".spec_orch"
    report_dir.mkdir(parents=True, exist_ok=True)
    selftest_path = report_dir / "selftest.json"
    atomic_write_json(selftest_path, selftest_report)

    if json_output:
        typer.echo(json.dumps(selftest_report, indent=2, ensure_ascii=False))
    else:
        for r in results:
            typer.echo(f"[{r['status'].upper()}] {r['step']}")
            if r.get("error"):
                typer.echo(f"       {r['error']}")
        typer.echo(
            f"\nSelftest: {counts['pass']} pass, {counts.get('fail', 0)} fail, "
            f"{counts.get('skip', 0)} skip"
        )
        typer.echo(f"Report: {selftest_path}")

    if counts.get("fail", 0) > 0:
        raise typer.Exit(1)


@app.command("model-probe")
def model_probe_cmd(
    model: str = typer.Option(..., "--model", help="Model identifier to probe."),
    transport: str = typer.Option(
        "litellm",
        "--transport",
        help="Probe transport. Supported: litellm, anthropic-http.",
    ),
    api_type: str = typer.Option(
        "anthropic",
        "--api-type",
        help="Provider type used for model normalization and env fallback lookup.",
    ),
    api_key: str | None = typer.Option(None, "--api-key", help="Explicit API key override."),
    api_base: str | None = typer.Option(None, "--api-base", help="Explicit API base override."),
    api_key_env: str | None = typer.Option(
        None,
        "--api-key-env",
        help="Environment variable name containing the API key.",
    ),
    api_base_env: str | None = typer.Option(
        None,
        "--api-base-env",
        help="Environment variable name containing the API base URL.",
    ),
    max_tokens: int = typer.Option(400, "--max-tokens", help="Max tokens per probe request."),
    timeout_seconds: float = typer.Option(
        30.0,
        "--timeout-seconds",
        help="Request timeout per probe case.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit raw JSON report."),
) -> None:
    """Probe a model for exact-text and structured-output compliance."""
    report = probe_model_compliance(
        model=model,
        transport=transport,
        api_type=api_type,
        api_key=api_key,
        api_base=api_base,
        api_key_env=api_key_env,
        api_base_env=api_base_env,
        max_tokens=max_tokens,
        timeout_seconds=timeout_seconds,
    )

    if json_output:
        typer.echo(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        typer.echo(
            f"Model probe: {report['model']} via {report['transport']} "
            f"({report['summary']['passed']}/{report['summary']['total']} passed)"
        )
        for result in report["results"]:
            status = "PASS" if result.get("ok") else "FAIL"
            typer.echo(f"[{status}] {result['name']}")
            if result.get("failure_reason"):
                typer.echo(f"       {result['failure_reason']}")

    if report["summary"]["failed"] > 0:
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# config commands
# ---------------------------------------------------------------------------


@config_app.command("check")
def config_check(
    config: Path = typer.Option(
        "spec-orch.toml", "--config", "-c", help="Path to spec-orch.toml config file."
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Validate spec-orch.toml and related external dependencies."""
    import shutil

    from spec_orch.services.config_checker import CheckResult, ConfigChecker

    checker = ConfigChecker()
    results: list[CheckResult] = checker.check_toml(config)

    try:
        raw = checker.load_toml(config)
    except (FileNotFoundError, ValueError, OSError):
        raw = {}
    except Exception:
        raw = {}

    linear = raw.get("linear", {}) if isinstance(raw, dict) else {}
    builder = raw.get("builder", {}) if isinstance(raw, dict) else {}
    planner = raw.get("planner", {}) if isinstance(raw, dict) else {}

    linear_token_env = linear.get("token_env") if isinstance(linear, dict) else None
    linear_token = os.environ.get(linear_token_env, "") if linear_token_env else ""
    linear_team_key = linear.get("team_key", "") if isinstance(linear, dict) else ""
    builder_adapter = (
        builder.get("adapter", "codex_exec") if isinstance(builder, dict) else "codex_exec"
    )
    codex_executable = (
        builder.get("executable") or builder.get("codex_executable", "codex")
        if isinstance(builder, dict)
        else "codex"
    )
    builder_agent = builder.get("agent") if isinstance(builder, dict) else None
    builder_model = builder.get("model") if isinstance(builder, dict) else None
    planner_settings = resolve_role_litellm_settings(
        raw if isinstance(raw, dict) else {},
        section_name="planner",
        default_model=str(planner.get("model", "")) if isinstance(planner, dict) else "",
        default_api_type=(
            str(planner.get("api_type", "anthropic")) if isinstance(planner, dict) else "anthropic"
        ),
    )
    planner_model = str(planner_settings.get("model") or "")
    planner_api_type = str(planner_settings.get("api_type") or "anthropic")
    planner_api_key_env = str(planner_settings.get("api_key_env") or "")

    reviewer = raw.get("reviewer", {}) if isinstance(raw, dict) else {}
    reviewer_adapter = reviewer.get("adapter", "local") if isinstance(reviewer, dict) else "local"
    valid_reviewers = {"local", "llm"}
    if reviewer_adapter not in valid_reviewers:
        results.append(
            CheckResult(
                name="reviewer", status="fail", message=f"Unknown adapter: {reviewer_adapter!r}"
            )
        )
    else:
        results.append(
            CheckResult(name="reviewer", status="pass", message=f"Adapter: {reviewer_adapter}")
        )

    results.extend(checker.check_linear(linear_token, linear_team_key))
    results.append(
        checker.check_builder(builder_adapter, codex_executable, builder_agent, builder_model)
    )
    results.extend(checker.check_planner(planner_model, planner_api_key_env, planner_api_type))

    verification = raw.get("verification", {}) if isinstance(raw, dict) else {}
    if isinstance(verification, dict):
        for step_name, cmd_list in verification.items():
            if not isinstance(cmd_list, list) or not cmd_list:
                results.append(
                    CheckResult(
                        name=f"verify:{step_name}",
                        status="warn",
                        message=f"Invalid command definition for {step_name}",
                    )
                )
                continue
            token = cmd_list[0]
            if not isinstance(token, str):
                results.append(
                    CheckResult(
                        name=f"verify:{step_name}",
                        status="warn",
                        message=f"Non-string executable: {token!r}",
                    )
                )
                continue
            exe = token.replace("{python}", sys.executable)
            found = shutil.which(exe)
            if found:
                results.append(
                    CheckResult(
                        name=f"verify:{step_name}",
                        status="pass",
                        message=f"Executable found: {found}",
                    )
                )
            else:
                results.append(
                    CheckResult(
                        name=f"verify:{step_name}",
                        status="fail",
                        message=f"Executable not found: {exe}",
                    )
                )

    if json_output:
        checks = [{"name": r.name, "status": r.status, "message": r.message} for r in results]
        counts = {"pass": 0, "warn": 0, "fail": 0}
        for r in results:
            counts[r.status] = counts.get(r.status, 0) + 1
        typer.echo(json.dumps({"checks": checks, "summary": counts}, indent=2))
    else:
        _print_check_report(results)

    if any(r.status == "fail" for r in results):
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# memory subcommands (extend memory_app from mission_commands)
# ---------------------------------------------------------------------------
from spec_orch.cli.mission_commands import memory_app  # noqa: E402


@memory_app.command("status")
def memory_status_cmd(
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Show memory system status and statistics."""
    from spec_orch.services.memory.service import get_memory_service, reset_memory_service
    from spec_orch.services.memory.types import MemoryLayer

    reset_memory_service()
    svc = get_memory_service(repo_root=repo_root.resolve())
    provider = svc.provider
    typer.echo(f"Provider: {type(provider).__name__}")

    qdrant_idx = getattr(provider, "_qdrant", None)
    typer.echo(f"Qdrant active: {qdrant_idx is not None}")

    for layer in MemoryLayer:
        keys = provider.list_keys(layer=layer.value, limit=1_000_000)
        typer.echo(f"  {layer.value}: {len(keys)} entries")

    if qdrant_idx is not None:
        typer.echo(f"  Qdrant indexed: {qdrant_idx.count()} points")


@memory_app.command("reindex")
def memory_reindex_cmd(
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Rebuild the Qdrant vector index from filesystem memory entries."""
    from spec_orch.services.memory.service import get_memory_service, reset_memory_service
    from spec_orch.services.memory.types import MemoryLayer

    reset_memory_service()
    svc = get_memory_service(repo_root=repo_root.resolve())
    provider = svc.provider

    qdrant_idx = getattr(provider, "_qdrant", None)
    if qdrant_idx is None:
        typer.echo("Error: Qdrant is not active. Configure [memory.qdrant] in spec-orch.toml.")
        raise typer.Exit(1)

    indexed_layers = {MemoryLayer.EPISODIC, MemoryLayer.SEMANTIC}
    entries: list[tuple[str, str, str, list[str], dict[str, Any]]] = []
    for layer in indexed_layers:
        for key in provider.list_keys(layer=layer.value, limit=1_000_000):
            entry = provider.get(key)
            if entry:
                entries.append(
                    (entry.key, entry.content, entry.layer.value, entry.tags, entry.metadata)
                )

    typer.echo(f"Reindexing {len(entries)} entries from {len(indexed_layers)} layers...")
    count = qdrant_idx.reindex(entries)
    typer.echo(f"Done. {count} entries indexed into Qdrant.")
