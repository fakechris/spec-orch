from __future__ import annotations

import enum
import importlib.metadata
import json
import logging as _logging
import os
import shlex
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import IO, Any

import typer

# ---------------------------------------------------------------------------
# Version helpers
# ---------------------------------------------------------------------------


def _resolve_version() -> str:
    try:
        return importlib.metadata.version("spec-orch")
    except importlib.metadata.PackageNotFoundError:
        return "dev"


def _version_callback(value: bool) -> None:
    if not value:
        return
    typer.echo(_resolve_version())
    raise typer.Exit()


def _load_dotenv() -> None:
    """Load .env from repo root (or parents) if present."""
    candidate = Path.cwd()
    for _ in range(5):
        env_path = candidate / ".env"
        if env_path.is_file():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key, value = key.strip(), value.strip()
                if key and key not in os.environ:
                    os.environ[key] = value
            break
        parent = candidate.parent
        if parent == candidate:
            break
        candidate = parent


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ProfileLevel(enum.StrEnum):
    minimal = "minimal"
    standard = "standard"
    full = "full"


# ---------------------------------------------------------------------------
# Issue sort key
# ---------------------------------------------------------------------------
import re  # noqa: E402


def _issue_sort_key(issue_id: str) -> list[int | str]:
    return [
        int(part) if part.isdigit() else part.lower()
        for part in re.split(r"(\d+)", issue_id)
        if part
    ]


# ---------------------------------------------------------------------------
# Preflight helpers
# ---------------------------------------------------------------------------


def _run_preflight(
    root: Path,
    *,
    try_llm: bool = False,
) -> dict[str, Any]:
    """Run preflight checks and return the report dict (no I/O side effects)."""
    import importlib.util
    import shutil as _shutil

    checks: list[dict[str, Any]] = []

    def _add(name: str, status: str, message: str, fix: str | None = None) -> None:
        entry: dict[str, Any] = {"name": name, "status": status, "message": message}
        if fix:
            entry["fix"] = fix
        checks.append(entry)

    major, minor = sys.version_info[:2]
    if (major, minor) >= (3, 11):
        _add("python", "pass", f"Python {major}.{minor}")
    else:
        _add("python", "fail", f"Python {major}.{minor} < 3.11", "pyenv install 3.11")

    git = _shutil.which("git")
    _add("git", "pass" if git else "fail", git or "not found", None if git else "brew install git")

    core_deps = {"typer": "typer", "httpx": "httpx", "yaml": "pyyaml"}
    all_ok = all(importlib.util.find_spec(mod) for mod in core_deps)
    _add("core_deps", "pass" if all_ok else "fail", "typer, httpx, pyyaml")

    litellm_ok = importlib.util.find_spec("litellm") is not None
    _add(
        "planner_deps",
        "pass" if litellm_ok else "warn",
        "litellm" if litellm_ok else "litellm not installed",
        "pip install 'spec-orch[planner]'" if not litellm_ok else None,
    )

    dash_mods = {"fastapi": "fastapi", "uvicorn": "uvicorn", "websockets": "websockets"}
    dash_missing = [name for name, mod in dash_mods.items() if not importlib.util.find_spec(mod)]
    if dash_missing:
        _add(
            "dashboard_deps",
            "warn",
            f"missing: {', '.join(dash_missing)}",
            "pip install 'spec-orch[dashboard]'",
        )
    else:
        _add("dashboard_deps", "pass", "fastapi, uvicorn, websockets")

    env_path = root / ".env"
    _add(
        "dotenv",
        "pass" if env_path.exists() else "warn",
        str(env_path) if env_path.exists() else ".env not found",
        "cp .env.example .env && $EDITOR .env" if not env_path.exists() else None,
    )

    llm_key = os.environ.get("SPEC_ORCH_LLM_API_KEY", "")
    _add(
        "llm_api_key",
        "pass" if llm_key else "fail",
        "SPEC_ORCH_LLM_API_KEY is set" if llm_key else "SPEC_ORCH_LLM_API_KEY not set",
        "Edit .env and set SPEC_ORCH_LLM_API_KEY=your-key" if not llm_key else None,
    )

    config_path = root / "spec-orch.toml"
    if config_path.exists():
        try:
            with config_path.open("rb") as f:
                raw = tomllib.load(f)
            _add("config", "pass", f"spec-orch.toml loaded ({len(raw)} sections)")
            planner_cfg = raw.get("planner", {})
            planner_model = planner_cfg.get("model") if isinstance(planner_cfg, dict) else None
            if planner_model:
                _add("planner_model", "pass", f"model = {planner_model}")
            else:
                _add(
                    "planner_model",
                    "warn",
                    "[planner] model not configured",
                    "Run 'spec-orch init --reconfigure' or edit spec-orch.toml",
                )
        except Exception as exc:
            _add("config", "fail", f"Failed to parse: {exc}")
    else:
        _add("config", "fail", "spec-orch.toml not found", "spec-orch init")

    if try_llm and llm_key and litellm_ok:
        try:
            planner = _build_planner_from_toml(root)
            if planner is not None:
                planner.brainstorm(
                    conversation_history=[{"role": "user", "content": "Say OK"}],
                    codebase_context="",
                )
                _add("llm_connectivity", "pass", "LLM responded successfully")
            else:
                _add("llm_connectivity", "warn", "Planner not configured")
        except Exception as exc:
            _add("llm_connectivity", "fail", f"LLM request failed: {exc}")
    elif try_llm:
        _add("llm_connectivity", "warn", "Skipped (missing API key or litellm)")

    counts = {"pass": 0, "warn": 0, "fail": 0}
    for c in checks:
        counts[c["status"]] += 1

    ready: list[str] = []
    not_ready: list[str] = []
    if litellm_ok and llm_key:
        ready.extend(["run", "discuss", "plan"])
    else:
        not_ready.extend(["run", "discuss", "plan"])
    if not dash_missing:
        ready.append("dashboard")
    else:
        not_ready.append("dashboard")
    if os.environ.get("SPEC_ORCH_LINEAR_TOKEN"):
        ready.append("daemon")
    else:
        not_ready.append("daemon")

    report = {
        "checks": checks,
        "summary": counts,
        "ready": ready,
        "not_ready": not_ready,
    }

    report_dir = root / ".spec_orch"
    report_dir.mkdir(parents=True, exist_ok=True)
    from spec_orch.services.io import atomic_write_json

    atomic_write_json(report_dir / "preflight.json", report, ensure_ascii=False)

    return report


def _print_preflight(report: dict[str, Any], report_path: Path) -> None:
    """Print preflight report to stdout."""
    for c in report["checks"]:
        line = f"[{c['status'].upper()}] {c['name']}: {c['message']}"
        typer.echo(line)
        if c.get("fix"):
            typer.echo(f"       fix: {c['fix']}")
    counts = report["summary"]
    typer.echo(f"\nPreflight: {counts['pass']} pass, {counts['warn']} warn, {counts['fail']} fail")
    if report.get("ready"):
        typer.echo(f"Ready to use: {', '.join(report['ready'])}")
    if report.get("not_ready"):
        typer.echo(f"Not ready: {', '.join(report['not_ready'])}")
    typer.echo(f"\nReport saved to {report_path}")


def _run_preflight_inline(root: Path) -> None:
    """Run preflight from init — prints results but never fails init."""
    report = _run_preflight(root)
    report_path = root / ".spec_orch" / "preflight.json"
    _print_preflight(report, report_path)


# ---------------------------------------------------------------------------
# Controller / planner helpers
# ---------------------------------------------------------------------------

from spec_orch.services.run_controller import RunController  # noqa: E402


def _make_controller(
    *,
    repo_root: Path,
    codex_executable: str = "codex",
    live_stream: IO[str] | None = None,
    source: str = "fixture",
    auto_approve: bool = False,
    reviewer_override: str | None = None,
) -> RunController:
    from spec_orch.services.adapter_factory import (
        create_builder,
        create_issue_source,
        create_reviewer,
    )

    toml_raw = _load_toml_raw(repo_root)
    if codex_executable != "codex":
        builder_cfg = toml_raw.setdefault("builder", {})
        builder_cfg["executable"] = codex_executable
        builder_cfg.setdefault("adapter", "codex_exec")

    if reviewer_override:
        reviewer_cfg = toml_raw.setdefault("reviewer", {})
        reviewer_cfg["adapter"] = reviewer_override

    issue_source = create_issue_source(repo_root, toml_override=toml_raw, source_override=source)

    planner = _build_planner_from_toml(repo_root)
    builder = create_builder(repo_root, toml_override=toml_raw)
    reviewer = create_reviewer(repo_root, toml_override=toml_raw)

    toml_spec = toml_raw.get("spec", {})
    require_approval = (
        toml_spec.get("require_approval", True) if isinstance(toml_spec, dict) else True
    )
    if auto_approve:
        require_approval = False

    return RunController(
        repo_root=repo_root,
        builder_adapter=builder,
        issue_source=issue_source,
        planner_adapter=planner,
        review_adapter=reviewer,
        live_stream=live_stream,
        require_spec_approval=require_approval,
    )


def _load_toml_raw(repo_root: Path) -> dict[str, Any]:
    """Load spec-orch.toml as raw dict. Returns empty dict on failure."""
    config_path = repo_root / "spec-orch.toml"
    if not config_path.exists():
        return {}
    try:
        with config_path.open("rb") as f:
            return tomllib.load(f)
    except Exception:
        return {}


_planner_logger = _logging.getLogger("spec_orch.cli.planner")


def _require_planner(repo_root: Path) -> Any:
    """Build planner or exit with actionable error if unavailable."""
    planner = _build_planner_from_toml(repo_root)
    if planner is None:
        typer.echo("Planner not available. Possible causes:")
        typer.echo("  1. litellm not installed      → pip install 'spec-orch[planner]'")
        typer.echo("  2. [planner] model not set     → spec-orch init --reconfigure")
        typer.echo("  3. API key not configured      → edit .env, set SPEC_ORCH_LLM_API_KEY")
        typer.echo("Run 'spec-orch preflight' for full diagnostics.")
        raise typer.Exit(1)
    return planner


def _build_planner_from_toml(repo_root: Path) -> Any:
    """Build a PlannerAdapter from spec-orch.toml if planner section exists."""
    config_path = repo_root / "spec-orch.toml"
    if not config_path.exists():
        _planner_logger.info("spec-orch.toml not found at %s; planner disabled", config_path)
        return None
    try:
        with config_path.open("rb") as f:
            raw = tomllib.load(f)
    except Exception:
        _planner_logger.warning("Failed to parse %s; planner disabled", config_path, exc_info=True)
        return None

    planner_cfg = raw.get("planner", {})
    model = planner_cfg.get("model")
    if not model:
        _planner_logger.info(
            "[planner] model not set in spec-orch.toml; planner disabled. "
            "Fix: run 'spec-orch init --reconfigure' or edit spec-orch.toml."
        )
        return None

    api_key: str | None = None
    api_key_env = planner_cfg.get("api_key_env")
    if api_key_env:
        api_key = os.environ.get(api_key_env)
        if not api_key:
            _planner_logger.warning(
                "Environment variable %s is not set; LLM calls will fail. "
                "Fix: edit .env and set %s=your-key",
                api_key_env,
                api_key_env,
            )

    api_base: str | None = None
    api_base_env = planner_cfg.get("api_base_env")
    if api_base_env:
        api_base = os.environ.get(api_base_env)

    token_command = planner_cfg.get("token_command")
    api_type = planner_cfg.get("api_type", "anthropic")

    try:
        from spec_orch.services.litellm_planner_adapter import LiteLLMPlannerAdapter

        return LiteLLMPlannerAdapter(
            model=model,
            api_type=api_type,
            api_key=api_key,
            api_base=api_base,
            token_command=token_command,
        )
    except ImportError:
        _planner_logger.warning(
            "litellm not installed; planner disabled. Fix: pip install 'spec-orch[planner]'"
        )
        return None


def _edit_fixture_json(fixture: dict[str, object]) -> dict[str, object]:
    editor = os.environ.get("EDITOR")
    if not editor:
        typer.echo("$EDITOR is not set")
        raise typer.Exit(1)

    with tempfile.NamedTemporaryFile(
        mode="w+",
        suffix=".json",
        encoding="utf-8",
        delete=False,
    ) as temp_file:
        temp_path = Path(temp_file.name)
        temp_file.write(json.dumps(fixture, indent=2) + "\n")

    try:
        result = subprocess.run(shlex.split(editor) + [str(temp_path)], check=False)
        if result.returncode != 0:
            typer.echo(f"editor exited with code {result.returncode}")
            raise typer.Exit(1)
        result_data: dict[str, object] = json.loads(
            temp_path.read_text(encoding="utf-8"),
        )
        return result_data
    except json.JSONDecodeError as exc:
        typer.echo(f"edited fixture is not valid JSON: {exc}")
        raise typer.Exit(1) from exc
    finally:
        temp_path.unlink(missing_ok=True)


def _load_conversation_planner(
    repo_root: Path,
) -> Any:
    """Build a LiteLLMPlannerAdapter from spec-orch.toml for conversation use."""
    toml_path = repo_root / "spec-orch.toml"
    if not toml_path.exists():
        return None
    try:
        with open(toml_path, "rb") as f:
            raw = tomllib.load(f)
        planner_cfg = raw.get("planner", {})
        model = planner_cfg.get("model")
        if not model:
            return None
        api_key_env = planner_cfg.get("api_key_env")
        api_base_env = planner_cfg.get("api_base_env")
        token_command = planner_cfg.get("token_command")
        api_type = planner_cfg.get("api_type", "anthropic")

        from spec_orch.services.litellm_planner_adapter import LiteLLMPlannerAdapter

        api_key = os.environ.get(api_key_env) if api_key_env else None
        if not api_key and not token_command:
            hint_env = api_key_env or "SPEC_ORCH_LLM_API_KEY"
            typer.echo(
                f"Warning: environment variable '{hint_env}' is not set.\n"
                f"  The LLM planner will not work until you provide an API key.\n"
                f"  Option 1: Add to .env file   →  {hint_env}=your-key\n"
                f"  Option 2: Export in shell     →  export {hint_env}=your-key\n"
                f'  Option 3: Set token_command   →  [planner] token_command = "..."\n',
            )

        return LiteLLMPlannerAdapter(
            model=model,
            api_type=api_type,
            api_key=api_key,
            api_base=os.environ.get(api_base_env) if api_base_env else None,
            token_command=token_command,
        )
    except (ImportError, FileNotFoundError, tomllib.TOMLDecodeError):
        return None


def _load_planner_config(repo_root: Path) -> dict[str, Any]:
    """Load planner config from spec-orch.toml."""
    config_path = repo_root / "spec-orch.toml"
    if not config_path.exists():
        return {}
    try:
        with config_path.open("rb") as f:
            raw = tomllib.load(f)
    except (FileNotFoundError, tomllib.TOMLDecodeError):
        return {}
    planner_cfg = raw.get("planner", {})
    result: dict[str, Any] = {}
    if planner_cfg.get("model"):
        result["model"] = planner_cfg["model"]
    if planner_cfg.get("api_type"):
        result["api_type"] = planner_cfg["api_type"]
    api_key_env = planner_cfg.get("api_key_env")
    if api_key_env:
        result["api_key"] = os.environ.get(api_key_env)
    api_base_env = planner_cfg.get("api_base_env")
    if api_base_env:
        result["api_base"] = os.environ.get(api_base_env)
    result["token_command"] = planner_cfg.get("token_command")
    return result


# ---------------------------------------------------------------------------
# Gate helpers
# ---------------------------------------------------------------------------


def _load_gate_policy(
    policy_path: Path,
    profile: str,
) -> Any:
    from spec_orch.services.gate_service import GatePolicy

    if Path(policy_path).exists():
        gate_policy = GatePolicy.from_yaml(Path(policy_path))
    else:
        gate_policy = GatePolicy.default()
    if profile:
        gate_policy = gate_policy.with_profile(profile)
    return gate_policy


def _build_gate_input_from_report(data: dict[str, Any]) -> Any:
    """Construct a GateInput from a report.json dict."""
    from spec_orch.domain.models import (
        GateInput,
        ReviewSummary,
        VerificationDetail,
        VerificationSummary,
    )

    builder_data = data.get("builder", {})
    review_data = data.get("review", {})
    verification_data = data.get("verification", {})
    acceptance_data = data.get("human_acceptance", {})

    _fail = VerificationDetail(command=[], exit_code=1, stdout="", stderr="")
    details = {
        name: VerificationDetail(
            command=detail.get("command", []),
            exit_code=detail.get("exit_code", 1),
            stdout="",
            stderr="",
        )
        for name, detail in verification_data.items()
    }
    verification = VerificationSummary(details=details)
    for name, detail in details.items():
        verification.set_step_passed(name, detail.exit_code == 0)
    review = ReviewSummary(
        verdict=review_data.get("verdict", "pending"),
        reviewed_by=review_data.get("reviewed_by"),
    )
    return GateInput(
        spec_exists=True,
        spec_approved=True,
        within_boundaries=True,
        builder_succeeded=builder_data.get("succeeded", False),
        verification=verification,
        review=review,
        human_acceptance=acceptance_data.get("accepted", False),
    )


# ---------------------------------------------------------------------------
# Print helpers
# ---------------------------------------------------------------------------


def _print_jsonl(path: Path, filter_type: str) -> None:
    if not path.exists():
        typer.echo(f"file not found: {path}")
        raise typer.Exit(1)
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        if filter_type:
            try:
                obj = json.loads(line)
                etype = obj.get("event_type", "") or obj.get("type", "")
                if filter_type.lower() not in etype.lower():
                    continue
            except json.JSONDecodeError:
                continue
        typer.echo(line)


def _print_check_report(results: list[Any]) -> None:
    counts = {"pass": 0, "warn": 0, "fail": 0}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
        typer.echo(f"[{result.status.upper()}] {result.name}: {result.message}")
    typer.echo(f"Summary: {counts['pass']} pass, {counts['warn']} warn, {counts['fail']} fail")


# ---------------------------------------------------------------------------
# Linear writeback
# ---------------------------------------------------------------------------


def _linear_writeback_on_pr(
    issue_id: str,
    report: dict[str, Any],
    pr_url: str | None,
    gate: Any,
    repo_root: Path,
) -> None:
    """Post a pipeline summary to Linear when a token is available."""
    import tomllib as _tomllib

    config_path = repo_root / "spec-orch.toml"
    if not config_path.exists():
        return
    try:
        with config_path.open("rb") as f:
            raw = _tomllib.load(f)
    except (FileNotFoundError, _tomllib.TOMLDecodeError):
        return

    linear_cfg = raw.get("linear", {})
    token_env = linear_cfg.get("token_env", "")
    token = os.environ.get(token_env, "") if token_env else ""
    if not token:
        return

    try:
        import httpx  # noqa: F401

        from spec_orch.services.linear_client import LinearClient

        client = LinearClient(token=token)
    except (ImportError, RuntimeError) as exc:
        typer.echo(f"linear writeback skipped: {exc}")
        return

    try:
        issue_data = client.get_issue(issue_id)
        linear_id = issue_data["id"]

        state = report.get("state", "unknown")
        title = report.get("title", issue_id)
        mergeable = "yes" if gate.mergeable else "no"
        blocked = ", ".join(gate.failed_conditions) if gate.failed_conditions else "none"

        comment = (
            f"## SpecOrch Pipeline Complete\n\n"
            f"**Issue**: {issue_id} — {title}\n"
            f"**State**: {state}\n"
            f"**Mergeable**: {mergeable}\n"
            f"**Blocked by**: {blocked}\n"
        )
        if pr_url:
            comment += f"**PR**: {pr_url}\n"
        comment += f"\n_Auto-close on merge via `Closes {issue_id}` in PR body._"

        client.add_comment(linear_id, comment)
        client.update_issue_state(linear_id, "In Progress")
        typer.echo(f"linear: posted summary to {issue_id}")
    except Exception as exc:
        typer.echo(f"linear writeback skipped: {exc}")
    finally:
        client.close()


# ---------------------------------------------------------------------------
# Pipeline next-step hint
# ---------------------------------------------------------------------------


def _show_next_step(mission_id: str, repo_root: Path) -> None:
    """Print the next pipeline step hint after a command completes."""
    from spec_orch.services.pipeline_checker import next_step

    nxt = next_step(mission_id, repo_root)
    if nxt:
        typer.echo(f"\n>> next: {nxt.label}  ({nxt.command_hint})")


# ---------------------------------------------------------------------------
# OpenSpec layer map
# ---------------------------------------------------------------------------

_OPENSPEC_LAYER_MAP = {
    "spec.md": "semantic",
    "prd.md": "semantic",
    "proposal.md": "semantic",
    "design.md": "semantic",
    "tasks.md": "procedural",
}
