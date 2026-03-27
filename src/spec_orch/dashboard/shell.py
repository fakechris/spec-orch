from __future__ import annotations


def build_dashboard_html() -> str:
    from .app import DASHBOARD_HTML

    return DASHBOARD_HTML


__all__ = ["build_dashboard_html"]
