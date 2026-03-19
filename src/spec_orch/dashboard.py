"""Lightweight web dashboard for spec-orch — pipeline status and execution results.

Start with:  spec-orch dashboard
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from spec_orch.services.mission_service import MissionService
from spec_orch.services.pipeline_checker import check_pipeline
from spec_orch.services.promotion_service import load_plan

logger = logging.getLogger(__name__)


def _get_event_bus():
    try:
        from spec_orch.services.event_bus import get_event_bus

        return get_event_bus()
    except ImportError:
        return None


def _get_lifecycle_manager(repo_root: Path):
    try:
        from spec_orch.services.lifecycle_manager import MissionLifecycleManager

        return MissionLifecycleManager(repo_root)
    except ImportError:
        return None


def _get_conversation_service(repo_root: Path):
    try:
        from spec_orch.services.conversation_service import ConversationService

        return ConversationService(repo_root=repo_root)
    except Exception:
        return None


def _gather_missions(repo_root: Path) -> list[dict[str, Any]]:
    svc = MissionService(repo_root=repo_root)
    missions = svc.list_missions()
    results = []
    for m in missions:
        plan_path = repo_root / "docs/specs" / m.mission_id / "plan.json"
        plan_info: dict[str, Any] | None = None
        if plan_path.exists():
            plan = load_plan(plan_path)
            plan_info = {
                "plan_id": plan.plan_id,
                "status": plan.status.value,
                "wave_count": len(plan.waves),
                "packet_count": sum(len(w.work_packets) for w in plan.waves),
                "waves": [
                    {
                        "wave_number": w.wave_number,
                        "description": w.description,
                        "packets": [
                            {
                                "packet_id": p.packet_id,
                                "title": p.title,
                                "run_class": p.run_class,
                                "linear_issue_id": p.linear_issue_id,
                                "depends_on": p.depends_on,
                            }
                            for p in w.work_packets
                        ],
                    }
                    for w in plan.waves
                ],
            }

        stages = check_pipeline(m.mission_id, repo_root)
        pipeline = [
            {"key": s.key, "label": s.label, "status": s.status, "hint": s.command_hint}
            for s in stages
        ]

        results.append(
            {
                "mission_id": m.mission_id,
                "title": m.title,
                "status": m.status.value,
                "created_at": m.created_at,
                "approved_at": m.approved_at,
                "completed_at": m.completed_at,
                "plan": plan_info,
                "pipeline": pipeline,
                "pipeline_done": sum(1 for s in stages if s.status == "done"),
                "pipeline_total": len(stages),
            }
        )
    return results


def _gather_lifecycle_states(repo_root: Path) -> dict[str, Any]:
    mgr = _get_lifecycle_manager(repo_root)
    if mgr is None:
        return {}
    return {mid: ms.to_dict() for mid, ms in mgr.all_states().items()}


def _gather_evolution_metrics(repo_root: Path) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "prompt_variants": 0,
        "scoper_hints": 0,
        "policies": 0,
        "success_rate": 0.0,
        "total_runs": 0,
        "successful_runs": 0,
        "variants": [],
        "hint_categories": {},
        "run_trend": [],
    }
    try:
        evo_dir = repo_root / ".spec_orch_runs" / "evolution"
        if evo_dir.exists():
            prompts_dir = evo_dir / "prompts"
            if prompts_dir.exists():
                metrics["prompt_variants"] = len(list(prompts_dir.glob("*.md")))
            hints_path = evo_dir / "scoper_hints.json"
            if hints_path.exists():
                hints = json.loads(hints_path.read_text())
                metrics["scoper_hints"] = (
                    len(hints) if isinstance(hints, list) else len(hints.keys())
                )
                if isinstance(hints, dict):
                    metrics["hint_categories"] = {
                        k: len(v) if isinstance(v, list) else 1 for k, v in hints.items()
                    }
            policies_path = evo_dir / "policies.json"
            if policies_path.exists():
                policies = json.loads(policies_path.read_text())
                metrics["policies"] = (
                    len(policies) if isinstance(policies, list) else len(policies.keys())
                )

        _load_prompt_variant_metrics(repo_root, metrics)
        _load_run_trend(repo_root, metrics)
    except Exception:
        logger.warning("Failed to gather evolution metrics", exc_info=True)
    return metrics


def _load_prompt_variant_metrics(repo_root: Path, metrics: dict[str, Any]) -> None:
    try:
        from spec_orch.services.prompt_evolver import PromptEvolver

        evolver = PromptEvolver(repo_root)
        history = evolver.load_history()
        variants = []
        for v in history:
            variants.append(
                {
                    "variant_id": v.variant_id,
                    "total_runs": v.total_runs,
                    "successful_runs": v.successful_runs,
                    "success_rate": round(v.success_rate * 100, 1),
                    "is_active": v.is_active,
                    "is_candidate": v.is_candidate,
                    "rationale": v.rationale[:120] if v.rationale else "",
                    "created_at": v.created_at,
                }
            )
        metrics["variants"] = variants
        if variants:
            metrics["prompt_variants"] = len(variants)
    except ImportError:
        pass


def _load_run_trend(repo_root: Path, metrics: dict[str, Any]) -> None:
    runs_dir = repo_root / ".spec_orch_runs"
    if not runs_dir.exists():
        return
    total = 0
    success = 0
    trend: list[dict[str, Any]] = []
    for report in sorted(runs_dir.glob("*/report.json")):
        try:
            data = json.loads(report.read_text())
            total += 1
            ok = data.get("state") == "merged" or data.get("mergeable")
            if ok:
                success += 1
            trend.append(
                {
                    "run": report.parent.name,
                    "ok": bool(ok),
                    "cumulative_rate": round(success / total * 100, 1),
                }
            )
        except (json.JSONDecodeError, OSError):
            logger.debug("Skipping malformed report: %s", report)
    metrics["total_runs"] = total
    metrics["successful_runs"] = success
    if total > 0:
        metrics["success_rate"] = round(success / total * 100, 1)
    metrics["run_trend"] = trend[-30:]


def _gather_run_history(repo_root: Path) -> list[dict[str, Any]]:
    """Scan workspace directories for run reports."""
    runs: list[dict[str, Any]] = []
    for base in [repo_root / ".worktrees", repo_root / ".spec_orch_runs"]:
        if not base.exists():
            continue
        for ws in sorted(base.iterdir()):
            report = ws / "report.json"
            conclusion = ws / "run_artifact" / "conclusion.json"
            try:
                if conclusion.exists():
                    cdata = json.loads(conclusion.read_text())
                    data = {
                        "issue_id": cdata.get("issue_id", ws.name),
                        "state": cdata.get("state", "unknown"),
                        "mergeable": cdata.get("mergeable", False),
                        "failed_conditions": cdata.get("failed_conditions", []),
                        "builder": {},
                    }
                elif report.exists():
                    data = json.loads(report.read_text())
                else:
                    continue
                runs.append(
                    {
                        "issue_id": data.get("issue_id", ws.name),
                        "title": data.get("title", ws.name),
                        "state": data.get("state", "unknown"),
                        "mergeable": data.get("mergeable", False),
                        "failed_conditions": data.get("failed_conditions", []),
                        "builder_adapter": data.get("builder", {}).get("adapter", ""),
                        "builder_succeeded": data.get("builder", {}).get("succeeded", False),
                    }
                )
            except (json.JSONDecodeError, OSError):
                continue
    return runs


def _get_spec_content(repo_root: Path, mission_id: str) -> str | None:
    spec_path = repo_root / "docs" / "specs" / mission_id / "spec.md"
    if spec_path.exists():
        return spec_path.read_text()
    return None


# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------

DASHBOARD_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>spec-orch dashboard</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0f1117;--card:#1a1d27;--border:#2a2d3a;--text:#e1e4eb;--dim:#8b8fa3;
  --green:#22c55e;--amber:#f59e0b;--red:#ef4444;--blue:#3b82f6;--purple:#a855f7;
  --accent:#6366f1;--card-hover:#22253a;
  font-family:'Inter',system-ui,-apple-system,sans-serif;
}
body{background:var(--bg);color:var(--text);min-height:100vh;display:flex;flex-direction:column}

/* ---- header ---- */
.header{display:flex;align-items:center;gap:.75rem;padding:.75rem 1.5rem;
  border-bottom:1px solid var(--border);background:var(--card)}
.header h1{font-size:1.1rem;font-weight:700;display:flex;align-items:center;gap:.4rem}
.header h1 .tag{background:var(--accent);color:#fff;padding:.1rem .45rem;border-radius:4px;
  font-size:.65rem;font-weight:600;letter-spacing:.02em}
.header-spacer{flex:1}
.status-dot{width:8px;height:8px;border-radius:50%;display:inline-block}
.status-dot.connected{background:var(--green);box-shadow:0 0 6px var(--green)}
.status-dot.disconnected{background:var(--red)}
.header-label{font-size:.75rem;color:var(--dim);margin-left:.25rem}
.btn{padding:.35rem .75rem;border:1px solid var(--border);border-radius:6px;
  background:var(--card);color:var(--text);cursor:pointer;font-size:.78rem;
  transition:all .15s}
.btn:hover{border-color:var(--accent);background:var(--card-hover)}
.btn-primary{background:var(--accent);border-color:var(--accent);color:#fff}
.btn-primary:hover{opacity:.9}
.btn-green{background:var(--green);border-color:var(--green);color:#fff}
.btn-green:hover{opacity:.9}
.btn-amber{background:var(--amber);border-color:var(--amber);color:#000}
.btn-amber:hover{opacity:.9}
.btn-red{background:rgba(239,68,68,.15);border-color:var(--red);color:var(--red)}
.btn-red:hover{background:rgba(239,68,68,.25)}
.btn-sm{padding:.2rem .5rem;font-size:.7rem}

/* ---- layout ---- */
.main-wrap{display:flex;flex:1;overflow:hidden}
.main-content{flex:1;overflow-y:auto;padding:1.25rem}
.sidebar{width:0;overflow:hidden;transition:width .25s ease;border-left:1px solid var(--border);
  display:flex;flex-direction:column;background:var(--card)}
.sidebar.open{width:380px}

/* ---- grid ---- */
.grid{display:grid;gap:1rem;grid-template-columns:repeat(auto-fill,minmax(460px,1fr))}
.card{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:1.25rem;
  transition:background .4s,border-color .3s}
.card.flash{border-color:var(--accent);background:var(--card-hover)}
.card-header{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:.75rem}
.card-title{font-size:.95rem;font-weight:600;word-break:break-word}
.badge{display:inline-block;padding:.1rem .5rem;border-radius:4px;font-size:.68rem;
  font-weight:600;text-transform:uppercase;letter-spacing:.03em}
.badge.approved{background:rgba(34,197,94,.15);color:var(--green)}
.badge.completed{background:rgba(168,85,247,.15);color:var(--purple)}
.badge.drafting{background:rgba(139,143,163,.15);color:var(--dim)}
.badge.in_progress,.badge.executing,.badge.promoting,.badge.planning,.badge.planned{
  background:rgba(59,130,246,.15);color:var(--blue)}
.badge.failed{background:rgba(239,68,68,.15);color:var(--red)}
.badge.all_done{background:rgba(245,158,11,.15);color:var(--amber)}
.badge.retrospecting,.badge.evolving{background:rgba(168,85,247,.15);color:var(--purple)}

/* ---- pipeline bar ---- */
.pipeline{display:flex;gap:2px;margin:.75rem 0;flex-wrap:wrap}
.stage{width:28px;height:8px;border-radius:2px;cursor:pointer;transition:transform .1s}
.stage:hover{transform:scaleY(1.8)}
.stage.done{background:var(--green)}
.stage.current{background:var(--amber);animation:pulse 1.5s infinite}
.stage.pending{background:var(--border)}
.stage.skipped{background:var(--border);opacity:.4}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.5}}
.progress-text{font-size:.75rem;color:var(--dim);margin-top:.25rem}

/* ---- issue progress ---- */
.issue-progress{margin:.5rem 0}
.issue-bar{height:6px;background:var(--border);border-radius:3px;overflow:hidden}
.issue-bar-fill{height:100%;background:var(--blue);border-radius:3px;transition:width .5s}
.issue-label{font-size:.72rem;color:var(--dim);margin-top:.2rem}

/* ---- waves ---- */
.waves{margin-top:.75rem}
.wave{border-left:2px solid var(--border);padding-left:.75rem;margin-bottom:.5rem}
.wave-label{font-size:.75rem;color:var(--dim);font-weight:600;margin-bottom:.25rem}
.packet{font-size:.8rem;padding:.15rem 0;display:flex;align-items:center;gap:.35rem}
.run-class{font-size:.65rem;padding:.05rem .3rem;border-radius:2px;
  background:rgba(99,102,241,.15);color:var(--accent)}
.linear-id{font-size:.65rem;color:var(--dim)}

/* ---- card meta / actions ---- */
.card-actions{display:flex;gap:.4rem;margin-top:.75rem;flex-wrap:wrap}
.meta{font-size:.75rem;color:var(--dim);margin-top:.5rem}
.error-banner{background:rgba(239,68,68,.1);border:1px solid rgba(239,68,68,.3);
  border-radius:4px;padding:.35rem .6rem;font-size:.75rem;color:var(--red);margin:.5rem 0}

/* ---- chat sidebar ---- */
.chat-header{display:flex;align-items:center;padding:.65rem .75rem;border-bottom:1px solid var(--border)}
.chat-header h3{font-size:.85rem;flex:1}
.chat-messages{flex:1;overflow-y:auto;padding:.75rem;display:flex;flex-direction:column;gap:.5rem}
.chat-msg{max-width:90%;padding:.45rem .65rem;border-radius:8px;font-size:.82rem;line-height:1.45;
  word-break:break-word}
.chat-msg.user{align-self:flex-end;background:var(--accent);color:#fff;border-bottom-right-radius:2px}
.chat-msg.bot{align-self:flex-start;background:var(--border);color:var(--text);border-bottom-left-radius:2px}
.chat-msg.system{align-self:center;background:transparent;color:var(--dim);font-size:.72rem;
  font-style:italic;text-align:center}
.chat-input-wrap{display:flex;padding:.5rem;border-top:1px solid var(--border);gap:.35rem}
.chat-input{flex:1;background:var(--bg);border:1px solid var(--border);border-radius:6px;
  padding:.45rem .6rem;color:var(--text);font-size:.82rem;outline:none}
.chat-input:focus{border-color:var(--accent)}
.chat-input::placeholder{color:var(--dim)}

/* ---- bottom bar ---- */
.bottom-bar{display:flex;align-items:center;gap:1.5rem;padding:.5rem 1.5rem;
  border-top:1px solid var(--border);background:var(--card);font-size:.75rem;color:var(--dim)}
.metric{display:flex;align-items:center;gap:.3rem}
.metric-value{color:var(--text);font-weight:600}
.metric-label{color:var(--dim)}

/* ---- empty state ---- */
.empty{text-align:center;padding:3rem;color:var(--dim)}

/* ---- tooltip ---- */
.tooltip{position:relative}
.tooltip:hover::after{content:attr(data-tip);position:absolute;bottom:calc(100% + 4px);
  left:50%;transform:translateX(-50%);background:#000;color:#fff;padding:.25rem .5rem;
  border-radius:4px;font-size:.7rem;white-space:nowrap;z-index:10}

/* ---- scrollbar ---- */
::-webkit-scrollbar{width:6px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
::-webkit-scrollbar-thumb:hover{background:var(--dim)}
</style>
</head>
<body>

<!-- ===== HEADER ===== -->
<div class="header">
  <h1>spec-orch <span class="tag">dashboard</span></h1>
  <div class="header-spacer"></div>
  <span class="status-dot disconnected" id="ws-dot"></span>
  <span class="header-label" id="ws-label">disconnected</span>
  <button class="btn" onclick="load()">Refresh</button>
  <button class="btn btn-primary" id="btn-new-mission" onclick="openNewMission()">+ New Mission</button>
</div>

<!-- ===== MAIN ===== -->
<div class="main-wrap">
  <div class="main-content" id="main">
    <div id="root" class="grid"></div>
  </div>

  <!-- ===== SIDEBAR CHAT ===== -->
  <div class="sidebar" id="sidebar">
    <div class="chat-header">
      <h3 id="chat-title">Discuss</h3>
      <button class="btn btn-sm" onclick="closeSidebar()">&times;</button>
    </div>
    <div class="chat-messages" id="chat-messages"></div>
    <div class="chat-input-wrap">
      <input class="chat-input" id="chat-input" placeholder="Type a message… (@freeze, @approve)"
             onkeydown="if(event.key==='Enter')sendChat()"/>
      <button class="btn btn-primary btn-sm" onclick="sendChat()">Send</button>
    </div>
  </div>
</div>

<!-- ===== EVOLUTION PANEL ===== -->
<div class="bottom-bar" id="bottom-bar" style="cursor:pointer" onclick="toggleEvoPanel()">
  <div class="metric"><span class="metric-label">Prompts:</span><span class="metric-value" id="m-prompts">—</span></div>
  <div class="metric"><span class="metric-label">Hints:</span><span class="metric-value" id="m-hints">—</span></div>
  <div class="metric"><span class="metric-label">Policies:</span><span class="metric-value" id="m-policies">—</span></div>
  <div class="metric"><span class="metric-label">Success:</span><span class="metric-value" id="m-success">—</span></div>
  <div class="metric"><span class="metric-label">Runs:</span><span class="metric-value" id="m-runs">—</span></div>
  <div style="flex:1"></div>
  <span style="font-size:.7rem;color:var(--dim)">▼ Evolution Details</span>
  <span id="event-log" style="font-size:.7rem;color:var(--dim);max-width:30%;overflow:hidden;
    text-overflow:ellipsis;white-space:nowrap;margin-left:.5rem"></span>
</div>
<div id="evo-panel" style="display:none;background:var(--card);border-top:1px solid var(--border);padding:1rem;max-height:50vh;overflow-y:auto">
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem">
    <div>
      <h3 style="margin:0 0 .5rem;color:var(--accent);font-size:.9rem">Prompt Variants</h3>
      <div id="evo-variants" style="font-size:.8rem"></div>
    </div>
    <div>
      <h3 style="margin:0 0 .5rem;color:var(--accent);font-size:.9rem">Success Rate Trend</h3>
      <div id="evo-trend" style="height:80px;display:flex;align-items:flex-end;gap:2px"></div>
      <div id="evo-trend-labels" style="font-size:.65rem;color:var(--dim);margin-top:.25rem"></div>
    </div>
  </div>
</div>

<script>
/* ===== STATE ===== */
let missions = [];
let lifecycleStates = {};
let ws = null;
let wsRetryMs = 1000;
let chatThreadId = null;
let chatMessages = [];

/* ===== DATA LOADING ===== */
async function load() {
  try {
    const [mRes, lcRes] = await Promise.all([
      fetch('/api/missions'),
      fetch('/api/lifecycle').catch(() => ({ok:false}))
    ]);
    missions = await mRes.json();
    if (lcRes.ok) {
      lifecycleStates = await lcRes.json();
    }
    renderMissions();
  } catch(e) {
    console.error('load failed', e);
  }
}

let evoPanelOpen = false;
function toggleEvoPanel() {
  evoPanelOpen = !evoPanelOpen;
  document.getElementById('evo-panel').style.display = evoPanelOpen ? 'block' : 'none';
}

async function loadEvolution() {
  try {
    const r = await fetch('/api/evolution');
    if (!r.ok) return;
    const d = await r.json();
    document.getElementById('m-prompts').textContent = d.prompt_variants ?? '—';
    document.getElementById('m-hints').textContent = d.scoper_hints ?? '—';
    document.getElementById('m-policies').textContent = d.policies ?? '—';
    document.getElementById('m-success').textContent = d.success_rate != null ? d.success_rate + '%' : '—';
    document.getElementById('m-runs').textContent = d.total_runs ?? '—';
    renderEvoVariants(d.variants || []);
    renderEvoTrend(d.run_trend || []);
  } catch(e) {}
}

function renderEvoVariants(variants) {
  const el = document.getElementById('evo-variants');
  if (!el) return;
  if (variants.length === 0) { el.innerHTML = '<span style="color:var(--dim)">No prompt variants yet</span>'; return; }
  el.innerHTML = variants.map(v => {
    const vid = escHtml(v.variant_id);
    const rat = escHtml(v.rationale || '');
    const badge = v.is_active ? '<span style="color:#4ade80;font-weight:bold">● active</span>' : v.is_candidate ? '<span style="color:#facc15">◎ candidate</span>' : '<span style="color:var(--dim)">○</span>';
    const pct = Number(v.success_rate) || 0;
    const bar = v.total_runs > 0 ? `<div style="display:inline-block;width:60px;height:8px;background:var(--border);border-radius:4px;overflow:hidden;vertical-align:middle"><div style="width:${pct}%;height:100%;background:${pct>=70?'#4ade80':pct>=40?'#facc15':'#f87171'}"></div></div>` : '';
    const ratSnip = rat.length > 50 ? rat.slice(0,50) + '…' : rat;
    return `<div style="padding:.25rem 0;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:.5rem">${badge} <strong>${vid}</strong> ${bar} <span>${pct}%</span> <span style="color:var(--dim)">(${Number(v.successful_runs)||0}/${Number(v.total_runs)||0})</span>${rat ? `<span style="color:var(--dim);font-size:.7rem;margin-left:auto" title="${rat}">${ratSnip}</span>` : ''}</div>`;
  }).join('');
}

function renderEvoTrend(trend) {
  const el = document.getElementById('evo-trend');
  const labels = document.getElementById('evo-trend-labels');
  if (!el) return;
  if (trend.length === 0) { el.innerHTML = '<span style="color:var(--dim);font-size:.8rem">No run data yet</span>'; return; }
  const maxH = 70;
  el.innerHTML = trend.map(t => {
    const h = Math.max(3, (t.cumulative_rate / 100) * maxH);
    const color = t.ok ? '#4ade80' : '#f87171';
    const runName = escHtml(t.run);
    return `<div title="${runName}: ${t.cumulative_rate}%" style="width:${Math.max(4, Math.floor(200/trend.length))}px;height:${h}px;background:${color};border-radius:2px 2px 0 0;transition:height .3s"></div>`;
  }).join('');
  if (labels && trend.length > 0) {
    const last = trend[trend.length - 1];
    labels.textContent = `${trend.length} runs | latest: ${last.cumulative_rate}% cumulative`;
  }
}

/* ===== RENDER ===== */
function phaseFor(m) {
  const lc = lifecycleStates[m.mission_id];
  return lc ? lc.phase : m.status;
}

function renderMissions() {
  const root = document.getElementById('root');
  if (!missions.length) {
    root.innerHTML = '<div class="empty">No missions found. Click <b>+ New Mission</b> to start.</div>';
    return;
  }
  root.innerHTML = missions.map(m => {
    const phase = phaseFor(m);
    const lc = lifecycleStates[m.mission_id];
    const stages = m.pipeline.map(s =>
      `<div class="stage ${s.status} tooltip" data-tip="${s.label}"></div>`).join('');

    let actionsHtml = '';
    if (phase === 'approved' || phase === 'drafting') {
      actionsHtml = `<button class="btn btn-green btn-sm" onclick="approveGo('${m.mission_id}')">Approve &amp; Go</button>`;
    } else if (phase === 'failed') {
      const errHtml = lc && lc.error
        ? `<div class="error-banner">${escHtml(lc.error)}</div>`
        : '';
      actionsHtml = errHtml +
        `<button class="btn btn-red btn-sm" onclick="retryMission('${m.mission_id}')">Retry</button>`;
    } else if (phase === 'completed' || phase === 'all_done') {
      actionsHtml = `<button class="btn btn-sm" onclick="alert('Retrospective coming soon')">View Retrospective</button>`;
    }

    let issueBar = '';
    if (phase === 'executing' && lc) {
      const done = (lc.completed_issues || []).length;
      const total = (lc.issue_ids || []).length || 1;
      const pct = Math.round(done / total * 100);
      issueBar = `<div class="issue-progress">
        <div class="issue-bar"><div class="issue-bar-fill" style="width:${pct}%"></div></div>
        <div class="issue-label">${done}/${total} issues completed</div>
      </div>`;
    }

    let wavesHtml = '';
    if (m.plan) {
      wavesHtml = '<div class="waves">' + m.plan.waves.map(w =>
        `<div class="wave"><div class="wave-label">Wave ${w.wave_number}: ${w.description}</div>` +
        w.packets.map(p =>
          `<div class="packet"><span class="run-class">${p.run_class}</span> ${escHtml(p.title)}` +
          (p.linear_issue_id ? ` <span class="linear-id">${p.linear_issue_id}</span>` : '') +
          `</div>`).join('') +
        `</div>`).join('') + '</div>';
    }

    return `<div class="card" id="card-${m.mission_id}" data-mid="${m.mission_id}">
      <div class="card-header">
        <div class="card-title">${escHtml(m.title)}</div>
        <span class="badge ${phase}">${phase}</span>
      </div>
      <div class="pipeline">${stages}</div>
      <div class="progress-text">${m.pipeline_done}/${m.pipeline_total} stages complete</div>
      ${issueBar}
      ${wavesHtml}
      <div class="card-actions">${actionsHtml}
        <button class="btn btn-sm" onclick="openDiscuss('${m.mission_id}')">Discuss</button>
      </div>
      <div class="meta">${m.mission_id}</div>
    </div>`;
  }).join('');
}

function escHtml(s) {
  const d = document.createElement('div');
  d.textContent = s || '';
  return d.innerHTML;
}

/* ===== ACTIONS ===== */
async function approveGo(mid) {
  const btn = event.target;
  btn.disabled = true; btn.textContent = 'Starting…';
  try {
    const r = await fetch(`/api/missions/${mid}/approve`, {method:'POST'});
    const d = await r.json();
    if (!r.ok) alert(d.error || 'Failed');
    await load();
  } catch(e) { alert('Error: ' + e.message); }
  finally { btn.disabled = false; btn.textContent = 'Approve & Go'; }
}

async function retryMission(mid) {
  const btn = event.target;
  btn.disabled = true; btn.textContent = 'Retrying…';
  try {
    const r = await fetch(`/api/missions/${mid}/retry`, {method:'POST'});
    const d = await r.json();
    if (!r.ok) alert(d.error || 'Failed');
    await load();
  } catch(e) { alert('Error: ' + e.message); }
  finally { btn.disabled = false; btn.textContent = 'Retry'; }
}

/* ===== CHAT / DISCUSS ===== */
function openSidebar() {
  document.getElementById('sidebar').classList.add('open');
}
function closeSidebar() {
  document.getElementById('sidebar').classList.remove('open');
}

function openNewMission() {
  chatThreadId = 'web-' + crypto.randomUUID().slice(0,8);
  chatMessages = [];
  renderChat();
  document.getElementById('chat-title').textContent = 'New Mission';
  openSidebar();
  addSystemMsg('Start describing your feature. Use @freeze to create a spec, @approve to approve.');
}

function openDiscuss(missionId) {
  chatThreadId = 'discuss-' + missionId;
  chatMessages = [];
  renderChat();
  document.getElementById('chat-title').textContent = 'Discuss: ' + missionId.slice(0,12);
  openSidebar();
  addSystemMsg('Discussing mission ' + missionId);
}

function addSystemMsg(text) {
  chatMessages.push({role:'system', text});
  renderChat();
}

function renderChat() {
  const el = document.getElementById('chat-messages');
  el.innerHTML = chatMessages.map(m =>
    `<div class="chat-msg ${m.role}">${escHtml(m.text)}</div>`
  ).join('');
  el.scrollTop = el.scrollHeight;
}

async function sendChat() {
  const input = document.getElementById('chat-input');
  const text = input.value.trim();
  if (!text || !chatThreadId) return;
  input.value = '';

  chatMessages.push({role:'user', text});
  renderChat();

  try {
    const r = await fetch('/api/discuss', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({thread_id: chatThreadId, message: text})
    });
    const d = await r.json();
    const reply = d.reply || d.error || 'No response';
    chatMessages.push({role:'bot', text: reply});
    renderChat();

    if (reply.toLowerCase().includes('frozen') || reply.toLowerCase().includes('spec frozen')) {
      addSystemMsg('Spec frozen. Refreshing missions…');
      closeSidebar();
      await load();
    }
  } catch(e) {
    chatMessages.push({role:'bot', text: 'Error: ' + e.message});
    renderChat();
  }
}

/* ===== WEBSOCKET ===== */
function connectWs() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  ws = new WebSocket(`${proto}//${location.host}/ws`);

  ws.onopen = () => {
    wsRetryMs = 1000;
    document.getElementById('ws-dot').className = 'status-dot connected';
    document.getElementById('ws-label').textContent = 'live';
  };

  ws.onmessage = (ev) => {
    try {
      const evt = JSON.parse(ev.data);
      handleEvent(evt);
    } catch(e) {}
  };

  ws.onclose = () => {
    document.getElementById('ws-dot').className = 'status-dot disconnected';
    document.getElementById('ws-label').textContent = 'disconnected';
    setTimeout(() => { wsRetryMs = Math.min(wsRetryMs * 2, 30000); connectWs(); }, wsRetryMs);
  };

  ws.onerror = () => { ws.close(); };
}

function handleEvent(evt) {
  const logEl = document.getElementById('event-log');
  logEl.textContent = `${evt.topic}: ${JSON.stringify(evt.payload).slice(0,80)}`;

  if (evt.topic === 'mission.state' || evt.topic === 'issue.state') {
    const mid = evt.payload.mission_id;
    if (mid) {
      const card = document.getElementById('card-' + mid);
      if (card) {
        card.classList.add('flash');
        setTimeout(() => card.classList.remove('flash'), 1500);
      }
      if (evt.payload.mission_id) {
        loadSingleMission(mid);
      }
    }
    load();
  }
}

async function loadSingleMission(mid) {
  try {
    const r = await fetch(`/api/missions/${mid}`);
    if (!r.ok) return;
    const m = await r.json();
    const idx = missions.findIndex(x => x.mission_id === mid);
    if (idx >= 0) missions[idx] = m;
    const lcr = await fetch('/api/lifecycle').catch(() => ({ok:false}));
    if (lcr.ok) lifecycleStates = await lcr.json();
    renderMissions();
  } catch(e) {}
}

/* ===== INIT ===== */
load();
loadEvolution();
connectWs();
setInterval(load, 15000);
setInterval(loadEvolution, 30000);
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# FastAPI application factory
# ---------------------------------------------------------------------------


def create_app(repo_root: Path | None = None) -> Any:
    """Create the FastAPI app. Requires ``pip install fastapi uvicorn``."""
    from fastapi import Body, FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

    root = repo_root or Path(".")
    app = FastAPI(title="spec-orch dashboard")

    # ---- pages ----

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return DASHBOARD_HTML

    # ---- existing read endpoints ----

    @app.get("/api/missions")
    async def api_missions() -> JSONResponse:
        return JSONResponse(_gather_missions(root))

    @app.get("/api/missions/{mission_id}")
    async def api_mission(mission_id: str) -> JSONResponse:
        missions = _gather_missions(root)
        for m in missions:
            if m["mission_id"] == mission_id:
                return JSONResponse(m)
        return JSONResponse({"error": "not found"}, status_code=404)

    @app.get("/api/missions/{mission_id}/spec")
    async def api_mission_spec(mission_id: str) -> PlainTextResponse:
        content = _get_spec_content(root, mission_id)
        if content is None:
            return PlainTextResponse("not found", status_code=404)
        return PlainTextResponse(content)

    @app.get("/api/runs")
    async def api_runs() -> JSONResponse:
        return JSONResponse(_gather_run_history(root))

    @app.get("/api/health")
    async def api_health() -> JSONResponse:
        return JSONResponse(
            {
                "status": "ok",
                "repo_root": str(root),
                "missions": len(_gather_missions(root)),
            }
        )

    @app.get("/api/events")
    async def api_events(
        issue_id: str | None = None,
        run_id: str | None = None,
        topic: str | None = None,
        limit: int = 100,
    ) -> JSONResponse:
        bus = _get_event_bus()
        if bus is None:
            return JSONResponse([])
        parsed_topic = None
        if topic:
            try:
                from spec_orch.services.event_bus import EventTopic

                parsed_topic = EventTopic(topic)
            except Exception:
                parsed_topic = None
        events = bus.query_history(
            topic=parsed_topic,
            issue_id=issue_id,
            run_id=run_id,
            limit=limit,
        )
        return JSONResponse(
            [
                {
                    "topic": ev.topic.value if hasattr(ev.topic, "value") else str(ev.topic),
                    "payload": ev.payload,
                    "timestamp": ev.timestamp,
                    "source": ev.source,
                }
                for ev in events
            ]
        )

    # ---- lifecycle & evolution endpoints ----

    @app.get("/api/lifecycle")
    async def api_lifecycle() -> JSONResponse:
        return JSONResponse(_gather_lifecycle_states(root))

    @app.get("/api/evolution")
    async def api_evolution() -> JSONResponse:
        return JSONResponse(_gather_evolution_metrics(root))

    # ---- action endpoints ----

    @app.post("/api/missions/{mission_id}/approve")
    async def api_approve(mission_id: str) -> JSONResponse:
        mgr = _get_lifecycle_manager(root)
        if mgr is None:
            return JSONResponse({"error": "Lifecycle manager unavailable"}, status_code=503)
        try:
            mgr.begin_tracking(mission_id)
            state = mgr.auto_advance(mission_id)
            return JSONResponse({"ok": True, "phase": state.phase.value if state else "unknown"})
        except Exception:
            logger.exception("approve failed for %s", mission_id)
            return JSONResponse({"error": "Mission approval failed"}, status_code=500)

    @app.post("/api/missions/{mission_id}/retry")
    async def api_retry(mission_id: str) -> JSONResponse:
        mgr = _get_lifecycle_manager(root)
        if mgr is None:
            return JSONResponse({"error": "Lifecycle manager unavailable"}, status_code=503)
        try:
            mgr.retry(mission_id)
            state = mgr.auto_advance(mission_id)
            return JSONResponse({"ok": True, "phase": state.phase.value if state else "unknown"})
        except Exception:
            logger.exception("retry failed for %s", mission_id)
            return JSONResponse({"error": "Mission retry failed"}, status_code=500)

    @app.post("/api/discuss")
    async def api_discuss(
        thread_id: str = Body(...),
        message: str = Body(...),
    ) -> JSONResponse:
        svc = _get_conversation_service(root)
        if svc is None:
            return JSONResponse({"error": "Conversation service unavailable"}, status_code=503)
        try:
            from spec_orch.domain.models import ConversationMessage

            msg = ConversationMessage(
                message_id=f"web-{uuid.uuid4().hex[:8]}",
                thread_id=thread_id,
                sender="user",
                content=message,
                timestamp=datetime.now(UTC).isoformat(),
                channel="web-dashboard",
            )
            reply = svc.handle_message(msg)
            return JSONResponse({"reply": reply or ""})
        except Exception:
            logger.exception("discuss failed")
            return JSONResponse({"error": "Discussion request failed"}, status_code=500)

    @app.post("/api/btw")
    async def api_btw(
        issue_id: str = Body(...),
        message: str = Body(...),
    ) -> JSONResponse:
        mgr = _get_lifecycle_manager(root)
        if mgr is None:
            return JSONResponse({"error": "Lifecycle manager unavailable"}, status_code=503)
        try:
            ok = mgr.inject_btw(issue_id, message, channel="web-dashboard")
            return JSONResponse({"ok": ok})
        except Exception:
            logger.exception("btw injection failed")
            return JSONResponse({"error": "BTW injection failed"}, status_code=500)

    # ---- websocket ----

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await websocket.accept()
        bus = _get_event_bus()
        if bus is None:
            await websocket.send_json(
                {
                    "topic": "system",
                    "payload": {"message": "EventBus unavailable"},
                    "timestamp": 0,
                    "source": "dashboard",
                }
            )
            await websocket.close()
            return

        queue = bus.create_async_queue()
        try:
            while True:
                event = await queue.get()
                await websocket.send_json(
                    {
                        "topic": event.topic.value
                        if hasattr(event.topic, "value")
                        else str(event.topic),
                        "payload": event.payload,
                        "timestamp": event.timestamp,
                        "source": event.source,
                    }
                )
        except WebSocketDisconnect:
            pass
        except Exception:
            logger.exception("Error in websocket endpoint")
        finally:
            bus.remove_async_queue(queue)

    return app
