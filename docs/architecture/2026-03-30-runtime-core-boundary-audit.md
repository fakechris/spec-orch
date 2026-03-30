# Runtime Core Boundary Audit

> 日期: 2026-03-30
> 状态: Epic 2 / Task 4 audit closeout
> 目的: 记录 `runtime_core` 当前已经真正接住了哪些职责，哪些文件仍然只是 bridge，哪些泄漏故意留到后续 epic

---

## 1. 结论

到 2026-03-30 这个节点，`runtime_core` 已经不再是空壳：

- canonical execution models 已经稳定存在
- normalized read / write 事实已经落到 `runtime_core`
- issue spine 和 mission spine 的直接 writer owners 都已经开始委托到 `runtime_core`
- dashboard / analytics / context 的主要 consumer 已经直接读 `runtime_core.readers`

但它还没有完成到“owner 全部瘦身”的程度。

更准确地说，当前边界是：

- `done`
  - execution semantics
  - canonical path helpers
  - normalized readers
  - normalized writers
  - first owner-facing adapters
  - issue run owner delegation
  - mission leaf / round direct writer delegation
  - primary read-side consumer cutover

- `bridge`
  - service shims
  - `run_report_writer.py`
  - `run_artifact_service.py`
  - `round_orchestrator.py`
  - `acpx_worker_handle.py`
  - `oneshot_worker_handle.py`
  - `packet_executor.py`

- `follow-up`
  - broader mission leaf owner set
  - remaining dashboard / daemon shells
  - direct builder adapter participation
  - package-boundary cleanup for old `services/*` imports outside current tranche

---

## 2. What Is Canonical Now

下面这些位置现在应被视为 canonical runtime seam：

- [`runtime_core/models.py`](../../src/spec_orch/runtime_core/models.py)
- [`runtime_core/paths.py`](../../src/spec_orch/runtime_core/paths.py)
- [`runtime_core/readers.py`](../../src/spec_orch/runtime_core/readers.py)
- [`runtime_core/writers.py`](../../src/spec_orch/runtime_core/writers.py)
- [`runtime_core/adapters.py`](../../src/spec_orch/runtime_core/adapters.py)

如果后续再需要新增：

- normalized path helper
- normalized artifact write helper
- execution attempt/outcome shaping helper

优先落在这里，而不是回到 `services/`。

---

## 3. Migrated Owners

以下 owner 已经开始通过 `runtime_core` 输出 canonical payload：

### 3.1 Issue path

- [`run_artifact_service.py`](../../src/spec_orch/services/run_artifact_service.py)
  - uses `runtime_core.writers.write_issue_execution_payloads(...)`

- [`run_report_writer.py`](../../src/spec_orch/services/run_report_writer.py)
  - uses `runtime_core.paths` to reference canonical normalized paths

### 3.2 Mission leaf path

- [`acpx_worker_handle.py`](../../src/spec_orch/services/workers/acpx_worker_handle.py)
  - uses runtime-core worker payload writer

- [`oneshot_worker_handle.py`](../../src/spec_orch/services/workers/oneshot_worker_handle.py)
  - now uses `runtime_core.adapters.write_worker_attempt_payloads(...)`

- [`packet_executor.py`](../../src/spec_orch/services/packet_executor.py)
  - now uses `runtime_core.adapters.build_packet_attempt_payload(...)`
  - it still does not persist packet-local canonical files; current seam is payload shaping, not packet artifact storage

### 3.3 Mission round path

- [`round_orchestrator.py`](../../src/spec_orch/services/round_orchestrator.py)
  - uses `runtime_core.writers.write_round_supervision_payloads(...)`

---

## 4. Consumer Cutover Status

这些 consumer 现在已直接依赖 `runtime_core.readers`：

- [`dashboard/control.py`](../../src/spec_orch/dashboard/control.py)
- [`dashboard/missions.py`](../../src/spec_orch/dashboard/missions.py)
- [`dashboard/surfaces.py`](../../src/spec_orch/dashboard/surfaces.py)
- [`dashboard/transcript.py`](../../src/spec_orch/dashboard/transcript.py)
- [`services/context/context_assembler.py`](../../src/spec_orch/services/context/context_assembler.py)
- [`services/evidence_analyzer.py`](../../src/spec_orch/services/evidence_analyzer.py)
- [`services/eval_runner.py`](../../src/spec_orch/services/eval_runner.py)

这意味着 `services/execution_semantics_reader.py` 现在是明确的 compatibility bridge，而不是主要入口。

---

## 5. Intentional Bridges

下面这些文件当前仍保留在原位置，而且这是有意的：

- [`services/execution_semantics_reader.py`](../../src/spec_orch/services/execution_semantics_reader.py)
- [`services/execution_semantics_writer.py`](../../src/spec_orch/services/execution_semantics_writer.py)

它们的要求现在很简单：

- 不承载新业务逻辑
- 只做 re-export / compatibility bridge

这条边界已经被结构测试覆盖。

---

## 6. Remaining Leaks

这些地方仍然是 runtime_core 未完全吃下的剩余泄漏，但目前可以接受：

### 6.1 Owner-local side effects that are not yet normalized carriers

- `round_orchestrator.py`
  - still writes `visual_evaluation.json` and `acceptance_review.json`
  - these belong to later acceptance / decision follow-up, not this runtime tranche

- `run_report_writer.py`
  - still manages legacy report carrier lifecycle
  - this is a bridge, not a target home

### 6.2 Builder adapter internals

- `services/builders/*`
  - still own raw builder event/report production
  - runtime_core currently normalizes around them rather than replacing them

### 6.3 Trigger shells

- `daemon.py`
- CLI routes
- broader dashboard route composition

这些还不是 runtime_core 的 first move。

---

## 7. Interpretation Rule Going Forward

从现在开始，如果新增 runtime 相关代码，按下面顺序判断：

1. 它是在定义 canonical path / read / write / attempt shaping 吗？
   - 放进 `runtime_core`

2. 它是在定义 owner 如何调用 runtime seam 吗？
   - 放在 owner 文件里，但只保留 orchestration

3. 它是在定义 acceptance / intervention / supervision state 吗？
   - 优先看 `decision_core`

4. 它只是 legacy carrier 兼容吗？
   - 放 bridge，不把 bridge 当新归属地

---

## 8. Closeout

`Epic 2` 到这个节点的真实状态不是“完全结束”，而是：

> runtime seam 已经落地，major consumers 已经切过来，剩余工作主要是 boundary cleanup 和 later-epic integration，而不是再发明新的 execution semantics。
