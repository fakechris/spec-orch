# ruff: noqa: E501

"""Lightweight web dashboard for spec-orch — pipeline status and execution results.

Start with:  spec-orch dashboard
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .approvals import (
    _record_approval_action as _approval_record_approval_action,
)
from .approvals import (
    _resolve_approval_action as _approval_resolve_approval_action,
)
from .control import _control_degradation as _control_control_degradation
from .control import _control_eval as _control_control_eval
from .control import _control_eval_trigger as _control_control_eval_trigger
from .control import _control_overview as _control_control_overview
from .control import _control_reactions as _control_control_reactions
from .control import _control_skills as _control_control_skills
from .control import _gather_evolution_metrics as _control_gather_evolution_metrics
from .control import _gather_run_history as _control_gather_run_history
from .control import _get_spec_content as _control_get_spec_content
from .launcher import _approve_and_plan_mission as _launcher_approve_and_plan_mission
from .launcher import _bind_linear_issue_to_mission as _launcher_bind_linear_issue_to_mission
from .launcher import _create_linear_issue_for_mission as _launcher_create_linear_issue_for_mission
from .launcher import _create_mission_draft as _launcher_create_mission_draft
from .launcher import _gather_launcher_readiness as _launcher_gather_launcher_readiness
from .launcher import _launch_mission as _launcher_launch_mission
from .missions import _gather_inbox as _missions_gather_inbox
from .missions import _gather_lifecycle_states as _missions_gather_lifecycle_states
from .missions import _gather_mission_detail as _missions_gather_mission_detail
from .missions import _gather_missions as _missions_gather_missions
from .surfaces import _gather_approval_queue as _surfaces_gather_approval_queue
from .surfaces import _gather_mission_acceptance_review as _surfaces_gather_mission_acceptance
from .surfaces import _gather_mission_costs as _surfaces_gather_mission_costs
from .surfaces import _gather_mission_visual_qa as _surfaces_gather_mission_visual_qa
from .transcript import _gather_packet_transcript as _transcript_gather_packet_transcript
from .transcript import (
    _gather_round_evidence_blocks as _transcript_gather_round_evidence_blocks,
)
from .transcript import _group_transcript_blocks as _transcript_group_transcript_blocks
from .transcript import _transcript_block_from_entry as _transcript_block_from_entry_impl

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


_gather_packet_transcript = _transcript_gather_packet_transcript
_transcript_block_from_entry = _transcript_block_from_entry_impl
_group_transcript_blocks = _transcript_group_transcript_blocks
_gather_round_evidence_blocks = _transcript_gather_round_evidence_blocks
_gather_missions = _missions_gather_missions
_gather_inbox = _missions_gather_inbox
_gather_mission_detail = _missions_gather_mission_detail
_gather_lifecycle_states = _missions_gather_lifecycle_states
_gather_launcher_readiness = _launcher_gather_launcher_readiness
_create_mission_draft = _launcher_create_mission_draft
_approve_and_plan_mission = _launcher_approve_and_plan_mission
_create_linear_issue_for_mission = _launcher_create_linear_issue_for_mission
_bind_linear_issue_to_mission = _launcher_bind_linear_issue_to_mission
_launch_mission = _launcher_launch_mission
_gather_approval_queue = _surfaces_gather_approval_queue
_gather_mission_acceptance_review = _surfaces_gather_mission_acceptance
_gather_mission_visual_qa = _surfaces_gather_mission_visual_qa
_gather_mission_costs = _surfaces_gather_mission_costs
_record_approval_action = _approval_record_approval_action
_resolve_approval_action = _approval_resolve_approval_action
_gather_evolution_metrics = _control_gather_evolution_metrics
_control_overview = _control_control_overview
_control_skills = _control_control_skills
_control_eval = _control_control_eval
_control_eval_trigger = _control_control_eval_trigger
_control_reactions = _control_control_reactions
_control_degradation = _control_control_degradation
_gather_run_history = _control_gather_run_history
_get_spec_content = _control_get_spec_content


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
<link rel="stylesheet" href="/static/operator-console.css"/>
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
.btn-primary:hover{background:#5458e8;border-color:#5458e8;transform:translateY(-1px);box-shadow:0 8px 20px rgba(99,102,241,.25)}
.btn-green{background:var(--green);border-color:var(--green);color:#fff}
.btn-green:hover{background:#1fb255;border-color:#1fb255;transform:translateY(-1px);box-shadow:0 8px 20px rgba(34,197,94,.25)}
.btn-amber{background:var(--amber);border-color:var(--amber);color:#000}
.btn-amber:hover{opacity:.9;transform:translateY(-1px)}
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
.sidebar-panel{display:none;flex:1;min-height:0}
.sidebar-panel.active{display:flex;flex-direction:column}
.launcher-panel{padding:.75rem;gap:.75rem;overflow-y:auto}
.launcher-section{display:flex;flex-direction:column;gap:.35rem}
.launcher-section label{font-size:.72rem;color:var(--dim);font-weight:600}
.launcher-input,.launcher-textarea{width:100%;background:var(--bg);border:1px solid var(--border);border-radius:6px;padding:.5rem .6rem;color:var(--text);font-size:.8rem;outline:none}
.launcher-input:focus,.launcher-textarea:focus{border-color:var(--accent)}
.launcher-textarea{min-height:88px;resize:vertical;font-family:inherit}
.launcher-readiness,.launcher-status{border:1px solid var(--border);border-radius:8px;padding:.6rem .7rem;background:rgba(255,255,255,.02)}
.launcher-status{transition:border-color .16s ease,background .16s ease,color .16s ease,box-shadow .16s ease}
.launcher-status[data-tone="working"]{border-color:rgba(99,102,241,.45);background:rgba(99,102,241,.10);color:var(--text)}
.launcher-status[data-tone="success"]{border-color:rgba(34,197,94,.5);background:rgba(34,197,94,.12);color:#d8ffe6}
.launcher-status[data-tone="failed"]{border-color:rgba(239,68,68,.5);background:rgba(239,68,68,.10);color:#ffd7d7}
.launcher-readiness-item{display:flex;justify-content:space-between;gap:.5rem;font-size:.75rem;padding:.2rem 0}
.launcher-readiness-state.ready{color:var(--green)}
.launcher-readiness-state.missing{color:var(--amber)}
.launcher-actions{display:grid;grid-template-columns:1fr 1fr;gap:.45rem}
.launcher-actions .btn{width:100%;transition:transform .14s ease,background .14s ease,border-color .14s ease,box-shadow .14s ease,opacity .14s ease}
.launcher-actions .btn:not(.btn-primary){background:transparent;border-color:var(--border);color:var(--text)}
.launcher-actions .btn:not(.btn-primary):hover{border-color:var(--accent);background:rgba(99,102,241,.08);transform:translateY(-1px);box-shadow:0 8px 18px rgba(15,23,42,.16)}
.launcher-actions .btn:hover{cursor:pointer}
.launcher-actions .btn.is-pending{opacity:.72;cursor:progress;pointer-events:none;transform:none !important;box-shadow:none !important}
.launcher-actions .btn.is-complete{border-color:rgba(34,197,94,.55);background:rgba(34,197,94,.14);color:#d8ffe6}
.launcher-actions .btn.is-failed{border-color:rgba(239,68,68,.55);background:rgba(239,68,68,.12);color:#ffd7d7}
.launcher-actions .btn .btn-meta{display:block;font-size:.66rem;color:var(--dim);margin-top:.12rem}
.launcher-actions .btn.is-pending .btn-meta,.launcher-actions .btn.is-complete .btn-meta,.launcher-actions .btn.is-failed .btn-meta{color:inherit;opacity:.82}

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
  <button class="btn btn-primary" id="btn-new-mission" data-automation-target="open-launcher" onclick="openNewMission()">+ New Mission</button>
</div>

<!-- ===== MAIN ===== -->
<div class="main-wrap">
  <div class="main-content" id="main">
    <div id="operator-shell" class="operator-shell">
      <aside class="operator-pane operator-nav">
        <div class="operator-nav-header">
          <h2>Mission Control</h2>
        </div>
        <div class="operator-nav-modes">
          <button class="operator-mode active" id="operator-mode-inbox" data-automation-target="operator-mode" data-mode-key="inbox" data-active="true" type="button" onclick="setOperatorMode('inbox')"><span id="inbox-attention-chip">Needs Attention</span></button>
          <button class="operator-mode" id="operator-mode-missions" data-automation-target="operator-mode" data-mode-key="missions" data-active="false" type="button" onclick="setOperatorMode('missions')">All Missions</button>
          <button class="operator-mode" id="operator-mode-approvals" data-automation-target="operator-mode" data-mode-key="approvals" data-active="false" type="button" onclick="setOperatorMode('approvals')">Decision Queue</button>
          <button class="operator-mode" id="operator-mode-evidence" data-automation-target="operator-mode" data-mode-key="evidence" data-active="false" type="button" onclick="setOperatorMode('evidence')">Deep Evidence</button>
        </div>
        <div id="operator-nav-context" class="operator-nav-context"></div>
        <div id="inbox-list" class="mission-list"></div>
        <div id="mission-list" class="mission-list"></div>
      </aside>

      <section class="operator-pane operator-main">
        <div class="operator-main-header">
          <h2>Mission Detail</h2>
        </div>
        <div id="mission-detail-view" class="mission-detail-view">
          <div id="packet-transcript-view" class="transcript-list"></div>
        </div>
      </section>

      <aside class="operator-pane operator-context">
        <div class="operator-context-header">
          <h2>Context Rail</h2>
        </div>
        <div id="operator-context-rail" class="mission-detail-view operator-context-rail">
          <div id="transcript-inspector"></div>
        </div>
      </aside>
    </div>
  </div>

  <!-- ===== SIDEBAR CHAT ===== -->
  <div class="sidebar" id="sidebar">
    <div class="chat-header">
      <h3 id="chat-title">Discuss</h3>
      <button class="btn btn-sm" onclick="closeSidebar()">&times;</button>
    </div>
    <div id="launcher-panel" class="sidebar-panel launcher-panel">
      <div id="launcher-readiness" class="launcher-readiness">Checking environment…</div>
      <div id="launcher-status" class="launcher-status" data-automation-target="launcher-status">Use this panel to create, plan, bind, and launch a mission.</div>
      <div class="launcher-section">
        <label for="launcher-title">Mission title</label>
        <input id="launcher-title" class="launcher-input" data-automation-target="launcher-field" data-field-key="title" placeholder="Operator Console Dogfood Smoke"/>
      </div>
      <div class="launcher-section">
        <label for="launcher-mission-id">Mission id (optional)</label>
        <input id="launcher-mission-id" class="launcher-input" data-automation-target="launcher-field" data-field-key="mission-id" placeholder="operator-console-dogfood-smoke"/>
      </div>
      <div class="launcher-section">
        <label for="launcher-intent">Intent</label>
        <textarea id="launcher-intent" class="launcher-textarea" data-automation-target="launcher-field" data-field-key="intent" placeholder="Validate one real supervised mission through the operator console."></textarea>
      </div>
      <div class="launcher-section">
        <label for="launcher-acceptance">Acceptance criteria (one per line)</label>
        <textarea id="launcher-acceptance" class="launcher-textarea" data-automation-target="launcher-field" data-field-key="acceptance" placeholder="daemon picks up this issue as a mission&#10;dashboard shows Mission Detail / Transcript / Approval / Visual QA / Costs"></textarea>
      </div>
      <div class="launcher-section">
        <label for="launcher-constraints">Constraints (one per line)</label>
        <textarea id="launcher-constraints" class="launcher-textarea" data-automation-target="launcher-field" data-field-key="constraints" placeholder="Keep this run small&#10;Prefer 1 wave / 1-2 packets"></textarea>
      </div>
      <div class="launcher-section">
        <label for="launcher-linear-title">Linear title</label>
        <input id="launcher-linear-title" class="launcher-input" data-automation-target="launcher-field" data-field-key="linear-title" placeholder="Real supervised mission dogfood"/>
      </div>
      <div class="launcher-section">
        <label for="launcher-linear-description">Linear description</label>
        <textarea id="launcher-linear-description" class="launcher-textarea" data-automation-target="launcher-field" data-field-key="linear-description" placeholder="Validate one real supervised mission through the operator console."></textarea>
      </div>
      <div class="launcher-section">
        <label for="launcher-linear-issue-id">Bind existing Linear issue (optional)</label>
        <input id="launcher-linear-issue-id" class="launcher-input" data-automation-target="launcher-field" data-field-key="linear-issue-id" placeholder="SON-241"/>
      </div>
      <div class="launcher-actions">
        <button class="btn" type="button" data-automation-target="launcher-action" data-launcher-action="create-draft" onclick="createMissionDraft()">Create Draft</button>
        <button class="btn" type="button" data-automation-target="launcher-action" data-launcher-action="approve-plan" onclick="approveAndPlanMission()">Approve &amp; Plan</button>
        <button class="btn" type="button" data-automation-target="launcher-action" data-launcher-action="linear-create" onclick="createLinearIssueForMission()">Create Linear Issue</button>
        <button class="btn" type="button" data-automation-target="launcher-action" data-launcher-action="linear-bind" onclick="bindLinearIssueForMission()">Bind Existing Issue</button>
      </div>
      <div class="launcher-actions">
        <button class="btn btn-primary" type="button" data-automation-target="launcher-action" data-launcher-action="launch" onclick="launchMissionFromLauncher()">Launch Mission</button>
        <button class="btn" type="button" data-automation-target="launcher-action" data-launcher-action="refresh-readiness" onclick="loadLauncherReadiness()">Refresh Readiness</button>
      </div>
    </div>
    <div id="discuss-panel" class="sidebar-panel active">
      <div class="chat-messages" id="chat-messages"></div>
      <div class="chat-input-wrap">
        <input class="chat-input" id="chat-input" placeholder="Type a message… (@freeze, @approve)"
               onkeydown="if(event.key==='Enter')sendChat()"/>
        <button class="btn btn-primary btn-sm" onclick="sendChat()">Send</button>
      </div>
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

<script src="/static/operator-console.js"></script>
<script>
/* ===== STATE ===== */
let missions = [];
let lifecycleStates = {};
let ws = null;
let wsRetryMs = 1000;
let chatThreadId = null;
let chatMessages = [];
let selectedOperatorMode = 'inbox';
let selectedMissionId = null;
let selectedMissionDetail = null;
let selectedMissionTab = 'overview';
let selectedMissionVisualQa = null;
let selectedMissionAcceptance = null;
let selectedMissionCosts = null;
let selectedPacketId = null;
let pendingRoutePacketId = null;
let selectedPacketTranscript = null;
let selectedTranscriptFilter = 'all';
let selectedTranscriptBlockIndex = null;
let inboxSummary = {counts:{approvals:0, paused:0, failed:0, attention:0}, items:[]};
let approvalQueue = {counts:{pending:0, missions:0}, items:[]};
let approvalActionStates = {};
let selectedApprovalMissionIds = [];
let approvalBatchState = null;
let sidebarMode = 'discuss';
let launcherState = {
  missionId: '',
  linearIssueId: '',
  readiness: null,
  activeAction: null,
};

function parseOperatorRoute(route) {
  try {
    const url = new URL(route, window.location.origin);
    return {
      missionId: url.searchParams.get('mission'),
      mode: url.searchParams.get('mode'),
      tab: url.searchParams.get('tab'),
      packetId: url.searchParams.get('packet'),
    };
  } catch (error) {
    return null;
  }
}

function syncOperatorRoute() {
  const url = new URL(window.location.href);
  if (selectedMissionId) {
    url.searchParams.set('mission', selectedMissionId);
  } else {
    url.searchParams.delete('mission');
  }
  url.searchParams.set('mode', selectedOperatorMode);
  const activeTab = selectedOperatorMode === 'evidence' ? 'transcript' : selectedMissionTab;
  url.searchParams.set('tab', activeTab);
  if (selectedPacketId && activeTab === 'transcript') {
    url.searchParams.set('packet', selectedPacketId);
  } else {
    url.searchParams.delete('packet');
  }
  window.history.replaceState({}, '', `${url.pathname}?${url.searchParams.toString()}`);
}

async function navigateOperatorRoute(route) {
  const parsed = parseOperatorRoute(route);
  if (!parsed) return false;
  if (parsed.mode) {
    selectedOperatorMode = parsed.mode;
  }
  if (parsed.tab) {
    selectedMissionTab = parsed.tab === 'visual' ? 'visual-qa' : parsed.tab;
  }
  pendingRoutePacketId = parsed.packetId || null;
  renderOperatorModes();
  if (parsed.missionId) {
    await selectMission(parsed.missionId, {force:true});
  } else {
    await load();
  }
  return true;
}

function hydrateInitialRoute() {
  const parsed = parseOperatorRoute(window.location.href);
  if (!parsed) return;
  if (parsed.mode) selectedOperatorMode = parsed.mode;
  if (parsed.tab) selectedMissionTab = parsed.tab === 'visual' ? 'visual-qa' : parsed.tab;
  if (parsed.missionId) selectedMissionId = parsed.missionId;
  pendingRoutePacketId = parsed.packetId || null;
}

/* ===== DATA LOADING ===== */
async function load() {
  try {
    const [mRes, lcRes, inboxRes, approvalsRes] = await Promise.all([
      fetch('/api/missions'),
      fetch('/api/lifecycle').catch(() => ({ok:false})),
      fetch('/api/inbox').catch(() => ({ok:false})),
      fetch('/api/approvals').catch(() => ({ok:false}))
    ]);
    missions = await mRes.json();
    if (lcRes.ok) {
      lifecycleStates = await lcRes.json();
    }
    if (inboxRes.ok) {
      inboxSummary = await inboxRes.json();
    }
    if (approvalsRes.ok) {
      approvalQueue = await approvalsRes.json();
      selectedApprovalMissionIds = selectedApprovalMissionIds.filter(mid =>
        (approvalQueue.items || []).some(item => item.mission_id === mid)
      );
    }
    renderMissions();
    await ensureMissionSelection();
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

function phaseMeta(phase) {
  const normalized = String(phase || 'unknown');
  if (normalized === 'approved') {
    return {label: 'Ready to plan', hint: 'The mission spec is frozen but no execution plan is running yet.'};
  }
  if (normalized === 'planning') {
    return {label: 'Planning', hint: 'Spec-orch is generating or refreshing the execution plan.'};
  }
  if (normalized === 'planned') {
    return {label: 'Ready to promote', hint: 'The execution plan exists and can now be turned into runnable work.'};
  }
  if (normalized === 'promoting') {
    return {label: 'Preparing work', hint: 'Spec-orch is wiring plan packets into tracked execution units.'};
  }
  if (normalized === 'executing') {
    return {label: 'Running now', hint: 'Workers should be executing or waiting for the next supervised round.'};
  }
  if (normalized === 'all_done') {
    return {label: 'Execution finished', hint: 'All packets have finished and post-run wrap-up is next.'};
  }
  if (normalized === 'retrospecting') {
    return {label: 'Retrospective', hint: 'Spec-orch is summarizing what happened and what changed.'};
  }
  if (normalized === 'evolving') {
    return {label: 'Improving system', hint: 'Spec-orch is updating its own prompts, rules, or guidance.'};
  }
  if (normalized === 'completed') {
    return {label: 'Completed', hint: 'The mission finished and all post-run work is done.'};
  }
  if (normalized === 'failed') {
    return {label: 'Failed', hint: 'The mission stopped because planning, execution, or verification failed.'};
  }
  return {label: normalized, hint: 'Current lifecycle state.'};
}

function operatorModeMeta(mode) {
  if (mode === 'inbox') {
    return {
      title: 'Needs Attention',
      description: 'Only items that need operator action now: approvals, paused missions, failures, or budget alerts.',
    };
  }
  if (mode === 'missions') {
    return {
      title: 'All Missions',
      description: 'Every mission known to this workspace, with running and recently active missions floated to the top.',
    };
  }
  if (mode === 'approvals') {
    return {
      title: 'Decision Queue',
      description: 'Only missions that are actively waiting on operator decisions, sorted by urgency and wait time.',
    };
  }
  if (mode === 'evidence') {
    return {
      title: 'Deep Evidence',
      description: 'Browse missions through evidence density: recorded rounds, visual reviews, and operator actions.',
    };
  }
  return {
    title: 'Mission Control',
    description: 'Operator surfaces for supervised software delivery.',
  };
}

function renderOperatorModes() {
  const modes = ['inbox', 'missions', 'approvals', 'evidence'];
  const evidenceMissionCount = missions.filter(m => {
    const ev = m.evidence || {};
    return (ev.round_count || 0) > 0 || (ev.visual_round_count || 0) > 0 || (ev.approval_action_count || 0) > 0;
  }).length;
  const modeLabels = {
    inbox: ['Needs Attention', inboxSummary?.counts?.attention || 0],
    missions: ['All Missions', missions.length],
    approvals: ['Decision Queue', approvalQueue?.counts?.pending || 0],
    evidence: ['Deep Evidence', evidenceMissionCount],
  };
  for (const mode of modes) {
    const button = document.getElementById(`operator-mode-${mode}`);
    if (!button) continue;
    button.classList.toggle('active', selectedOperatorMode === mode);
    button.dataset.active = selectedOperatorMode === mode ? 'true' : 'false';
    const [label, count] = modeLabels[mode];
    button.innerHTML = count ? `${escHtml(label)} <span class="operator-mode-count">${escHtml(String(count))}</span>` : escHtml(label);
  }
  const navContext = document.getElementById('operator-nav-context');
  if (navContext) {
    const meta = operatorModeMeta(selectedOperatorMode);
    navContext.innerHTML = `<strong>${escHtml(meta.title)}</strong><br/>${escHtml(meta.description)}`;
  }
}

function setOperatorMode(mode) {
  selectedOperatorMode = mode;
  if (mode === 'evidence') {
    selectedMissionTab = 'transcript';
  }
  syncOperatorRoute();
  renderMissions();
  renderOperatorModes();
  renderMissionDetail(selectedMissionDetail);
  renderContextRail(selectedMissionDetail);
}

function renderMissions() {
  const root = document.getElementById('mission-list');
  const inboxRoot = document.getElementById('inbox-list');
  renderOperatorModes();
  if (!missions.length) {
    selectedMissionId = null;
    selectedMissionDetail = null;
    selectedPacketId = null;
    root.innerHTML = '<div class="empty-panel">No missions found yet.</div>';
    if (inboxRoot) {
      inboxRoot.style.display = selectedOperatorMode === 'inbox' ? 'flex' : 'none';
    }
    root.style.display = selectedOperatorMode === 'inbox' ? 'none' : 'flex';
    renderMissionDetail(null);
    renderContextRail(null);
    return;
  }
  if (!selectedMissionId || !missions.some(m => m.mission_id === selectedMissionId)) {
    selectedMissionId = missions[0].mission_id;
  }
  if (selectedOperatorMode === 'approvals') {
    const items = approvalQueue?.items || [];
    root.innerHTML = items.length ? items.map(item => `
      <button class="mission-list-item ${selectedMissionId === item.mission_id ? 'active' : ''}"
        type="button" onclick='selectMission(${safeJsArg(item.mission_id)})'>
        <div class="mission-list-title">${escHtml(item.title)}</div>
        <div class="mission-list-meta">
          <span class="badge ${escHtml(item.phase || 'approval')}">${escHtml(item.approval_state?.status || 'awaiting_human')}</span>
          <span>${escHtml(item.age_bucket || 'fresh')}</span>
          <span>${escHtml(String(item.wait_minutes || 0))} min waiting</span>
        </div>
        <div class="mission-list-meta">
          <span>${escHtml(item.summary || '')}</span>
        </div>
      </button>
    `).join('') : '<div class="empty-panel">No approval decisions are waiting right now.</div>';
    if (inboxRoot) inboxRoot.style.display = 'none';
    root.style.display = 'flex';
    return;
  }
  root.innerHTML = missions.map(m => {
    const phase = phaseFor(m);
    const phaseInfo = phaseMeta(phase);
    const lc = lifecycleStates[m.mission_id];
    const pipelineText = `${m.pipeline_done}/${m.pipeline_total} stages complete`;
    const issueSummary = selectedOperatorMode === 'evidence'
      ? `${m.evidence?.round_count || 0} rounds · ${m.evidence?.visual_round_count || 0} visual reviews · ${m.evidence?.approval_action_count || 0} operator actions`
      : lc && phase === 'executing'
      ? `${(lc.completed_issues || []).length}/${(lc.issue_ids || []).length || 1} issues complete`
      : m.plan ? `${m.plan.packet_count} packets across ${m.plan.wave_count} waves` : 'Spec in progress';
    return `<button class="mission-list-item ${selectedMissionId === m.mission_id ? 'active' : ''}"
      id="card-${escAttr(m.mission_id)}"
      data-mid="${escAttr(m.mission_id)}"
      data-mission-id="${escAttr(m.mission_id)}"
      data-automation-target="mission-card"
      onclick='selectMission(${safeJsArg(m.mission_id)})'>
      <div class="mission-list-title">${escHtml(m.title)}</div>
      <div class="mission-list-meta">
        <span class="badge ${phase}">${escHtml(phaseInfo.label)}</span>
        <span>${pipelineText}</span>
      </div>
      <div class="mission-list-meta">
        <span>${escHtml(m.mission_id)}</span>
        <span>${escHtml(issueSummary)}</span>
      </div>
      <div class="mission-list-meta">
        <span>${escHtml(phaseInfo.hint)}</span>
      </div>
    </button>`;
  }).join('');
  renderInboxSummary();
  if (inboxRoot) {
    inboxRoot.style.display = selectedOperatorMode === 'inbox' ? 'flex' : 'none';
  }
  root.style.display = selectedOperatorMode === 'inbox' ? 'none' : 'flex';
}

function renderInboxSummary() {
  const chip = document.getElementById('inbox-attention-chip');
  const list = document.getElementById('inbox-list');
  const attention = inboxSummary?.counts?.attention || 0;
  if (chip) {
    chip.textContent = attention ? `Needs Attention ${attention}` : 'Needs Attention';
    chip.title = attention
      ? `${inboxSummary.counts.approvals || 0} approvals, ${inboxSummary.counts.budgets || 0} budget alerts, ${inboxSummary.counts.paused || 0} paused, ${inboxSummary.counts.failed || 0} failed`
      : 'No operator attention items';
  }
  if (!list) return;
  const items = inboxSummary?.items || [];
  if (!items.length) {
    list.innerHTML = '<div class="empty-panel">No approvals, paused missions, or failures.</div>';
    return;
  }
  list.innerHTML = items.map(item => `
    <button
      class="mission-list-item"
      type="button"
      data-automation-target="inbox-item"
      data-mission-id="${escAttr(item.mission_id)}"
      data-inbox-kind="${escAttr(item.kind || 'attention')}"
      data-review-route="${escAttr(item.review_route || '')}"
      onclick='openInboxItem(${safeJsArg(item.mission_id)}, ${safeJsArg(item.review_route || "")})'
    >
      <div class="mission-list-title">${escHtml(item.title)}</div>
      <div class="mission-list-meta">
        <span class="badge ${escHtml(item.phase || item.kind || 'attention')}">${escHtml(item.kind)}</span>
        ${item.current_round ? `<span>Round ${escHtml(String(item.current_round))}</span>` : ''}
      </div>
      <div class="mission-list-meta">
        <span>${escHtml(item.summary || '')}</span>
      </div>
      ${item.approval_state?.summary ? `
        <div class="mission-list-meta">
          <span class="detail-chip">${escHtml(item.approval_state.status || 'approval')}</span>
          <span>${escHtml(item.approval_state.summary)}</span>
        </div>
      ` : ''}
      ${item.budget_status ? `
        <div class="mission-list-meta">
          <span class="detail-chip">${escHtml(item.budget_status)}</span>
          <span>${escHtml(String(item.cost_usd || 0))} USD</span>
        </div>
      ` : ''}
      ${item.latest_operator_action ? `
        <div class="mission-list-meta">
          <span class="detail-chip">${escHtml(item.latest_operator_action.label || item.latest_operator_action.action_key || 'Action')}</span>
          <span>${escHtml(item.latest_operator_action.effect || 'guidance_sent')}</span>
        </div>
      ` : ''}
    </button>
  `).join('');
}

async function openInboxItem(missionId, reviewRoute = '') {
  if (reviewRoute) {
    try {
      const navigated = await navigateOperatorRoute(reviewRoute);
      if (navigated) {
        return;
      }
    } catch (error) {
      console.warn('Failed to navigate inbox review route', reviewRoute, error);
    }
    console.warn('Failed to navigate inbox review route', reviewRoute);
  }
  await selectMission(missionId);
}

async function ensureMissionSelection() {
  if (!selectedMissionId) return;
  await selectMission(selectedMissionId, {force:true});
}

async function selectMission(missionId, options = {}) {
  if (!options.force && missionId === selectedMissionId && selectedMissionDetail) {
    renderMissions();
    renderMissionDetail(selectedMissionDetail);
    renderContextRail(selectedMissionDetail);
    return;
  }
  selectedMissionId = missionId;
  renderMissions();
  renderMissionDetailLoading();
  renderContextRailLoading();
  try {
    const [detailResponse, visualResponse, acceptanceResponse, costsResponse] = await Promise.all([
      fetch(`/api/missions/${missionId}/detail`),
      fetch(`/api/missions/${missionId}/visual-qa`).catch(() => ({ok:false})),
      fetch(`/api/missions/${missionId}/acceptance-review`).catch(() => ({ok:false})),
      fetch(`/api/missions/${missionId}/costs`).catch(() => ({ok:false})),
    ]);
    if (!detailResponse.ok) throw new Error(`Failed to load mission detail (${detailResponse.status})`);
    selectedMissionDetail = await detailResponse.json();
    selectedMissionVisualQa = visualResponse.ok ? await visualResponse.json() : null;
    selectedMissionAcceptance = acceptanceResponse.ok ? await acceptanceResponse.json() : null;
    selectedMissionCosts = costsResponse.ok ? await costsResponse.json() : null;
    const packetIds = (selectedMissionDetail.packets || []).map(packet => packet.packet_id);
    selectedPacketId = packetIds.includes(pendingRoutePacketId)
      ? pendingRoutePacketId
      : (selectedMissionDetail.packets?.[0]?.packet_id || pendingRoutePacketId || null);
    pendingRoutePacketId = null;
    selectedPacketTranscript = null;
    selectedTranscriptFilter = 'all';
    selectedTranscriptBlockIndex = null;
    syncOperatorRoute();
    renderMissionDetail(selectedMissionDetail);
    renderContextRail(selectedMissionDetail);
    await loadSelectedPacketTranscript();
  } catch (error) {
    console.error(error);
    selectedMissionDetail = null;
    selectedPacketTranscript = null;
    renderMissionDetailError(error);
    renderContextRailError(error);
  }
}

function renderMissionDetailLoading() {
  const view = document.getElementById('mission-detail-view');
  view.innerHTML = '<div class="empty-panel">Loading mission detail…</div>';
}

function renderContextRailLoading() {
  const rail = document.getElementById('operator-context-rail');
  rail.innerHTML = '<div class="empty-panel">Loading context…</div>';
}

function renderMissionDetailError(error) {
  const view = document.getElementById('mission-detail-view');
  view.innerHTML = `<div class="error-banner">${escHtml(error?.message || 'Failed to load mission detail')}</div>`;
}

function renderContextRailError(error) {
  const rail = document.getElementById('operator-context-rail');
  rail.innerHTML = `<div class="error-banner">${escHtml(error?.message || 'Failed to load context')}</div>`;
}

function renderMissionDetail(detail) {
  const view = document.getElementById('mission-detail-view');
  if (!detail) {
    view.innerHTML = '<div class="empty-panel">Select a mission to inspect its rounds, packets, and evidence.</div>';
    return;
  }

  const mission = detail.mission || {};
  const lifecycle = detail.lifecycle || {};
  const packets = detail.packets || [];
  const rounds = detail.rounds || [];
  const latestRound = rounds.length ? rounds[rounds.length - 1] : null;
  const approvalRequest = detail.approval_request || null;
  const approvalHistory = detail.approval_history || [];
  const approvalState = approvalActionStates[mission.mission_id] || detail.approval_state || null;
  const currentPhase = lifecycle.phase || mission.status || 'unknown';
  const completedIssues = lifecycle.completed_issues || [];
  const issueIds = lifecycle.issue_ids || [];
  const metrics = [
    { label: 'Phase', value: currentPhase },
    { label: 'Round', value: detail.current_round || '—' },
    { label: 'Packets', value: packets.length || '—' },
    { label: 'Issues', value: issueIds.length ? `${completedIssues.length}/${issueIds.length}` : '—' },
  ];

  if (selectedOperatorMode === 'approvals') {
    view.innerHTML = renderApprovalQueuePanel();
    return;
  }

  const activeTab = selectedOperatorMode === 'evidence' ? 'transcript' : selectedMissionTab;
  const tabButtons = [
    ['overview', 'Overview'],
    ['transcript', 'Transcript'],
    ['approvals', 'Approvals'],
    ['visual-qa', 'Visual QA'],
    ['acceptance', 'Acceptance'],
    ['costs', 'Costs'],
  ];

  let primarySurface = '';
  if (activeTab === 'transcript') {
    primarySurface = `
      <section class="mission-section">
        <div class="section-heading">
          <h3>Transcript</h3>
          <div id="transcript-filter-bar" class="transcript-filter-bar"></div>
        </div>
        <div id="packet-transcript-view" class="transcript-list">${renderTranscriptPreview()}</div>
      </section>
    `;
  } else if (activeTab === 'approvals') {
    primarySurface = `
      <section class="mission-section">
        <h3>Approval Workspace</h3>
        ${approvalRequest ? renderApprovalWorkspace(approvalRequest, approvalHistory, approvalState, mission.mission_id || '', 'mission-detail') : '<div class="empty-panel">No active approval request.</div>'}
      </section>
    `;
  } else if (activeTab === 'visual-qa') {
    primarySurface = `
      <section class="mission-section">
        <h3>Visual QA</h3>
        ${renderVisualQaPanel(selectedMissionVisualQa || detail.visual_qa)}
      </section>
    `;
  } else if (activeTab === 'acceptance') {
    primarySurface = `
      <section class="mission-section">
        <h3>Acceptance Review</h3>
        ${renderAcceptancePanel(selectedMissionAcceptance || detail.acceptance_review)}
      </section>
    `;
  } else if (activeTab === 'costs') {
    primarySurface = `
      <section class="mission-section">
        <h3>Costs & Budgets</h3>
        ${renderCostsPanel(selectedMissionCosts || detail.costs)}
      </section>
    `;
  } else {
    primarySurface = `
      <section class="mission-workbench">
        <div class="mission-section">
          <h3>Packets</h3>
          <div class="packet-list">
            ${packets.length ? packets.map(packet => renderPacketRow(packet)).join('') : '<div class="empty-panel">No packets scoped yet.</div>'}
          </div>
        </div>
        <div class="mission-section">
          <h3>Latest Round</h3>
          ${latestRound ? renderLatestRound(latestRound) : '<div class="empty-panel">No round evidence yet.</div>'}
        </div>
      </section>
      <section class="mission-section">
        <div class="section-heading">
          <h3>Transcript</h3>
          <div id="transcript-filter-bar" class="transcript-filter-bar"></div>
        </div>
        <div id="packet-transcript-view" class="transcript-list">${renderTranscriptPreview()}</div>
      </section>
      <section class="mission-workbench">
        <div class="mission-section">
          <h3>Acceptance Criteria</h3>
          ${renderSimpleList(mission.acceptance_criteria, 'No acceptance criteria recorded yet.')}
        </div>
        <div class="mission-section">
          <h3>Constraints</h3>
          ${renderSimpleList(mission.constraints, 'No constraints recorded yet.')}
        </div>
      </section>
    `;
  }

  view.innerHTML = `
    <section class="mission-hero" data-automation-target="mission-detail-ready" data-mission-id="${escAttr(mission.mission_id || '')}">
      <div class="mission-hero-copy">
        <div class="mission-kicker">Mission ${escHtml(mission.mission_id || '')}</div>
        <div class="mission-hero-title">${escHtml(mission.title || 'Untitled mission')}</div>
        <div class="mission-hero-subtitle">${escHtml(buildMissionSubtitle(detail))}</div>
      </div>
      <div class="mission-primary-actions">
        ${renderActionButtons(detail.actions || [], mission.mission_id || '')}
      </div>
    </section>
    <section class="mission-metrics">
      ${metrics.map(metric => `
        <div class="mission-metric">
          <div class="mission-metric-label">${escHtml(metric.label)}</div>
          <div class="mission-metric-value">${escHtml(String(metric.value))}</div>
        </div>
      `).join('')}
    </section>
    <section class="mission-tabs">
      ${tabButtons.map(([key, label]) => `
        <button
          class="mission-tab ${activeTab === key ? 'active' : ''}"
          type="button"
          data-automation-target="mission-tab"
          data-tab-key="${escAttr(key)}"
          data-active="${activeTab === key ? 'true' : 'false'}"
          onclick="setMissionTab('${key}')"
        >${escHtml(label)}</button>
      `).join('')}
      <button class="mission-tab" type="button" data-automation-target="mission-secondary-action" data-action-key="discuss" onclick='openDiscuss(${safeJsArg(mission.mission_id || "")})'>Discuss</button>
      <button class="mission-tab" type="button" data-automation-target="mission-secondary-action" data-action-key="refresh" onclick="load()">Refresh</button>
    </section>
    ${primarySurface}
  `;
}

function renderContextRail(detail) {
  const rail = document.getElementById('operator-context-rail');
  if (!detail) {
    rail.innerHTML = '<div class="empty-panel">Mission context will appear here.</div>';
    return;
  }
  const mission = detail.mission || {};
  const rounds = detail.rounds || [];
  const latestRound = rounds.length ? rounds[rounds.length - 1] : null;
  const approvalRequest = detail.approval_request || null;
  const approvalHistory = detail.approval_history || [];
  const approvalState = approvalActionStates[mission.mission_id] || detail.approval_state || null;
  const packet = (detail.packets || []).find(item => item.packet_id === selectedPacketId) || detail.packets?.[0];
  const visualQa = selectedMissionVisualQa || detail.visual_qa || {};
  const acceptance = selectedMissionAcceptance || detail.acceptance_review || {};
  const costs = selectedMissionCosts || detail.costs || {};
  rail.innerHTML = `
    <div class="mission-section">
      <h3>Lifecycle</h3>
      <div class="context-list">
        <div class="context-card">
          <div class="context-title">${escHtml(phaseMeta(detail.lifecycle?.phase || detail.mission?.status || '').label)}</div>
          <div class="context-meta">${escHtml(phaseMeta(detail.lifecycle?.phase || detail.mission?.status || '').hint)}</div>
        </div>
      </div>
    </div>
    <div class="mission-section">
      <h3>Interventions</h3>
      <div class="context-list">
        <div class="context-card">
          <div class="context-title">Available actions</div>
          <div class="context-meta">${(detail.actions || []).join(' • ') || 'No actions'}</div>
        </div>
        <div class="context-card">
          <div class="context-title">Current packet</div>
          <div class="context-meta">${packet ? escHtml(packet.title) : 'No packet selected'}</div>
        </div>
      </div>
    </div>
    <div class="mission-section">
      <h3>Approval workspace</h3>
      <div class="context-list">
        ${approvalRequest ? renderApprovalWorkspace(approvalRequest, approvalHistory, approvalState, mission.mission_id || '', 'context-rail') : '<div class="empty-panel">No active approval request.</div>'}
      </div>
    </div>
    <div class="mission-section">
      <h3>Artifacts</h3>
      <div class="artifact-list">
        ${renderArtifactLinks(detail.artifacts || {})}
      </div>
    </div>
    <div class="mission-section">
      <h3>Round evidence</h3>
      <div class="context-list">
        ${latestRound ? renderRoundContext(latestRound) : '<div class="empty-panel">Waiting for first round evidence.</div>'}
      </div>
    </div>
    <div class="mission-section">
      <h3>Surface alerts</h3>
      <div class="context-list">
        <div class="context-card">
          <div class="context-title">Visual QA</div>
          <div class="context-meta">
            <span>${escHtml(`${visualQa?.summary?.blocking_findings || 0} blocking`)}</span>
            <span>${escHtml(`${visualQa?.summary?.gallery_items || 0} gallery`)}</span>
          </div>
          ${visualQa?.review_route ? `<div class="context-meta">${renderInternalRouteButton(visualQa.review_route, 'Open visual review')}</div>` : ''}
        </div>
        <div class="context-card">
          <div class="context-title">Acceptance</div>
          <div class="context-meta">
            <span class="detail-chip">${escHtml(acceptance?.latest_review?.status || 'pending')}</span>
            <span>${escHtml(String(acceptance?.summary?.filed_issues || 0))} filed</span>
          </div>
          ${acceptance?.review_route ? `<div class="context-meta">${renderInternalRouteButton(acceptance.review_route, 'Open acceptance review')}</div>` : ''}
        </div>
        <div class="context-card">
          <div class="context-title">Costs</div>
          <div class="context-meta">
            <span class="detail-chip">${escHtml(costs?.summary?.budget_status || 'unconfigured')}</span>
            <span>${escHtml(String(costs?.summary?.cost_usd || 0))} USD</span>
          </div>
          ${costs?.review_route ? `<div class="context-meta">${renderInternalRouteButton(costs.review_route, 'Open cost review')}${costs?.highest_cost_worker?.transcript_route ? renderInternalRouteButton(costs.highest_cost_worker.transcript_route, 'Open top packet') : ''}</div>` : ''}
        </div>
      </div>
    </div>
    <div class="mission-section">
      <h3>Transcript inspector</h3>
      <div id="transcript-inspector" class="context-list">
        ${renderTranscriptInspector()}
      </div>
    </div>
    <div class="mission-section">
      <h3>Spec</h3>
      <div class="context-list">
        <div class="context-card">
          <div class="context-title">${escHtml(mission.spec_path || 'No spec path')}</div>
          <div class="context-meta">Mission source of truth</div>
        </div>
      </div>
    </div>
  `;
}

function renderApprovalWorkspace(approvalRequest, approvalHistory, approvalState, missionId, scope) {
  return getOperatorConsoleHelpers().renderApprovalWorkspace(
    approvalRequest,
    approvalHistory,
    approvalState,
    missionId,
    scope,
    escHtml,
  );
}

function renderApprovalQueue(items) {
  return getOperatorConsoleHelpers().renderApprovalQueue(items, escHtml);
}

function renderApprovalQueuePanel() {
  return getOperatorConsoleHelpers().renderApprovalQueuePanel(
    approvalQueue,
    selectedApprovalMissionIds,
    approvalBatchState,
    escHtml,
  );
}

function renderVisualQaPanel(visualQa) {
  return getOperatorConsoleHelpers().renderVisualQaPanel(visualQa, escHtml);
}

function renderAcceptancePanel(acceptance) {
  return getOperatorConsoleHelpers().renderAcceptancePanel(acceptance, escHtml);
}

function renderCostsPanel(costs) {
  return getOperatorConsoleHelpers().renderCostsPanel(costs, escHtml);
}

function renderActionButtons(actions, missionId) {
  return getOperatorConsoleHelpers().renderActionButtons(actions, missionId, escHtml);
}

function renderPacketRow(packet) {
  return getOperatorConsoleHelpers().renderPacketRow(packet, selectedPacketId, escHtml);
}

function renderLatestRound(round) {
  return getOperatorConsoleHelpers().renderLatestRound(round, escHtml);
}

function renderSimpleList(items, emptyText) {
  return getOperatorConsoleHelpers().renderSimpleList(items, emptyText, escHtml);
}

function renderArtifactLinks(artifacts) {
  return getOperatorConsoleHelpers().renderArtifactLinks(artifacts, escHtml);
}

function renderRoundContext(round) {
  return getOperatorConsoleHelpers().renderRoundContext(round, escHtml);
}

function renderInternalRouteButton(route, label) {
  return getOperatorConsoleHelpers().renderInternalRouteButton(route, label, escHtml);
}

function buildMissionSubtitle(detail) {
  return getOperatorConsoleHelpers().buildMissionSubtitle(detail);
}

function setMissionTab(tab) {
  selectedMissionTab = tab;
  syncOperatorRoute();
  renderMissionDetail(selectedMissionDetail);
  renderContextRail(selectedMissionDetail);
}

function toggleApprovalSelection(missionId, checked) {
  const next = new Set(selectedApprovalMissionIds);
  if (checked) {
    next.add(missionId);
  } else {
    next.delete(missionId);
  }
  selectedApprovalMissionIds = Array.from(next);
  renderMissionDetail(selectedMissionDetail);
}

function toggleAllApprovalSelections(checked) {
  selectedApprovalMissionIds = checked
    ? (approvalQueue.items || []).map(item => item.mission_id)
    : [];
  renderMissionDetail(selectedMissionDetail);
}

async function triggerApprovalBatchAction(actionKey) {
  if (!selectedApprovalMissionIds.length) {
    return;
  }
  approvalBatchState = {
    pending: true,
    summary: `Applying ${actionKey} to ${selectedApprovalMissionIds.length} missions…`,
  };
  renderMissionDetail(selectedMissionDetail);
  try {
    const response = await fetch('/api/approvals/batch-action', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        mission_ids: selectedApprovalMissionIds,
        action_key: actionKey,
      }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || 'Batch approval action failed');
    }
    approvalBatchState = {
      pending: false,
      summary: `${data.summary.applied} applied, ${data.summary.not_applied} recorded, ${data.summary.failed} failed`,
      results: data.results || [],
      focusMissionId: data.focus_mission_id || null,
      nextPendingMissionId: data.next_pending_mission_id || null,
    };
    selectedApprovalMissionIds = [];
    await load();
  } catch (error) {
    approvalBatchState = {
      pending: false,
      summary: error?.message || 'Batch approval action failed',
    };
    renderMissionDetail(selectedMissionDetail);
  }
}

async function focusMissionFromBatch(missionId) {
  if (!missionId) return;
  selectedOperatorMode = 'missions';
  selectedMissionTab = 'approvals';
  selectedApprovalMissionIds = [];
  renderOperatorModes();
  await selectMission(missionId, {force:true});
}

async function selectPacket(packetId) {
  selectedPacketId = packetId;
  selectedPacketTranscript = null;
  selectedTranscriptBlockIndex = null;
  syncOperatorRoute();
  renderMissionDetail(selectedMissionDetail);
  renderContextRail(selectedMissionDetail);
  await loadSelectedPacketTranscript();
}

async function loadSelectedPacketTranscript() {
  if (!selectedMissionId || !selectedPacketId) {
    selectedPacketTranscript = null;
    renderTranscriptContainer();
    return;
  }
  selectedPacketTranscript = {loading: true, entries: []};
  renderTranscriptContainer();
  try {
    const response = await fetch(`/api/missions/${selectedMissionId}/packets/${selectedPacketId}/transcript`);
    if (!response.ok) {
      selectedPacketTranscript = {error: 'No transcript available for this packet yet.', entries: []};
      renderTranscriptContainer();
      renderContextRail(selectedMissionDetail);
      return;
    }
    selectedPacketTranscript = await response.json();
    const blocks = selectedPacketTranscript.blocks || [];
    selectedTranscriptBlockIndex = blocks.length ? blocks.length - 1 : null;
  } catch (error) {
    selectedPacketTranscript = {error: error?.message || 'Failed to load transcript.', entries: []};
  }
  renderTranscriptContainer();
  renderContextRail(selectedMissionDetail);
}

function renderTranscriptContainer() {
  renderTranscriptFilters();
  const container = document.getElementById('packet-transcript-view');
  if (!container) return;
  container.innerHTML = renderTranscriptPreview();
}

function selectTranscriptBlock(index) {
  selectedTranscriptBlockIndex = index;
  renderTranscriptContainer();
  renderContextRail(selectedMissionDetail);
}

function renderTranscriptFilters() {
  const root = document.getElementById('transcript-filter-bar');
  if (!root) return;
  root.innerHTML = getOperatorConsoleHelpers().renderTranscriptFilters(
    selectedPacketTranscript,
    selectedTranscriptFilter,
    escHtml,
  );
}

function selectTranscriptFilter(filterKey) {
  selectedTranscriptFilter = filterKey || 'all';
  renderTranscriptContainer();
}

function renderTranscriptPreview() {
  return getOperatorConsoleHelpers().renderTranscriptPreview(
    selectedPacketId,
    selectedPacketTranscript,
    selectedTranscriptFilter,
    selectedTranscriptBlockIndex,
    escHtml,
    renderTranscriptBody,
  );
}

function renderTranscriptInspector() {
  return getOperatorConsoleHelpers().renderTranscriptInspector(
    selectedPacketId,
    selectedPacketTranscript,
    selectedTranscriptBlockIndex,
    escHtml,
    renderTranscriptDetails,
  );
}

function renderTranscriptDetails(details) {
  return getOperatorConsoleHelpers().renderTranscriptDetails(details, escHtml);
}

function renderDetailValue(value) {
  return getOperatorConsoleHelpers().renderDetailValue(value, escHtml);
}

function formatApprovalActionState(action) {
  return getOperatorConsoleHelpers().formatApprovalActionState(action);
}

function getOperatorConsoleHelpers() {
  if (!window.SpecOrchOperatorConsole) {
    throw new Error('Operator console helpers failed to load');
  }
  return window.SpecOrchOperatorConsole;
}

function renderTranscriptBody(entry) {
  if (!entry.raw) return '';
  const body = typeof entry.raw === 'string' ? entry.raw : JSON.stringify(entry.raw, null, 2);
  return `<div class="transcript-entry-body">${escHtml(body)}</div>`;
}

function escHtml(s) {
  const d = document.createElement('div');
  d.textContent = s || '';
  return d.innerHTML;
}

function safeJsArg(value) {
  return getOperatorConsoleHelpers().safeJsArg(value);
}

function escAttr(value) {
  return getOperatorConsoleHelpers().escAttr(value);
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

async function triggerApprovalAction(missionId, actionKey) {
  approvalActionStates[missionId] = {
    status: 'pending',
    summary: 'Applying operator action…',
  };
  if (selectedMissionDetail?.mission?.mission_id === missionId) {
    renderContextRail(selectedMissionDetail);
  }
  try {
    const response = await fetch(`/api/missions/${missionId}/approval-action`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({action_key: actionKey}),
    });
    const data = await response.json();
    if (!response.ok && !data.action) {
      throw new Error(data.error || 'Approval action failed');
    }
    const actionState = formatApprovalActionState(data.action || {});
    approvalActionStates[missionId] = {
      status: data.action?.status || (data.ok ? 'applied' : 'failed'),
      summary: actionState || (data.ok ? 'Operator action applied' : 'Operator action failed'),
    };
    addSystemMsg(`${data.ok ? 'Applied' : 'Recorded'} ${actionKey} for ${missionId}${actionState ? ` (${actionState})` : ''}`);
    if (!data.ok) {
      openDiscussPreset(missionId, data.message || '');
    }
    await load();
    delete approvalActionStates[missionId];
    if (selectedMissionDetail?.mission?.mission_id === missionId) {
      renderMissionDetail(selectedMissionDetail);
      renderContextRail(selectedMissionDetail);
    }
  } catch (error) {
    approvalActionStates[missionId] = {
      status: 'failed',
      summary: error?.message || 'Approval action failed',
    };
    if (selectedMissionDetail?.mission?.mission_id === missionId) {
      renderContextRail(selectedMissionDetail);
    }
    alert('Error: ' + (error?.message || 'Approval action failed'));
  }
}

/* ===== CHAT / DISCUSS ===== */
function openSidebar() {
  document.getElementById('sidebar').classList.add('open');
}
function closeSidebar() {
  document.getElementById('sidebar').classList.remove('open');
}

function setSidebarMode(mode) {
  sidebarMode = mode;
  const launcherPanel = document.getElementById('launcher-panel');
  const discussPanel = document.getElementById('discuss-panel');
  launcherPanel?.classList.toggle('active', mode === 'launcher');
  discussPanel?.classList.toggle('active', mode !== 'launcher');
}

function parseLauncherLines(id) {
  const value = document.getElementById(id)?.value || '';
  return value.split('\\n').map(line => line.trim()).filter(Boolean);
}

function setLauncherStatus(message, tone = 'neutral') {
  const el = document.getElementById('launcher-status');
  if (!el) return;
  el.textContent = message;
  el.dataset.tone = tone;
}

function launcherActionButton(actionKey) {
  return document.querySelector(`[data-launcher-action="${actionKey}"]`);
}

function resetLauncherActionState() {
  document.querySelectorAll('[data-launcher-action]').forEach(btn => {
    btn.classList.remove('is-pending', 'is-complete', 'is-failed');
    btn.disabled = false;
    if (btn.dataset.defaultLabel) {
      btn.innerHTML = btn.dataset.defaultLabel;
    }
  });
  launcherState.activeAction = null;
}

function setLauncherActionState(actionKey, state, label = null) {
  const btn = launcherActionButton(actionKey);
  if (!btn) return;
  if (!btn.dataset.defaultLabel) {
    btn.dataset.defaultLabel = btn.innerHTML;
  }

  if (state === 'pending') {
    resetLauncherActionState();
    btn.classList.add('is-pending');
    btn.disabled = true;
    btn.innerHTML = label || btn.dataset.defaultLabel;
    launcherState.activeAction = actionKey;
    return;
  }

  btn.classList.remove('is-pending', 'is-complete', 'is-failed');
  btn.disabled = false;

  if (state === 'idle') {
    btn.innerHTML = btn.dataset.defaultLabel;
    if (launcherState.activeAction === actionKey) {
      launcherState.activeAction = null;
    }
    return;
  }

  btn.classList.add(state === 'success' ? 'is-complete' : 'is-failed');
  btn.innerHTML = label || btn.dataset.defaultLabel;
  launcherState.activeAction = null;
  window.setTimeout(() => {
    if (!btn.isConnected) return;
    btn.classList.remove('is-complete', 'is-failed');
    btn.innerHTML = btn.dataset.defaultLabel;
  }, 1800);
}

function launcherMissionId() {
  return launcherState.missionId
    || (document.getElementById('launcher-mission-id')?.value || '').trim();
}

async function refreshLauncherMissionSelection(missionId) {
  try {
    await load();
    await selectMission(missionId, {force:true});
    return null;
  } catch (error) {
    console.warn('Launcher follow-up refresh failed', error);
    return error;
  }
}

function renderLauncherReadiness(data) {
  const el = document.getElementById('launcher-readiness');
  if (!el || !data) return;
  const rows = [
    ['Config', data.config_present ? 'ready' : 'missing', data.config_present ? 'spec-orch.toml found' : 'spec-orch.toml missing'],
    ['Dashboard', data.dashboard?.ready ? 'ready' : 'missing', data.dashboard?.ready ? 'frontend deps available' : 'dashboard deps missing'],
    ['Linear', data.linear?.ready ? 'ready' : 'missing', data.linear?.ready ? 'token available' : `set ${data.linear?.token_env || 'SPEC_ORCH_LINEAR_TOKEN'}`],
    ['Planner', data.planner?.ready ? 'ready' : 'missing', data.planner?.ready ? String(data.planner?.model || 'configured') : 'planner not ready'],
    ['Supervisor', data.supervisor?.ready ? 'ready' : 'missing', data.supervisor?.ready ? String(data.supervisor?.model || 'configured') : 'supervisor not ready'],
    ['Builder', data.builder?.ready ? 'ready' : 'missing', data.builder?.ready ? String(data.builder?.adapter || 'configured') : 'builder not ready'],
  ];
  el.innerHTML = rows.map(([label, state, detail]) => `
    <div class="launcher-readiness-item">
      <span>${escHtml(label)}</span>
      <span class="launcher-readiness-state ${escAttr(state)}">${escHtml(detail)}</span>
    </div>
  `).join('');
}

async function loadLauncherReadiness() {
  setLauncherActionState('refresh-readiness', 'pending', 'Refreshing<span class="btn-meta">Checking config</span>');
  try {
    const res = await fetch('/api/launcher/readiness');
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Launcher readiness failed');
    launcherState.readiness = data;
    renderLauncherReadiness(data);
    setLauncherActionState('refresh-readiness', 'success', 'Ready<span class="btn-meta">Readiness updated</span>');
  } catch (error) {
    setLauncherStatus('Failed to load launcher readiness: ' + (error?.message || 'unknown error'), 'failed');
    setLauncherActionState('refresh-readiness', 'failed', 'Retry<span class="btn-meta">Readiness failed</span>');
  }
}

function openNewMission() {
  launcherState.missionId = '';
  launcherState.linearIssueId = '';
  for (const id of [
    'launcher-title',
    'launcher-mission-id',
    'launcher-intent',
    'launcher-acceptance',
    'launcher-constraints',
    'launcher-linear-title',
    'launcher-linear-description',
    'launcher-linear-issue-id',
  ]) {
    const el = document.getElementById(id);
    if (el) el.value = '';
  }
  resetLauncherActionState();
  setSidebarMode('launcher');
  document.getElementById('chat-title').textContent = 'New Mission';
  setLauncherStatus('Fill the mission setup fields, then create the draft.', 'neutral');
  openSidebar();
  loadLauncherReadiness();
}

function openDiscuss(missionId) {
  setSidebarMode('discuss');
  chatThreadId = 'discuss-' + missionId;
  chatMessages = [];
  renderChat();
  document.getElementById('chat-title').textContent = 'Discuss: ' + missionId.slice(0,12);
  openSidebar();
  addSystemMsg('Discussing mission ' + missionId);
}

function openDiscussPreset(missionId, presetMessage) {
  openDiscuss(missionId);
  const input = document.getElementById('chat-input');
  if (input) {
    input.value = presetMessage || '';
    input.focus();
  }
}

async function createMissionDraft() {
  const payload = {
    title: (document.getElementById('launcher-title')?.value || '').trim(),
    mission_id: (document.getElementById('launcher-mission-id')?.value || '').trim(),
    intent: (document.getElementById('launcher-intent')?.value || '').trim(),
    acceptance_criteria: parseLauncherLines('launcher-acceptance'),
    constraints: parseLauncherLines('launcher-constraints'),
  };
  setLauncherActionState('create-draft', 'pending', 'Creating<span class="btn-meta">Writing mission files</span>');
  setLauncherStatus('Creating mission draft…', 'working');
  try {
    const res = await fetch('/api/launcher/missions', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Mission draft creation failed');
    launcherState.missionId = data.mission_id;
    document.getElementById('launcher-mission-id').value = data.mission_id;
    setLauncherStatus(`Draft created: ${data.mission_id}`, 'success');
    setLauncherActionState('create-draft', 'success', 'Draft ready<span class="btn-meta">Mission files created</span>');
    const syncError = await refreshLauncherMissionSelection(data.mission_id);
    if (syncError) {
      addSystemMsg(`Draft created for ${data.mission_id}, but the workbench refresh needs a manual retry.`);
    }
  } catch (error) {
    setLauncherStatus(error?.message || 'Mission draft creation failed', 'failed');
    setLauncherActionState('create-draft', 'failed', 'Try again<span class="btn-meta">Draft creation failed</span>');
  }
}

async function approveAndPlanMission() {
  const missionId = launcherMissionId();
  if (!missionId) {
    setLauncherStatus('Create a mission draft first.', 'failed');
    return;
  }
  setLauncherActionState('approve-plan', 'pending', 'Planning<span class="btn-meta">Freezing and scoping</span>');
  setLauncherStatus(`Approving and planning ${missionId}…`, 'working');
  try {
    const res = await fetch(`/api/launcher/missions/${encodeURIComponent(missionId)}/approve-plan`, {method: 'POST'});
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Approve & Plan failed');
    setLauncherStatus(`Approved and planned ${missionId}`, 'success');
    setLauncherActionState('approve-plan', 'success', 'Planned<span class="btn-meta">plan.json ready</span>');
    const syncError = await refreshLauncherMissionSelection(missionId);
    if (syncError) {
      addSystemMsg(`Approve & Plan succeeded for ${missionId}, but the workbench refresh needs a manual retry.`);
    }
  } catch (error) {
    setLauncherStatus(error?.message || 'Approve & Plan failed', 'failed');
    setLauncherActionState('approve-plan', 'failed', 'Retry plan<span class="btn-meta">Planner failed</span>');
  }
}

async function createLinearIssueForMission() {
  const missionId = launcherMissionId();
  if (!missionId) {
    setLauncherStatus('Create a mission draft first.', 'failed');
    return;
  }
  setLauncherActionState('linear-create', 'pending', 'Creating issue<span class="btn-meta">Writing to Linear</span>');
  setLauncherStatus(`Creating a new Linear issue for ${missionId}…`, 'working');
  try {
    const res = await fetch(`/api/launcher/missions/${encodeURIComponent(missionId)}/linear-create`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        title: (document.getElementById('launcher-linear-title')?.value || '').trim() || missionId,
        description: (document.getElementById('launcher-linear-description')?.value || '').trim(),
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Linear issue creation failed');
    launcherState.linearIssueId = data.linear_issue?.identifier || '';
    document.getElementById('launcher-linear-issue-id').value = launcherState.linearIssueId;
    setLauncherStatus(`Created Linear issue ${launcherState.linearIssueId}`, 'success');
    setLauncherActionState('linear-create', 'success', 'Issue ready<span class="btn-meta">Linear issue created</span>');
  } catch (error) {
    setLauncherStatus(error?.message || 'Linear issue creation failed', 'failed');
    setLauncherActionState('linear-create', 'failed', 'Try again<span class="btn-meta">Issue creation failed</span>');
  }
}

async function bindLinearIssueForMission() {
  const missionId = launcherMissionId();
  const linearIssueId = (document.getElementById('launcher-linear-issue-id')?.value || '').trim();
  if (!missionId || !linearIssueId) {
    setLauncherStatus('Mission id and Linear issue id are required.', 'failed');
    return;
  }
  setLauncherActionState('linear-bind', 'pending', 'Binding issue<span class="btn-meta">Updating Linear description</span>');
  setLauncherStatus(`Binding ${missionId} to ${linearIssueId}…`, 'working');
  try {
    const res = await fetch(`/api/launcher/missions/${encodeURIComponent(missionId)}/linear-bind`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({linear_issue_id: linearIssueId}),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Linear issue binding failed');
    launcherState.linearIssueId = data.linear_issue?.identifier || linearIssueId;
    setLauncherStatus(`Bound ${missionId} to ${launcherState.linearIssueId}`, 'success');
    setLauncherActionState('linear-bind', 'success', 'Bound<span class="btn-meta">Mission linked</span>');
  } catch (error) {
    setLauncherStatus(error?.message || 'Linear issue binding failed', 'failed');
    setLauncherActionState('linear-bind', 'failed', 'Try again<span class="btn-meta">Bind failed</span>');
  }
}

async function launchMissionFromLauncher() {
  const missionId = launcherMissionId();
  if (!missionId) {
    setLauncherStatus('Create or select a mission first.', 'failed');
    return;
  }
  setLauncherActionState('launch', 'pending', 'Launching<span class="btn-meta">Handing off to lifecycle</span>');
  setLauncherStatus(`Launching ${missionId}…`, 'working');
  try {
    const res = await fetch(`/api/launcher/missions/${encodeURIComponent(missionId)}/launch`, {method: 'POST'});
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Mission launch failed');
    setLauncherStatus(`Mission launched: ${missionId}`, 'success');
    setLauncherActionState('launch', 'success', 'Live<span class="btn-meta">Mission executing</span>');
    selectedOperatorMode = 'missions';
    const syncError = await refreshLauncherMissionSelection(missionId);
    if (syncError) {
      addSystemMsg(`Mission launched for ${missionId}, but the workbench refresh needs a manual retry.`);
    }
    closeSidebar();
  } catch (error) {
    setLauncherStatus(error?.message || 'Mission launch failed', 'failed');
    setLauncherActionState('launch', 'failed', 'Retry launch<span class="btn-meta">Launch failed</span>');
  }
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
    const raw = typeof ev.data === 'string' ? ev.data.trim() : '';
    if (!raw) return;
    if (raw[0] !== '{' && raw[0] !== '[') return;
    try {
      const evt = JSON.parse(raw);
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
    if (idx < 0) missions.push(m);
    const lcr = await fetch('/api/lifecycle').catch(() => ({ok:false}));
    if (lcr.ok) lifecycleStates = await lcr.json();
    renderMissions();
    if (selectedMissionId === mid) {
      await selectMission(mid, {force:true});
    }
  } catch(e) {}
}

/* ===== INIT ===== */
hydrateInitialRoute();
load();
loadEvolution();
connectWs();
setInterval(load, 15000);
setInterval(loadEvolution, 30000);
</script>
</body>
</html>
"""


def create_app(repo_root: Path | None = None) -> Any:
    """Create the FastAPI app. Requires ``pip install fastapi uvicorn``."""
    from fastapi import FastAPI
    from fastapi.staticfiles import StaticFiles

    from .routes import register_routes

    root = repo_root or Path(".")
    app = FastAPI(title="spec-orch dashboard")
    static_dir = Path(__file__).resolve().parent.parent / "dashboard_assets" / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=static_dir), name="dashboard-static")
    register_routes(app, root)
    return app
