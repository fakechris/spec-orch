"""Lightweight web dashboard for spec-orch — pipeline status and execution results.

Start with:  spec-orch dashboard
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from spec_orch.services.mission_service import MissionService
from spec_orch.services.pipeline_checker import check_pipeline
from spec_orch.services.promotion_service import load_plan


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


DASHBOARD_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>spec-orch dashboard</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#0f1117;--card:#1a1d27;--border:#2a2d3a;--text:#e1e4eb;--dim:#8b8fa3;
--green:#22c55e;--amber:#f59e0b;--red:#ef4444;--blue:#3b82f6;--purple:#a855f7;
--accent:#6366f1;font-family:system-ui,-apple-system,sans-serif}
body{background:var(--bg);color:var(--text);min-height:100vh;padding:2rem}
h1{font-size:1.5rem;margin-bottom:1.5rem;display:flex;align-items:center;gap:.5rem}
h1 span{background:var(--accent);color:#fff;padding:.15rem .5rem;border-radius:4px;
font-size:.75rem;font-weight:500}
.grid{display:grid;gap:1rem;grid-template-columns:repeat(auto-fill,minmax(480px,1fr))}
.card{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:1.25rem}
.card-header{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:.75rem}
.card-title{font-size:1rem;font-weight:600;word-break:break-word}
.badge{display:inline-block;padding:.1rem .45rem;border-radius:4px;font-size:.7rem;font-weight:600}
.badge.approved{background:rgba(34,197,94,.15);color:var(--green)}
.badge.completed{background:rgba(168,85,247,.15);color:var(--purple)}
.badge.drafting{background:rgba(139,143,163,.15);color:var(--dim)}
.badge.in_progress{background:rgba(59,130,246,.15);color:var(--blue)}
.pipeline{display:flex;gap:2px;margin:.75rem 0;flex-wrap:wrap}
.stage{width:28px;height:8px;border-radius:2px;cursor:pointer;transition:transform .1s}
.stage:hover{transform:scaleY(1.8)}
.stage.done{background:var(--green)}
.stage.current{background:var(--amber);animation:pulse 1.5s infinite}
.stage.pending{background:var(--border)}
.stage.skipped{background:var(--border);opacity:.4}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.5}}
.progress-text{font-size:.75rem;color:var(--dim);margin-top:.25rem}
.waves{margin-top:.75rem}
.wave{border-left:2px solid var(--border);padding-left:.75rem;margin-bottom:.5rem}
.wave-label{font-size:.75rem;color:var(--dim);font-weight:600;margin-bottom:.25rem}
.packet{font-size:.8rem;padding:.15rem 0;display:flex;align-items:center;gap:.35rem}
.run-class{font-size:.65rem;padding:.05rem .3rem;border-radius:2px;
background:rgba(99,102,241,.15);color:var(--accent)}
.linear-id{font-size:.65rem;color:var(--dim)}
.meta{font-size:.75rem;color:var(--dim);margin-top:.5rem}
.refresh{position:fixed;bottom:1rem;right:1rem;background:var(--accent);color:#fff;
border:none;padding:.5rem 1rem;border-radius:6px;cursor:pointer;font-size:.8rem}
.refresh:hover{opacity:.9}
.empty{text-align:center;padding:3rem;color:var(--dim)}
.tooltip{position:relative}
.tooltip:hover::after{content:attr(data-tip);position:absolute;bottom:calc(100% + 4px);
left:50%;transform:translateX(-50%);background:#000;color:#fff;padding:.25rem .5rem;
border-radius:4px;font-size:.7rem;white-space:nowrap;z-index:10}
</style>
</head>
<body>
<h1>spec-orch <span>dashboard</span></h1>
<div id="root" class="grid"></div>
<button class="refresh" onclick="load()">Refresh</button>
<script>
async function load(){
 const r=await fetch('/api/missions');
 const missions=await r.json();
 const root=document.getElementById('root');
 if(!missions.length){root.innerHTML='<div class="empty">No missions found</div>';return}
 root.innerHTML=missions.map(m=>{
  const stages=m.pipeline.map(s=>
   `<div class="stage ${s.status} tooltip" data-tip="${s.label}"></div>`).join('');
  let wavesHtml='';
  if(m.plan){
   wavesHtml='<div class="waves">'+m.plan.waves.map(w=>
    `<div class="wave"><div class="wave-label">Wave ${w.wave_number}: ${w.description}</div>`+
    w.packets.map(p=>
     `<div class="packet"><span class="run-class">${p.run_class}</span> ${p.title}`+
     (p.linear_issue_id?` <span class="linear-id">${p.linear_issue_id}</span>`:'')+
     `</div>`).join('')+
    `</div>`).join('')+'</div>';
  }
  return `<div class="card">
   <div class="card-header">
    <div class="card-title">${m.title}</div>
    <span class="badge ${m.status}">${m.status}</span>
   </div>
   <div class="pipeline">${stages}</div>
   <div class="progress-text">${m.pipeline_done}/${m.pipeline_total} stages complete</div>
   ${wavesHtml}
   <div class="meta">${m.mission_id}</div>
  </div>`;
 }).join('');
}
load();
setInterval(load,10000);
</script>
</body>
</html>
"""


def _gather_run_history(repo_root: Path) -> list[dict[str, Any]]:
    """Scan workspace directories for run reports."""
    import json

    runs: list[dict[str, Any]] = []
    for base in [repo_root / ".worktrees", repo_root / ".spec_orch_runs"]:
        if not base.exists():
            continue
        for ws in sorted(base.iterdir()):
            report = ws / "report.json"
            if not report.exists():
                continue
            try:
                data = json.loads(report.read_text())
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


def create_app(repo_root: Path | None = None) -> Any:
    """Create the FastAPI app. Requires ``pip install fastapi uvicorn``."""
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

    root = repo_root or Path(".")
    app = FastAPI(title="spec-orch dashboard")

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return DASHBOARD_HTML

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

    return app
