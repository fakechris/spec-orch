# Implementation Plan: Memory vNext (Phase 1–4)

**Date:** 2026-03-22
**References:**
- [ADR-0002: Memory vNext](adr-0002-memory-vnext.md)
- [PRD: ProjectProfile + Learning Views](prd-project-profile.md)

## Phase 1: 最小关系层

**目标：** 不改底层架构，只增强 memory 的可演化性和可过滤性。

### 1.1 SQLite schema 扩展 + 自动迁移

**当前 schema**（`fs_provider.py:312-318`）：

```sql
CREATE TABLE IF NOT EXISTS memory_index (
    key        TEXT PRIMARY KEY,
    layer      TEXT NOT NULL,
    tags       TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT ''
);
```

**新增三列：**

```sql
ALTER TABLE memory_index ADD COLUMN entity_scope TEXT NOT NULL DEFAULT '';
ALTER TABLE memory_index ADD COLUMN entity_id    TEXT NOT NULL DEFAULT '';
ALTER TABLE memory_index ADD COLUMN relation_type TEXT NOT NULL DEFAULT 'observed';
```

**新增索引：**

```sql
CREATE INDEX IF NOT EXISTS idx_entity ON memory_index(entity_scope, entity_id);
CREATE INDEX IF NOT EXISTS idx_relation ON memory_index(relation_type);
```

**迁移策略：** 在 `_init_db_connection` 中用 `PRAGMA table_info(memory_index)` 检测
是否缺少 `entity_scope` 列，缺少时执行 `ALTER TABLE`。与现有的 `_maybe_migrate_json`
模式一致。

**修改文件：**
- `src/spec_orch/services/memory/fs_provider.py` — `_init_db_connection` 增加列检测与迁移

**测试：**
- 新 DB 自动包含三列
- 旧 DB 打开时自动迁移
- 迁移后现有条目的默认值正确

### 1.2 写入侧补充关系字段

在所有写入点补充 `entity_scope`、`entity_id`、`relation_type`，并同步写入 SQLite 列。

**当前写入点与改造方案：**

| 方法 | 文件 | entity_scope | entity_id | relation_type |
|------|------|--------------|-----------|---------------|
| `consolidate_run()` | `service.py:281-320` | `issue` | `issue_id` | `summarize` |
| `record_builder_telemetry()` | `service.py:322-370` | `issue` | `issue_id` | `observed` |
| `record_acceptance()` | `service.py:372-376` | `issue` | `issue_id` | `observed` |
| `compact()` 蒸馏 | `service.py:130-230` | `issue` | 从源条目继承 | `derive` |
| EventBus 订阅写入 | `service.py` | 按事件类型推断 | 按事件内容提取 | `observed` |
| `store()` 透传 | `fs_provider.py:158` | 从 `entry.metadata` 读取 | 同左 | 同左 |

**`store()` 改造（`fs_provider.py:158-178`）：**

```python
def store(self, entry: MemoryEntry) -> str:
    entity_scope = entry.metadata.get("entity_scope", "")
    entity_id = entry.metadata.get("entity_id", "")
    relation_type = entry.metadata.get("relation_type", "observed")
    # ... INSERT OR REPLACE 时包含三列 ...
```

**修改文件：**
- `src/spec_orch/services/memory/fs_provider.py` — `store()` 提取并写入新列
- `src/spec_orch/services/memory/service.py` — `consolidate_run`, `record_builder_telemetry`, `record_acceptance` 在 metadata 中填充新字段
- `src/spec_orch/services/run_controller.py` — `_consolidate_run_memory` 确保传递 entity 信息

**测试：**
- `consolidate_run` 写入条目的 SQLite 列值正确
- `record_builder_telemetry` 写入条目的列值正确
- `record_acceptance` 写入条目的列值正确
- `compact` 蒸馏条目继承 `entity_id` 并标记 `relation_type=derive`

### 1.3 recall_latest API + ContextAssembler 改造

**新增辅助方法（`MemoryService`）：**

```python
def recall_latest(
    self,
    *,
    entity_scope: str,
    entity_id: str,
    layer: MemoryLayer | None = None,
    tags: list[str] | None = None,
    top_k: int = 5,
) -> list[MemoryEntry]:
    """Recall the most recent entries for a given entity, preferring
    entries that have not been superseded."""
```

实现思路：先用 SQL 按 `entity_scope + entity_id` 过滤，再排除
`relation_type = 'superseded'` 的条目，最后按 `updated_at DESC` 取 `top_k`。

**`_filtered_keys` 扩展（`fs_provider.py`）：**

新增参数 `entity_scope`, `entity_id`, `exclude_relation_types`，在 SQL
`WHERE` 中使用新列过滤。

**ContextAssembler 改造（`context_assembler.py:435-508`）：**

- `similar_failure_samples` 召回时增加 `exclude_relation_types=["superseded"]`
- 优先使用同 issue 的失败记录（`entity_id` 匹配）
- `relevant_procedures` 不变（PROCEDURAL 层不涉及关系语义）

**修改文件：**
- `src/spec_orch/services/memory/service.py` — 新增 `recall_latest`
- `src/spec_orch/services/memory/fs_provider.py` — `_filtered_keys` 扩展 SQL 过滤
- `src/spec_orch/services/context/context_assembler.py` — 使用 latest 优先召回

**测试：**
- `recall_latest` 对同一 entity 的多次 run 返回最新条目
- 被 `supersedes_key` 替代的条目不出现在结果中
- ContextAssembler 注入的失败样本不含已被修复的旧失败

---

## Phase 2: ProjectProfile + Learning Views

**目标：** 把离散记忆变成节点可直接消费的结构化上下文。

**前置条件：** Phase 1 完成。

详细设计见 [PRD: ProjectProfile + Learning Views](prd-project-profile.md)。

### 实现步骤

1. **定义数据类型**
   - `ProjectProfile` dataclass 在 `src/spec_orch/domain/context.py`
   - `FailurePattern`, `SuccessRecipe`, `ActiveRunSignals` dataclass

2. **MemoryService 新增四个视图方法**
   - `get_failure_patterns(entity_id, top_k)` — 聚合 EPISODIC `issue-result` + SEMANTIC `run-summary`
   - `get_success_recipes(entity_id, top_k)` — 筛选 `succeeded=True` 的 run-summary
   - `get_project_profile()` — 从 SEMANTIC `entity_scope=project` + `spec-orch.toml` 降级
   - `get_active_run_signals(days)` — 最近 N 天的 EPISODIC + SEMANTIC 聚合

3. **ContextAssembler 差异化注入**
   - 按 `NodeContextSpec.node_name` 或新增 `role` 分流
   - Builder: `failure_patterns` + `success_recipes`
   - Planner: `project_profile` + `active_run_signals`
   - Reviewer: `failure_patterns` + `active_run_signals`

4. **LearningContext 扩展**
   - 新增 `project_profile`, `failure_patterns`, `success_recipes`, `active_run_signals`
   - 注册到 `_add_learning_sections` + `_LEARNING_LIST_FIELDS` / `_LEARNING_DICT_FIELDS`

5. **降级填充**
   - 无 Phase 4 async derivation 时，从配置文件 + 现有 trend 实时组装

**修改文件：**
- `src/spec_orch/domain/context.py`
- `src/spec_orch/services/memory/service.py`
- `src/spec_orch/services/context/context_assembler.py`

---

## Phase 3: Hybrid Retrieval

**目标：** 提高 recall 命中质量，尤其是 issue/spec/code 场景。

**前置条件：** Phase 1 完成。

### 3.1 SQLite FTS5

**新增虚拟表：**

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts
USING fts5(key, content, tokenize='unicode61');
```

**同步策略：** `store()` 时同步 `INSERT OR REPLACE INTO memory_fts`；`forget()` 时
同步 `DELETE FROM memory_fts`。`_rebuild_index()` 时全量重建 FTS 表。

**CJK 支持：** FTS5 的 `unicode61` tokenizer 对中文效果有限。可选方案：
- 使用 `unicode61 remove_diacritics 2` + trigram
- 或在 FTS 插入时预处理（jieba 分词后以空格连接）
- 评估后选择

### 3.2 Hybrid Recall（RRF 融合）

`FileSystemMemoryProvider.recall()` 改造为三路召回：

```
1. SQL 过滤（layer, tags, entity_scope, entity_id, relation_type）→ 候选 key 集合
2. FTS5 lexical match（query.text against memory_fts）→ lexical 排序
3. Qdrant semantic match（query.text embedding）→ semantic 排序
4. RRF(lexical, semantic, k=60) → 融合排序
5. 取 top_k → metadata filter → 返回
```

**RRF 实现（Reciprocal Rank Fusion）：**

```python
def _rrf_merge(
    lexical_keys: list[str],
    semantic_keys: list[str],
    k: int = 60,
    lexical_weight: float = 1.0,
    semantic_weight: float = 1.0,
) -> list[str]:
    scores: dict[str, float] = {}
    for rank, key in enumerate(lexical_keys):
        scores[key] = scores.get(key, 0) + lexical_weight / (k + rank + 1)
    for rank, key in enumerate(semantic_keys):
        scores[key] = scores.get(key, 0) + semantic_weight / (k + rank + 1)
    return sorted(scores, key=scores.get, reverse=True)
```

### 3.3 Exact Token Boost

对精确标识符（issue ID、error code、file path、gate condition name）给 lexical
更高权重：

- 检测 `query.text` 中的 `SON-\d+`、文件路径模式、已知 gate condition name
- 对匹配到的查询，将 `lexical_weight` 从 1.0 提升到 2.0

### 3.4 Recall Provenance

`recall()` 返回的 `MemoryEntry` 增加临时字段或在 metadata 中添加召回元信息：

```python
entry.metadata["_recall_provenance"] = {
    "match_reason": "lexical" | "semantic" | "both",
    "rrf_score": 0.032,
    "is_latest": True,
    "is_derived": False,
    "source_type": "failure_sample" | "run_summary" | "procedure",
}
```

ContextAssembler 在注入 LLM 上下文时，可选择包含 provenance 摘要以便调试。

**修改文件：**
- `src/spec_orch/services/memory/fs_provider.py` — FTS5 表、hybrid recall
- `src/spec_orch/services/memory/vector_provider.py` — 配合 hybrid 流程
- `src/spec_orch/services/context/context_assembler.py` — provenance 注入

---

## Phase 4: 异步 Derivation

**目标：** 把重计算从主 pipeline 中剥离，形成 Evolution Plane 的"慢脑"。

**前置条件：** Phase 2 + Phase 3。

### 4.1 Derivation 任务类型

| 任务 | 触发条件 | 输入 | 输出 |
|------|----------|------|------|
| issue-summarize | 同一 issue 累计 3+ 次 run | 该 issue 的所有 EPISODIC/SEMANTIC 条目 | SEMANTIC `entity_scope=issue` `relation_type=summarize` |
| project-profile-refresh | 每 N 次 run 或手动触发 | 全部 run-summary + spec-orch.toml | SEMANTIC `entity_scope=project` |
| skill-patch-suggestion | 新 run-summary + 已有 skill manifests | Run artifacts + skills YAML | Evolution event 或直接 patch skill |
| stale-memory-soft-delete | 定期扫描 | EPISODIC + SEMANTIC `updated_at` | 标记 `relation_type=superseded` |
| success-recipe-extraction | `succeeded=True` 的 run | Run-summary + builder telemetry | SEMANTIC `relation_type=derive` |

### 4.2 调度模型

两种模式，由配置切换：

**同步模式（默认，向后兼容）：**

与当前相同，`_finalize_run` 中顺序执行。适合低频率使用和开发环境。

**异步模式（daemon 场景）：**

```toml
[memory]
derivation_mode = "async"  # "sync" | "async"
```

新增 `DerivationQueue`（基于 SQLite 的轻量任务队列）：

```python
class DerivationQueue:
    def enqueue(self, task_type: str, payload: dict) -> str: ...
    def dequeue(self, batch_size: int = 5) -> list[DerivationTask]: ...
    def complete(self, task_id: str) -> None: ...
```

`_finalize_run` 在 async 模式下只 enqueue，daemon 的 tick 循环中 dequeue 并执行。

### 4.3 从 `_finalize_run` 剥离

当前 `_finalize_run` 中的三个重操作改造为可配置：

| 操作 | sync 模式 | async 模式 |
|------|-----------|------------|
| `consolidate_run()` | 立即执行（快，保留） | 立即执行（快，保留） |
| `compact()` | 立即执行 | enqueue `compact` 任务 |
| `_maybe_trigger_evolution()` | 立即执行 | enqueue `evolution` 任务 |

`consolidate_run` 始终同步，因为后续 phase 的 recall 可能立即需要该条目。

### 4.4 Profile 自动刷新

`project-profile-refresh` 任务的 LLM prompt 结构：

```
Given the following run history and project configuration:
- Recent 30 runs: [success/failure summary]
- spec-orch.toml: [project type, verification commands]
- Existing profile: [current ProjectProfile if any]

Update the ProjectProfile:
- tech_stack: [infer from runs and config]
- common_failures: [top recurring failure reasons]
- ...
```

输出写入 SEMANTIC 层，`entity_scope=project`，`entity_id=<repo_name>`，
`relation_type=summarize`。

**新增文件：**
- `src/spec_orch/services/memory/derivation.py` — `DerivationQueue`, `DerivationWorker`

**修改文件：**
- `src/spec_orch/services/run_controller.py` — `_finalize_run` 支持 sync/async
- `src/spec_orch/services/memory/service.py` — `compact` 和 evolution 的 enqueue 路径

---

## 优先级与依赖关系

```
Phase 1.1 (schema)
    ↓
Phase 1.2 (write-side) ──→ Phase 1.3 (recall + assembler)
    ↓                            ↓
Phase 2 (profile + views)   Phase 3 (hybrid retrieval)
    ↓                            ↓
    └──────────→ Phase 4 (async derivation) ←────┘
```

Phase 2 和 Phase 3 可以并行开发，互不依赖。Phase 4 依赖两者。

## 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| FTS5 中文分词效果差 | Phase 3 的 lexical 对中文查询质量低 | 预处理时用 jieba 分词后空格连接再入 FTS5 |
| async derivation 任务积压 | 大量 run 时队列增长 | 限制队列深度 + 优先级排序 + 超时丢弃 |
| SQLite 列迁移对大型 memory store 慢 | 首次启动延迟 | ALTER TABLE ADD COLUMN 在 SQLite 中是 O(1) 操作 |
| ProjectProfile LLM 蒸馏质量不稳 | Static 部分错误 | 保留配置文件降级路径，人工可覆盖 |
| relation_type 分类不够用 | 需要更多关系类型 | 预留 `custom` 类型 + 扩展字段 |

## 估算

| Phase | 工作量 | 测试 | 总计 |
|-------|--------|------|------|
| 1.1 Schema + 迁移 | 2h | 1h | 3h |
| 1.2 写入侧填充 | 3h | 2h | 5h |
| 1.3 recall_latest + Assembler | 4h | 3h | 7h |
| 2 ProjectProfile + Views | 6h | 4h | 10h |
| 3 Hybrid Retrieval | 6h | 4h | 10h |
| 4 Async Derivation | 8h | 4h | 12h |
| **合计** | | | **~47h** |
