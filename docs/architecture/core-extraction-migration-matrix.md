# Core Extraction Migration Matrix

> 日期: 2026-03-29
> 状态: implementation-track 配套矩阵
> 目的: 把当前模块逐个映射到目标 core、迁移时机、以及是否需要 compatibility shim

---

## 1. 使用方式

这份矩阵不是新的方案文档，而是下面三份文档的落地映射表：

- [`system-primitives-and-high-level-organization.md`](./system-primitives-and-high-level-organization.md)
- [`shared-execution-semantics.md`](./shared-execution-semantics.md)
- [`../plans/2026-03-29-runtime-extraction-phase-2.md`](../plans/2026-03-29-runtime-extraction-phase-2.md)

它回答四个问题：

1. 当前这个模块本质上属于哪个 core
2. 现在要不要搬
3. 如果不搬，应该通过 shim 还是直接保留
4. 哪些模块现在绝对不要动

---

## 2. 迁移策略

统一采用三种状态：

- `extract-now`
  - 现在就应该开始抽到目标 core

- `wrap-now`
  - 现在不直接搬，但要先通过新的 core seam 包住

- `leave-for-later`
  - 现在不动，等前置 core 稳定后再处理

统一采用两种兼容策略：

- `shim`
  - 老模块保留，内部改成调用新 core

- `stay`
  - 暂时继续留在原地，不做兼容抽象

---

## 3. Runtime Core Matrix

### 3.1 直接属于 Runtime Core

| 当前模块 | 目标位置 | 现在动作 | 兼容策略 | 说明 |
|---|---|---:|---:|---|
| `services/execution_semantics_reader.py` | `runtime_core/readers.py` | `extract-now` | `shim` | 计划中的真实 reader 实现，应成为 runtime-core 入口 |
| `services/execution_semantics_writer.py` | `runtime_core/writers.py` | `extract-now` | `shim` | 计划中的真实 writer 实现，应成为 runtime-core 入口 |
| `services/run_artifact_service.py` 中的 normalized shaping | `runtime_core/writers.py` / `runtime_core/paths.py` | `extract-now` | `shim` | 只抽 normalized shaping，不抽 owner 时序 |
| `services/run_report_writer.py` 中的 normalized outcome shaping | `runtime_core/writers.py` | `extract-now` | `shim` | report carrier 继续保留，但 normalized write 迁出去 |
| `round_orchestrator.py` 中 round artifact normalization 部分 | `runtime_core/supervision.py` + `runtime_core/writers.py` | `extract-now` | `shim` | 仅抽 payload shaping，不抽 round loop owner |
| `services/packet_executor.py` 中 packet outcome shaping | `runtime_core/writers.py` | `extract-now` | `shim` | packet executor 保留为 owner |

### 3.2 应包住但不立刻搬走的 Runtime Owners

| 当前模块 | 目标关系 | 现在动作 | 兼容策略 | 说明 |
|---|---|---:|---:|---|
| [`run_controller.py`](../../src/spec_orch/services/run_controller.py) | runtime-core consumer | `wrap-now` | `stay` | owner 保留，只把 normalized read/write 收到 runtime-core |
| [`round_orchestrator.py`](../../src/spec_orch/services/round_orchestrator.py) | runtime-core consumer | `wrap-now` | `stay` | round owner 保留，不提前拆 supervision owner |
| [`mission_execution_service.py`](../../src/spec_orch/services/mission_execution_service.py) | runtime-core consumer | `wrap-now` | `stay` | mission owner 门面，不做 first move |
| [`parallel_run_controller.py`](../../src/spec_orch/services/parallel_run_controller.py) | runtime-core consumer | `wrap-now` | `stay` | 执行 owner，等 runtime-core 稳定后再细拆 |
| `services/workers/*_worker_handle.py` | runtime-core consumer | `wrap-now` | `stay` | continuity 和 outcome write 通过 runtime-core 输出 |

### 3.3 现在不要碰的 Runtime 周边

| 当前模块 | 现在动作 | 说明 |
|---|---:|---|
| `services/builders/*` | `leave-for-later` | builder adapter 是执行后端，不是当前抽象中心 |
| `services/verification_service.py` | `leave-for-later` | 先作为 outcome input 保留 |
| `services/gate_service.py` | `leave-for-later` | gate 先作为 outcome/review input，不急着 core 化 |

---

## 4. Decision Core Matrix

### 4.1 直接属于 Decision Core

| 当前模块 | 目标位置 | 现在动作 | 兼容策略 | 说明 |
|---|---|---:|---:|---|
| `RoundDecision` dataclass（当前在 `domain/models.py`） | `decision_core/models.py` 或 `domain` re-export + `decision_core` helpers | `wrap-now` | `shim` | 不急着搬 object，本轮先让 decision-core 围绕它组织 |
| `litellm_supervisor_adapter.py` 中 review parsing / decision shaping | `decision_core/records.py` | `extract-now` | `shim` | 抽出 `DecisionRecord` write path |
| `dashboard/approvals.py` | `decision_core/interventions.py` + `decision_core/review_queue.py` | `extract-now` | `shim` | approval queue 先从 dashboard 语义里抽出来 |
| `dashboard/missions.py` 中 approval-state derivation | `decision_core/review_queue.py` | `extract-now` | `shim` | approval state 不应继续散在 dashboard model adapter 里 |

### 4.2 应包住但不立刻搬走的 Decision Owners

| 当前模块 | 目标关系 | 现在动作 | 兼容策略 | 说明 |
|---|---|---:|---:|---|
| [`round_orchestrator.py`](../../src/spec_orch/services/round_orchestrator.py) | decision-core consumer | `wrap-now` | `stay` | supervision owner 保留，decision shaping 外委 |
| [`dashboard/routes.py`](../../src/spec_orch/dashboard/routes.py) | decision-core consumer | `wrap-now` | `stay` | route 层不应自己推导 decision 语义 |
| [`dashboard/app.py`](../../src/spec_orch/dashboard/app.py) | decision-core consumer | `wrap-now` | `stay` | UI 只消费 queue / intervention / state |

### 4.3 现在不要碰的 Decision 周边

| 当前模块 | 现在动作 | 说明 |
|---|---:|---|
| `flow_engine/flow_router.py` | `leave-for-later` | 虽然也是 decision，但先不混入 mission supervision 抽取 |
| `reaction_engine.py` / `skill_degradation.py` | `leave-for-later` | 属于另一条 decision 子系统，后续再纳入统一 inventory |

---

## 5. Contract Core Matrix

| 当前模块 | 目标位置 | 现在动作 | 兼容策略 | 说明 |
|---|---|---:|---:|---|
| [`domain/task_contract.py`](../../src/spec_orch/domain/task_contract.py) | `contract_core/contracts.py` | `leave-for-later` | `stay` | 先保留在 domain，后面再细分 |
| [`services/spec_snapshot_service.py`](../../src/spec_orch/services/spec_snapshot_service.py) | `contract_core/snapshots.py` | `leave-for-later` | `stay` | 当前可稳定运行，不挡住 runtime extraction |
| [`spec_import/`](../../src/spec_orch/spec_import) | `contract_core/importers/` | `leave-for-later` | `stay` | 更偏 contract ingestion，优先级低于 runtime/decision |
| `cli/spec_commands.py` 中 question/decision recording | `contract_core/decisions.py` | `leave-for-later` | `stay` | 这条和 decision-core 相关，但先不并线 |

结论：

- Contract Core 明确重要
- 但不是第一批 extraction 目标
- 当前先避免再往 `services/` 随手加新的 contract helper

---

## 6. Memory Core Matrix

| 当前模块 | 目标位置 | 现在动作 | 兼容策略 | 说明 |
|---|---|---:|---:|---|
| [`services/memory/*`](../../src/spec_orch/services/memory) | `memory_core/*` | `leave-for-later` | `stay` | 已形成相对完整子包，后续可整体 alias 或 rename |
| [`services/context/*`](../../src/spec_orch/services/context) | `memory_core/views/` 或平行 context package | `leave-for-later` | `stay` | 先别在 runtime extraction 时动 context 结构 |
| `MemoryRecorder.record_*` 的决策相关扩展 | `memory_core/recorder.py` | `wrap-now` | `stay` | 等 `DecisionRecord` 稳定后接入，不先改 provider |

结论：

- Memory 已经是一个“半独立 core”
- 当前问题不是 provider 不存在，而是它还没有吃到新的 decision artifacts
- 所以 memory 先保持稳定，后接 decision-core

---

## 7. Evolution Core Matrix

| 当前模块 | 目标位置 | 现在动作 | 兼容策略 | 说明 |
|---|---|---:|---:|---|
| [`services/evolution/*`](../../src/spec_orch/services/evolution) | `evolution_core/*` | `leave-for-later` | `stay` | 当前先不拆 |
| [`services/evolution_policy.py`](../../src/spec_orch/services/evolution_policy.py) | `evolution_core/policy.py` | `leave-for-later` | `stay` | 等 decision artifacts 稳定后再接 |
| [`docs/architecture/evolution-trigger-architecture.md`](./evolution-trigger-architecture.md) 对应的 inventory | `decision_core` + `evolution_core` 共享输入 | `wrap-now` | `stay` | 文档先更新，代码后接 |

结论：

- Evolution 现在不该是 first move
- 但后面必须吃到 `DecisionRecord` / `DecisionReview`

---

## 8. Surfaces Matrix

| 当前模块 | 目标关系 | 现在动作 | 兼容策略 | 说明 |
|---|---|---:|---:|---|
| `cli/*` | surface | `leave-for-later` | `stay` | CLI 先继续走旧入口 |
| `dashboard/*` | surface | `wrap-now` | `stay` | 只抽 approval / decision shaping，不动整体 UI |
| `daemon.py` | surface + owner trigger | `leave-for-later` | `stay` | daemon 先不参与第一轮 core extraction |
| external adapters (`linear`, `github`, `browser`, ACPX) | surface/backend | `leave-for-later` | `stay` | 这些先继续作为边界依赖存在 |

---

## 9. 第一批实施边界

如果只看第一批真正应该开始改的东西，就是下面这 4 组：

### 9.1 必建新包

- `src/spec_orch/runtime_core/`
- `src/spec_orch/decision_core/`

### 9.2 必加 shim

- `services/execution_semantics_reader.py`
- `services/execution_semantics_writer.py`

### 9.3 必先接入的 owner

- `run_controller.py`
- `round_orchestrator.py`
- `litellm_supervisor_adapter.py`

### 9.4 先不要碰的模块

- `services/memory/*`
- `services/evolution/*`
- 大范围 dashboard UI
- `daemon.py`
- builder adapter internals

---

## 10. 一周内的成功标准

第一周不要求“系统完成重构”，只要求下面这些结构事实成立：

1. 新的 shared primitives 不再默认落进 `services/`
2. `runtime_core` 成为 execution semantic 的真实归属地
3. `decision_core` 成为 supervision / intervention 的真实归属地
4. `RunController` 和 `RoundOrchestrator` 开始消费 core seam，而不是继续自己拼所有 payload
5. 新增概念不会再直接绑到 dashboard 或 JSON carrier 上

---

## 11. 解释规则

如果后续遇到“这个文件到底该放哪里”的争议，按下面顺序判断：

1. 它定义的是 subject、attempt、outcome、decision、memory 这种对象吗？
   - 是：优先放 core

2. 它定义的是 owner 如何调度生命周期吗？
   - 是：先留在当前 owner 模块

3. 它只是某个 JSON / md / jsonl 的 carrier 吗？
   - 是：不要把 carrier 当归属地

4. 它只是 CLI / dashboard / daemon 的展示或触发逻辑吗？
   - 是：留在 surface

这个规则的目的只有一个：

> **以后新增结构，优先归属到 core；以后新增流程，优先留在 owner；以后新增展示，优先留在 surface。**
