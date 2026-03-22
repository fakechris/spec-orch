import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture(autouse=True)
def _reset_memory_singleton():
    """Prevent memory singleton leakage between tests."""
    from spec_orch.services.memory.service import reset_memory_service

    reset_memory_service()
    yield
    reset_memory_service()
