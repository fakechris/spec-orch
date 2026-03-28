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

<!-- frozen APIs / schemas -->

## Active Wave

- Wave 0: Define contracts and schemas for mission data structures, daemon APIs, and dashboard interfaces

## Active Packets

- dogfood-contract-scaffold: Mission Data Models & API Contracts
