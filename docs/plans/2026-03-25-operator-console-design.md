# Operator Console Design

## Goal

Design the next-generation SpecOrch operator console as a workbench, not a dashboard.

The console should help a technical operator answer five questions quickly:

1. What is happening now?
2. What is blocked, and why?
3. What needs my action?
4. What can I safely do next?
5. How did we get here?

This design is informed by:
- Paperclip's operator-first control plane
- `superset.sh`'s IDE-style persistent workbench layout
- SpecOrch's existing evidence model: missions, rounds, packets, approvals, logs, transcripts, visual evaluation, and gate decisions

## Product Stance

This is not:
- a BI dashboard
- a chat-first interface
- a flashy AI control panel

This is:
- a software delivery operator console
- a cockpit for supervised execution
- a persistent workbench for monitoring, intervention, and audit

## Global Information Architecture

Top-level navigation should represent operator work modes, not content categories:

- `Inbox`
  - pending approvals
  - blocked missions
  - failed rounds
  - budget incidents
  - visual QA failures
- `Missions`
  - searchable mission list
  - mission status, current round, urgency, assignee/owner
- `Approvals`
  - full approval queue and resolved history
- `Costs`
  - mission, packet, and model spend
- `Evidence`
  - transcripts, artifacts, visual evaluations, logs
- `Settings`
  - providers, adapters, budgets, policies

### Layout Rule

Global navigation changes the operator's mode.
Local navigation must preserve mission context.

Once the user opens a mission, the mission header remains fixed while the center and right panes change between:
- overview
- transcript
- approvals
- visual QA
- artifacts
- costs

## Core Layout Pattern

Use a three-zone workbench layout:

1. `Left rail`
   - global nav
   - mission list or inbox list
   - filters and saved views

2. `Main canvas`
   - the active mission page
   - transcript timeline
   - approval queue
   - costs view

3. `Context / action rail`
   - operator actions
   - blocking reason
   - next recommended step
   - related artifacts
   - linked approvals or findings

This structure keeps overview and deep inspection available without full context resets.

## Mission Detail

`Mission Detail` is the anchor page and should carry most operator traffic.

### Primary mission header

Persistent top strip:
- mission title and ID
- current state
- current round / wave
- blocking reason
- last meaningful event timestamp
- budget / cost badge
- owner or source

Persistent primary actions:
- approve
- request revision
- resume
- rerun
- stop
- inject guidance

These actions must stay in one stable location across all mission subviews.

### Main body composition

#### Left column: Execution structure

Purpose: show shape and progress of work.

- wave list
- packet swimlanes
- packet status
- worker session state
- last packet event
- retry / replan markers

This area should read like a structured execution map, not like a loose collection of cards.

#### Center column: Situation awareness

Purpose: summarize what matters now.

- mission summary
- current supervisor decision
- open blockers
- recent anomalies
- latest verification result
- latest visual QA result

This is the fastest route to "what is going on?"

#### Right column: Human intervention

Purpose: centralize operator action.

- approvals needed now
- ask-human prompts
- recommended next action
- risk notes
- latest guidance injected
- destructive controls with confirmation

### Secondary mission tabs

Use local tabs or segmented views inside mission context:
- `Overview`
- `Transcript`
- `Approvals`
- `Visual QA`
- `Artifacts`
- `Costs`

Do not navigate to a completely different page shell for these.

## Run Transcript

The transcript is not a chat window.
It is a multi-source execution narrative.

### Required event categories

- assistant/user messages
- tool calls
- activity events
- stdout/stderr
- supervisor decisions
- approvals
- visual evaluator findings
- operator interventions

### Layout

Use a split view:

#### Left: Event timeline

- chronological grouped timeline
- visual distinction by event type
- collapsible noisy sections
- compact default density
- explicit markers for failures, pauses, approvals, reruns

#### Right: Context inspector

- selected event details
- raw payload
- linked artifact
- related packet / round / approval
- jump links to neighboring evidence

### Transcript UX rules

- raw JSON is secondary, never the default reading mode
- command bursts should be grouped
- stdout should be collapsible
- important state transitions should stand out as milestones
- filters should support packet, round, event type, and severity

## Inbox and Approval Queue

Inbox is the operator's triage surface.

Each row must answer at a glance:
- what is wrong or waiting
- what object is affected
- why it matters
- what action is available
- how urgent it is

Required fields:
- severity
- object type
- mission / round / packet link
- short reason
- age
- recommended action

Approval queue should be a specialized inbox slice, not a generic modal or floating panel.

## Visual QA

Visual evaluation should be promoted from JSON artifact to product surface.

Required elements:
- screenshot gallery
- failed checks
- confidence
- changed areas
- page targets
- linked transcript and round

The operator must be able to connect a visual failure to the exact mission round and transcript segment that produced it.

## Costs

Costs should answer:
- what is spending right now
- which mission or packet is consuming budget
- whether any threshold or auto-pause rule is near
- what changed relative to recent runs

Avoid vanity charts.
Prioritize spend table, trend, threshold markers, and incident history.

## State Semantics

The UI must clearly distinguish:
- running
- queued
- paused by human
- paused by budget
- blocked on approval
- blocked on missing context
- failed
- completed

Color alone must not carry this meaning.
Each state needs:
- label
- icon or shape cue
- explanatory copy
- recommended operator action when relevant

## Design Workflow

Use the installed design skills in this order:

1. `teach-impeccable`
2. `arrange`
3. `clarify`
4. `typeset`
5. `normalize`
6. `harden`
7. `polish`
8. `audit`

### Why this order

- `arrange` solves structural operator-console problems first
- `clarify` fixes state and action semantics
- `typeset` establishes density and readable hierarchy for high-information views
- `normalize` aligns the resulting patterns into a system
- `harden` ensures the console survives real execution edge cases
- `polish` comes last

## Immediate Next Slice

Start with:

1. `Mission Detail`
2. `Run Transcript`

These two pages define whether SpecOrch feels like an operator control plane or just a collection of artifacts.
