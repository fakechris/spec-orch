#!/usr/bin/env bash
#
# Exploratory acceptance smoke/full runner
#
# Dry-run:
#   ./tests/e2e/exploratory_acceptance_smoke.sh
#
# Full mode:
#   MINIMAX_API_KEY=$KEY MINIMAX_ANTHROPIC_BASE_URL=https://api.minimaxi.com/anthropic \
#     ./tests/e2e/exploratory_acceptance_smoke.sh --full
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
. "$SCRIPT_DIR/_shared_env.sh"
FULL_MODE=false
VARIANT="${SPEC_ORCH_FRESH_VARIANT:-default}"
REQUESTED_DASHBOARD_PORT="${SPEC_ORCH_DASHBOARD_PORT:-8426}"
DASHBOARD_PORT=""

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
      VARIANT="$1"
      ;;
    *)
      fail "unknown argument: $1"
      ;;
  esac
  shift
done

cd "$REPO_ROOT"

activate_shared_worktree_context

# Bridge legacy single-model envs into the default reasoning chain for the
# second-stage exploratory critique. Keep this compatibility shim in the
# harness layer so application-side slot env resolution stays explicit.
if [ -z "${MINIMAX_API_KEY:-}" ] && [ -n "${SPEC_ORCH_LLM_API_KEY:-}" ]; then
  export MINIMAX_API_KEY="$SPEC_ORCH_LLM_API_KEY"
fi
if [ -z "${MINIMAX_ANTHROPIC_BASE_URL:-}" ] && [ -n "${SPEC_ORCH_LLM_API_BASE:-}" ]; then
  export MINIMAX_ANTHROPIC_BASE_URL="$SPEC_ORCH_LLM_API_BASE"
fi

MISSION_DIR=""
MISSION_ID=""
ROUND_DIR=""
HARNESS_PID=""
HARNESS_LOG=""
DASHBOARD_PID=""

if [ "$FULL_MODE" != true ]; then
  warn "Dry-run only. This script wraps the canonical fresh exploratory acceptance path."
  echo
  echo "To run full mode:"
  echo "  MINIMAX_API_KEY=\$KEY MINIMAX_ANTHROPIC_BASE_URL=https://api.minimaxi.com/anthropic \\"
  echo "    ./tests/e2e/exploratory_acceptance_smoke.sh --full --variant ${VARIANT}"
  exit 0
fi

step "Capture mission directories before exploratory run"
BEFORE_FILE="$(mktemp)"
AFTER_FILE="$(mktemp)"
HARNESS_LOG="$(mktemp)"

cleanup() {
  if [ -n "$HARNESS_PID" ] && kill -0 "$HARNESS_PID" >/dev/null 2>&1; then
    kill "$HARNESS_PID" >/dev/null 2>&1 || true
  fi
  if [ -n "$DASHBOARD_PID" ] && kill -0 "$DASHBOARD_PID" >/dev/null 2>&1; then
    kill "$DASHBOARD_PID" >/dev/null 2>&1 || true
  fi
  rm -f "$BEFORE_FILE" "$AFTER_FILE" "$HARNESS_LOG"
}
trap cleanup EXIT

find docs/specs -mindepth 1 -maxdepth 1 -type d -print 2>/dev/null | sort > "$BEFORE_FILE" || true

step "Run canonical fresh ACPX mission smoke harness"
./tests/e2e/fresh_acpx_mission_smoke.sh --full --variant "$VARIANT" >"$HARNESS_LOG" 2>&1 &
HARNESS_PID=$!

LAST_CHAIN_STATUS=""
while kill -0 "$HARNESS_PID" >/dev/null 2>&1; do
  find docs/specs -mindepth 1 -maxdepth 1 -type d -print 2>/dev/null | sort > "$AFTER_FILE" || true
  if [ -z "$MISSION_DIR" ]; then
    MISSION_DIR="$(comm -13 "$BEFORE_FILE" "$AFTER_FILE" | tail -n 1 || true)"
    if [ -n "$MISSION_DIR" ]; then
      MISSION_ID="$(basename "$MISSION_DIR")"
      ok "detected mission: ${MISSION_ID}"
    fi
  fi

  if [ -n "$MISSION_ID" ]; then
    CURRENT_CHAIN_STATUS="$(
      uv run --python 3.13 spec-orch chain status --mission-id "$MISSION_ID" 2>/dev/null || true
    )"
    if [ -n "$CURRENT_CHAIN_STATUS" ] && [ "$CURRENT_CHAIN_STATUS" != "$LAST_CHAIN_STATUS" ]; then
      echo "chain: ${CURRENT_CHAIN_STATUS}"
      LAST_CHAIN_STATUS="$CURRENT_CHAIN_STATUS"
    fi
  fi
  sleep 5
done

if wait "$HARNESS_PID"; then
  ok "fresh ACPX mission smoke harness completed"
else
  step "Materialize exploratory acceptance failure report"
  uv run --python 3.13 python - <<'PY' "$VARIANT" "$HARNESS_LOG" "${MISSION_ID:-}"
import json
import sys
from pathlib import Path

from spec_orch.services.stability_acceptance import (
    write_exploratory_acceptance_failure_report,
)

repo_root = Path(".").resolve()
variant = sys.argv[1]
log_path = Path(sys.argv[2]).resolve()
mission_id = sys.argv[3]
failure_reason = "fresh ACPX mission smoke harness failed"
if log_path.exists():
    tail = log_path.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-20:]
    if tail:
        failure_reason = "\n".join(tail)
report = write_exploratory_acceptance_failure_report(
    repo_root=repo_root,
    mission_id=mission_id,
    variant=variant,
    source="fresh-acpx-mission-smoke",
    failure_reason=failure_reason,
)
print(json.dumps(report))
PY
  cat "$HARNESS_LOG" >&2 || true
  fail "fresh ACPX mission smoke harness failed"
fi

step "Identify the newly created mission"
find docs/specs -mindepth 1 -maxdepth 1 -type d -print 2>/dev/null | sort > "$AFTER_FILE" || true
if [ -z "$MISSION_DIR" ]; then
  MISSION_DIR="$(comm -13 "$BEFORE_FILE" "$AFTER_FILE" | tail -n 1 || true)"
  [ -n "$MISSION_DIR" ] && MISSION_ID="$(basename "$MISSION_DIR")"
fi
[ -n "$MISSION_DIR" ] || fail "could not determine new mission directory"
ROUND_DIR="$(find "$MISSION_DIR/rounds" -mindepth 1 -maxdepth 1 -type d | sort | tail -n 1 || true)"
[ -n "$ROUND_DIR" ] || fail "could not determine latest round directory for ${MISSION_ID}"
[ -f "$ROUND_DIR/acceptance_review.json" ] || fail "acceptance_review.json missing"

step "Resolve isolated dashboard ports"
DASHBOARD_PORT_CANDIDATES=()
while IFS= read -r candidate_port; do
  [ -n "$candidate_port" ] || continue
  DASHBOARD_PORT_CANDIDATES+=("$candidate_port")
done < <(
  uv run --python 3.13 python - <<'PY' "$REQUESTED_DASHBOARD_PORT"
import sys

from spec_orch.services.fresh_acpx_e2e import resolve_dashboard_port_candidates

for port in resolve_dashboard_port_candidates(int(sys.argv[1])):
    print(port)
PY
)
[ "${#DASHBOARD_PORT_CANDIDATES[@]}" -gt 0 ] || fail "could not resolve dashboard port"
if [ "${DASHBOARD_PORT_CANDIDATES[0]}" != "$REQUESTED_DASHBOARD_PORT" ]; then
  warn "dashboard port ${REQUESTED_DASHBOARD_PORT} busy; using isolated port ${DASHBOARD_PORT_CANDIDATES[0]}"
fi

step "Start isolated dashboard for exploratory critique"
EXPLORATORY_DASHBOARD_LOG=/tmp/spec_orch_exploratory_dashboard.log
DASHBOARD_STARTED=false
for candidate_port in "${DASHBOARD_PORT_CANDIDATES[@]}"; do
  DASHBOARD_PORT="$candidate_port"
  uv run --python 3.13 spec-orch dashboard --port "$DASHBOARD_PORT" >"$EXPLORATORY_DASHBOARD_LOG" 2>&1 &
  DASHBOARD_PID=$!
  if uv run --python 3.13 python - <<'PY' "$DASHBOARD_PORT"
import sys

from spec_orch.services.fresh_acpx_e2e import wait_for_dashboard_ready

port = sys.argv[1]
result = wait_for_dashboard_ready(f"http://127.0.0.1:{port}/", timeout_seconds=20.0)
print(result)
PY
  then
    DASHBOARD_STARTED=true
    break
  fi
  kill "$DASHBOARD_PID" >/dev/null 2>&1 || true
  wait "$DASHBOARD_PID" >/dev/null 2>&1 || true
  DASHBOARD_PID=""
  if grep -qiE "address already in use|Errno 98|Errno 48" "$EXPLORATORY_DASHBOARD_LOG"; then
    warn "dashboard port ${DASHBOARD_PORT} raced busy during startup; retrying on a new isolated port"
    continue
  fi
  cat "$EXPLORATORY_DASHBOARD_LOG" >&2 || true
  fail "dashboard never became ready for exploratory critique"
done
[ "$DASHBOARD_STARTED" = true ] || fail "dashboard could not start on any isolated port"
ok "dashboard started at http://127.0.0.1:${DASHBOARD_PORT}"

step "Materialize exploratory acceptance smoke report"
SPEC_ORCH_VISUAL_EVAL_URL="http://127.0.0.1:${DASHBOARD_PORT}" \
uv run --python 3.13 python - <<'PY' "$MISSION_ID" "$VARIANT" "$ROUND_DIR"
import json
import sys
from pathlib import Path

from spec_orch.services.fresh_acpx_e2e import run_fresh_exploratory_acceptance_review
from spec_orch.services.stability_acceptance import write_exploratory_acceptance_report

repo_root = Path(".").resolve()
mission_id = sys.argv[1]
variant = sys.argv[2]
round_dir = Path(sys.argv[3]).resolve()
operator_dir = repo_root / "docs" / "specs" / mission_id / "operator"
mission_payload = {}
mission_bootstrap_path = operator_dir / "mission_bootstrap.json"
if mission_bootstrap_path.exists():
    mission_payload = json.loads(mission_bootstrap_path.read_text(encoding="utf-8"))
browser_evidence = {}
browser_evidence_path = round_dir / "browser_evidence.json"
if browser_evidence_path.exists():
    browser_evidence = json.loads(browser_evidence_path.read_text(encoding="utf-8"))
run_fresh_exploratory_acceptance_review(
    repo_root=repo_root,
    mission_id=mission_id,
    round_dir=round_dir,
    mission_payload=mission_payload,
    browser_evidence=browser_evidence,
)
report = write_exploratory_acceptance_report(
    repo_root=repo_root,
    mission_id=mission_id,
    variant=variant,
    round_dir=round_dir,
    source="fresh-acpx-mission-smoke",
)
print(json.dumps(report))
PY
ok "exploratory acceptance smoke report written"

echo ""
echo -e "${GREEN}Exploratory acceptance smoke completed${NC}"
echo "Mission: ${MISSION_ID}"
echo "Round:   ${ROUND_DIR}"
echo "Report:  docs/specs/${MISSION_ID}/operator/exploratory_acceptance_smoke.md"
