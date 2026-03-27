"""Compatibility wrapper for the dashboard package.

The canonical implementation now lives in :mod:`spec_orch.dashboard.app`.
"""

from __future__ import annotations

from spec_orch.dashboard.app import create_app

__all__ = ["create_app"]
