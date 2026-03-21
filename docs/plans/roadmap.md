# SpecOrch Roadmap

> 本文档是 SpecOrch 的活路线图，持续更新。
> 参见 [Seven Planes 架构](../architecture/seven-planes.md) / [Project Vision](../../VISION.md)

---

## 项目状态

**v0.5.1** — Alpha，内部 dogfood 模式。1196+ 测试，65+ 命令。

七层架构骨架完备，Credibility Flywheel 各环基线就位，架构债务已清理。
当前处于**从内部原型走向外部验证**的转折点。

Linear 状态：170 Done / 16 Canceled / 0 Open。

---

## 接下来要做什么

按优先级排列。每项启动前应创建 Linear issue 并回填到本表。

### Milestone 1: 外部用户端到端验证

**为什么是第一优先级**：内部 dogfood 已证明系统可以跑通，但从未在真实外部用户的项目上验证过。产品假设需要真实数据支撑。

| 任务 | 说明 | Linear |
|------|------|--------|
| 选定 1~2 个外部项目 | 非 spec-orch 自身的中型 Python/TS 项目 | — |
| 端到端 run 记录 | `init → run → gate → PR → review → merge` 全链路 | — |
| 收集反馈并归档 | 用户体验痛点、报错、fallback 路径质量 | — |
| Daemon + MiniMax 全链路实测 | 低成本模型下 daemon 模式自动执行验证 | — |

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

### Milestone 4: 深化已有基线

以下能力已有基线实现，后续需深化为生产级：

| 方向 | 当前状态 | 深化目标 |
|------|----------|----------|
| Reaction Engine | 内置 3 个 reaction + daemon 集成 | 用户自定义 recipe、更多内置 reaction |
| Skill Runtime | SkillEvolver 自动发现 + ContextAssembler 自动注入 | Repo-level registry、Skill→Policy 蒸馏、execute_skill 协议 |
| Memory System | 4 层记忆 + compaction + TTL + run consolidation | 向量检索、cross-repo 知识共享 |
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
