# Acceptance History

This directory is the durable archive for formal release-acceptance baselines.

It starts with the first frozen baseline:

- `acceptance-freeze-baseline-2026-04-02`

And it is tracked in Linear as:

- `SON-419` `[Epic] Release Acceptance History and Archive`
- `SON-420`..`SON-424` for schema, index/manifest writing, finding lineage, first bundle seeding, and downstream read models

Future dashboard/workbench/showcase surfaces should read this directory instead of reconstructing historical state from ad hoc filesystem scans.

This directory stores the durable, version-level archive for formal acceptance
baselines.

It exists so future dashboard/workbench/showcase surfaces can render historical
acceptance runs without reconstructing state from scattered runtime artifacts.

## Structure

```text
docs/acceptance-history/
  index.json
  releases/
    <release_id>/
      manifest.json
      summary.md
      status.json
      findings.json
      source_runs.json
      artifacts.json
```

## Rules

1. Only formal acceptance versions belong here.
2. Every release entry must be reproducible from canonical report artifacts.
3. `index.json` stays small and append-only.
4. The archive stores both result state and provenance state.
5. Future UI layers should treat this directory as the primary history read
   model.
