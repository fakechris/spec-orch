from __future__ import annotations


def test_dashboard_package_exports_app_factory() -> None:
    from spec_orch.dashboard import create_app
    from spec_orch.dashboard.app import create_app as package_create_app

    assert create_app is package_create_app


def test_dashboard_package_exposes_api_helpers() -> None:
    from spec_orch.dashboard.api import _gather_inbox, _gather_packet_transcript

    assert callable(_gather_inbox)
    assert callable(_gather_packet_transcript)


def test_dashboard_package_exposes_route_registrar() -> None:
    from spec_orch.dashboard.routes import register_routes

    assert callable(register_routes)


def test_dashboard_package_exposes_transcript_helpers() -> None:
    from spec_orch.dashboard.transcript import _gather_packet_transcript

    assert callable(_gather_packet_transcript)
