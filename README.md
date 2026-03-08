# SpecOrch

SpecOrch is an AI-native software delivery orchestration system for individuals and small teams.

It treats:

- `Linear` as the control plane for deciding what to work on
- `Obsidian` as the knowledge plane for capturing why and how work happened
- `Orchestrator` as the runtime control center
- `Codex`, `Claude`, and browser/mobile agents as execution adapters
- `Spec` and `Gate` as the definition-of-done and mergeability layer

This repository currently contains the initial architecture document and a v1 implementation plan.

## Documents

- [System Design v0](docs/architecture/spec-orch-system-design-v0.md)
- [v1 Implementation Plan](docs/plans/2026-03-07-spec-orch-v1-implementation.md)

## Current Scope

The initial goal is to prove a reliable, auditable, agent-native delivery loop:

1. Pull work from Linear.
2. Create an isolated execution workspace per issue.
3. Generate task spec and progress artifacts.
4. Route implementation to Codex.
5. Route review to Claude.
6. Run verification and optional preview checks.
7. Write structured results back to Linear, PRs, and local audit storage.
8. Compute `Mergeable` through a Gate layer instead of trusting any single agent.
