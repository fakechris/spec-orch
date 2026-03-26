#!/usr/bin/env bash
#
# Supervised Mission smoke/full E2E
#
# Dry-run:
#   ./tests/e2e/supervised_mission_minimax.sh
#
# Full mode:
#   MINIMAX_API_KEY=$KEY ./tests/e2e/supervised_mission_minimax.sh --full
#
# Full mode exercises:
#   1. tools/visual_eval.py against a tiny local website
#   2. LiteLLMSupervisorAdapter with MiniMax
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
FULL_MODE=false

for arg in "$@"; do
  case "$arg" in
    --full) FULL_MODE=true ;;
  esac
done

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

step() { echo -e "\n${GREEN}▶ STEP: $1${NC}"; }
fail() { echo -e "${RED}✗ FAIL: $1${NC}" >&2; exit 1; }
ok()   { echo -e "${GREEN}✓ $1${NC}"; }
warn() { echo -e "${YELLOW}⚠ $1${NC}"; }

command -v python3 >/dev/null || fail "python3 not found"
command -v git >/dev/null || fail "git not found"
command -v rsync >/dev/null || fail "rsync not found"

if [ "$FULL_MODE" = true ]; then
  [ -n "${MINIMAX_API_KEY:-}" ] || fail "MINIMAX_API_KEY required for --full mode"
fi

WORK_DIR=$(mktemp -d -t spec-orch-supervised-XXXXXX)
cleanup() {
  if [ -n "${SERVER_PID:-}" ]; then
    kill "$SERVER_PID" >/dev/null 2>&1 || true
  fi
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT

step "Clone and install"
mkdir -p "$WORK_DIR/spec-orch-test"
rsync -a \
  --exclude ".git" \
  --exclude ".venv" \
  --exclude ".mypy_cache" \
  --exclude ".pytest_cache" \
  --exclude ".ruff_cache" \
  "$REPO_ROOT/" "$WORK_DIR/spec-orch-test/" >/dev/null
cd "$WORK_DIR/spec-orch-test"

step "Prepare MiniMax supervisor config sample"
cat > spec-orch.toml <<'EOF'
[builder]
adapter = "codex_exec"

[supervisor]
adapter = "litellm"
model = "minimax/MiniMax-M2.5"
api_key_env = "MINIMAX_API_KEY"

[supervisor.visual_evaluator]
adapter = "command"
command = ["{python}", "tools/visual_eval.py", "{input_json}", "{output_json}"]
timeout_seconds = 120
EOF
ok "spec-orch.toml written"

if [ "$FULL_MODE" != true ]; then
  [ -f tools/visual_eval.py ] || fail "tools/visual_eval.py missing"
  ok "visual evaluator sample script present"
  warn "Dry-run only. To execute MiniMax supervisor + browser sample:"
  echo "  MINIMAX_API_KEY=\$KEY ./tests/e2e/supervised_mission_minimax.sh --full"
  exit 0
fi

python3 -m venv .venv
source .venv/bin/activate

step "Install base package"
pip install --default-timeout 120 -e . >/dev/null
ok "base package installed"

step "Install planner + visual extras"
pip install --default-timeout 120 -e ".[planner,visual]" >/dev/null
ok "planner and visual extras installed"

step "Install Playwright browser"
python -m playwright install chromium >/dev/null
ok "chromium installed"

step "Start tiny local website"
mkdir -p test-site/settings
cat > test-site/index.html <<'EOF'
<!doctype html>
<html>
  <head><title>Home</title></head>
  <body data-ready="true"><h1>Home</h1></body>
</html>
EOF
cat > test-site/settings/index.html <<'EOF'
<!doctype html>
<html>
  <head><title>Settings</title></head>
  <body data-ready="true"><h1>Settings</h1></body>
</html>
EOF
python -m http.server 4173 --directory test-site >/tmp/spec_orch_supervised_http.log 2>&1 &
SERVER_PID=$!
sleep 1
ok "site running on http://127.0.0.1:4173"

step "Run browser-driven visual evaluator"
mkdir -p docs/specs/supervised-e2e/rounds/round-01
cat > docs/specs/supervised-e2e/rounds/round-01/input.json <<'EOF'
{
  "mission_id": "supervised-e2e",
  "round_id": 1,
  "round_dir": "docs/specs/supervised-e2e/rounds/round-01"
}
EOF
SPEC_ORCH_VISUAL_EVAL_URL="http://127.0.0.1:4173" \
SPEC_ORCH_VISUAL_EVAL_PATHS="/,/settings/" \
SPEC_ORCH_VISUAL_EVAL_WAIT_FOR="[data-ready]" \
python tools/visual_eval.py \
  docs/specs/supervised-e2e/rounds/round-01/input.json \
  docs/specs/supervised-e2e/rounds/round-01/output.json
[ -f docs/specs/supervised-e2e/rounds/round-01/output.json ] || fail "visual evaluator output missing"
ok "visual evaluator produced output"

step "Run MiniMax supervisor review"
python - <<'PY'
import json
from pathlib import Path

from spec_orch.domain.models import ExecutionPlan, RoundArtifacts, VisualEvaluationResult
from spec_orch.services.litellm_supervisor_adapter import LiteLLMSupervisorAdapter

repo_root = Path(".").resolve()
round_dir = repo_root / "docs/specs/supervised-e2e/rounds/round-01"
visual = VisualEvaluationResult.from_dict(
    json.loads((round_dir / "output.json").read_text(encoding="utf-8"))
)
adapter = LiteLLMSupervisorAdapter(
    repo_root=repo_root,
    model="minimax/MiniMax-M2.5",
    api_key=None,
    api_base=None,
)
decision = adapter.review_round(
    round_artifacts=RoundArtifacts(
        round_id=1,
        mission_id="supervised-e2e",
        visual_evaluation=visual,
    ),
    plan=ExecutionPlan(plan_id="supervised-e2e-plan", mission_id="supervised-e2e"),
    round_history=[],
    context={"mission": {"mission_id": "supervised-e2e", "mode": "e2e-smoke"}},
)
print(decision.action.value)
PY
[ -f docs/specs/supervised-e2e/rounds/round-01/round_decision.json ] || fail "round_decision.json missing"
ok "MiniMax supervisor completed"

echo ""
echo -e "${GREEN}supervised mission MiniMax E2E passed${NC}"
