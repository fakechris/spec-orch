# P0-Alpha Issue Backlog

This backlog is ordered for dogfood-first execution.

## Now

### SPC-R1
Extract `IssueSource` and move fixture loading out of `RunController`.

**Done when:**
- `RunController` no longer reads fixture files directly
- `FixtureIssueSource` is the current local implementation
- The next Linear source can plug into the same interface

### SPC-R2
Introduce a `BuilderAdapter` protocol.

**Done when:**
- `RunController` depends on a builder interface instead of a concrete Codex class
- The current Codex harness adapter implements the protocol cleanly

### SPC-R3
Extract shared run finalization logic.

**Done when:**
- `run_issue`, `review_issue`, and `accept_issue` share a common finalize path
- Gate, explain, and report writing are no longer duplicated across three methods

### SPC-L1
Add Linear client configuration and auth loading.

**Done when:**
- SpecOrch can read a Linear API token from config or env
- A minimal client can fetch a single issue by ID
- Unit tests cover auth/config loading

### SPC-L2
Load issue context from Linear instead of fixture JSON.

**Done when:**
- `run-issue <linear-id>` can pull a real issue
- Fixture mode still works for tests
- The source mode is visible in telemetry or report metadata

### SPC-L3
Map Linear issue fields into the internal `Issue` model.

**Done when:**
- Title, summary/description, labels, project, and state are mapped deterministically
- Missing fields degrade safely
- Tests cover mapping behavior

### SPC-W1
Write run summaries back to Linear.

**Done when:**
- After `run-issue`, SpecOrch posts or updates a concise run summary in Linear
- The summary includes mergeability and blocked conditions

## Next

### SPC-R4
Evaluate `codex exec` as an alternate builder adapter path.

**Done when:**
- SpecOrch can document or prototype a `codex exec` adapter
- The current `app-server` harness remains the primary dogfood path unless the alternate path proves clearly better

### SPC-W2
Write review and acceptance status back to Linear.

**Done when:**
- `review-issue` and `accept-issue` both sync state summaries to Linear
- Acceptance can be seen without inspecting local files

### SPC-W3
Add minimal PR write-back.

**Done when:**
- If a PR reference is available, SpecOrch can write an explain/gate summary comment
- The comment is short and idempotent

### SPC-D1
Add queue and claim semantics per issue.

**Done when:**
- The system prevents duplicate concurrent runs for the same issue
- Claimed issues are visible in local state

### SPC-D2
Add `spec-orch daemon`.

**Done when:**
- A daemon can poll Linear and dispatch runs continuously
- One failed issue does not stop the loop

### SPC-D3
Add rerun support by issue ID / run ID.

**Done when:**
- A human can rerun a failed or stale issue safely
- The rerun links back to the earlier run artifacts

## After That

### SPC-A1
Define a unified acceptance summary schema.

**Done when:**
- One structured object can power `explain.md`, Linear write-back, and PR write-back

### SPC-A2
Render unified acceptance summary artifact.

**Done when:**
- Humans can read a single artifact to decide acceptance

### SPC-A3
Use unified acceptance summary everywhere.

**Done when:**
- Local artifact, Linear update, and PR comment all reuse the same summary data
