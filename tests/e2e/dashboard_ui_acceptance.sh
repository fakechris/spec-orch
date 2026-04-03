#!/usr/bin/env bash
#
# Dashboard/UI acceptance runner
#
# Dry-run:
#   ./tests/e2e/dashboard_ui_acceptance.sh
#
# Full mode:
#   ./tests/e2e/dashboard_ui_acceptance.sh --full
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
. "$SCRIPT_DIR/_shared_env.sh"
FULL_MODE=false

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
    *)
      fail "unknown argument: $1"
      ;;
  esac
  shift
done

cd "$REPO_ROOT"
activate_shared_worktree_context

if [ "$FULL_MODE" != true ]; then
  warn "Dry-run only. This script runs the canonical dashboard/UI acceptance subset."
  echo
  echo "To run full mode:"
  echo "  ./tests/e2e/dashboard_ui_acceptance.sh --full"
  exit 0
fi

step "Run canonical dashboard/API acceptance subset"
uv run --python 3.13 python -m pytest \
  tests/unit/test_dashboard_api.py \
  tests/unit/test_dashboard_package.py \
  -q \
  -k 'launcher_readiness_endpoint or acceptance_review_endpoint_surfaces_latest_review_and_filed_issues or mission_detail_endpoint_surfaces_approval_request or visual_qa_endpoint_aggregates_round_findings or visual_qa_endpoint_links_back_to_packet_transcripts or costs_endpoint_aggregates_worker_reports or approvals_endpoint_returns_dedicated_queue or approvals_batch_action_endpoint_processes_multiple_items or test_dashboard_package_exposes_api_helpers or test_dashboard_package_exposes_surface_helpers or test_dashboard_package_exposes_route_registrar or test_dashboard_package_exposes_shell_template'

step "Materialize dashboard/UI acceptance report"
uv run --python 3.13 python - <<'PY'
import json
from pathlib import Path

from spec_orch.services.stability_acceptance import write_dashboard_ui_acceptance_report

repo_root = Path(".").resolve()
report = write_dashboard_ui_acceptance_report(
    repo_root=repo_root,
    command="./tests/e2e/dashboard_ui_acceptance.sh --full",
    suite_summary={
        "status": "pass",
        "selected_tests": [
            "test_launcher_readiness_endpoint",
            "test_acceptance_review_endpoint_surfaces_latest_review_and_filed_issues",
            "test_mission_detail_endpoint_surfaces_approval_request",
            "test_visual_qa_endpoint_aggregates_round_findings",
            "test_visual_qa_endpoint_links_back_to_packet_transcripts",
            "test_costs_endpoint_aggregates_worker_reports",
            "test_approvals_endpoint_returns_dedicated_queue",
            "test_approvals_batch_action_endpoint_processes_multiple_items",
            "test_dashboard_package_exposes_api_helpers",
            "test_dashboard_package_exposes_surface_helpers",
            "test_dashboard_package_exposes_route_registrar",
            "test_dashboard_package_exposes_shell_template",
        ],
        "surface_summary": {
            "launcher": "pass",
            "mission_detail": "pass",
            "acceptance_review": "pass",
            "visual_qa": "pass",
            "costs": "pass",
            "approvals": "pass",
            "shell": "pass",
        },
    },
)
print(json.dumps(report))
PY
ok "dashboard/UI acceptance report written"

echo ""
echo -e "${GREEN}Dashboard/UI acceptance completed${NC}"
echo "Report:  .spec_orch/acceptance/dashboard_ui_acceptance.md"
