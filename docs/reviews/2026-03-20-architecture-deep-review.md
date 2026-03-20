# SpecOrch 架构深度 Review

> 日期: 2026-03-20
> 范围: 代码结构、AI-Native 设计、数据持久化、Protocol 一致性、可操作改进建议
> 基于: 30,213 行 Python / 80 个 services 文件 / 1,158 测试 / ruff 零警告
> 前置: [方向性深度拷问](../architecture/2026-03-19-directional-review.zh.md) / [全局状态盘点](../plans/2026-03-18-overall-status-and-roadmap.md)

---

## 一、总体评估

spec-orch 代码库在 AI-Native 设计方面达到了业界前沿水准——ContextBundle 三层上下文、NodeContextSpec 声明式需求、CompactRetentionPriority 压缩策略、FlowRouter 混合路由等设计在同类项目中独树一帜。domain 层对 services 层的零依赖验证了分层纪律。

**但代码组织和工程健壮性存在结构性债务。** 三个 God Object（RunController / cli.py / daemon.py）合计 7,000 行，所有 JSON 状态文件使用非原子写入，6 个 Evolver 未对齐 LifecycleEvolver protocol。这些问题不影响当前 dogfood 阶段，但会阻塞生产化（Phase 14+ Daemon 健壮性）。

---

## 二、架构强项（值得保持）

### 2.1 AI-Native 上下文工程

| 组件 | 文件 | 设计亮点 |
|------|------|---------|
| ContextBundle | `domain/context.py` | Task / Execution / Learning 三层分离，每个 LLM 节点按需组装 |
| NodeContextSpec | `domain/context.py` L103-117 | 声明式 spec：节点声明需要哪些字段、token 预算、是否排除 framework events |
| CompactRetentionPriority | `domain/context.py` L71-100 | 五级压缩优先级，architecture_decisions 永不摘要，tool_output 优先丢弃 |
| ContextAssembler | `services/context_assembler.py` | 根据 NodeContextSpec 动态组装 ContextBundle，所有 LLM 节点共用 |

**建议：保持此设计不变。** 这是 spec-orch 在同类项目中的核心差异化。

### 2.2 混合路由

| 组件 | 文件 | 设计亮点 |
|------|------|---------|
| FlowRouter | `flow_engine/flow_router.py` | 规则快路径 + LLM 复杂度评估，confidence < 0.7 自动 fallback |
| SmartProjectAnalyzer | `services/smart_project_analyzer.py` | LLM-first 项目检测 + rules fallback，符合方向性文档"骨架硬、肌肉软" |
| TraceSampler | `services/trace_sampler.py` | 负反馈 100% 采样 + 变更后 48h 窗口密集采样 |

### 2.3 分层纪律

- `domain/` 对 `services/` **零依赖**（已通过全文 import 验证）
- 所有 adapter 接口使用 `Protocol` + `@runtime_checkable`，不用 ABC
- `domain/models.py` + `domain/context.py` + `domain/protocols.py` 构成干净的领域核心

---

## 三、结构性问题

### 3.1 God Object：三个文件合计 7,000 行

| 文件 | 行数 | 问题 |
|------|------|------|
| `services/run_controller.py` | 1,585 | 同时负责 builder 执行、gate 评估、文件 I/O、事件发射、流程状态管理 |
| `cli.py` | 4,091 | 所有子命令在一个文件内，从 `run` 到 `dashboard` 到 `evolution` |
| `services/daemon.py` | 1,323 | 8 处 inline import 规避循环依赖，说明依赖关系已超出单文件承载力 |

**影响**：新开发者进入成本高，改一个子命令需要理解 4,000 行上下文，daemon 的 inline import 是循环依赖的信号。

### 3.2 services/ 目录扁平化

`services/` 有 80 个 `.py` 文件平铺，无子包分组。七层架构（Contract / Task / Harness / Execution / Evidence / Control / Evolution）在代码目录中完全没有体现。

当前 evolvers 已经散落在 services/ 根目录：
```
services/prompt_evolver.py
services/plan_strategy_evolver.py
services/intent_evolver.py
services/config_evolver.py
services/gate_policy_evolver.py
services/flow_policy_evolver.py
services/evolver_protocol.py
services/evolution_trigger.py
```

### 3.3 非原子 JSON 写入

以下位置使用 `path.write_text()` 直接写入状态文件，在 daemon 并发场景下可能导致数据损坏：

| 文件 | 行号 | 写入目标 |
|------|------|---------|
| `services/run_progress.py` | L74 | `progress.json` |
| `services/daemon.py` | L146 | `daemon_state.json` |
| `services/daemon.py` | L1076 | heartbeat 文件 |
| `services/daemon.py` | L1256 | retry 文件 |

**风险场景**：daemon 在 `write_text()` 过程中被信号中断 → 文件被截断为空 → 重启后读取失败 → 无法恢复运行状态。这直接阻塞 Phase 14（SON-46 Daemon 健壮性）。

### 3.4 全局单例模式

`EventBus` 和 `MemoryService` 使用 `_global_xxx` + `threading.Lock` 双重检查锁定：

```python
# event_bus.py L275-286
_global_bus: EventBus | None = None
_global_lock = threading.Lock()

def get_event_bus() -> EventBus:
    global _global_bus
    if _global_bus is None:
        with _global_lock:
            if _global_bus is None:
                _global_bus = EventBus()
    return _global_bus
```

**影响**：测试中无法创建独立实例，需要 `reset_global_bus()` hack；多 worker 场景下共享可变状态。

---

## 四、Protocol 一致性问题

### 4.1 LifecycleEvolver 未被采用

`domain/protocols.py` 定义了 `LifecycleEvolver` protocol，规范了四阶段生命周期：

```python
class LifecycleEvolver(Protocol):
    def observe(self, run_dirs, *, context=None) -> list[dict]: ...
    def propose(self, evidence, *, context=None) -> list[EvolutionProposal]: ...
    def validate(self, proposal) -> EvolutionOutcome: ...
    def promote(self, proposal) -> bool: ...
```

但 6 个 evolver 实现仍使用旧接口：

| Evolver | 实际方法 | 应对齐方法 |
|---------|---------|----------|
| `PromptEvolver` | `evolve()` | `observe` → `propose` → `validate` → `promote` |
| `IntentEvolver` | `evolve()` | 同上 |
| `ConfigEvolver` | `evolve()` | 同上 |
| `GatePolicyEvolver` | `evolve()` | 同上 |
| `FlowPolicyEvolver` | `evolve()` | 同上 |
| `PlanStrategyEvolver` | `analyze()` | 同上 |

`EvolutionTrigger` 通过硬编码 dispatch 表调用这些 evolvers，而非通过 protocol 多态分发。

### 4.2 旧 evolver_protocol.py 仍存在

`services/evolver_protocol.py` 定义了旧版 `Evolver` protocol（单一 `evolve()` 方法），与 `domain/protocols.py` 的 `LifecycleEvolver` 共存。两个 protocol 的并存会让新开发者困惑。

---

## 五、代码 Review 具体发现

### 5.1 高优先级

#### F1: run_progress.py — 非原子 JSON 写入

```python
# services/run_progress.py L70-78
def save(self, base_dir: Path | None = None) -> Path:
    path = self._resolve_path(base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(                    # ← 非原子写入
        json.dumps(self.to_dict(), indent=2) + "\n",
        encoding="utf-8",
    )
    return path
```

**修复方案**：抽取 `atomic_write_json()` 工具函数，所有 JSON 状态写入统一使用：

```python
import tempfile, os

def atomic_write_json(path: Path, data: dict) -> None:
    """Write JSON atomically via write-to-temp + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)  # POSIX atomic rename
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
```

**受影响文件**：`run_progress.py`、`daemon.py`（4 处）、`run_controller.py`（report.json 写入）、`telemetry_service.py`。

#### F2: RunController God Object

`run_controller.py`（1,585 行）混合了多个关注点：

- Pipeline 执行编排（`run_issue` / `advance` / `advance_to_completion`）
- 文件 I/O（report.json 读写、spec snapshot 管理）
- 事件发射（`_log_and_emit`、`_emit_fallback`）
- Gate 评估与结果组装（`_finalize_run`）
- 合规检测（`_check_compliance`）

**修复方案**：按关注点拆分为 3 个模块：

```
services/
├── pipeline/
│   ├── executor.py          # run_issue, advance, advance_to_completion
│   ├── artifact_writer.py   # report.json, explain.md, state 管理
│   └── event_emitter.py     # _log_and_emit, telemetry 集成
```

拆分原则：每个文件 < 500 行，通过构造函数注入依赖。

### 5.2 中优先级

#### F3: cli.py 单文件 4,091 行

**修复方案**：拆分为 `cli/` 目录：

```
cli/
├── __init__.py       # app = typer.Typer() + 注册子命令组
├── run_commands.py   # run, advance, rerun, accept
├── spec_commands.py  # spec, plan, scope
├── daemon_commands.py
├── evolution_commands.py
├── dashboard_commands.py
└── utils.py          # 共享的 output formatting
```

#### F4: flow_router.py — LLM JSON 输出无 schema 验证

```python
# flow_engine/flow_router.py L172-184
parsed = json.loads(content)
flow_str = parsed.get("flow", "standard")  # ← 无类型检查
```

**修复方案**：使用 Pydantic 或手动 schema 验证所有 LLM JSON 输出。LLM 可能返回非预期结构（如 `"flow"` 值不在 `FlowType` 枚举中），应有明确的 validation + fallback。

```python
# 推荐模式
try:
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise ValueError("LLM returned non-dict JSON")
    flow_str = parsed.get("flow", "standard")
    flow_type = FlowType(flow_str)  # 枚举验证
except (json.JSONDecodeError, ValueError, KeyError):
    logger.warning("LLM routing output invalid, falling back to STANDARD")
    return FlowRoutingDecision(
        recommended_flow=FlowType.STANDARD,
        confidence=0.0,
        source="fallback",
        reasoning="Invalid LLM output",
    )
```

#### F5: context_assembler.py — json.loads() 无类型检查

```python
# services/context_assembler.py L138-147
parsed = json.loads(raw_content)
# 直接当 dict 使用，未检查是否为 list 或其他类型
```

**修复方案**：加 `isinstance(parsed, dict)` 检查。

### 5.3 低优先级

#### F6: smart_project_analyzer.py — fallback 事件缺失异常详情

```python
# services/smart_project_analyzer.py L254-262
except Exception:
    emit_fallback_safe(...)  # ← 未传入 exc_info
```

**修复方案**：在 fallback 事件的 data 中记录 `str(e)` 或 `traceback` 摘要，方便排查 LLM 调用失败原因。

### 5.4 正面发现

#### F7: NodeContextSpec — 优秀的声明式设计

```python
# domain/context.py L103-117
@dataclass(slots=True)
class NodeContextSpec:
    node_name: str
    required_task_fields: list[str] = field(default_factory=list)
    required_execution_fields: list[str] = field(default_factory=list)
    required_learning_fields: list[str] = field(default_factory=list)
    optional_fields: list[str] = field(default_factory=list)
    max_tokens_budget: int = 8000
    exclude_framework_events: bool = True
```

每个 LLM 节点声明自己需要什么，ContextAssembler 按需组装。这避免了"所有节点拿同一个巨大 prompt"的常见反模式。`exclude_framework_events` 过滤掉对当前节点无意义的事件，节省 token 预算。

---

## 六、改进建议（按优先级排序）

### P0：原子 JSON 写入（阻塞 Phase 14）

| 工作项 | 预估 | 说明 |
|--------|------|------|
| 实现 `atomic_write_json()` 工具函数 | 0.5d | `services/file_utils.py` 或 `services/io.py` |
| 替换所有 `.write_text()` JSON 写入点 | 1d | run_progress / daemon / run_controller / telemetry |
| 添加测试：模拟中断后文件完整性 | 0.5d | 在写入过程中 kill → 验证文件不损坏 |

**验收标准**：grep 全库不存在 `write_text(json` 模式。

### P1：Evolver Protocol 对齐

| 工作项 | 预估 | 说明 |
|--------|------|------|
| 6 个 Evolver 实现 `LifecycleEvolver` 四阶段接口 | 2d | `evolve()` → `observe` + `propose` + `validate` + `promote` |
| `EvolutionTrigger` 改为 protocol 多态分发 | 1d | 删除硬编码 dispatch 表 |
| 删除旧 `services/evolver_protocol.py` | 0.5d | 统一到 `domain/protocols.py` |
| 更新测试 | 1d | — |

**验收标准**：`mypy --strict` 通过，所有 evolver 满足 `isinstance(e, LifecycleEvolver)`。

### P1：services/ 子包化

| 工作项 | 预估 | 说明 |
|--------|------|------|
| 按七层分组创建子包 | 1d | 见下方建议结构 |
| 更新所有 import 路径 | 2d | 可用 `rope` 或 `ruff` 批量重构 |
| 验证测试全部通过 | 0.5d | — |

**建议目录结构**：

```
services/
├── context/           # ContextAssembler, ContextRanker, NodeContextRegistry
├── evolution/         # 6 Evolvers, EvolutionTrigger, EvolutionPolicy
├── execution/         # RunController (拆分后), Workspace, Builder adapters
├── evidence/          # Gate, Verification, Artifact, Telemetry
├── memory/            # (已有子包)
├── flow_engine/       # (已有，位于 src/spec_orch/flow_engine/)
└── ... (其余辅助 services)
```

### P1：RunController 拆分

| 工作项 | 预估 | 说明 |
|--------|------|------|
| 抽取 `ArtifactWriter` | 1d | report.json / explain.md / state 读写 |
| 抽取 `EventEmitter` | 0.5d | `_log_and_emit` + telemetry 集成 |
| RunController 瘦身到 < 600 行 | 1d | 只保留 pipeline 编排逻辑 |

### P2：cli.py 拆分

| 工作项 | 预估 | 说明 |
|--------|------|------|
| 创建 `cli/` 目录 + 子模块 | 1.5d | 按命令组拆分 |
| 更新 `pyproject.toml` entry point | 0.5d | `spec-orch = "spec_orch.cli:app"` → `spec_orch.cli.__init__:app` |

### P2：LLM JSON 输出验证

| 工作项 | 预估 | 说明 |
|--------|------|------|
| 为所有 LLM JSON 输出点添加 schema 验证 | 1.5d | flow_router / context_assembler / smart_project_analyzer |
| 统一 fallback 模式 | 0.5d | 验证失败 → log warning + emit_fallback_safe + 使用默认值 |

### P3：VerificationSummary 遗留字段清理

`VerificationSummary` 中存在历史遗留的 `details` 字段与新的 `VerificationDetail` 类型并存，可在后续版本统一清理。

---

## 七、与现有路线图的关系

| 本文建议 | 关联路线图 | 关系 |
|----------|----------|------|
| P0 原子写入 | Phase 14 SON-46 Daemon 健壮性 | **前置依赖** — 无原子写入则 daemon 重启恢复不可靠 |
| P1 Evolver 对齐 | Epic A~H 中 Evolution 相关项 | **技术债清理** — 降低后续 evolution 深化成本 |
| P1 services/ 子包化 | 七层 → 骨架三层 架构叙事 | **代码反映架构** — 让代码结构匹配架构设计 |
| P1 RunController 拆分 | Phase 14 Daemon Hotfix | **降低改动风险** — 瘦化后更容易加 hotfix 路径 |
| P2 cli.py 拆分 | Phase 16 产品化 | **开发者体验** — 新人可以只看相关子命令 |
| P2 LLM JSON 验证 | 方向性文档 张力3 "LLM 化关键决策点" | **健壮性** — LLM 输出不可靠时优雅降级 |

---

## 八、执行建议

1. **先做 P0 原子写入**：工作量小（2d），价值高，直接解锁 Phase 14
2. **P1 三项可并行**：Evolver 对齐、services 子包化、RunController 拆分互不依赖
3. **拆分类重构使用 `git mv` + 批量 import 更新**：保留 git blame 历史
4. **每个 P1 项完成后跑全量测试**：`pytest tests/ && ruff check src/`
