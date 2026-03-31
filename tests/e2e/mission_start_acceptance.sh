#!/usr/bin/env bash
#
# Mission-start smoke/full acceptance runner
#
# Dry-run:
#   ./tests/e2e/mission_start_acceptance.sh
#
# Full mode:
#   MINIMAX_API_KEY=$KEY MINIMAX_ANTHROPIC_BASE_URL=https://api.minimaxi.com/anthropic \
#     ./tests/e2e/mission_start_acceptance.sh --full
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

if [ "$FULL_MODE" != true ]; then
  warn "Dry-run only. This script wraps the fresh ACPX mission smoke path."
  echo
  echo "To run full mode:"
  echo "  MINIMAX_API_KEY=\$KEY MINIMAX_ANTHROPIC_BASE_URL=https://api.minimaxi.com/anthropic \\"
  echo "    ./tests/e2e/mission_start_acceptance.sh --full --variant ${VARIANT}"
  exit 0
fi

step "Capture mission directories before launch"
BEFORE_FILE="$(mktemp)"
AFTER_FILE="$(mktemp)"
find docs/specs -mindepth 1 -maxdepth 1 -type d -print 2>/dev/null | sort > "$BEFORE_FILE" || true

step "Run canonical fresh mission smoke harness"
./tests/e2e/fresh_acpx_mission_smoke.sh --full --variant "$VARIANT"

step "Identify the newly created mission"
find docs/specs -mindepth 1 -maxdepth 1 -type d -print 2>/dev/null | sort > "$AFTER_FILE" || true
MISSION_DIR="$(comm -13 "$BEFORE_FILE" "$AFTER_FILE" | tail -n 1 || true)"
[ -n "$MISSION_DIR" ] || fail "could not determine new mission directory"
MISSION_ID="$(basename "$MISSION_DIR")"
ROUND_DIR="$(find "$MISSION_DIR/rounds" -mindepth 1 -maxdepth 1 -type d | sort | tail -n 1 || true)"
[ -n "$ROUND_DIR" ] || fail "could not determine latest round directory for ${MISSION_ID}"
[ -f "$ROUND_DIR/fresh_acpx_mission_e2e_report.json" ] || fail "fresh_acpx_mission_e2e_report.json missing"

step "Materialize mission-start acceptance report"
uv run --python 3.13 python - <<'PY' "$MISSION_ID" "$VARIANT" "$ROUND_DIR"
import json
import sys
from pathlib import Path

from spec_orch.services.stability_acceptance import write_mission_start_acceptance_report

repo_root = Path(".").resolve()
mission_id = sys.argv[1]
variant = sys.argv[2]
round_dir = Path(sys.argv[3]).resolve()
report = write_mission_start_acceptance_report(
    repo_root=repo_root,
    mission_id=mission_id,
    launch_mode="fresh",
    variant=variant,
    round_dir=round_dir,
)
print(json.dumps(report))
PY
ok "mission-start acceptance report written"

echo ""
echo -e "${GREEN}Mission-start acceptance smoke completed${NC}"
echo "Mission: ${MISSION_ID}"
echo "Round:   ${ROUND_DIR}"
echo "Report:  docs/specs/${MISSION_ID}/operator/mission_start_acceptance.md"
