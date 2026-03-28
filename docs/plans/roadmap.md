# SpecOrch Roadmap

> 本文档是 SpecOrch 的活路线图，持续更新。
> 参见 [Seven Planes 架构](../architecture/seven-planes.md) / [Project Vision](../../VISION.md)

---

## 项目状态

**v0.5.2** — Alpha，内部 dogfood 模式。1245+ 测试，65+ 命令。

七层架构骨架完备，Credibility Flywheel 各环基线就位，架构债务已清理。
Memory Architecture v2 完成：SQLite WAL 索引替代 JSON、LLM 摘要蒸馏、Builder telemetry 入库、用户反馈存储、时间趋势聚合、4 层记忆全部激活。
分层记忆架构（ADR-0001）已通过完整 E2E 验证：Qdrant 语义索引 + 真实 run-issue 链路确认可用。
当前处于**从内部原型走向外部验证**的转折点。

Linear 现状：主干基础能力已完成，当前重新打开了下一阶段 backlog，重点集中在：

- `SON-234` Operator Console Phase 2
- `SON-242` Acceptance Harness Phase 2
- `SON-243` Harness Selfhood
- `SON-244` Operator Feedback and Social Learning

---

## 接下来要做什么

按优先级排列。每项启动前应创建 Linear issue 并回填到本表。

### Milestone 0: Memory vNext（SON-227）✅ DONE

**状态**：全部 6 个 child issues 已合并。Review 修复 PR 已提交（distilled key 覆盖、SQL 下推、soft-delete、跨进程安全、service 拆分、entity filter 协议化）。

设计文档：`docs/specs/memory-vnext/`

| Phase | 任务 | Linear | 状态 |
|-------|------|--------|------|
| 1.1 | SQLite schema 扩展 + 自动迁移（entity_scope, entity_id, relation_type） | SON-228 | ✅ |
| 1.2 | 写入侧补充关系字段 | SON-229 | ✅ |
| 1.3 | recall_latest API + ContextAssembler 改造 | SON-230 | ✅ |
| 2 | ProjectProfile + Learning Views | SON-231 | ✅ |
| 3 | Hybrid Retrieval（FTS5 + RRF） | SON-232 | ✅ |
| 4 | Async Derivation | SON-233 | ✅ |
| Review | 8 项 review 修复（P0/P1/P2） | — | ✅ |

### Milestone 1: 外部用户端到端验证

**为什么是第一优先级**：内部 dogfood 已证明系统可以跑通，但从未在真实外部用户的项目上验证过。产品假设需要真实数据支撑。

| 任务 | 说明 | Linear |
|------|------|--------|
| 选定 1~2 个外部项目 | 非 spec-orch 自身的中型 Python/TS 项目 | — |
| 端到端 run 记录 | `init → run → gate → PR → review → merge` 全链路 | — |
| 收集反馈并归档 | 用户体验痛点、报错、fallback 路径质量 | — |
| Daemon + MiniMax 全链路实测 | 低成本模型下 daemon 模式自动执行验证 | — |

### Milestone 1A: Harness Engineering vNext

**为什么现在做**：Operator Console、Mission Launcher、Acceptance Evaluator 基线都已经落地。下一阶段不该只补 UI 细节，而应该把 acceptance、self-evolution、memory synthesis、feedback learning 这些更深的 harness 能力接起来。

详细设计见：
- [SpecOrch vs yoyo-evolve: Harness Engineering Roadmap](2026-03-28-spec-orch-vs-yoyo-evolve-roadmap.md)

| 方向 | 说明 | Linear |
|------|------|--------|
| Operator Console Phase 2 | 收口 transcript / approvals / Visual QA / costs / dogfood 闭环 | `SON-234`, `SON-235..241` |
| Acceptance Harness Phase 2 | exploratory / adversarial acceptance、route planning、browser interaction | `SON-242`, `SON-245..248` |
| Harness Selfhood | constitutions、active memory synthesis、role-scoped memory、evolution journal | `SON-243`, `SON-249..252` |
| Operator Feedback & Social Learning | operator feedback capture、feedback synthesis、policy loop、social ingestion spike | `SON-244`, `SON-253..256` |

### Milestone 2: Contract 自动化

**目标**：自动为高风险 task 生成 Contract，减少人工干预。

| 任务 | 说明 | Linear |
|------|------|--------|
| Contract 模板标准化 | 基于积累的 spec 样本提炼模板 | — |
| `generate-task-contract` Skill | Conductor 根据风险等级自动生成 | — |
| Risk Level 自动评估 | import graph + 修改文件被引用次数 | — |
| Gate 增加 contract_violations 维度 | 越界行为作为门控条件 | — |

### Milestone 3: 产品化

**目标**：从原型走向可发布产品。

| 任务 | 说明 | Linear |
|------|------|--------|
| TUI 集成测试 + 稳定性 | React/Ink TUI 在多终端下的验证 | — |
| 文档刷新 | 快速上手指南 + API 文档 | — |
| PyPI 发布自动化 | CI 自动发布 + 版本号管理 | — |
| 端到端 dogfood 连续 7 天 | 用 spec-orch 开发 spec-orch | — |

### Milestone 4: 架构一致性 + 深化基线

**核心架构矛盾（优先解决）：**

| 矛盾 | 现状 | 目标 |
|------|------|------|
| FlowEngine 未接入 run_issue | `graphs.py` 定义 Full/Standard/Hotfix 三套 DAG，但 `run_issue()` 硬编码 build→verify→review→gate 顺序 | `run_issue()` 通过 FlowEngine 驱动，消除两个并行编排引擎 |
| Spec auto-approve | `run_issue()` 直接 `approved=True` 跳过 spec freeze | 提供 `--require-spec-approval` flag，daemon 模式默认要求 spec 审批 |

**已有基线深化：**

| 方向 | 当前状态 | 深化目标 |
|------|----------|----------|
| Reaction Engine | 内置 3 个 reaction + daemon 集成 | 用户自定义 recipe、更多内置 reaction |
| Skill Runtime | SkillEvolver 自动发现 + ContextAssembler 自动注入 | Repo-level registry、Skill→Policy 蒸馏、execute_skill 协议 |
| Memory System | 4 层记忆 + SQLite WAL + LLM 蒸馏 + telemetry + 用户反馈 + 趋势聚合 + Qdrant 语义索引 + **Memory vNext 已全量落地**: entity relation layer, ProjectProfile, FTS5+RRF hybrid retrieval, async derivation, MemoryService 拆分 (Analytics/Distiller/Recorder), soft-delete compaction, SQL 下推, 跨进程安全 | 跨 repo 知识 silo 打通, WORKING/PROCEDURAL 消费侧增强 |
| Control Tower | API endpoints + 基础 UI | Session 视图、成本监控、移动端 |
| Harness Evals | EvalRunner + CLI 基线 | 自动 A/B 对比、变更自动 eval |
| Preview & Sandbox | Gate 有条件，未实际接入 | Preview provider + Docker sandbox |

---

## 不做的方向

1. **不做 multi-agent 通信总线** — 默认 orchestrator-worker
2. **不做 graph-first workflow builder** — spec-first，不是 graph-first
3. **不做 AI IDE** — 控制面，不是编辑器
4. **不追"更聪明的 prompt"** — 先把 trace / artifacts / eval / gate 做扎实
5. **不做多个 builder 并行改同一片代码** — 一任务一隔离始终如此

---

## 已完成的里程碑

### Credibility Flywheel（2026-03-18 ~ 2026-03-20）

七条 Plane 的基线能力构建，从 P0 Context Contract 到 P6 Harness Evals：

| 轨道 | 交付 | Linear |
|------|------|--------|
| Context Contract 全面接入 | 12 个 LLM 节点全部走 ContextAssembler | SON-174, SON-177~180 |
| Run Artifact 统一 | 统一 schema + EventBus 历史查询 + Dashboard 消费 | SON-189, SON-194~200 |
| Reaction Engine | YAML recipe + 3 个内置 reaction + daemon 集成 | SON-191, SON-201 |
| Skill Format | SkillManifest schema + validation + loader | SON-192, SON-203 |
| Control Tower | API endpoints (overview/skills/eval/reactions) | SON-193, SON-204 |
| Harness Evals | EvalRunner + `spec-orch eval` CLI + 指标集 | SON-190, SON-202 |

### SkillCraft 涌现管道（2026-03-21）

基于 SkillCraft 论文和 Hermes/Cognee 记忆架构分析，补齐 Skill 发现闭环和记忆治理：

| 交付 | 说明 |
|------|------|
| SkillEvolver | 第 7 个 LifecycleEvolver，从 builder telemetry 自动发现 tool-call 模式并保存为 SkillManifest YAML |
| Skill Runtime | ContextAssembler 自动加载、匹配、注入 skills 到 builder 上下文 |
| ContextRanker 完整接入 | Learning context 纳入优先级分配，热/冷分离覆盖 hints、skills、failure samples |
| Memory compaction + TTL | EPISODIC 层 30 天自动过期，run 结束自动 consolidate 到 SEMANTIC 层 |

### 分层记忆架构 ADR-0001（2026-03-21）

| 交付 | 说明 | Linear |
|------|------|--------|
| ADR-0001 | 文件系统真相源 + Qdrant 语义索引 + QMD 文档检索 | SON-210~214 |
| QdrantIndex | 可选语义索引层，store 后写 embedding，recall 走语义搜索 | SON-212 |
| VectorEnhancedProvider | 组合 FS + Qdrant，Qdrant 不可用时静默降级 | SON-212 |
| memory extra | `pip install spec-orch[memory]` 引入 qdrant-client | SON-213 |
| 消费点接入 | similar_failure_samples 增加 query.text 语义召回 | SON-214 |

### Memory Architecture v2（2026-03-22）

Memory 系统全面升级，从"事件记录"进化为"学习记忆"：

| 交付 | 说明 | Linear |
|------|------|--------|
| SQLite WAL 索引 | `_index.json` 全量重写迁移到 SQLite，解决 10k+ 条目性能瓶颈 | SON-220 |
| LLM 摘要蒸馏 | `compact()` 将过期 EPISODIC 按 issue 分组，LLM 蒸馏为 SEMANTIC 摘要 | SON-222 |
| PROCEDURAL 层激活 | `ContextAssembler` 消费 PROCEDURAL 层的 ingested specs/contracts | SON-223 |
| Builder telemetry 入库 | run finalize 时读取 JSONL telemetry，工具调用序列存入 episodic memory | SON-224 |
| 用户反馈存储 | `accept-issue` 写入 `record_acceptance()`，人工验收进入 memory | SON-225 |
| 时间趋势聚合 | `get_trend_summary()` 提供最近 N 天成功率、失败原因统计 | SON-225 |
| run-summary 丰富 | builder adapter、verification 结果、key_learnings 写入 semantic memory | SON-226 |
| Review findings 修复 | LIMIT-before-tags、get() 竞态保护、空 model 默认值、CJK bigram 混合文本、ContextRanker budget 注册 | SON-218~226 |

### E2E 验证通过（2026-03-21）

| 验证项 | 结果 |
|--------|------|
| qdrant-client + fastembed 安装 | qdrant-client 1.17.1 + fastembed 0.7.4 |
| Qdrant 集成测试（真实 embedding） | 8/8 全部通过，BAAI/bge-small-zh-v1.5 |
| 中文语义搜索验证 | 5 条中文数据写入，语义匹配成功，FS 对照返回 0 条 |
| spec-orch.toml 配置自动切换 | VectorEnhancedProvider 自动激活 |
| SON-215 + SON-216 真实 run-issue | Builder 成功，Gate 评估完成，consolidate_run 写入 Qdrant |
| 跨 run 语义 recall | 两次 run-summary 均可通过语义查询召回 |

### 架构债务清理（2026-03-20）

| 交付 | 说明 | Linear |
|------|------|--------|
| 原子文件写入 | `atomic_write_json/text` 覆盖全部状态文件 | SON-206 |
| LifecycleEvolver 协议 | 6 个 Evolver 统一 4 阶段 + 多态分发 | SON-206 |
| CLI 模块化 | `cli/` 包 10 个子模块替代 4092 行单文件 | SON-206 |
| LLM JSON 验证 | Schema 验证 + fallback + 可观测事件 | SON-206 |
| 跨平台文件锁 | `file_lock()` 支持 POSIX + Windows | PR #117 |

### Agent-First Decision Architecture（2026-03-17）

| Phase | 交付 | Linear |
|-------|------|--------|
| A | 配置外部化：gate / reviewer / evolution 参数提取到 TOML | SON-162 |
| B1 | Smart Init：LLM-driven 项目分析 + 验证命令生成 | SON-163 |
| B2 | 动态验证步骤：VerificationSummary 支持任意步骤名 | SON-164 |
| B3 | Monorepo / Multi-Language 自定义步骤 | SON-165 |
| C | Config Evolver：基于 evidence 持续优化配置 | SON-166 |

### Agent 工程化 Epic A~H（2026-03-18）

用户启动体验、Preflight/Selftest、评测体系、追踪可观测性、上下文深化、Prompt Caching、Skill 退化检测、多 Agent 幻觉防护 — 全部完成。

### 基础架构 Phase 1~14（2026-03 ~ 2026-03-20）

12 个 Phase/Epic：Gate-as-a-Layer → EODF 闭环 → Daemon → Self-Evolution → Mission Control → 混合架构 → 编排大脑 → 可插拔适配器 → E2E 验证 → 上下文治理 → 生产健壮性。170 个 Linear issue 全部关闭。

---

## 变更日志

| 日期 | 变更 |
|------|------|
| 2026-03-18 | 初版，P0~P6 按 Plane 组织 |
| 2026-03-20 | 重构为 Milestone 格式：未来方向优先、已完成附后、去除日期前缀 |
| 2026-03-21 | SkillCraft 涌现管道落地：SkillEvolver + Skill Runtime + ContextRanker 完整接入 + Memory compaction |
| 2026-03-21 | 分层记忆架构 ADR-0001 落地 + Qdrant 语义索引 + E2E 验证通过 |
| 2026-03-22 | Memory Architecture v2：SQLite WAL、LLM 蒸馏、telemetry 入库、用户反馈、趋势聚合、4 层激活、review findings 修复 |
| 2026-03-22 | Memory vNext 规划：ADR-0002 + PRD + Implementation Plan + Linear Epic SON-227（6 个 child issues） |
| 2026-03-22 | Memory vNext 全量落地：SON-228~233 全部合并（6 PRs, #134~#139） |
| 2026-03-22 | Memory vNext Review 修复：8 项 P0/P1/P2 修复 — distilled key 去重、SQL 下推、soft-delete compaction、BEGIN EXCLUSIVE 跨进程安全、MemoryService 拆分(Analytics+Distiller+Recorder)、FTS5 文档校正、entity filter 协议化 |
