#!/usr/bin/env bash
#
# Fresh Acpx Mission E2E smoke/full runner
#
# Dry-run:
#   ./tests/e2e/fresh_acpx_mission_smoke.sh
#
# Full mode:
#   ./tests/e2e/fresh_acpx_mission_smoke.sh --full
#
# The script sources .env when present and resolves planner/supervisor/
# acceptance_evaluator credentials from spec-orch.toml model chains.
#
# Full mode exercises:
#   1. fresh mission bootstrap via launcher helpers
#   2. approve/plan/launch through the lifecycle path
#   3. wait for a fresh round directory
#   4. post-run dashboard workflow replay
#   5. acceptance review with proof split
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
. "$SCRIPT_DIR/_shared_env.sh"
FULL_MODE=false
REQUESTED_DASHBOARD_PORT="${SPEC_ORCH_DASHBOARD_PORT:-8426}"
DASHBOARD_PORT=""
FRESH_VARIANT="${SPEC_ORCH_FRESH_VARIANT:-default}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

step() { echo -e "\n${GREEN}▶ STEP: $1${NC}"; }
fail() { echo -e "${RED}✗ FAIL: $1${NC}" >&2; exit 1; }
ok()   { echo -e "${GREEN}✓ $1${NC}"; }
warn() { echo -e "${YELLOW}⚠ $1${NC}"; }

while [ "$#" -gt 0 ]; do
  case "$1" in
    --full) FULL_MODE=true ;;
    --variant)
      shift
      [ "$#" -gt 0 ] || fail "--variant requires a value"
      FRESH_VARIANT="$1"
      ;;
  esac
  shift
done

command -v python3 >/dev/null || fail "python3 not found"
command -v git >/dev/null || fail "git not found"

cd "$REPO_ROOT"

if [ "$FULL_MODE" != true ]; then
  warn "Dry-run only. This script expects a configured local SpecOrch repo with:"
  echo "  - spec-orch.toml present"
  echo "  - planner/supervisor/acceptance model credentials resolvable"
  echo "  - dashboard deps installed"
  echo "  - ACPX builder executable available"
  echo
  echo "To run full mode:"
  echo "  ./tests/e2e/fresh_acpx_mission_smoke.sh --full"
  exit 0
fi

[ -f spec-orch.toml ] || fail "spec-orch.toml missing"

activate_shared_worktree_context

# Bridge legacy single-model envs into the default reasoning chain when the
# repo still uses SPEC_ORCH_* values in .env. Keep this at the harness layer
# so role-level slot env resolution stays explicit inside application code.
if [ -z "${MINIMAX_API_KEY:-}" ] && [ -n "${SPEC_ORCH_LLM_API_KEY:-}" ]; then
  export MINIMAX_API_KEY="$SPEC_ORCH_LLM_API_KEY"
fi
if [ -z "${MINIMAX_ANTHROPIC_BASE_URL:-}" ] && [ -n "${SPEC_ORCH_LLM_API_BASE:-}" ]; then
  export MINIMAX_ANTHROPIC_BASE_URL="$SPEC_ORCH_LLM_API_BASE"
fi

step "Validate model-chain credentials for full mode"
uv run --python 3.13 python - <<'PY'
import tomllib
from pathlib import Path

from spec_orch.services.litellm_profile import resolve_role_litellm_settings

raw = tomllib.loads(Path("spec-orch.toml").read_text(encoding="utf-8"))


def usable_count(role: str) -> int:
    settings = resolve_role_litellm_settings(raw, section_name=role)
    chain = settings.get("model_chain") or []
    return sum(1 for profile in chain if getattr(profile, "is_usable", False))


missing: list[str] = []
for role in ("planner", "supervisor"):
    if usable_count(role) == 0:
        missing.append(role)

acceptance_cfg = raw.get("acceptance_evaluator", {})
if not isinstance(acceptance_cfg, dict):
    acceptance_cfg = {}
if acceptance_cfg.get("adapter", "litellm") == "litellm" and usable_count("acceptance_evaluator") == 0:
    missing.append("acceptance_evaluator")

if missing:
    raise SystemExit(
        "missing usable model-chain credentials for full mode: " + ", ".join(missing)
    )
PY
ok "model-chain credentials resolved"

step "Validate fresh E2E runtime dependencies"
uv run --python 3.13 python - <<'PY'
import importlib.util
import sys

required = [
    "litellm",
    "fastembed",
    "qdrant_client",
    "fastapi",
    "uvicorn",
    "websockets",
    "playwright",
]
missing = [name for name in required if importlib.util.find_spec(name) is None]
if missing:
    raise SystemExit(
        "missing runtime deps: "
        + ", ".join(missing)
        + ". Run `uv sync --python 3.13 --extra dev` before --full mode."
    )
PY
ok "runtime dependencies present"

RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
META_FILE=".spec_orch/fresh_acpx_run_meta_${RUN_ID}.json"
LOCK_DIR=".spec_orch/fresh_acpx_mission_smoke.lock"
LOCK_PID_FILE="${LOCK_DIR}/pid"
mkdir -p .spec_orch

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  LOCK_PID=""
  if [ -f "$LOCK_PID_FILE" ]; then
    LOCK_PID="$(cat "$LOCK_PID_FILE" 2>/dev/null || true)"
  fi
  if [ -n "$LOCK_PID" ] && kill -0 "$LOCK_PID" >/dev/null 2>&1; then
    fail "fresh_acpx_mission_smoke.sh is already running in this worktree; wait for the active run to finish"
  fi
  warn "reclaiming stale fresh_acpx_mission_smoke lock"
  rm -f "$LOCK_PID_FILE" >/dev/null 2>&1 || true
  rmdir "$LOCK_DIR" >/dev/null 2>&1 || fail "fresh_acpx_mission_smoke lock exists but could not be reclaimed"
  mkdir "$LOCK_DIR" 2>/dev/null || fail "fresh_acpx_mission_smoke.sh lock exists and could not be acquired"
fi
printf '%s\n' "$$" > "$LOCK_PID_FILE"

RUN_ID="${RUN_ID}-$$"
META_FILE=".spec_orch/fresh_acpx_run_meta_${RUN_ID}.json"

cleanup() {
  if [ -n "${DASHBOARD_PID:-}" ]; then
    kill "$DASHBOARD_PID" >/dev/null 2>&1 || true
  fi
  rm -f "$LOCK_PID_FILE" >/dev/null 2>&1 || true
  rmdir "$LOCK_DIR" >/dev/null 2>&1 || true
}
trap cleanup EXIT

step "Bootstrap a fresh mission request"
uv run --python 3.13 python - <<'PY' "$FRESH_VARIANT" > "$META_FILE"
import json
import sys
from pathlib import Path

from spec_orch.dashboard.launcher import _build_fresh_acpx_mission_request, _create_mission_draft

repo_root = Path(".").resolve()
variant = sys.argv[1]
payload = _build_fresh_acpx_mission_request(repo_root, variant=variant)
draft = _create_mission_draft(repo_root, payload)
mission_id = draft["mission_id"]
operator_dir = repo_root / "docs" / "specs" / mission_id / "operator"
operator_dir.mkdir(parents=True, exist_ok=True)
(operator_dir / "mission_bootstrap.json").write_text(
    json.dumps(payload, indent=2) + "\n",
    encoding="utf-8",
)
metadata = payload.get("metadata", {})
print(
    json.dumps(
        {
            "mission_id": mission_id,
            "title": draft["title"],
            "variant": metadata.get("fresh_variant", variant),
            "requires_linear": bool(metadata.get("requires_linear", False)),
        }
    )
)
PY

MISSION_ID="$(python3 - <<'PY' "$META_FILE"
import json, pathlib, sys
print(json.loads(pathlib.Path(sys.argv[1]).read_text())["mission_id"])
PY
)"
SPEC_DIR="docs/specs/${MISSION_ID}"
ROUND_GLOB="${SPEC_DIR}/rounds/round-*"
RUN_VARIANT="$(python3 - <<'PY' "$META_FILE"
import json, pathlib, sys
print(json.loads(pathlib.Path(sys.argv[1]).read_text())["variant"])
PY
)"
REQUIRES_LINEAR="$(python3 - <<'PY' "$META_FILE"
import json, pathlib, sys
print("true" if json.loads(pathlib.Path(sys.argv[1]).read_text())["requires_linear"] else "false")
PY
)"
ok "fresh mission created: ${MISSION_ID} (variant=${RUN_VARIANT})"

step "Approve and plan the mission"
uv run --python 3.13 python - <<'PY' "$MISSION_ID"
import json
import sys
from pathlib import Path

from spec_orch.dashboard.launcher import _approve_and_plan_mission
from spec_orch.services.fresh_acpx_e2e import assert_fresh_plan_budget

repo_root = Path(".").resolve()
mission_id = sys.argv[1]
result = _approve_and_plan_mission(repo_root, mission_id)
mission_bootstrap = json.loads(
    (repo_root / "docs" / "specs" / mission_id / "operator" / "mission_bootstrap.json").read_text(
        encoding="utf-8"
    )
)
metadata = mission_bootstrap.get("metadata", {})
budget = assert_fresh_plan_budget(
    result["plan"],
    max_waves=int(metadata.get("max_waves", 1)),
    max_packets=int(metadata.get("max_packets", 2)),
)
result["plan_budget"] = budget
(repo_root / "docs" / "specs" / mission_id / "operator" / "approve_plan.json").write_text(
    json.dumps(result, indent=2) + "\n",
    encoding="utf-8",
)
PY
ok "plan.json generated"

if [ "$REQUIRES_LINEAR" = "true" ]; then
  step "Bind Linear issue before launch"
  [ -n "${SPEC_ORCH_LINEAR_TOKEN:-${LINEAR_TOKEN:-${LINEAR_API_TOKEN:-}}}" ] || fail "Linear-bound variant requires SPEC_ORCH_LINEAR_TOKEN or LINEAR_TOKEN"
  uv run --python 3.13 python - <<'PY' "$MISSION_ID"
import json
import sys
from pathlib import Path

from spec_orch.dashboard.launcher import _create_linear_issue_for_mission

repo_root = Path(".").resolve()
mission_id = sys.argv[1]
bootstrap = json.loads(
    (repo_root / "docs" / "specs" / mission_id / "operator" / "mission_bootstrap.json").read_text(
        encoding="utf-8"
    )
)
result = _create_linear_issue_for_mission(
    repo_root,
    mission_id,
    title=f"{bootstrap.get('title', mission_id)} [fresh-acpx]",
    description=str(bootstrap.get("intent", "")).strip() or f"mission: {mission_id}",
)
(repo_root / "docs" / "specs" / mission_id / "operator" / "linear_issue.json").write_text(
    json.dumps(result, indent=2) + "\n",
    encoding="utf-8",
)
PY
  ok "linear issue bound"
fi

step "Launch and pick up the mission"
uv run --python 3.13 python - <<'PY' "$MISSION_ID"
import json
import sys
from pathlib import Path

from spec_orch.services.fresh_acpx_e2e import run_fresh_launch_and_pickup

repo_root = Path(".").resolve()
mission_id = sys.argv[1]
result = run_fresh_launch_and_pickup(repo_root=repo_root, mission_id=mission_id)
(repo_root / "docs" / "specs" / mission_id / "operator" / "launch_pickup.json").write_text(
    json.dumps(result, indent=2) + "\n",
    encoding="utf-8",
)
PY
ok "mission launch/pickup path completed"

step "Locate the fresh round directory"
ROUND_DIR=""
for _ in $(seq 1 30); do
  ROUND_DIR="$(ls -d ${ROUND_GLOB} 2>/dev/null | sort | tail -n 1 || true)"
  if [ -n "$ROUND_DIR" ] && [ -f "$ROUND_DIR/round_summary.json" ]; then
    break
  fi
  sleep 2
done
[ -n "$ROUND_DIR" ] || fail "no fresh round directory appeared under ${SPEC_DIR}/rounds"
ok "fresh round detected: ${ROUND_DIR}"

step "Resolve isolated dashboard port"
DASHBOARD_PORT="$(
  uv run --python 3.13 python - <<'PY' "$REQUESTED_DASHBOARD_PORT"
import sys

from spec_orch.services.fresh_acpx_e2e import resolve_dashboard_port

print(resolve_dashboard_port(int(sys.argv[1])))
PY
)"
[ -n "$DASHBOARD_PORT" ] || fail "could not resolve dashboard port"
if [ "$DASHBOARD_PORT" != "$REQUESTED_DASHBOARD_PORT" ]; then
  warn "dashboard port ${REQUESTED_DASHBOARD_PORT} busy; using isolated port ${DASHBOARD_PORT}"
fi

step "Start dashboard for post-run workflow replay"
uv run --python 3.13 spec-orch dashboard --port "$DASHBOARD_PORT" >/tmp/spec_orch_fresh_dashboard.log 2>&1 &
DASHBOARD_PID=$!
if ! uv run --python 3.13 python - <<'PY' "$DASHBOARD_PORT"
import sys

from spec_orch.services.fresh_acpx_e2e import wait_for_dashboard_ready

port = sys.argv[1]
result = wait_for_dashboard_ready(f"http://127.0.0.1:{port}/", timeout_seconds=20.0)
print(result)
PY
then
  cat /tmp/spec_orch_fresh_dashboard.log >&2 || true
  kill "$DASHBOARD_PID" >/dev/null 2>&1 || true
  fail "dashboard never became ready"
fi
ok "dashboard started at http://127.0.0.1:${DASHBOARD_PORT}"

step "Run post-run workflow replay and acceptance review"
SPEC_ORCH_VISUAL_EVAL_URL="http://127.0.0.1:${DASHBOARD_PORT}" \
uv run --python 3.13 python - <<'PY' "$MISSION_ID" "$ROUND_DIR" "$DASHBOARD_PORT"
import json
import os
import sys
from pathlib import Path

from spec_orch.dashboard.launcher import _read_launch_metadata
from spec_orch.services.acceptance.browser_evidence import collect_playwright_browser_evidence
from spec_orch.services.acceptance.litellm_acceptance_evaluator import LiteLLMAcceptanceEvaluator
from spec_orch.services.fresh_acpx_e2e import (
    materialize_fresh_execution_artifacts,
    write_fresh_acpx_mission_report,
)
from spec_orch.services.mission_service import MissionService
from spec_orch.services.round_orchestrator import build_fresh_acpx_post_run_campaign

repo_root = Path(".").resolve()
mission_id = sys.argv[1]
round_dir = Path(sys.argv[2])
port = sys.argv[3]
mission = MissionService(repo_root).get_mission(mission_id)
campaign = build_fresh_acpx_post_run_campaign(repo_root, mission_id)

browser_evidence = collect_playwright_browser_evidence(
    mission_id=mission_id,
    round_id=int(round_dir.name.split("-")[-1]),
    round_dir=round_dir,
    paths=campaign.primary_routes + campaign.related_routes[: campaign.related_route_budget],
    interaction_plans=campaign.interaction_plans,
)
if browser_evidence is None:
    raise RuntimeError("browser replay did not run; SPEC_ORCH_VISUAL_EVAL_URL missing")

launch = _read_launch_metadata(repo_root, mission_id)
fresh_execution = materialize_fresh_execution_artifacts(
    repo_root=repo_root,
    mission_id=mission_id,
    round_dir=round_dir,
    launch_result={"state": launch.get("last_launch", {}).get("state", {}), "background_runner_started": launch.get("runner", {}).get("status") == "running"},
)
workflow_replay = {
    "proof_type": "workflow_replay",
    "review_routes": {
        "overview": f"/?mission={mission_id}&mode=missions&tab=overview",
        "transcript": f"/?mission={mission_id}&mode=missions&tab=transcript",
        "approvals": f"/?mission={mission_id}&mode=missions&tab=approvals",
        "judgment": f"/?mission={mission_id}&mode=missions&tab=judgment",
    },
}
artifacts = {
    "mission": {
        "mission_id": mission_id,
        "title": mission.title,
        "acceptance_criteria": list(mission.acceptance_criteria),
        "constraints": list(mission.constraints),
    },
    "round_summary": json.loads((round_dir / "round_summary.json").read_text(encoding="utf-8")),
    "browser_evidence": browser_evidence,
    "fresh_execution": fresh_execution,
    "workflow_replay": workflow_replay,
    "proof_split": {
        "fresh_execution": fresh_execution,
        "workflow_replay": workflow_replay,
    },
}

adapter = LiteLLMAcceptanceEvaluator(
    repo_root=repo_root,
    model="MiniMax-M2.7-highspeed",
    api_type="anthropic",
)
result = adapter.evaluate_acceptance(
    mission_id=mission_id,
    round_id=int(round_dir.name.split("-")[-1]),
    round_dir=round_dir,
    worker_results=[],
    artifacts=artifacts,
    repo_root=repo_root,
    campaign=campaign,
)
(round_dir / "acceptance_review.json").write_text(
    json.dumps(result.to_dict(), indent=2) + "\n",
    encoding="utf-8",
)
report = write_fresh_acpx_mission_report(
    round_dir=round_dir,
    mission_id=mission_id,
    dashboard_url=f"http://127.0.0.1:{port}/?mission={mission_id}&mode=missions&tab=overview",
    fresh_execution=fresh_execution,
    workflow_replay=workflow_replay,
    acceptance_review=result,
)
print(json.dumps(report))
PY

ok "fresh mission workflow replay completed"
echo ""
echo -e "${GREEN}Fresh Acpx Mission E2E completed${NC}"
echo "Mission: ${MISSION_ID}"
echo "Variant: ${RUN_VARIANT}"
echo "Round:   ${ROUND_DIR}"
echo "Report:  ${ROUND_DIR}/fresh_acpx_mission_e2e_report.md"
