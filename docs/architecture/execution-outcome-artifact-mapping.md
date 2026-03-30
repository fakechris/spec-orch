# Execution Outcome Artifact Mapping

> Status: current-state mapping document, not a target design
> Date: 2026-03-29

## Purpose

This document maps the proposed `ExecutionOutcome.artifacts` semantic keys to the files and producers that already exist today.

It does **not** define a final schema implementation.
It only answers:

- which semantic keys already exist in `issue` execution
- which semantic keys already exist in `Mission` leaf execution
- which semantic keys are only completed at the `Mission` round level

This is the bridge between:

- the execution decomposition
- the object boundary recovery
- the future shared `ExecutionOutcome` vocabulary

## Scope

We are mapping three current execution paths:

1. `issue` run
2. `Mission` leaf execution (`WorkPacket` worker execution)
3. `Mission` round execution (`RoundOrchestrator` evidence collection + supervision)

The semantic keys being mapped are:

- `builder_report`
- `event_log`
- `manifest`
- `workspace_root`
- `verification_report`
- `review_report`
- `gate_report`
- `acceptance_report`
- `visual_report`
- `browser_evidence`

## Reading Rule

Each row below answers a semantic question, not a file-name question.

Example:

- `builder_report` means “where is the builder outcome evidenced?”
- it does **not** mean every path must use a file literally named `builder_report.json`

## 1. Mapping Table

| Semantic key | issue run | Mission leaf | Mission round | Notes |
|---|---|---|---|---|
| `builder_report` | `workspace/builder_report.json` via builder adapter | `docs/specs/<mission_id>/workers/<packet_id>/builder_report.json` via `WorkerHandle.send()` | indirect, included in `RoundArtifacts.builder_reports` and round payloads | already naturally shared |
| `event_log` | `workspace/telemetry/events.jsonl`, `workspace/telemetry/incoming_events.jsonl`, `workspace/telemetry/activity.log`; unified export at `workspace/run_artifact/events.jsonl` | `docs/specs/<mission_id>/workers/<packet_id>/telemetry/incoming_events.jsonl` and `telemetry/activity.log` | no single canonical round event log file; round summary references worker/round artifacts | shared semantically, not structurally |
| `manifest` | canonical `workspace/run_artifact/manifest.json`; legacy bridge `workspace/artifact_manifest.json` | no standalone manifest file; closest current form is `RoundArtifacts.manifest_paths` collecting worker report + scoped files | `round_summary.json` and supervisor payload include `manifest_paths`; not yet a canonical manifest object | currently fragmented on mission path |
| `workspace_root` | issue workspace root prepared by `WorkspaceService` | `docs/specs/<mission_id>/workers/<packet_id>` via `RoundOrchestrator._packet_workspace()` | `docs/specs/<mission_id>/rounds/round-XX` for round-local evidence; mission root is `docs/specs/<mission_id>` | should be treated as an `ArtifactRef` with `carrier_kind=directory` |
| `verification_report` | embedded in `report.json`, `run_artifact/live.json`, and explain report; no dedicated verification JSON file | usually absent at leaf completion time | present as structured `verification_outputs` inside `RoundArtifacts`, `round_summary.json`, and supervisor prompt payload | mission verification is mostly round-owned today |
| `review_report` | `workspace/review_report.json` when review exists | absent | `docs/specs/<mission_id>/rounds/round-XX/supervisor_review.md` is the current closest review artifact | review is leaf-owned for issue, round-owned for mission |
| `gate_report` | embedded in `report.json`, `run_artifact/live.json`, `run_artifact/conclusion.json`, and `explain.md`; no dedicated gate JSON file | absent | packet-level gate verdicts exist as `gate_verdicts` in `RoundArtifacts` and round payloads; no standalone gate file | gate exists in both paths, but file shape differs |
| `acceptance_report` | `workspace/acceptance.json` after human acceptance | absent | `docs/specs/<mission_id>/rounds/round-XX/acceptance_review.json` | acceptance is optional issue post-step, but native round artifact in mission |
| `visual_report` | usually absent in classic issue run | absent | `docs/specs/<mission_id>/rounds/round-XX/visual_evaluation.json` | mission-only today |
| `browser_evidence` | usually absent in classic issue run | absent | stored inside `acceptance_review.json` input/output flow and collected under round acceptance evidence paths; produced by `collect_playwright_browser_evidence()` | mission-only today, and still structurally loose |

## 2. Path-by-Path Notes

### 2.1 issue run

Current issue execution has the most complete leaf-level evidence bundle.

Its strongest artifact producers are:

- builder adapters writing `builder_report.json`
- `ActivityLogger` writing `telemetry/activity.log`
- telemetry stream writers producing `events.jsonl` / `incoming_events.jsonl`
- `RunReportWriter` writing `report.json` and `artifact_manifest.json`
- `RunArtifactService` writing `run_artifact/live.json`, `events.jsonl`, `conclusion.json`, `retro.json`, `manifest.json`
- `ArtifactService` writing `explain.md` and `acceptance.json`

This means the issue path already behaves like a relatively complete `ExecutionOutcome + EvidenceBundle` producer.

What it still lacks is not evidence volume, but evidence normalization:

- verification is embedded, not first-class as its own artifact
- gate is embedded, not first-class as its own artifact
- review is both embedded and separately persisted

### 2.2 Mission leaf

Mission leaf execution is intentionally much thinner.

The worker packet path currently produces:

- packet workspace directory
- builder report
- worker telemetry logs
- changed files under packet scope
- session identity

It does **not** usually produce:

- standalone review artifact
- standalone gate artifact
- standalone acceptance artifact
- canonical manifest file

That is why the mission leaf should be treated as a valid `ExecutionOutcome` producer with sparse artifacts.

Its evidence is sufficient for the next owner to reason over, but not sufficient to claim local closure.

### 2.3 Mission round

Mission round is where the mission path becomes evidence-rich.

The round layer produces or persists:

- `round_summary.json`
- `round_decision.json`
- `supervisor_review.md`
- `visual_evaluation.json`
- `acceptance_review.json`
- round-local `task.spec.md`
- aggregated `manifest_paths`
- aggregated `builder_reports`
- aggregated `verification_outputs`
- aggregated `gate_verdicts`

This confirms the core architectural distinction:

- issue path closes at leaf level
- mission path closes at round level

So for a shared `ExecutionOutcome.artifacts` vocabulary, the mission path should be allowed to populate some semantic keys only at `scope=round`.

## 3. What Is Already Naturally Shared

These semantic keys already make sense across both issue and mission paths:

- `builder_report`
- `event_log`
- `workspace_root`

These are the safest first keys for any future shared `ArtifactRef` mapping.

## 4. What Exists In Both Paths But At Different Layers

These semantic keys exist in both worlds, but not at the same closure location:

- `verification_report`
- `review_report`
- `gate_report`
- `acceptance_report`

Interpretation:

- issue path tends to fill them at `scope=leaf`
- mission path tends to fill them at `scope=round`

This is the strongest evidence for the rule we already established:

> shared schema, different closure location

## 5. What Is Mission-Specific Today

These semantic keys are currently mission-specific or mission-native:

- `visual_report`
- `browser_evidence`

That does **not** mean they should never exist for issue execution.
It only means the current implementation provides them primarily through the mission round acceptance/visual flow.

## 6. Recommended Interpretation For ArtifactRef

Based on current-state mapping, the most stable interpretation of `ArtifactRef` is:

```text
ArtifactRef
- key
- scope
- producer_kind
- subject_kind
- carrier_kind
- path
```

Reason:

- the semantic key stays stable even if filenames change
- `scope` explains whether this evidence belongs to leaf or round closure
- `subject_kind` prevents issue evidence from being confused with round evidence
- `carrier_kind` prevents file paths from being mistaken for object identity

## 7. Extra Current Artifacts Not In The Minimal Shared Set

There are several useful current artifacts that do not need to be in the first minimal shared set:

- `task.spec.md`
- `progress.md`
- `explain.md`
- `retro.json`
- `conclusion.json`
- `mission_bootstrap.json`
- `launch.json`
- `daemon_run.json`

These should be treated as supporting artifacts for now, not mandatory semantic keys in the first shared `ExecutionOutcome.artifacts` vocabulary.

## 8. Conclusion

The mapping confirms three things:

1. We do not need identical file layouts to share `ExecutionOutcome.artifacts`
2. We do need stable semantic keys
3. We must preserve `scope` because issue and mission evidence mature at different layers

That means the right next step is **not** to normalize filenames first.
The right next step is to normalize how we talk about evidence:

- semantic key
- scope
- producer
- subject
- carrier
- path
