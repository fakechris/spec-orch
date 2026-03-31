#!/usr/bin/env bash
#
# Stability acceptance status refresh
#
# Usage:
#   ./tests/e2e/update_stability_acceptance_status.sh
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$REPO_ROOT"

uv run --python 3.13 python - <<'PY'
import json
from pathlib import Path

from spec_orch.services.stability_acceptance import write_stability_acceptance_status

repo_root = Path(".").resolve()
report = write_stability_acceptance_status(repo_root=repo_root)
print(json.dumps(report))
PY
