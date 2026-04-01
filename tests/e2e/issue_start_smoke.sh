#!/usr/bin/env bash
#
# Issue-start smoke/full acceptance runner
#
# Dry-run:
#   ./tests/e2e/issue_start_smoke.sh
#
# Full mode:
#   ./tests/e2e/issue_start_smoke.sh --full --issue-id SPC-1
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
FULL_MODE=false
ISSUE_ID="SPC-1"
SOURCE="fixture"

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
    --issue-id)
      shift
      [ "$#" -gt 0 ] || fail "--issue-id requires a value"
      ISSUE_ID="$1"
      ;;
    --source)
      shift
      [ "$#" -gt 0 ] || fail "--source requires a value"
      SOURCE="$1"
      ;;
    *)
      fail "unknown argument: $1"
      ;;
  esac
  shift
done

command -v python3 >/dev/null || fail "python3 not found"

cd "$REPO_ROOT"

if [ "$FULL_MODE" != true ]; then
  warn "Dry-run only. This script expects:"
  echo "  - spec-orch.toml present"
  echo "  - a runnable builder/reviewer config"
  echo "  - fixture issue present under fixtures/issues/"
  echo
  echo "To run full mode:"
  echo "  ./tests/e2e/issue_start_smoke.sh --full --issue-id ${ISSUE_ID}"
  exit 0
fi

[ -f spec-orch.toml ] || fail "spec-orch.toml missing"
[ -f "fixtures/issues/${ISSUE_ID}.json" ] || fail "fixture issue fixtures/issues/${ISSUE_ID}.json missing"

step "Run preflight"
PREFLIGHT_EXIT=0
if uv run --python 3.13 spec-orch preflight --json >/tmp/spec_orch_issue_start_preflight.json; then
  ok "preflight completed"
else
  PREFLIGHT_EXIT=$?
  warn "preflight exited with status ${PREFLIGHT_EXIT}; materializing smoke report before failing"
fi

step "Run fixture issue through full pipeline"
RUN_EXIT=0
RUN_LOG="$(mktemp -t spec_orch_issue_start_run.XXXXXX.log)"
LAST_CHAIN_STATUS=""
if [ "$PREFLIGHT_EXIT" -eq 0 ]; then
  uv run --python 3.13 spec-orch run "$ISSUE_ID" --source "$SOURCE" --auto-approve >"$RUN_LOG" 2>&1 &
  RUN_PID=$!
  while kill -0 "$RUN_PID" 2>/dev/null; do
    CHAIN_STATUS="$(uv run --python 3.13 spec-orch chain status --issue-id "$ISSUE_ID" 2>/dev/null || true)"
    if [ -n "$CHAIN_STATUS" ] && [ "$CHAIN_STATUS" != "$LAST_CHAIN_STATUS" ]; then
      echo "chain> $CHAIN_STATUS"
      LAST_CHAIN_STATUS="$CHAIN_STATUS"
    fi
    sleep 5
  done
  if wait "$RUN_PID"; then
    :
  else
    RUN_EXIT=$?
    warn "spec-orch run exited with status ${RUN_EXIT}; materializing smoke report before failing"
    tail -n 80 "$RUN_LOG" >&2 || true
  fi
else
  RUN_EXIT=$PREFLIGHT_EXIT
  warn "Skipping fixture issue run because preflight failed"
fi

step "Materialize issue-start acceptance report"
uv run --python 3.13 python - <<'PY' "$ISSUE_ID" "$RUN_EXIT"
import json
import sys
from pathlib import Path

from spec_orch.services.stability_acceptance import write_issue_start_acceptance_report

repo_root = Path(".").resolve()
issue_id = sys.argv[1]
run_exit_code = int(sys.argv[2])
preflight_path = Path("/tmp/spec_orch_issue_start_preflight.json")
try:
    preflight = (
        json.loads(preflight_path.read_text(encoding="utf-8"))
        if preflight_path.exists()
        else {}
    )
except (OSError, json.JSONDecodeError):
    preflight = {}
report = write_issue_start_acceptance_report(
    repo_root=repo_root,
    issue_id=issue_id,
    fixture_issue_id=issue_id,
    preflight_report=preflight,
    run_exit_code=run_exit_code,
)
print(json.dumps(report))
PY
ok "issue-start acceptance report written to .spec_orch/acceptance/"

[ "$RUN_EXIT" -eq 0 ] || fail "issue-start pipeline smoke failed"
echo ""
echo -e "${GREEN}Issue-start acceptance smoke completed${NC}"
echo "Issue:   ${ISSUE_ID}"
echo "Report:  .spec_orch/acceptance/issue_start_smoke.md"
