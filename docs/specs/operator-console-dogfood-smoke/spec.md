# Operator Console Dogfood Smoke

## Intent

Validate one real supervised mission through the operator console.

## Acceptance Criteria

- daemon picks up this issue as a mission
- dashboard shows Mission Detail / Transcript / Approval / Visual QA / Costs
- at least one round is visible end-to-end
- if ask_human appears, operator can intervene from the dashboard

## Constraints

- Keep this run small
- Prefer 1 wave / 1-2 packets

## Interface Contracts

<!-- frozen APIs / schemas — Wave 1 e2e tests validate against these contracts -->

### Mission Schema

A mission is identified by `id` and progresses through lifecycle states. Its full runtime
state is assembled from several subsystem views (detail, transcript, approvals, visual QA,
costs).

```json
{
  "id": "operator-console-dogfood-smoke",
  "status": "in_progress" | "drafting" | "approved" | "completed" | "archived",
  "detail": { ... },      // MissionDetail — GET /api/missions/{id}/detail
  "transcript": { ... },  // TranscriptData — GET /api/missions/{id}/packets/{packet_id}/transcript
  "approval_state": { ... }, // ApprovalState — derived from approval request + history
  "visual_qa_data": { ... }, // VisualQAData — GET /api/missions/{id}/visual-qa
  "costs": { ... }        // MissionCosts — GET /api/missions/{id}/costs
}
```

### Dashboard API Contracts

#### GET /api/missions/{mission_id}/detail
Returns the full mission detail surface.

Response fields:
- `mission` (object): `{mission_id, title, status, created_at, approved_at, completed_at, acceptance_criteria, constraints, spec_path}`
- `lifecycle` (object): `{phase, current_round, round_orchestrator_state, updated_at, ...}`
- `current_round` (int): highest completed round number
- `rounds` (array): list of `RoundSummary` objects (see below)
- `packets` (array): list of `{packet_id, title, wave_id, run_class, linear_issue_id, depends_on, files_in_scope}`
- `actions` (array): available operator actions e.g. `["approve", "inject_guidance", "resume", "stop", "rerun"]`
- `approval_request` (object | null): latest `ApprovalRequest` if pending
- `approval_history` (array): list of `ApprovalHistoryEntry` objects
- `approval_state` (object | null): `{status, summary}` derived from latest history entry
- `visual_qa` (object | null): `VisualQAData` for the mission
- `acceptance_review` (object): `{mission_id, summary, review_route, latest_review, reviews}`
- `costs` (object | null): `MissionCosts` for the mission
- `artifacts` (object): `{spec, plan, rounds_dir}` — relative paths

#### GET /api/missions/{mission_id}/packets/{packet_id}/transcript
Returns the execution transcript for a single packet.

Response fields:
- `mission_id` (string)
- `packet_id` (string)
- `entries` (array): raw log/event entries, each `{kind, timestamp, message, source_path}`
  - `kind`: `"activity"` | `"event"` | `"incoming"`
- `summary` (object): `{entry_count, kind_counts, block_counts, latest_timestamp, operator_readout}`
- `milestones` (array): `mission_packet_*` events, each `{timestamp, event_type, message}`
- `blocks` (array): grouped transcript blocks, each `{block_type, emphasis, timestamp, title, body, source_path, jump_targets}`
  - `block_type`: `"activity"` | `"message"` | `"tool"` | `"command_burst"` | `"milestone"` | `"supervisor"` | `"visual_finding"` | `"event"`
  - `emphasis`: `"log"` | `"narrative"` | `"tool"` | `"burst"` | `"decision"` | `"alert"` | `"milestone"` | `"event"` | `"neutral"`
- `telemetry` (object): `{activity_log, events, incoming}` — relative paths to telemetry files

#### GET /api/missions/{mission_id}/visual-qa
Returns visual evaluation results across all rounds.

Response fields:
- `mission_id` (string)
- `summary` (object): `{total_rounds, blocking_findings, warning_findings, latest_confidence, blocking_rounds, gallery_items, diff_items, comparison_rounds, focus_transcript_route}`
- `review_route` (string): dashboard URL to visual QA tab
- `rounds` (array): per-round visual results, each `{round_id, summary, confidence, status, artifact_path, findings, artifacts, gallery, primary_artifact, comparison, transcript_routes, review_route}`
  - `status`: `"pass"` | `"warning"` | `"blocking"`
  - `gallery` (array): `[{label, path, kind}]` where `kind` = `"image"` | `"diff"`
  - `comparison` (object | null): `{mode, primary: {label, path, kind}, related: [...]}`

#### GET /api/missions/{mission_id}/costs
Returns cost breakdown and budget incidents.

Response fields:
- `mission_id` (string)
- `summary` (object): `{workers, input_tokens, output_tokens, cost_usd, budget_status, thresholds, incident_count, remaining_budget_usd}`
  - `budget_status`: `"unconfigured"` | `"healthy"` | `"warning"` | `"critical"`
- `review_route` (string): dashboard URL to costs tab
- `focus_packet_id` (string | null): packet with highest cost
- `highest_cost_worker` (object | null): `{packet_id, cost_usd, report_path, transcript_route}`
- `incidents` (array): budget threshold violations, each `{severity, message, status_copy, recommended_action, operator_guidance, suggested_action: {label, route}, transcript_route, actual_cost_usd, threshold_usd}`
- `workers` (array): per-packet cost rows, each `{packet_id, report_path, adapter, turn_status, input_tokens, output_tokens, cost_usd, transcript_route}`

#### GET /api/approvals
Returns the approval queue (all missions with pending approval requests).

Response fields:
- `counts` (object): `{pending, missions, requires_followup, stale, aged, failed_actions}`
- `items` (array): approval items each `{mission_id, title, kind, phase, summary, updated_at, current_round, blocking_question, decision_action, latest_operator_action, approval_request, approval_state, recommended_action, wait_minutes, urgency, age_bucket, review_route, available_actions}`

### MissionRound Schema

Round summaries are embedded in the Mission Detail response.

```json
{
  "round_id": 1,
  "wave_id": 1,
  "status": "completed" | "executing" | "failed",
  "started_at": "2025-03-27T00:00:00Z",
  "completed_at": "2025-03-27T00:05:00Z" | null,
  "worker_results": [
    {
      "packet_id": "dogfood-contract-scaffold",
      "builder_result": { "succeeded": true, "adapter": "codex", ... },
      "review_result": { "verdict": "accepted", ... }
    }
  ],
  "decision": {
    "action": "ASK_HUMAN" | "APPROVE" | "RETRY" | "STOP" | "CONTINUE",
    "reason_code": "string",
    "summary": "string",
    "confidence": 0.95,
    "affected_workers": [],
    "artifacts": {},
    "session_ops": { "reuse": [], "spawn": [], "cancel": [] },
    "blocking_questions": ["Should we proceed with rollout?"],
    "plan_patch": null | { "modified_packets": {}, "added_packets": [], "removed_packet_ids": [], "reason": "" }
  }
}
```

### HumanInterventionRequest Schema (ask_human contract)

Emitted when `RoundDecision.action == ASK_HUMAN`. The dashboard surfaces this as an
approval request on the Approvals tab.

```json
{
  "round_id": 1,
  "timestamp": "2025-03-27T00:05:00Z",
  "summary": "Human approval required before rollout.",
  "blocking_question": "Should we proceed with rollout?" | null,
  "decision_action": "ASK_HUMAN",
  "review_route": "/?mission=operator-console-dogfood-smoke&mode=missions&tab=approvals&round=1",
  "actions": [
    { "key": "approve", "label": "Approve", "message": "@approve Should we proceed..." },
    { "key": "request_revision", "label": "Request revision", "message": "@request-revision ..." },
    { "key": "ask_followup", "label": "Ask follow-up", "message": "@follow-up ..." }
  ]
}
```

### Daemon Mission Pickup Interface

The daemon claims an issue for execution by acquiring a lockfile.

- **Lockfile path**: `.spec_orch_locks/{issue_id}.lock`
- **Lockfile content**: Unix timestamp (string) written atomically
- **Claim**: `Daemon._claim(issue_id)` → writes lockfile
- **Release**: `Daemon._release(issue_id)` → deletes lockfile
- **Check locked**: `Daemon._is_locked(issue_id)` → bool

Pickup cycle:
1. Daemon scans for un-locked issues with pending Linear assignments
2. Daemon calls `_claim(issue_id)` to acquire exclusive lock
3. Daemon executes the mission round
4. On completion/failure, daemon calls `_release(issue_id)`

If a lockfile exists, the issue is considered "owned" by another daemon instance or a
stuck process. The lockfile also serves as the basis for `MissionLifecycleManager`
state tracking.
