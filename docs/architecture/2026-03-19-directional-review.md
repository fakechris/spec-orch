# SpecOrch Directional Review: Are We on the Right Track?

> Date: 2026-03-19
> Based on: 10 frontier AI engineering articles + project status cross-examination
> See also: [Seven Planes Architecture](seven-planes.md) / [Overall Status & Roadmap](../plans/2026-03-18-overall-status-and-roadmap.md)
> Chinese version: [中文版](2026-03-19-directional-review.zh.md)

---

## Reference Index

| # | Article | Author | Core Thesis |
|---|---------|--------|-------------|
| 1 | The Machine that Builds the Machine | Dan McAteer | 300-line workflow file + Symphony orchestration = 36h / 26 tasks / 27 PRs |
| 2 | The Intention Layer | Simon Taylor | Attention economy → Intention economy; agents need native payment protocols |
| 3 | The Anatomy of an Agent Harness | Viv | Agent = Model + Harness; same model, harness change alone: Top 30 → Top 5 |
| 4 | Harness Engineering: Same Old Story | marv1nnnnn | Harness shrinks every quarter; real leverage is code verifiability |
| 5 | A Sufficiently Detailed Spec Is Code | Gabrielle Miller | A sufficiently detailed spec is essentially code; Garbage in / Garbage out |
| 6 | 5 Agent Skill Design Patterns (ADK) | — | Tool Wrapper / Generator / Reviewer / Inversion / Pipeline |
| 7 | Why Your AI Agent Skills Rot | — | Routing confusion / model drift / benchmark rot; monitoring > optimization |
| 8 | The Spec Is the New Code (SDD Guide) | — | SDD four-step method; MercadoLibre rolling out to 20,000 developers |
| 9 | The Harness Is Everything | — | ACI design yields 64% perf improvement; context window = entire working consciousness |
| 10 | Claude + Obsidian Memory Stack | — | Three-layer memory (Session / Knowledge Graph / Ingestion); memory is the OS of attention |

---

## I. Four Signals Converge

The 10 articles converge into four mutually conflicting signals:

**Signal A — Harness Is Everything (Optimists)**

Articles 3/9/1 agree: harness optimization yields massive returns. Same Opus 4.6, harness
change alone moved from Terminal Bench Top 30 to Top 5. McAteer's 300-line workflow file
is the core asset of his entire system. ACI design yields 64% relative performance gain.

**Signal B — Harness Is Dying (Skeptics)**

Article 4 directly challenges the above: Pi ships real software with a minimal harness
(no sub-agents, no plan mode, no MCP). Core equation:
agent = model + harness → harness shrinks → agent ≈ model.
All fancy components do one thing — give the agent a clear right/wrong signal.

**Signal C — Spec Is the New Code (Builders)**

Articles 8/1 see SDD as the way. MercadoLibre rolling out SDD to 20,000 developers.
McAteer: outcome-definition skill > coding skill. GitHub Spec Kit at 77k stars.

**Signal D — Spec Is Just Code (Deconstructors)**

Article 5 is the sharpest critique of SDD. A sufficiently detailed spec has the same
cognitive load as code. Even YAML — an extremely detailed spec — sees most implementations
still non-conformant. Flakiness + Slop are the two hard problems.

---

## II. Four Fundamental Tensions

### Tension 1: Are Seven Planes Too Heavy?

**Problem**: We have Contract / Task / Harness / Execution / Evidence / Control / Evolution —
seven planes and 65+ commands. Article 4 says Pi (minimal harness) already ships software.

**Hard questions**:
- Which layers will be consumed as models get stronger?
- If single-pass accuracy jumps from 60% to 95%, do Gate/Evidence/Evolution still matter?

**Judgment**: Gate and Evidence will not be consumed. Stronger models solve "single-execution
correctness" but not "proving to humans" or "organizational governance." Even if agents are
always right, you still need:

- Compliance audit trails (Evidence layer's essential value)
- Structured human acceptance interfaces (Control layer's essential value)
- Policy distillation and evolution (Evolution layer's essential value)

**However, much of the Task and Harness planes' complexity will likely be consumed by model capability.**

**Direction adjustment**: Simplify seven layers to a "skeleton three":

```text
Contract (intent freeze) ──→ Execution (isolated) ──→ Evidence (prove completion)
```

Task / Harness / Control / Evolution become optional enhancement modules, not mandatory paths.

---

### Tension 2: The Sweet Spot for Spec Granularity

**Problem**: Article 8 says spec is core. Article 5 says when detailed enough, spec IS code.
Article 1 says his 300-line workflow file is "a system prompt written for AI."

**Hard questions**:
- How detailed should our spec be?
- Is the frozen spec for AI or for humans?

**Reality check**: McAteer's actual practice is not traditional specs but
"executable intent + acceptance criteria + constraints." This sidesteps Miller's critique —
no need for spec to be precise down to every line of code, just define
"what to do, how to verify, what not to do."

**Direction adjustment**: Position Spec as **IAC (Intent + Acceptance + Constraints)**:

| Component | Content | Format |
|-----------|---------|--------|
| Intent | One paragraph describing what to achieve | Natural language |
| Acceptance | Acceptance criteria | Given/When/Then (directly convertible to tests) |
| Constraints | What must not be done, what must be respected | List |

Do not pursue "precise enough to replace code."

---

### Tension 3: Too Much Hardcoded, Too Little LLM-Driven

**Problem**: Project detection hardcodes Python → mypy / pytest / pip.
Flow is hardcoded to three choices (Full/Standard/Hotfix).

**Guidance from the literature**:
- Article 9: Harness defines cognitive architecture. Hardcoded = deterministic track = predictable
- Article 4: All components do one thing — give agents a clear right/wrong signal
- Article 6, Pipeline pattern: Gates are hard, step content is flexible
- Article 1 practice: Flow topology hardcoded, flow content LLM-generated

**Direction adjustment — redefine the boundary of "hard skeleton, soft muscle"**:

**Hardcoded (skeleton)**:
- Pipeline topology (step order and dependencies)
- Gate condition evaluation logic
- Artifact format contracts (JSON schema)
- Safety guardrails (no delete main, no force push)

**LLM-driven (muscle)**:
- Project detection (read project structure then judge, not hardcoded Python/Node rules)
- Verification command inference (recommend based on project config, not hardcoded pytest)
- Spec generation and completion
- Task decomposition granularity
- Review focus areas
- Evolution direction suggestions

**Hybrid (joints)**:
- Flow selection: skeleton provides candidates, LLM recommends, human confirms
- Toolchain inference: LLM infers, user confirms, written to config, no re-inference next time

---

### Tension 4: Skill Rot vs Skill Absence

**Problem**: Article 7 warns skills rot silently. But we don't even have a skill subsystem yet.

**Guidance from the literature**:
- Article 6: Skills are structured work methods, not prompt fragments
- Article 7: Monitoring > optimization. Routing audit / model canary / judge model
- Article 10: Memory is the operating system of attention

**Direction adjustment**:
- Defer skill layer. First connect ContextAssembler to all LLM nodes
- Current prompts / policies / evolvers are already "proto-skills" — no need to start over
- Before building skills, build skill degradation detection — Article 7's core lesson

---

## III. Conclusive Judgment

### Are we on the right track?

**The broad direction is correct, but complexity is over-budget.**

The core philosophy (spec-first + gate-first + evidence-driven + evolution) is validated
across all 10 articles. Articles 8, 1, and 9 all say the same thing: structured intent +
deterministic tracks + verifiable output.

But we are making a classic mistake: **over-engineering the architecture before the product
is validated.** Seven layers, 65+ commands, 12 LLM nodes, 6 Evolvers — this is enterprise-scale
design, but we haven't run a single external user's complete loop.

### Three Critical Adjustments

1. **Shrink the core loop**: MVP core loop = `Spec (IAC) → Execute (isolated) → Verify (gate + evidence)`. Other layers are enhancement modules.
2. **LLM-ify key decision points**: Project detection, toolchain inference, verification command recommendation → all to LLM inference + human confirmation. Current project_detector rule logic → demoted to fallback.
3. **Context governance above all else**: Phase 13 (ContextAssembler full integration) is the true P0. More important than skill systems, dashboard enhancements, or A2A protocols. Article 9 is clearest: the context window is not RAM — it is the entire working consciousness.

---

## IV. Action Priority

| Priority | Direction | Rationale |
|----------|-----------|-----------|
| P0 | ContextAssembler integration to all LLM nodes | Harness core value is in context governance |
| P0 | Project detection to LLM inference + fallback | Solves the "too much hardcoded" problem |
| P1 | Spec format standardization to IAC | Avoids "detailed spec = code" trap |
| P1 | External user end-to-end loop validation | Validates product hypothesis |
| P2 | Run trace + eval harness | Performance leaps driven by traces |
| P2 | Skill degradation detection | Detect before build |
| P3 | Skill system | After Context and IAC stabilize |
| P3 | Dashboard / Control Tower | After core loop stabilizes |

---

## V. Relationship to Existing Roadmap

This document does not replace the [Overall Roadmap](../plans/2026-03-18-overall-status-and-roadmap.md)
but adds directional constraints on top:

- Phase 13 (ContextAssembler full integration) **confirmed as highest priority**, consistent with existing roadmap
- **Added**: Project detection LLM-ification (current project_detector hardcoded logic demoted to fallback)
- **Added**: Spec format standardization to IAC (Intent + Acceptance + Constraints)
- **Demoted**: Skill system from P1 to P3; context governance first
- **Demoted**: Dashboard / Control Tower from P2 to P3; core loop first

---

## VI. Execution Status Snapshot (2026-03-19)

This status section tracks whether the directional adjustments above are already
implemented in code and synchronized into planning execution systems (Linear).

### 6.1 Relationship to older roadmaps (avoid misreading)

| Document | Role | Superseded by 3/19? |
|----------|------|---------------------|
| [Overall status & roadmap (2026-03-18)](../plans/2026-03-18-overall-status-and-roadmap.md) | Phase 13–16, gap list, execution order | **No**. The 3/19 doc adds **directional constraints** (scope, CEO flywheel, reprioritization) on top. |
| [Context governance / Context Contract (2026-03-17)](context-contract-design.md) | 12-node context, phased rollout | **No**. **Phases 0–1** (Assembler, node wiring, manifest) largely align with Phase 13 / `SON-174` and are mostly done; **Phases 2–3** (case-driven evolution, unified lifecycle, full auto-trigger) remain **deep backlog**. |
| [System Design v0](spec-orch-system-design-v0.md) | Initial design (2026-03-07) | **Historical**; current pipeline docs + code are authoritative. Informal “v0.6 direction” usually means **context governance + Phase 13**, not a version field in this file. |

**Takeaway**: **Strategic narrative = this 3/19 doc + CEO Credibility Flywheel.** But **not every row in §IV “Action ordering” is shipped** — see §6.3.

### 6.2 Directional items — done

| Directional item | Status | Evidence |
|------------------|--------|----------|
| Project detection LLM-first + rules fallback | ✅ Done | Linear Epic `SON-175` + issues `SON-181~184` completed |
| Spec format standardization to IAC | ✅ Done | Linear Epic `SON-176` + issues `SON-185~188` completed |
| ContextAssembler full integration across LLM nodes | ✅ Done | Linear Epic `SON-174`; issues `SON-177~180` merged via PR `#85~87` |
| Unified run artifact schema (P1 baseline) | ✅ Done | `SON-194`–`SON-200` merged; `run_artifact/*` is canonical, `artifact_manifest.json` is compatibility bridge |
| Reaction engine (P2) baseline | ✅ Done | Rules, `get_pr_signal`, daemon loop, `params` / `requeue_ready`, `.spec_orch/reactions_trace.jsonl`, etc. (e.g. PR `#95`/`#96`); **not** the same as **Harness-level evals** (see §6.3) |
| README / user-facing init docs synced to new behavior | ✅ Done | `README.md` / `README.zh.md` include `--offline` / `--reconfigure` |
| Flywheel roadmap (P1/P2/P5/P6/P4-format) represented in Linear epics | ✅ Done | Planning epics `SON-189~193` created and labeled `epic` |

### 6.3 Directional — not done or only partial (vs §IV + CEO scope)

Strategic choice ≠ shipped feature:

| Source | Direction | Status | Notes |
|--------|-----------|--------|-------|
| §IV P1 | **External user end-to-end validation** | ❌ Not done | Product hypothesis; distinct from internal dogfood |
| §IV P2 | **Run trace + eval harness** | 🟡 Partial | Unified artifacts + events + reaction traces exist; **SON-190 (P6 Harness Evals)** and systematic offline eval still missing |
| §IV P2 | **Skill degradation detection** | ❌ Not done | “Monitor before you optimize” (article 7) — not a standalone system yet |
| §IV P3 | **Skill system** | ⏸️ Explicitly deferred | Matches CEO “P4 format only” |
| §IV P3 | **Dashboard / Control Tower** | ❌ Not done | **SON-193 (P5)**; deferred until core loop is stable |
| CEO flywheel | **P4 Skill Format Definition (format-only)** | ❌ Not done | **SON-192** |
| CEO flywheel | **P5 Control Tower UI** | ❌ Not done | **SON-193** |
| CEO flywheel | **P6 Harness Evals** | ❌ Not done | **SON-190** |
| [context-contract-design](context-contract-design.md) | **Phases 2–3** (case-driven evolution, unified lifecycle, full auto-trigger) | 🟡 Partial / not deep | Phase 1 wiring advanced; evolution still skewed “report-driven” |
| [Overall roadmap](../plans/2026-03-18-overall-status-and-roadmap.md) **Phase 14+** | **Daemon production hardening, hotfix, conflict resolution** | 🟡 Partial | e.g. **SON-46** still in backlog |

**“Seven planes → three-layer skeleton”**: narrative and progressive simplification, **not** a single checkbox.

### 6.4 Overall snapshot & suggested priority (2026-03-22)

1. **Direction**: 3/19 + CEO **Credibility Flywheel** + **SELECTIVE_EXPANSION** remain the main line; **P0/P1 code-path items from the directional review are largely landed**.
2. **Largest gaps**: **external validation**, **eval / harness (P6)**, **Control Tower (P5)**, **skill format (P4)**, **skill degradation detection**, **context-contract Phases 2–3 depth**, **Phase 14 production daemon**.
3. **Suggested next “most important” slices** (when opening issues): pick one cross-cutting bet — **P6 eval baseline (small step: aligned with existing artifacts)** **or** **P5 minimal control surface**; parallelize **SON-46**-class work if the goal is unattended operation.

### CEO Review Sync (2026-03-19)

Source of truth:
`~/.gstack/projects/fakechris-spec-orch/ceo-plans/2026-03-19-credibility-flywheel.md`

CEO plan confirms a **Credibility Flywheel** roadmap in `SELECTIVE EXPANSION` mode.

Accepted scope:

- P0: Context contract full integration (`SON-174` / `SON-177~180`)
- P1: Unified run artifact schema
- P2: Reaction engine
- P5: Control tower UI
- P6: Harness evals
- P4 (partial): Skill format definition (not full runtime)

Explicitly deferred / skipped for now:

- Preview interface abstraction
- Sandbox abstraction
- Full skill runtime
- Broad external-beta expansion before P0/P1 stabilization

Operational implications:

1. Keep expansion selective: complete Context Governance (`SON-174`, `SON-177~180`) before broadening into flywheel implementation stages.
2. Align planning epics with P0/P1/P2/P5/P6 and P4-format-only; avoid introducing non-approved tracks.
3. Treat P0->P1->P6 as a loop, not isolated one-off phases.
