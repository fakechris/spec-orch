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
FULL_MODE=false
VARIANT="${SPEC_ORCH_FRESH_VARIANT:-default}"

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

MISSION_DIR=""
MISSION_ID=""
ROUND_DIR=""
HARNESS_PID=""
HARNESS_LOG=""

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

step "Materialize exploratory acceptance smoke report"
uv run --python 3.13 python - <<'PY' "$MISSION_ID" "$VARIANT" "$ROUND_DIR"
import json
import sys
from pathlib import Path

from spec_orch.services.stability_acceptance import write_exploratory_acceptance_report

repo_root = Path(".").resolve()
mission_id = sys.argv[1]
variant = sys.argv[2]
round_dir = Path(sys.argv[3]).resolve()
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
