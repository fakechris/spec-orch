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


def test_dashboard_package_exposes_approval_helpers() -> None:
    from spec_orch.dashboard.approvals import (
        _gather_latest_approval_request,
        _load_approval_history,
        _record_approval_action,
        _resolve_approval_action,
    )

    assert callable(_gather_latest_approval_request)
    assert callable(_load_approval_history)
    assert callable(_record_approval_action)
    assert callable(_resolve_approval_action)


def test_dashboard_package_exposes_mission_helpers() -> None:
    from spec_orch.dashboard.missions import (
        _gather_inbox,
        _gather_lifecycle_states,
        _gather_mission_detail,
        _gather_missions,
    )

    assert callable(_gather_missions)
    assert callable(_gather_inbox)
    assert callable(_gather_mission_detail)
    assert callable(_gather_lifecycle_states)
