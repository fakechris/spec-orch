from __future__ import annotations

from .app import DASHBOARD_HTML


def build_dashboard_html() -> str:
    return DASHBOARD_HTML


__all__ = ["DASHBOARD_HTML", "build_dashboard_html"]
