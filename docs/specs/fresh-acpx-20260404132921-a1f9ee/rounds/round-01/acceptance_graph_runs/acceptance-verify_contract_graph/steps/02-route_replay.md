## Route Replay Step Assessment

### Evidence Captured

**Declared Review Routes (6)**
| Route Key | Path |
|-----------|------|
| overview | `/?mission=fresh-acpx-20260404132921-a1f9ee&mode=missions&tab=overview` |
| transcript | `/?mission=fresh-acpx-20260404132921-a1f9ee&mode=missions&tab=transcript&round=1` |
| approvals | `/?mission=fresh-acpx-20260404132921-a1f9ee&mode=missions&tab=approvals&round=1` |
| visual_qa | `/?mission=fresh-acpx-20260404132921-a1f9ee&mode=missions&tab=visual&round=1` |
| costs | `/?mission=fresh-acpx-20260404132921-a1f9ee&mode=missions&tab=costs&round=1` |
| judgment | `/?mission=fresh-acpx-20260404132921-a1f9ee&mode=missions&tab=judgment&round=1` |

**Workflow Assertions (11)**
1. launcher panel can be opened from the header
2. needs attention mode can be selected from mission control
3. missions mode can be selected from mission control
4. decision queue mode can be selected from mission control
5. deep evidence mode can be selected from mission control
6. the target mission can be selected from the mission list
7. the transcript tab can be opened from mission detail
8. the approvals surface exposes actionable operator controls when present
9. the visual QA tab can be opened from mission detail
10. the judgment tab can be opened from mission detail
11. the costs tab can be opened from mission detail

### Contract Evidence Summary

The declared route and workflow assertions are properly captured from the mission's `workflow_replay` proof type. The parent fresh execution completed successfully:

| Metric | Value |
|--------|-------|
| Mission ID | fresh-acpx-20260404132921-a1f9ee |
| Waves Completed | 1 |
| Packets Completed | 2 (both succeeded) |
| Verification Steps | 6/6 passed per packet |
| Gate Verdicts | Both mergeable |
| Confidence | 0.97 |

### Scope Constraint

This step only **captures** the declared routes and assertions from graph state. Actual route replay (navigating to URLs, interacting with selectors) requires a running dashboard frontend, which is outside the graph execution boundary.

### Verdict

**Routes and assertions are documented and ready for downstream workflow replay validation.**
