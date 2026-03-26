from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import typer

from spec_orch.cli import app
from spec_orch.cli._helpers import (
    _build_planner_from_toml,
    _load_conversation_planner,
    _load_planner_config,
    _print_jsonl,
    _show_next_step,
)
from spec_orch.services.workspace_service import WorkspaceService

mission_app = typer.Typer()
app.add_typer(mission_app, name="mission")
discuss_app = typer.Typer()
app.add_typer(discuss_app, name="discuss")
memory_app = typer.Typer(help="Memory subsystem — unified knowledge store.")
app.add_typer(memory_app, name="memory")


# ---------------------------------------------------------------------------
# plan / plan-show / promote / pipeline commands
# ---------------------------------------------------------------------------


@app.command("plan")
def plan_mission(
    mission_id: str = typer.Argument(..., help="Mission ID to scope."),
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Generate a wave-based execution plan (DAG) from a Mission spec."""
    from spec_orch.services.mission_service import MissionService
    from spec_orch.services.promotion_service import save_plan
    from spec_orch.services.scoper_adapter import LiteLLMScoperAdapter

    svc = MissionService(repo_root=Path(repo_root))
    mission = svc.get_mission(mission_id)

    spec_file = Path(repo_root) / mission.spec_path
    spec_content = spec_file.read_text() if spec_file.exists() else ""

    tree_lines: list[str] = []
    src = Path(repo_root) / "src"
    if src.exists():
        for p in sorted(src.rglob("*.py")):
            tree_lines.append(str(p.relative_to(repo_root)))

    planner_cfg = _load_planner_config(Path(repo_root))

    evidence_ctx: str | None = None
    try:
        from spec_orch.services.evidence_analyzer import EvidenceAnalyzer

        analyzer = EvidenceAnalyzer(Path(repo_root))
        summary = analyzer.analyze()
        if summary.total_runs > 0:
            evidence_ctx = analyzer.format_as_llm_context(summary)
    except (OSError, ValueError) as exc:
        typer.echo(f"[plan] evidence analysis skipped: {exc}", err=True)

    hints_ctx: str | None = None
    try:
        from spec_orch.services.plan_strategy_evolver import PlanStrategyEvolver

        strategy_evolver = PlanStrategyEvolver(Path(repo_root))
        hints_ctx = strategy_evolver.format_hints_for_prompt() or None
    except (OSError, ValueError) as exc:
        typer.echo(f"[plan] scoper hints skipped: {exc}", err=True)

    scoper = LiteLLMScoperAdapter(
        model=planner_cfg.get("model", "claude-sonnet-4-20250514"),
        api_type=planner_cfg.get("api_type", "anthropic"),
        api_key=planner_cfg.get("api_key"),
        api_base=planner_cfg.get("api_base"),
        token_command=planner_cfg.get("token_command"),
        evidence_context=evidence_ctx,
        scoper_hints=hints_ctx,
    )

    plan = scoper.scope(
        mission=mission,
        codebase_context={
            "spec_content": spec_content,
            "file_tree": "\n".join(tree_lines),
        },
    )

    plan_path = Path(repo_root) / "docs/specs" / mission_id / "plan.json"
    save_plan(plan, plan_path)

    total_packets = sum(len(w.work_packets) for w in plan.waves)
    typer.echo(f"plan generated: {len(plan.waves)} waves, {total_packets} work packets")
    for w in plan.waves:
        typer.echo(f"  wave {w.wave_number}: {w.description} ({len(w.work_packets)} packets)")
    _show_next_step(mission_id, Path(repo_root))


@app.command("plan-show")
def plan_show(
    mission_id: str = typer.Argument(..., help="Mission ID."),
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Display the execution plan for a Mission."""
    from spec_orch.services.promotion_service import load_plan

    plan_path = Path(repo_root) / "docs/specs" / mission_id / "plan.json"
    if not plan_path.exists():
        typer.echo(f"no plan found for {mission_id}")
        raise typer.Exit(1)

    plan = load_plan(plan_path)
    typer.echo(f"plan: {plan.plan_id} | mission: {plan.mission_id}")
    typer.echo(f"status: {plan.status.value}")
    for w in plan.waves:
        typer.echo(f"\n--- Wave {w.wave_number}: {w.description} ---")
        for p in w.work_packets:
            deps = f" (depends: {', '.join(p.depends_on)})" if p.depends_on else ""
            issue = f" [{p.linear_issue_id}]" if p.linear_issue_id else ""
            typer.echo(f"  [{p.run_class}] {p.packet_id}: {p.title}{deps}{issue}")
    _show_next_step(mission_id, Path(repo_root))


@app.command("promote")
def promote_plan(
    mission_id: str = typer.Argument(..., help="Mission ID to promote."),
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Promote a plan to execution — create Linear issues from work packets."""
    from spec_orch.services.promotion_service import PromotionService, load_plan, save_plan

    plan_path = Path(repo_root) / "docs/specs" / mission_id / "plan.json"
    if not plan_path.exists():
        typer.echo(f"no plan found for {mission_id}")
        raise typer.Exit(1)

    plan = load_plan(plan_path)

    linear_client = None
    linear_token = os.environ.get("SPEC_ORCH_LINEAR_TOKEN")
    if linear_token:
        from spec_orch.services.linear_client import LinearClient

        linear_client = LinearClient(token=linear_token)

    try:
        svc = PromotionService(linear_client=linear_client)
        plan = svc.promote(plan)
        save_plan(plan, plan_path)
    finally:
        if linear_client is not None:
            linear_client.close()

    total = sum(len(w.work_packets) for w in plan.waves)
    typer.echo(f"promoted {total} work packets to execution")
    for w in plan.waves:
        for p in w.work_packets:
            typer.echo(f"  {p.linear_issue_id}: {p.title}")
    _show_next_step(mission_id, Path(repo_root))


@app.command("pipeline")
def pipeline_status(
    mission_id: str = typer.Argument(..., help="Mission ID to check."),
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Show the EODF pipeline progress for a mission."""
    from spec_orch.services.pipeline_checker import check_pipeline, format_pipeline

    stages = check_pipeline(mission_id, Path(repo_root))
    typer.echo(f"Pipeline: {mission_id}\n")
    typer.echo(format_pipeline(stages))

    done = sum(1 for s in stages if s.status == "done")
    typer.echo(f"\n{done}/{len(stages)} stages complete")


@app.command("retro")
def retro_mission(
    mission_id: str = typer.Argument(..., help="Mission ID."),
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Generate a retrospective for a Mission — deviations, decisions, outcomes."""
    from spec_orch.services.deviation_service import load_deviations
    from spec_orch.services.mission_service import MissionService
    from spec_orch.services.promotion_service import load_plan

    svc = MissionService(repo_root=Path(repo_root))
    mission = svc.get_mission(mission_id)

    mission_issue_ids: set[str] | None = None
    plan_path = Path(repo_root) / "docs/specs" / mission_id / "plan.json"
    if plan_path.exists():
        plan = load_plan(plan_path)
        mission_issue_ids = set()
        for w in plan.waves:
            for p in w.work_packets:
                if p.linear_issue_id:
                    mission_issue_ids.add(p.linear_issue_id)

    ws = WorkspaceService(repo_root=Path(repo_root))
    base_dir = ws.repo_root / ".spec_orch_runs"
    if not base_dir.exists():
        base_dir = ws.repo_root / ".worktrees"

    retro_lines = [
        f"# Retrospective: {mission.title}",
        f"\n**Mission**: `{mission_id}`",
        f"**Status**: {mission.status.value}",
        "",
        "## Issues",
        "",
    ]

    issue_dirs = sorted(base_dir.iterdir()) if base_dir.exists() else []
    total_deviations = 0
    issues_included = 0
    for issue_dir in issue_dirs:
        report_path = issue_dir / "report.json"
        if not report_path.exists():
            continue
        data = json.loads(report_path.read_text())
        issue_id = data.get("issue_id", issue_dir.name)
        if mission_issue_ids is not None and issue_id not in mission_issue_ids:
            continue
        issues_included += 1
        state = data.get("state", "unknown")
        mergeable = data.get("mergeable", False)
        retro_lines.append(
            f"- **{issue_id}**: {data.get('title', '')} | state={state} | mergeable={mergeable}"
        )
        deviations = load_deviations(issue_dir)
        if deviations:
            total_deviations += len(deviations)
            for d in deviations:
                retro_lines.append(f"  - [{d.severity}] {d.description} ({d.resolution})")

    retro_lines.extend(
        [
            "",
            "## Summary",
            "",
            f"- Total deviations: {total_deviations}",
            f"- Issues processed: {issues_included}",
        ]
    )

    retro_content = "\n".join(retro_lines) + "\n"
    retro_path = Path(repo_root) / "docs/specs" / mission_id / "retrospective.md"
    retro_path.parent.mkdir(parents=True, exist_ok=True)
    retro_path.write_text(retro_content)
    typer.echo(f"retrospective written: {retro_path}")
    typer.echo(retro_content)


# ---------------------------------------------------------------------------
# mission commands
# ---------------------------------------------------------------------------


@mission_app.command("create")
def mission_create(
    title: str = typer.Argument(..., help="Mission title."),
    mission_id: str | None = typer.Option(None, "--id", help="Override generated ID."),
    template: str | None = typer.Option(
        None,
        "--template",
        help="Create from an existing mission's spec (mission ID).",
    ),
    from_example: str | None = typer.Option(
        None,
        "--from-example",
        help="Reverse-engineer spec from a local file (JSON/MD/TXT).",
    ),
    from_url: str | None = typer.Option(
        None,
        "--from-url",
        help="Reverse-engineer spec from a URL.",
    ),
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Create a new Mission with a canonical spec skeleton.

    Optionally use --template, --from-example, or --from-url (mutually exclusive)
    to seed the spec from existing content.
    """
    from spec_orch.services.mission_service import MissionService

    sources = [s for s in (template, from_example, from_url) if s is not None]
    if len(sources) > 1:
        typer.echo(
            "Error: --template, --from-example, and --from-url are mutually exclusive.",
            err=True,
        )
        raise typer.Exit(code=1)

    svc = MissionService(repo_root=Path(repo_root))

    if template is not None:
        try:
            m = svc.create_mission_from_template(title, template, mission_id=mission_id)
        except (FileNotFoundError, ValueError) as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(code=1) from exc
    elif from_example is not None:
        example_path = Path(from_example)
        if not example_path.exists():
            typer.echo(f"Error: file not found: {from_example}", err=True)
            raise typer.Exit(code=1)
        content = example_path.read_text()
        planner = _build_planner_from_toml(Path(repo_root))
        m = svc.create_mission_from_example(title, content, mission_id=mission_id, planner=planner)
    elif from_url is not None:
        try:
            import httpx

            resp = httpx.get(from_url, timeout=30, follow_redirects=True)
            resp.raise_for_status()
            content = resp.text
        except Exception as exc:
            typer.echo(f"Error fetching URL: {exc}", err=True)
            raise typer.Exit(code=1) from exc
        planner = _build_planner_from_toml(Path(repo_root))
        m = svc.create_mission_from_example(title, content, mission_id=mission_id, planner=planner)
    else:
        m = svc.create_mission(title, mission_id=mission_id)

    typer.echo(f"mission created: {m.mission_id}")
    typer.echo(f"spec: {m.spec_path}")


@mission_app.command("approve")
def mission_approve(
    mission_id: str = typer.Argument(..., help="Mission ID to approve."),
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Approve a Mission spec, freezing it for execution."""
    from spec_orch.services.mission_service import MissionService

    svc = MissionService(repo_root=Path(repo_root))
    m = svc.approve_mission(mission_id)
    typer.echo(f"mission {m.mission_id} approved at {m.approved_at}")
    _show_next_step(m.mission_id, Path(repo_root))


@mission_app.command("status")
def mission_status(
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """List all Missions and their status."""
    from spec_orch.services.mission_service import MissionService

    svc = MissionService(repo_root=Path(repo_root))
    missions = svc.list_missions()
    if not missions:
        typer.echo("no missions found")
        return
    for m in missions:
        typer.echo(f"{m.mission_id:40s} {m.status.value:12s} {m.title}")


@mission_app.command("show")
def mission_show(
    mission_id: str = typer.Argument(..., help="Mission ID."),
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Print the canonical spec for a Mission."""
    from spec_orch.services.mission_service import MissionService

    svc = MissionService(repo_root=Path(repo_root))
    m = svc.get_mission(mission_id)
    spec_file = Path(repo_root) / m.spec_path
    if spec_file.exists():
        typer.echo(spec_file.read_text())
    else:
        typer.echo(f"spec file not found: {m.spec_path}")


@mission_app.command("logs")
def mission_logs(
    mission_id: str = typer.Argument(..., help="Mission ID."),
    packet_id: str = typer.Argument(..., help="Packet/worker ID."),
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
    raw: bool = typer.Option(
        False, "--raw", help="Print raw worker events (incoming_events.jsonl)."
    ),
    events: bool = typer.Option(
        False, "--events", help="Print orchestrator events (events.jsonl)."
    ),
    filter_type: str = typer.Option("", "--filter", help="Filter by event type substring."),
) -> None:
    """View logs for a supervised mission worker packet."""
    workspace = Path(repo_root) / "docs" / "specs" / mission_id / "workers" / packet_id
    telemetry_dir = workspace / "telemetry"

    if raw and events:
        typer.echo("choose either --raw or --events, not both")
        raise typer.Exit(2)

    if raw:
        _print_jsonl(telemetry_dir / "incoming_events.jsonl", filter_type)
        return
    if events:
        _print_jsonl(telemetry_dir / "events.jsonl", filter_type)
        return

    log_path = telemetry_dir / "activity.log"
    if not log_path.exists():
        typer.echo(f"no activity log found for {mission_id}/{packet_id}")
        raise typer.Exit(1)

    with log_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.rstrip("\n")
            if filter_type and filter_type.upper() not in line.upper():
                continue
            typer.echo(line)


# ---------------------------------------------------------------------------
# discuss commands
# ---------------------------------------------------------------------------


@discuss_app.callback(invoke_without_command=True)
def discuss_tui(
    ctx: typer.Context,
    channel: str = typer.Option(
        "cli",
        "--channel",
        "-c",
        help="Conversation channel: cli, slack, or linear.",
    ),
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Interactive brainstorming with the LLM planner."""
    if ctx.invoked_subcommand is not None:
        return

    from spec_orch.services.conversation_service import ConversationService

    planner = _load_conversation_planner(repo_root)
    svc = ConversationService(repo_root=repo_root, planner=planner)

    if channel == "slack":
        _start_slack_adapter(svc, repo_root)
        return

    if channel == "linear":
        _start_linear_adapter(svc, repo_root)
        return

    thread_id = f"cli-{uuid4().hex[:8]}"
    typer.echo("SpecOrch brainstorming (type 'quit' to exit, '@spec-orch freeze' to freeze)")
    typer.echo(f"Thread: {thread_id}")

    while True:
        try:
            user_input = input("\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            typer.echo("\nbye")
            break
        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            break

        from spec_orch.domain.models import ConversationMessage

        msg = ConversationMessage(
            message_id=f"cli-{uuid4().hex[:8]}",
            thread_id=thread_id,
            sender="user",
            content=user_input,
            timestamp=datetime.now(UTC).isoformat(),
            channel="cli",
        )
        try:
            reply = svc.handle_message(msg)
        except Exception as exc:
            error_message = f"\n[error] {type(exc).__name__}: {exc}\n"
            if planner:
                hint = (
                    "Hint: check your .env file or environment variables.\n"
                    "Run `spec-orch config check` for a configuration health check."
                )
            else:
                hint = "An unexpected error occurred. This might be a bug in spec-orch."
            typer.echo(error_message + hint, err=True)
            continue
        if reply:
            typer.echo(f"\nbot> {reply}")


def _start_slack_adapter(svc: Any, repo_root: Path) -> None:
    try:
        from spec_orch.services.slack_conversation_adapter import (
            SlackConversationAdapter,
        )
    except ImportError as exc:
        typer.echo("slack-bolt not installed. Run: pip install spec-orch[slack]")
        raise typer.Exit(1) from exc

    adapter = SlackConversationAdapter()
    typer.echo("Starting Slack bot (Socket Mode)...")
    adapter.listen(callback=svc.handle_message)


def _start_linear_adapter(svc: Any, repo_root: Path) -> None:
    import tomllib

    toml_path = repo_root / "spec-orch.toml"
    if not toml_path.exists():
        typer.echo("spec-orch.toml not found")
        raise typer.Exit(1)

    with open(toml_path, "rb") as f:
        raw = tomllib.load(f)

    linear_cfg = raw.get("linear", {})
    conv_section = raw.get("conversation", {})
    conv_cfg = conv_section.get("linear", {}) if isinstance(conv_section, dict) else {}

    from spec_orch.services.linear_client import LinearClient
    from spec_orch.services.linear_conversation_adapter import LinearConversationAdapter

    client = LinearClient(token_env=linear_cfg.get("token_env", "SPEC_ORCH_LINEAR_TOKEN"))
    adapter = LinearConversationAdapter(
        client=client,
        team_key=linear_cfg.get("team_key", "SON"),
        watch_label=conv_cfg.get("watch_label", "spec-orch"),
        poll_interval_seconds=conv_cfg.get("poll_interval_seconds", 30),
    )
    typer.echo("Starting Linear comment bot (polling)...")
    adapter.listen(callback=svc.handle_message)


@discuss_app.command("list")
def discuss_list(
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """List active conversation threads."""
    from spec_orch.services.conversation_service import ConversationService

    svc = ConversationService(repo_root=repo_root)
    threads = svc.list_threads()
    if not threads:
        typer.echo("No conversation threads found.")
        return
    for t in threads:
        n_msgs = len(t.messages)
        typer.echo(
            f"  {t.thread_id}  channel={t.channel}  status={t.status.value}  "
            f"messages={n_msgs}  mission={t.mission_id or '-'}"
        )


@discuss_app.command("freeze")
def discuss_freeze(
    thread_id: str = typer.Argument(..., help="Thread ID to freeze."),
    repo_root: Path = typer.Option(Path("."), "--repo-root", "-r"),
) -> None:
    """Manually freeze a conversation thread into a spec."""
    from spec_orch.domain.models import ConversationMessage
    from spec_orch.services.conversation_service import ConversationService

    planner = _load_conversation_planner(repo_root)
    svc = ConversationService(repo_root=repo_root, planner=planner)

    thread = svc.get_thread(thread_id)
    if thread is None or not thread.messages:
        typer.echo(f"Thread {thread_id} not found or empty.")
        raise typer.Exit(1)

    msg = ConversationMessage(
        message_id=f"cmd-{uuid4().hex[:8]}",
        thread_id=thread_id,
        sender="user",
        content="@spec-orch freeze",
        timestamp=datetime.now(UTC).isoformat(),
        channel=thread.channel,
    )
    result = svc.handle_message(msg)
    if result:
        typer.echo(result)


# ---------------------------------------------------------------------------
# memory commands
# ---------------------------------------------------------------------------


@memory_app.command("list")
def memory_list(
    layer: str = typer.Option("", help="Filter by layer (working/episodic/semantic/procedural)"),
    tag: str = typer.Option("", help="Filter by tag"),
    limit: int = typer.Option(50, help="Max entries to show"),
    repo_root: str = typer.Option(".", help="Repository root"),
) -> None:
    """List memory entry keys."""
    from spec_orch.services.memory.service import get_memory_service

    svc = get_memory_service(repo_root=Path(repo_root).resolve())
    tag_list = [tag] if tag else None
    summaries = svc.list_summaries(layer=layer or None, tags=tag_list, limit=limit)
    if not summaries:
        typer.echo("No entries found.")
        return
    for s in summaries:
        tags_str = ", ".join(s.get("tags", [])) or "-"
        typer.echo(f"  [{s['layer']:11s}] {s['key']}  ({tags_str})")


@memory_app.command("show")
def memory_show(
    key: str = typer.Argument(..., help="Entry key to display"),
    repo_root: str = typer.Option(".", help="Repository root"),
) -> None:
    """Display a single memory entry."""
    from spec_orch.services.memory.service import get_memory_service

    svc = get_memory_service(repo_root=Path(repo_root).resolve())
    entry = svc.get(key)
    if entry is None:
        typer.echo(f"Entry '{key}' not found.", err=True)
        raise typer.Exit(1)
    typer.echo(f"Key:       {entry.key}")
    typer.echo(f"Layer:     {entry.layer.value}")
    typer.echo(f"Tags:      {', '.join(entry.tags) or '-'}")
    typer.echo(f"Created:   {entry.created_at}")
    typer.echo(f"Updated:   {entry.updated_at}")
    if entry.metadata:
        typer.echo(f"Metadata:  {entry.metadata}")
    typer.echo(f"\n{entry.content}")


@memory_app.command("search")
def memory_search(
    query: str = typer.Argument(..., help="Search text"),
    layer: str = typer.Option("", help="Filter by layer"),
    limit: int = typer.Option(10, help="Max results"),
    repo_root: str = typer.Option(".", help="Repository root"),
) -> None:
    """Search memory entries by keyword."""
    from spec_orch.services.memory.service import get_memory_service
    from spec_orch.services.memory.types import MemoryLayer, MemoryQuery

    svc = get_memory_service(repo_root=Path(repo_root).resolve())
    q = MemoryQuery(text=query, top_k=limit)
    if layer:
        q.layer = MemoryLayer(layer)
    results = svc.recall(q)
    if not results:
        typer.echo("No results.")
        return
    for entry in results:
        snippet = entry.content[:120].replace("\n", " ")
        typer.echo(f"  [{entry.layer.value:11s}] {entry.key}")
        typer.echo(f"    {snippet}{'…' if len(entry.content) > 120 else ''}")


@memory_app.command("import")
def memory_import(
    repo_root: str = typer.Option(".", help="Repository root"),
) -> None:
    """Import existing implicit memory (prompt history, hints, reports, policies)."""
    from spec_orch.services.memory.migration import import_all
    from spec_orch.services.memory.service import get_memory_service

    root = Path(repo_root).resolve()
    svc = get_memory_service(repo_root=root)
    counts = import_all(svc.provider, root)
    total = sum(counts.values())
    typer.echo(f"Imported {total} entries:")
    for cat, n in counts.items():
        typer.echo(f"  {cat}: {n}")


@memory_app.command("forget")
def memory_forget(
    key: str = typer.Argument(..., help="Entry key to delete"),
    repo_root: str = typer.Option(".", help="Repository root"),
) -> None:
    """Delete a memory entry."""
    from spec_orch.services.memory.service import get_memory_service

    svc = get_memory_service(repo_root=Path(repo_root).resolve())
    if svc.forget(key):
        typer.echo(f"Deleted: {key}")
    else:
        typer.echo(f"Not found: {key}")


@memory_app.command("ingest-openspec")
def memory_ingest_openspec(
    openspec_dir: str = typer.Option("openspec", help="Path to openspec directory"),
    repo_root: str = typer.Option(".", help="Repository root"),
) -> None:
    """Ingest OpenSpec artifacts (specs, contracts, evidence) into Memory.

    Layer mapping:
      spec.md / prd.md / proposal.md / design.md → Semantic
      tasks.md / contracts/*.md                   → Procedural
      evidence/*.md                               → Episodic
    """
    from spec_orch.cli._helpers import _OPENSPEC_LAYER_MAP
    from spec_orch.services.memory.service import get_memory_service
    from spec_orch.services.memory.types import MemoryEntry, MemoryLayer

    root = Path(repo_root).resolve()
    svc = get_memory_service(repo_root=root)
    odir = root / openspec_dir / "changes"

    if not odir.is_dir():
        typer.echo(f"No changes directory at {odir}", err=True)
        raise typer.Exit(1)

    counts: dict[str, int] = {"semantic": 0, "episodic": 0, "procedural": 0}

    for change_dir in sorted(odir.iterdir()):
        if not change_dir.is_dir():
            continue
        change_name = change_dir.name

        for filename, layer_str in _OPENSPEC_LAYER_MAP.items():
            fpath = change_dir / filename
            if not fpath.is_file():
                continue
            content = fpath.read_text(encoding="utf-8")
            key = f"openspec-{change_name}-{fpath.stem}"
            entry = MemoryEntry(
                key=key,
                content=content,
                layer=MemoryLayer(layer_str),
                tags=["openspec", f"change:{change_name}", fpath.stem],
                metadata={
                    "change": change_name,
                    "file": filename,
                    "source": str(fpath.relative_to(root)),
                },
            )
            svc.store(entry)
            counts[layer_str] += 1

        contracts_dir = change_dir / "contract"
        if not contracts_dir.is_dir():
            contracts_dir = change_dir.parent.parent / "contracts"
        if contracts_dir.is_dir():
            for cpath in sorted(contracts_dir.glob("*.md")):
                if change_name not in cpath.stem and contracts_dir.name == "contracts":
                    continue
                content = cpath.read_text(encoding="utf-8")
                key = f"openspec-contract-{cpath.stem}"
                entry = MemoryEntry(
                    key=key,
                    content=content,
                    layer=MemoryLayer.PROCEDURAL,
                    tags=["openspec", "contract", f"change:{change_name}"],
                    metadata={
                        "change": change_name,
                        "file": cpath.name,
                        "source": str(cpath.relative_to(root)),
                    },
                )
                svc.store(entry)
                counts["procedural"] += 1

        evidence_dir = change_dir / "evidence"
        if evidence_dir.is_dir():
            for epath in sorted(evidence_dir.glob("*.md")):
                content = epath.read_text(encoding="utf-8")
                key = f"openspec-evidence-{epath.stem}"
                entry = MemoryEntry(
                    key=key,
                    content=content,
                    layer=MemoryLayer.EPISODIC,
                    tags=["openspec", "evidence", f"change:{change_name}", epath.stem],
                    metadata={
                        "change": change_name,
                        "file": epath.name,
                        "source": str(epath.relative_to(root)),
                    },
                )
                svc.store(entry)
                counts["episodic"] += 1

    top_contracts = root / openspec_dir / "contracts"
    if top_contracts.is_dir():
        for cpath in sorted(top_contracts.glob("*.md")):
            content = cpath.read_text(encoding="utf-8")
            key = f"openspec-contract-{cpath.stem}"
            entry = MemoryEntry(
                key=key,
                content=content,
                layer=MemoryLayer.PROCEDURAL,
                tags=["openspec", "contract", cpath.stem],
                metadata={"file": cpath.name, "source": str(cpath.relative_to(root))},
            )
            svc.store(entry)
            counts["procedural"] += 1

    total = sum(counts.values())
    typer.echo(f"Ingested {total} OpenSpec entries into Memory:")
    for layer_name, n in counts.items():
        typer.echo(f"  {layer_name}: {n}")
