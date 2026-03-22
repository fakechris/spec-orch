# PRD: ProjectProfile + Learning Views

**Status:** Draft
**Date:** 2026-03-22
**Depends on:** [ADR-0002](adr-0002-memory-vnext.md) Phase 1 (minimal relation layer)

## Problem

ContextAssembler 当前对所有 LLM 节点做相同的 recall：`similar_failure_samples`
（EPISODIC, tags=issue-result, succeeded=False）、`relevant_procedures`（PROCEDURAL）、
`success_trend`（`get_trend_summary()`）。见 `context_assembler.py:430-508`。

这带来三个问题：

1. **无差异化注入。** Builder 需要失败修复套路和可执行 recipe；Planner 需要项目长期画像；
   Reviewer 需要历史 deviation 和 gate 案例。但所有节点拿到的 learning context 相同。
   `NodeContextSpec.required_learning_fields` 虽然支持按字段过滤，但可选字段只有 7 个
   （`context.py:49-59`），且全部是扁平列表/字典，不区分结构化视图。

2. **无项目级画像。** `get_trend_summary()` 返回窗口内成功率和 top 失败原因，但不包含
   tech stack、常见验证命令、目录结构、架构约束等**稳定事实**。每次 run 都从零推断
   这些信息（或依赖 `spec-orch.toml` 中的静态配置）。

3. **recall 结果偏"命中"而非"结论"。** 当前注入的是原始 `MemoryEntry.content` 的截断片段
   （`_truncate(e.content, budget // 10)`），缺少结构化的 failure pattern / success
   recipe 视图。消费者必须自己从原文提取有效信息。

## Solution

### S1: ProjectProfile schema

新增 `ProjectProfile` dataclass，分为 Static 和 Dynamic 两部分：

```python
@dataclass(slots=True)
class ProjectProfile:
    """Long-lived project-level profile assembled from memory."""

    # Static: changes infrequently, updated by async derivation
    tech_stack: list[str] = field(default_factory=list)
    common_failures: list[str] = field(default_factory=list)
    verification_commands: list[str] = field(default_factory=list)
    architecture_constraints: list[str] = field(default_factory=list)
    directory_hotspots: list[str] = field(default_factory=list)

    # Dynamic: refreshed from recent runs
    recent_success_rate: float | None = None
    recent_period_days: int = 7
    high_freq_failure_conditions: list[str] = field(default_factory=list)
    volatile_components: list[str] = field(default_factory=list)
    active_skills: list[str] = field(default_factory=list)
    active_policies: list[str] = field(default_factory=list)
    builder_adapter_performance: dict[str, float] = field(default_factory=dict)
```

存放位置：`src/spec_orch/domain/context.py`（与 `LearningContext` 同文件）。

Static 部分从 SEMANTIC 层 `entity_scope=project` 的记忆中读取，由 Phase 4 的
async derivation 定期刷新。在 async derivation 未就绪时，从 `spec-orch.toml`
的 `[project]` / `[verification]` 配置中降级填充。

Dynamic 部分从 `get_trend_summary()` 和最近 run-summary entries 实时聚合。

### S2: 四类 Learning View

在 `MemoryService` 上新增四个结构化视图方法：

| View | 方法签名 | 数据来源 | 输出 |
|------|----------|----------|------|
| **failure_patterns** | `get_failure_patterns(entity_id: str \| None, top_k: int = 10) -> list[FailurePattern]` | EPISODIC `issue-result` + SEMANTIC `run-summary` where `succeeded=False` | 失败原因、修复尝试、最终 gate 结果、是否后续被修复 |
| **success_recipes** | `get_success_recipes(entity_id: str \| None, top_k: int = 5) -> list[SuccessRecipe]` | SEMANTIC `run-summary` where `succeeded=True`, 按 `entity_id` 聚合 | builder adapter、tool sequence 摘要、verification 路径、key learnings |
| **project_profile** | `get_project_profile() -> ProjectProfile` | SEMANTIC `entity_scope=project` + 实时 trend | 上文定义的 ProjectProfile |
| **active_run_signals** | `get_active_run_signals(days: int = 7) -> ActiveRunSignals` | EPISODIC + SEMANTIC 最近 N 天 | 当前波动组件、最近失败 issue、最近成功 skill |

每个视图返回**结构化类型**而非原始 `MemoryEntry`，消费者不需要解析 Markdown。

依赖 Phase 1 的 `entity_scope` / `entity_id` 列进行 SQL 级过滤，避免全量扫描。

### S3: 差异化注入策略

`ContextAssembler._build_learning_context` 改造为按 `NodeContextSpec.node_name`
（或新增 `role` 字段）差异化取数：

| Node role | 优先注入 | 次要注入 | 不注入 |
|-----------|----------|----------|--------|
| **builder** | `failure_patterns` + `success_recipes` | `matched_skills`, `relevant_procedures` | `project_profile`（太高层） |
| **planner** | `project_profile` + `active_run_signals` | `failure_patterns`（top 3） | `success_recipes` |
| **reviewer** | `failure_patterns` + `active_run_signals` | `relevant_policies` | `success_recipes` |
| **scoper** | `project_profile` | `scoper_hints` | 其余 |

`LearningContext` 增加两个新字段：

```python
project_profile: ProjectProfile | None = None
failure_patterns: list[dict[str, Any]] = field(default_factory=list)
success_recipes: list[dict[str, Any]] = field(default_factory=list)
active_run_signals: dict[str, Any] | None = None
```

这些字段注册到 `_add_learning_sections` 和 `_LEARNING_LIST_FIELDS` /
`_LEARNING_DICT_FIELDS` 以参与 ContextRanker 的 token budget 分配。

### S4: 从现有数据降级填充

Phase 2 不要求 Phase 4 的 async derivation 完成。降级策略：

- `project_profile.tech_stack`：从 `spec-orch.toml` 的 `[project].type` 读取
- `project_profile.verification_commands`：从 `[verification]` 配置读取
- `project_profile.common_failures`：从 `failure_patterns` 的 top 5 提取
- `project_profile.recent_success_rate`：从 `get_trend_summary()` 取
- `failure_patterns`：从现有 `similar_failure_samples` 召回 + run-summary 交叉引用
- `success_recipes`：从 `run-summary` where `succeeded=True` 提取

这样 Phase 2 交付后立即可用，Phase 4 的 async derivation 只是让 static 部分
更准确。

## Success Criteria

| 指标 | 当前基线 | 目标 |
|------|----------|------|
| Builder 首轮通过率 | 需要外部项目验证建立基线 | 显著提升 |
| Verification 一次通过率 | 需要外部项目验证建立基线 | 显著提升 |
| 重复 gate failure 原因占比 | 无统计 | 下降 |
| Learning context 中有效 token 占比 | 无统计 | 上升 |
| 相似失败召回的人工相关性评分 | 无评估 | 引入评估机制 |

注：成功指标应绑定到 Roadmap Milestone 1（外部用户端到端验证），避免仅在
spec-orch 自身项目上自证。

## Data Model Dependencies

```
Phase 1 relation fields
  ├── entity_scope TEXT (SQLite column)
  ├── entity_id TEXT (SQLite column)
  └── relation_type TEXT (SQLite column)
        │
        ↓
Phase 2 views use SQL:
  SELECT * FROM memory_index
  WHERE entity_scope = 'issue' AND entity_id = ?
  ORDER BY updated_at DESC
```

Without Phase 1, the views must fall back to Python-side filtering of all
entries — feasible but slow for large memory stores.

## Files Affected

| File | Change |
|------|--------|
| `src/spec_orch/domain/context.py` | Add `ProjectProfile`, extend `LearningContext` |
| `src/spec_orch/services/memory/service.py` | Add `get_failure_patterns`, `get_success_recipes`, `get_project_profile`, `get_active_run_signals` |
| `src/spec_orch/services/context/context_assembler.py` | Role-aware `_build_learning_context`, register new fields in budget system |
| `src/spec_orch/domain/context.py` | Optionally add `role` field to `NodeContextSpec` |
