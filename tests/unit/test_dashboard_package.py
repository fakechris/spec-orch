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
        _gather_showcase_workbench,
        _launch_mission,
    )

    assert callable(_gather_inbox)
    assert callable(_gather_packet_transcript)
    assert callable(_gather_showcase_workbench)
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
    assert "Showcase" in html
    assert "Deep Evidence" in html
    assert "Supervisor" in html
    assert 'id="operator-nav-context"' in html
    assert "function phaseMeta(phase)" in html
    assert "function setOperatorMode(mode)" in html
    assert "syncOperatorRoute();" in html
    assert "renderMissions();" in html
    assert "const raw = typeof ev.data === 'string' ? ev.data.trim() : '';" in html
    assert "if (!raw) return;" in html
    assert "async function refreshLauncherMissionSelection(missionId)" in html
    assert "console.warn('Launcher follow-up refresh failed'" in html
    assert "const syncError = await refreshLauncherMissionSelection(data.mission_id);" in html
    assert "const syncError = await refreshLauncherMissionSelection(missionId);" in html


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
    assert "onclick='selectMission(${safeJsArg(m.mission_id)})'" in source


def test_dashboard_select_mission_handlers_use_safe_attribute_quotes() -> None:
    app_path = Path(__file__).resolve().parents[2] / "src/spec_orch/dashboard/app.py"
    source = app_path.read_text(encoding="utf-8")

    assert (
        "onclick='openInboxItem(${safeJsArg(item.mission_id)}, ${safeJsArg(item.review_route || \"\")})'"
        in source
    )


def test_dashboard_mission_tabs_expose_stable_automation_targets() -> None:
    app_path = Path(__file__).resolve().parents[2] / "src/spec_orch/dashboard/app.py"
    source = app_path.read_text(encoding="utf-8")

    assert 'data-automation-target="mission-tab"' in source
    assert 'data-automation-target="mission-detail-ready"' in source
    assert 'data-tab-key="${escAttr(key)}"' in source
    assert "data-active=\"${activeTab === key ? 'true' : 'false'}\"" in source


def test_dashboard_cutover_maps_legacy_acceptance_tab_to_judgment() -> None:
    app_path = Path(__file__).resolve().parents[2] / "src/spec_orch/dashboard/app.py"
    source = app_path.read_text(encoding="utf-8")

    assert "selectedMissionTab = parsed.tab === 'visual' ? 'visual-qa' : parsed.tab;" not in source
    assert "parsed.tab === 'acceptance' ? 'judgment'" in source


def test_dashboard_cutover_thins_acceptance_tab_and_keeps_raw_acceptance_bridge() -> None:
    app_path = Path(__file__).resolve().parents[2] / "src/spec_orch/dashboard/app.py"
    source = app_path.read_text(encoding="utf-8")

    assert "['acceptance', 'Acceptance']" not in source
    assert "Open raw acceptance artifact" in source
    assert "acceptance_review_route" in source


def test_dashboard_operator_modes_and_launcher_actions_expose_workflow_targets() -> None:
    app_path = Path(__file__).resolve().parents[2] / "src/spec_orch/dashboard/app.py"
    source = app_path.read_text(encoding="utf-8")

    assert 'data-automation-target="open-launcher"' in source
    assert 'data-automation-target="operator-mode"' in source
    assert 'data-mode-key="inbox"' in source
    assert 'data-mode-key="missions"' in source
    assert 'data-mode-key="learning"' in source
    assert 'data-mode-key="showcase"' in source
    assert 'data-mode-key="approvals"' in source
    assert 'data-mode-key="evidence"' in source


def test_dashboard_showcase_surface_renders_governance_and_lineage_fields() -> None:
    app_path = Path(__file__).resolve().parents[2] / "src/spec_orch/dashboard/app.py"
    source = app_path.read_text(encoding="utf-8")

    assert "Linked workspaces" in source
    assert "Lineage notes" in source
    assert "Compared with" in source
    assert "Source-run compare" in source
    assert "Governance Story" in source
    assert "Promotion decision" in source
    assert "Latest release notes" in source
    assert "item.workspace_ids" in source
    assert "item.lineage_notes" in source
    assert "item.compare_target_release_id" in source
    assert "item.source_run_compare" in source
    assert "item.governance_story" in source
    assert "item.lineage_drilldown" in source
    assert "button.dataset.active = selectedOperatorMode === mode ? 'true' : 'false';" in source
    assert 'data-automation-target="launcher-action"' in source
    assert 'data-automation-target="launcher-field"' in source
    assert 'data-field-key="title"' in source
    assert 'data-field-key="mission-id"' in source
    assert 'data-field-key="acceptance"' in source
    assert 'data-automation-target="launcher-status"' in source


def test_operator_console_approval_actions_expose_stable_automation_targets() -> None:
    asset_path = (
        Path(__file__).resolve().parents[2]
        / "src/spec_orch/dashboard_assets/static/operator-console.js"
    )
    source = asset_path.read_text(encoding="utf-8")
    app_source = (Path(__file__).resolve().parents[2] / "src/spec_orch/dashboard/app.py").read_text(
        encoding="utf-8"
    )

    assert 'data-automation-target="approval-action"' in source
    assert 'data-automation-target="approval-state"' in source
    assert 'data-automation-scope="${escAttr(scope)}"' in source
    assert 'data-approval-status="${escAttr(stateStatus)}"' in source
    assert "data-action-key=\"${escAttr(action?.key || '')}\"" in source
    assert 'data-mission-id="${escAttr(missionId)}"' in source
    assert (
        "renderApprovalWorkspace(approvalRequest, approvalHistory, approvalState, mission.mission_id || '', 'mission-detail')"
        in app_source
    )
    assert (
        "renderApprovalWorkspace(approvalRequest, approvalHistory, approvalState, mission.mission_id || '', 'context-rail')"
        in app_source
    )
    assert (
        '<button class="btn btn-green btn-sm" type="button" data-automation-target="approval-action"'
        in source
    )
    assert "delete approvalActionStates[missionId];" in app_source
    assert "renderMissionDetail(selectedMissionDetail);" in app_source
    assert "renderContextRail(selectedMissionDetail);" in app_source


def test_operator_console_safe_js_args_use_single_quoted_handlers() -> None:
    asset_path = (
        Path(__file__).resolve().parents[2]
        / "src/spec_orch/dashboard_assets/static/operator-console.js"
    )
    source = asset_path.read_text(encoding="utf-8")

    assert (
        "onclick='triggerApprovalAction(${safeJsArg(missionId)}, ${safeJsArg(action?.key || '')})'"
        in source
    )
    assert (
        "onclick='openDiscussPreset(${safeJsArg(missionId)}, ${safeJsArg((approvalRequest?.actions || [])[0]?.message || '')})'"
        in source
    )
    assert "onclick='navigateOperatorRoute(${safeJsArg(route)})'" in source


def test_operator_console_transcript_and_internal_route_targets_are_exposed() -> None:
    asset_path = (
        Path(__file__).resolve().parents[2]
        / "src/spec_orch/dashboard_assets/static/operator-console.js"
    )
    source = asset_path.read_text(encoding="utf-8")

    assert 'data-automation-target="packet-row"' in source
    assert 'data-automation-target="transcript-packet-chooser"' in source
    assert "Choose a packet" in source
    assert "Open current packet evidence" in source
    assert "Choose a packet above to inspect its transcript timeline." in source
    assert "Current packet" in source


def test_dashboard_transcript_tab_primes_packet_selection_and_transcript_load() -> None:
    app_path = Path(__file__).resolve().parents[2] / "src/spec_orch/dashboard/app.py"
    source = app_path.read_text(encoding="utf-8")

    assert "async function setMissionTab(tab)" in source
    assert "if (tab == 'transcript' && selectedMissionDetail)" in source
    assert "const packetIds = packets.map(packet => packet.packet_id);" in source
    assert "await loadSelectedPacketTranscript();" in source
    assert 'data-automation-target="transcript-packet-chooser-section"' in source
    assert "Open first packet evidence" in source


def test_dashboard_inbox_and_approval_queue_expose_workflow_targets() -> None:
    app_source = (Path(__file__).resolve().parents[2] / "src/spec_orch/dashboard/app.py").read_text(
        encoding="utf-8"
    )
    asset_source = (
        Path(__file__).resolve().parents[2]
        / "src/spec_orch/dashboard_assets/static/operator-console.js"
    ).read_text(encoding="utf-8")

    assert 'data-automation-target="inbox-item"' in app_source
    assert "data-inbox-kind=\"${escAttr(item.kind || 'attention')}\"" in app_source
    assert "data-review-route=\"${escAttr(item.review_route || '')}\"" in app_source
    assert (
        "onclick='openInboxItem(${safeJsArg(item.mission_id)}, ${safeJsArg(item.review_route || \"\")})'"
        in app_source
    )
    assert 'data-automation-target="approval-queue-item"' in asset_source
    assert 'data-automation-target="approval-queue-selection"' in asset_source
    assert 'data-automation-target="approval-batch-toggle-all"' in asset_source
    assert 'data-automation-target="approval-batch-action"' in asset_source
    assert 'data-automation-target="approval-batch-status"' in asset_source
    assert 'data-automation-target="approval-queue-review-route"' in asset_source
    assert 'data-automation-target="approval-queue-state"' in asset_source
    assert (
        "onchange='toggleApprovalSelection(${safeJsArg(item?.mission_id || \"\")}, this.checked)'"
        in asset_source
    )
    assert 'data-packet-id="${escAttr(packet?.packet_id)}"' in asset_source
    assert 'data-automation-target="transcript-filter"' in asset_source
    assert 'data-filter-key="${escAttr(filter.key)}"' in asset_source
    assert 'data-automation-target="transcript-block"' in asset_source
    assert 'data-block-index="${escAttr(String(blockIndex))}"' in asset_source
    assert 'data-automation-target="transcript-inspector"' in asset_source
    assert 'data-packet-id="${escAttr(selectedPacketId)}"' in asset_source
    assert 'data-automation-target="internal-route"' in asset_source
    assert 'data-route-label="${escAttr(label)}"' in asset_source


def test_operator_console_exports_internal_route_helper() -> None:
    asset_path = (
        Path(__file__).resolve().parents[2]
        / "src/spec_orch/dashboard_assets/static/operator-console.js"
    )
    source = asset_path.read_text(encoding="utf-8")

    assert "window.SpecOrchOperatorConsole = {" in source
    assert "renderInternalRouteButton," in source
    assert "renderTranscriptPacketChooser," in source


def test_dashboard_context_rail_review_buttons_use_internal_route_helper() -> None:
    app_path = Path(__file__).resolve().parents[2] / "src/spec_orch/dashboard/app.py"
    source = app_path.read_text(encoding="utf-8")

    assert "renderInternalRouteButton(visualQa.review_route, 'Open visual review')" in source
    assert "renderInternalRouteButton(acceptance.review_route, 'Open acceptance review')" in source
    assert "renderInternalRouteButton(costs.review_route, 'Open cost review')" in source


def test_dashboard_context_rail_renders_runtime_chain_section() -> None:
    app_path = Path(__file__).resolve().parents[2] / "src/spec_orch/dashboard/app.py"
    source = app_path.read_text(encoding="utf-8")

    assert "<h3>Runtime chain</h3>" in source
    assert "const runtimeChain = detail.runtime_chain || {};" in source
    assert "runtimeChain?.current_status?.phase" in source
    assert "runtimeChain?.recent_events?.length || 0" in source


def test_dashboard_secondary_mission_actions_expose_automation_targets() -> None:
    app_path = Path(__file__).resolve().parents[2] / "src/spec_orch/dashboard/app.py"
    source = app_path.read_text(encoding="utf-8")

    assert 'data-automation-target="mission-secondary-action"' in source
    assert 'data-action-key="discuss"' in source
    assert 'data-action-key="refresh"' in source


def test_dashboard_inbox_review_routes_and_pending_packet_routes_are_preserved() -> None:
    app_path = Path(__file__).resolve().parents[2] / "src/spec_orch/dashboard/app.py"
    source = app_path.read_text(encoding="utf-8")

    assert "async function openInboxItem(missionId, reviewRoute = '')" in source
    assert "if (reviewRoute) {" in source
    assert "const navigated = await navigateOperatorRoute(reviewRoute);" in source
    assert "if (navigated) {" in source
    assert "console.warn('Failed to navigate inbox review route'" in source
    assert "await selectMission(missionId);" in source
    assert "selectedMissionDetail.packets?.[0]?.packet_id || pendingRoutePacketId || null" in source
    assert "if (!parsed) return false;" in source
    assert "return true;" in source


def test_dashboard_discuss_action_uses_js_safe_mission_id() -> None:
    app_path = Path(__file__).resolve().parents[2] / "src/spec_orch/dashboard/app.py"
    source = app_path.read_text(encoding="utf-8")

    assert 'data-action-key="discuss"' in source
    assert "onclick='openDiscuss(${safeJsArg(mission.mission_id || \"\")})'" in source
