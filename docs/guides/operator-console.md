# Operator Console Guide

## Goal

SpecOrch dashboard is now an operator console, not a generic status dashboard.

It is designed to answer six questions quickly:

1. What is happening now?
2. What is blocked, and why?
3. What needs my action?
4. What evidence supports the current state?
5. What can I safely do next?
6. Where should I intervene?

## Layout

The dashboard uses a three-zone workbench:

- `Left rail`
  - operator modes
  - Inbox
  - mission list
- `Main canvas`
  - Mission Detail
  - Approval Queue
  - Transcript
  - Visual QA
  - Costs & Budgets
- `Context Rail`
  - approval workspace
  - transcript inspector
  - artifact paths
  - round evidence

## Top-Level Modes

### Inbox

Use this to triage operator attention:

- approval-needed missions
- paused missions
- failed missions

Each item surfaces:

- mission title
- current round
- short reason
- latest approval state
- latest operator action when available

### Missions

Use this as the main workbench view for a selected mission.

### Approvals

Use this as the queue surface for approval-needed missions.

This is the fastest route when you want to process multiple operator decisions in one pass.

### Evidence

This forces the selected mission into transcript-first inspection mode.

## Mission Detail Tabs

Inside a selected mission, the main canvas supports:

- `Overview`
- `Transcript`
- `Approvals`
- `Visual QA`
- `Costs`

### Overview

Primary mission workbench:

- mission header
- phase / round / packet counts
- packet list
- latest round evidence
- acceptance criteria
- constraints

### Transcript

Transcript is not a chat window.

It is a multi-source execution timeline built from:

- `activity.log`
- `events.jsonl`
- `incoming_events.jsonl`
- round evidence blocks

Current transcript UX includes:

- block-type filtering
- command-burst grouping
- linked evidence markers
- transcript inspector in the right rail

### Approvals

Approvals are now treated as a dedicated operator surface.

Current approval flow includes:

- explicit approval state
- latest operator action
- recommended action
- direct action buttons

Dashboard actions currently write back through the mission `/btw` injection path.

### Visual QA

Visual QA is now a dedicated mission surface.

It shows:

- number of evaluated rounds
- blocking findings
- warnings
- latest confidence
- per-round findings
- linked artifact path to `visual_evaluation.json`

### Costs

Costs & Budgets is now a dedicated mission surface.

It shows:

- worker count
- input tokens
- output tokens
- cost in USD
- budget status
- per-worker builder report linkage

Current budget status is read as `unconfigured` unless a stricter budget layer is added later.

## Context Rail

The right rail is the persistent evidence and intervention panel.

It currently includes:

- available actions
- current packet
- approval workspace
- artifact links
- round evidence
- transcript inspector
- spec path

This rail should stay visible while switching mission tabs.

## Approval Workflow

Approval workflow is now explicitly stateful in the dashboard.

Current states include:

- `awaiting_human`
- `approval_granted`
- `revision_requested`
- `followup_requested`
- `not_applied`
- `failed`
- transient UI state: `pending`

Approval actions are persisted in:

```text
docs/specs/<mission_id>/operator/approval_actions.jsonl
```

This keeps operator decisions auditable even when guidance injection fails.

## Observability Sources

### Mission-level round artifacts

```text
docs/specs/<mission_id>/rounds/round-XX/
  round_summary.json
  round_decision.json
  supervisor_review.md
  visual_evaluation.json
```

### Packet-level worker telemetry

```text
docs/specs/<mission_id>/workers/<packet_id>/
  builder_report.json
  telemetry/
    incoming_events.jsonl
    events.jsonl
    activity.log
```

## How To Debug A Mission

Recommended order:

1. `Inbox`
   - determine whether the mission needs action
2. `Mission Detail`
   - understand current phase, round, and packet structure
3. `Transcript`
   - inspect command bursts, milestones, and linked evidence
4. `Context Rail`
   - inspect blocking question, latest operator action, and artifact paths
5. `Visual QA` or `Costs`
   - inspect specialized evidence when relevant

## CLI Complements

The dashboard is the primary operator surface, but CLI remains useful:

```bash
spec-orch mission logs <mission_id> <packet_id>
spec-orch mission logs <mission_id> <packet_id> --raw
spec-orch mission logs <mission_id> <packet_id> --events
```

Use the dashboard for high-level navigation and operator intervention.
Use the CLI when you need exact raw logs or shell-native workflows.
