"""Backward-compatible re-export — module moved to services/context/."""

from spec_orch.services.context.context_assembler import *  # noqa: F401,F403
from spec_orch.services.context.context_assembler import (  # noqa: F401
    _detect_chars_per_token,
    _truncate,
)
