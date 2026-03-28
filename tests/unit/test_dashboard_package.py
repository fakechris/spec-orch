from __future__ import annotations

from pathlib import Path


def test_dashboard_package_exports_app_factory() -> None:
    from spec_orch.dashboard import create_app
    from spec_orch.dashboard.app import create_app as package_create_app

    assert create_app is package_create_app


def test_dashboard_package_exposes_api_helpers() -> None:
    from spec_orch.dashboard.api import (
        _create_mission_draft,
        _gather_inbox,
        _gather_launcher_readiness,
        _gather_packet_transcript,
        _launch_mission,
    )

    assert callable(_gather_inbox)
    assert callable(_gather_packet_transcript)
    assert callable(_gather_launcher_readiness)
    assert callable(_create_mission_draft)
    assert callable(_launch_mission)


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
        _derive_approval_state,
        _gather_inbox,
        _gather_lifecycle_states,
        _gather_mission_detail,
        _gather_missions,
    )

    assert callable(_derive_approval_state)
    assert callable(_gather_missions)
    assert callable(_gather_inbox)
    assert callable(_gather_mission_detail)
    assert callable(_gather_lifecycle_states)


def test_dashboard_package_exposes_surface_helpers() -> None:
    from spec_orch.dashboard.surfaces import (
        _gather_approval_queue,
        _gather_mission_acceptance_review,
        _gather_mission_costs,
        _gather_mission_visual_qa,
    )

    assert callable(_gather_approval_queue)
    assert callable(_gather_mission_acceptance_review)
    assert callable(_gather_mission_visual_qa)
    assert callable(_gather_mission_costs)


def test_dashboard_package_exposes_control_helpers() -> None:
    from spec_orch.dashboard.control import (
        _control_eval,
        _control_overview,
        _gather_evolution_metrics,
        _gather_run_history,
        _get_spec_content,
    )

    assert callable(_gather_evolution_metrics)
    assert callable(_control_overview)
    assert callable(_control_eval)
    assert callable(_gather_run_history)
    assert callable(_get_spec_content)


def test_dashboard_package_exposes_shell_template() -> None:
    from spec_orch.dashboard.shell import build_dashboard_html

    html = build_dashboard_html()

    assert callable(build_dashboard_html)
    assert "operator-shell" in html
    assert "launcher-panel" in html
    assert "launcher-readiness" in html
    assert "Approve &amp; Plan" in html or "Approve & Plan" in html
    assert "Acceptance" in html
    assert "return value.split('\\n').map(line => line.trim()).filter(Boolean);" in html
    assert 'data-launcher-action="create-draft"' in html
    assert 'data-launcher-action="approve-plan"' in html
    assert 'data-launcher-action="linear-create"' in html
    assert 'data-launcher-action="linear-bind"' in html
    assert 'data-launcher-action="launch"' in html
    assert 'data-launcher-action="refresh-readiness"' in html
    assert '.launcher-status[data-tone="success"]' in html
    assert '.launcher-status[data-tone="failed"]' in html
    assert ".launcher-actions .btn.is-pending" in html
    assert "function setLauncherActionState(actionKey, state, label = null)" in html
    assert "if (!res.ok) throw new Error(data.error || 'Launcher readiness failed');" in html
    assert "launcherState.missionId = '';" in html
    assert "launcherState.linearIssueId = '';" in html
    assert "launcher-linear-issue-id" in html
    assert "resetLauncherActionState();" in html
    assert "Needs Attention" in html
    assert "All Missions" in html
    assert "Decision Queue" in html
    assert "Deep Evidence" in html
    assert "Supervisor" in html
    assert 'id="operator-nav-context"' in html
    assert "function phaseMeta(phase)" in html
    assert "function setOperatorMode(mode)" in html
    assert "syncOperatorRoute();" in html
    assert "renderMissions();" in html


def test_operator_console_asset_surfaces_acceptance_coverage_labels() -> None:
    asset_path = (
        Path(__file__).resolve().parents[2]
        / "src/spec_orch/dashboard_assets/static/operator-console.js"
    )
    source = asset_path.read_text(encoding="utf-8")

    assert "Coverage" in source
    assert "Next step" in source
    assert "Untested expected routes" in source
    assert "Array.isArray(latest.untested_expected_routes)" in source
    assert "Array.isArray(review.untested_expected_routes)" in source


def test_dashboard_mission_cards_expose_stable_automation_targets() -> None:
    app_path = Path(__file__).resolve().parents[2] / "src/spec_orch/dashboard/app.py"
    source = app_path.read_text(encoding="utf-8")

    assert 'data-automation-target="mission-card"' in source
    assert 'data-mission-id="${escAttr(m.mission_id)}"' in source


def test_dashboard_mission_tabs_expose_stable_automation_targets() -> None:
    app_path = Path(__file__).resolve().parents[2] / "src/spec_orch/dashboard/app.py"
    source = app_path.read_text(encoding="utf-8")

    assert 'data-automation-target="mission-tab"' in source
    assert 'data-tab-key="${escAttr(key)}"' in source
    assert "data-active=\"${activeTab === key ? 'true' : 'false'}\"" in source


def test_dashboard_operator_modes_and_launcher_actions_expose_workflow_targets() -> None:
    app_path = Path(__file__).resolve().parents[2] / "src/spec_orch/dashboard/app.py"
    source = app_path.read_text(encoding="utf-8")

    assert 'data-automation-target="open-launcher"' in source
    assert 'data-automation-target="operator-mode"' in source
    assert 'data-mode-key="inbox"' in source
    assert 'data-mode-key="missions"' in source
    assert 'data-mode-key="approvals"' in source
    assert 'data-mode-key="evidence"' in source
    assert "button.dataset.active = selectedOperatorMode === mode ? 'true' : 'false';" in source
    assert 'data-automation-target="launcher-action"' in source


def test_operator_console_approval_actions_expose_stable_automation_targets() -> None:
    asset_path = (
        Path(__file__).resolve().parents[2]
        / "src/spec_orch/dashboard_assets/static/operator-console.js"
    )
    source = asset_path.read_text(encoding="utf-8")

    assert 'data-automation-target="approval-action"' in source
    assert "data-action-key=\"${escAttr(action?.key || '')}\"" in source
    assert 'data-mission-id="${escAttr(missionId)}"' in source
    assert (
        '<button class="btn btn-green btn-sm" type="button" data-automation-target="approval-action"'
        in source
    )
