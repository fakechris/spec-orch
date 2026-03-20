# Roadmap v2 — 按 Seven Planes 组织

> 制定于 2026-03-18，基于 v0.5.0 现状和战略分析。
> 最近更新于 2026-03-20。
> 参见 [Seven Planes 架构映射](../architecture/seven-planes.md)

---

## 当前状态总结

spec-orch v0.5.1 已完成：
- 7 个 Plane 全部有代码覆盖，其中 Contract / Task / Execution / Evolution 相对成熟
- ACPX 统一 adapter 层支持 15+ agents
- 项目 Profile 架构（`spec-orch init` + 可配置验证命令 + 可配置 issue 源）
- **Agent-First Decision Architecture**：LLM-driven 项目分析（Smart Init）、动态验证步骤、Config Evolver
- EODF 闭环自验证
- 架构债务清理：原子写入 / Evolver 协议对齐 / CLI 模块化 / LLM JSON 验证 / 跨平台文件锁
- 1176+ 单元测试

核心判断：**骨架已搭好，Agent-First 决策层已落地，架构债务已清理，飞轮各环均有基线实现。**

---

## 飞轮完成状态（Milestone Tracker）

> 本节持续更新，跟踪每个优先级轨道的完成状态和 Linear 映射。

| 优先级 | Plane | 主题 | 状态 | Linear | 关键 PR |
|--------|-------|------|------|--------|---------|
| **P0** | Harness | Context Contract 全面接入 | ✅ 完成 | SON-174, SON-177~180 | #56~#60 |
| **P1** | Evidence | Run Artifact 统一 | ✅ 完成 | SON-189, SON-194~200 | #95~#98 |
| **P2** | Harness | Reaction Engine | ✅ 基线完成 | SON-191, SON-201 | #102 |
| **P3** | Execution | Preview & Sandbox | ⏭️ 延后 | — | — |
| **P4** | Harness+Evo | Skills / Policies（仅格式） | ✅ 格式完成 | SON-192, SON-203 | #100 |
| **P5** | Control | Control Tower UI | ✅ 基线完成 | SON-193, SON-204 | #101 |
| **P6** | Evolution | Harness Evals | ✅ 基线完成 | SON-190, SON-202 | #99 |
| — | 基础设施 | 架构债务清理 | ✅ 完成 | SON-206 | #116, #117 |
| — | 基础设施 | Agent-First 改造 (A~C) | ✅ 完成 | SON-161~166 | #85~#94 |
| — | 基础设施 | Agent 工程化 Epic A~H | ✅ 完成 | — | #112~#114 |

### Agent-First 改造详情（SON-161 ~ SON-166）

| Phase | 内容 | 状态 |
|-------|------|------|
| A | 配置外部化：gate 阈值、reviewer 参数、evolution 参数提取到 TOML | ✅ |
| B1 | Smart Init：LLM-driven 项目分析，读取文件树+配置生成最优验证命令 | ✅ |
| B2 | 动态验证步骤：VerificationSummary 支持任意步骤名（不限于 4 步） | ✅ |
| B3 | Monorepo/自定义步骤：security_scan、e2e、docker_test 等 | ✅ |
| C | Config Evolver：基于运行 evidence 建议配置更新 | ✅ |

**决策边界三层模型**：骨架（确定性）→ 配置（可外部化）→ 智能（LLM 驱动）。

---

## 下一步方向（未映射到 Linear，按优先级排列）

> 以下方向战略上已确定，但尚未创建 Linear issue 或尚未完工。
> 每次启动新工作时应先在此标注，并创建对应 Linear issue。

| 优先级 | 方向 | 说明 | Linear | 状态 |
|--------|------|------|--------|------|
| **P0** | 外部用户端到端验证 | 从内部 dogfood 到真实用户的产品假设验证 | — | ❌ 未做 |
| **P1** | Phase 15: Contract 自动化 | 自动为高风险 task 生成 Contract | — | ❌ 未做 |
| **P1** | Daemon + MiniMax 全链路实测 | 低成本自动化验证（Daemon 模式 + 自动执行） | — | ❌ 未做 |
| **P2** | Phase 16: 产品化 | TUI 稳定性、文档刷新、PyPI 发布自动化 | — | ❌ 未做 |
| **P2** | P2 深化: Reaction Engine 完善 | 用户自定义 recipe + 更多内置 reaction | — | 🟡 基线有 |
| **P2** | P4 深化: Skill Runtime | Skill loader + registry + Policy 蒸馏路径 | — | 🟡 格式有 |
| **P2** | P5 深化: Control Tower 完善 | Session-centric 视图、成本监控、移动端 | — | 🟡 基线有 |
| **P3** | P6 深化: Eval 完善 | 自动 A/B 对比、变更自动 eval、持久化查询 | — | 🟡 基线有 |
| **P3** | P3: Preview & Sandbox | Preview provider + sandbox 抽象 | — | ⏭️ 延后 |

---

## P0：Harness Plane — Context Contract 全面接入 ✅

**状态**: 完成（SON-174, SON-177~180）

**目标**：把 ContextAssembler 从"已建好但未全接"变成"每个 LLM 节点都用"。

### 关键任务

1. ✅ 所有 LLM 节点（ReadinessChecker、Planner、Scoper、IntentClassifier、Builder prompt 组装）统一走 ContextAssembler
2. ✅ 明确 context 分层顺序：project → spec → task → session → message
3. ✅ 确保 tool definitions 顺序稳定（为 prefix caching 做准备）
4. ✅ 将 prompt_history 的 active variant 注入 builder 运行时路径

---

## P1：Evidence Plane — Run Artifact 与 Observability 统一 ✅

**状态**: 完成（SON-189, SON-194~200）

**目标**：让 run artifact 成为统一产品面，而非散落文件。

### 关键任务

1. ✅ 定义统一 run artifact schema：manifest / event-stream / live-snapshot / retro / conclusion
2. ✅ EventBus 升级：支持 API + SSE 推送 + 可查询历史
3. ✅ Dashboard 消费统一 schema，替代当前的定制读取
4. ✅ 基础 run history query（JSON 文件）

---

## P2：Harness Plane — Reaction Engine ✅ 基线

**状态**: 基线完成（SON-191, SON-201）；用户自定义 recipe 待深化

**目标**：让 spec-orch 不只是"执行一次 run"，而是能持续经营 PR 生命周期。

### 关键任务

1. ✅ 定义 reaction 配置格式（YAML recipe）
2. ✅ 内置反应：ci-failed → 自动修复、changes-requested → 自动回应、approved-and-green → 自动合并
3. ✅ 与 daemon review loop 集成
4. 🟡 用户可自定义 reaction recipe

---

## P3：Execution + Evidence — Preview & Sandbox Lane ⏭️ 延后

**状态**: 延后（CEO 决策：先完成飞轮，再考虑 Preview/Sandbox）

**目标**：把 preview 从"可选门控条件"变成"真正可用的验收通道"。

### 关键任务

1. Preview provider abstraction（Vercel / Netlify / local）
2. Preview link 自动注入 Evidence Plane
3. Acceptance lane：spec checklist + preview + findings + deviation → 单一验收视图
4. 基础 sandbox 抽象（Docker container 执行）

---

## P4：Harness + Evolution — Skills / Policies Runtime 统一 ✅ 格式

**状态**: 格式定义完成（SON-192, SON-203）；Full Runtime 延后

**目标**：引入 repo-local skills 层，与现有 policy distillation 打通。

### 关键任务

1. ✅ 定义 skill 格式（instructions + scripts + resources 组合）— `SkillManifest` schema + loader
2. 🟡 Skill loader 与 progressive disclosure
3. 🟡 repo-level skill registry（`.spec-orch/skills/`）
4. 🟡 Skill → Policy 蒸馏路径：高频 skill 自动固化为 deterministic policy
5. 🟡 AGENTS.md 导入支持

---

## P5：Control Plane — Control Tower UI 升级 ✅ 基线

**状态**: 基线完成（SON-193, SON-204）；深化待做

**目标**：从"开发者状态页"升级为"运营控制塔"。

### 关键任务

1. 🟡 Session-centric 视图（除 issue 维度外增加 session 维度）
2. 🟡 Mission → Task Graph → Sessions → PRs → Gates 的层级导航
3. 🟡 成本 / token / cache-hit 监控面板
4. 🟡 卡住的 run 检测与告警
5. 🟡 移动端通知与轻审批（PWA 起步）

---

## P6：Evolution Plane — Harness Evals ✅ 基线

**状态**: 基线完成（SON-190, SON-202）；深化待做

**目标**：让进化有据可依，而非凭感觉改 prompt。

### 关键任务

1. ✅ 定义 eval 框架：固定模型 + 固定任务集 + 改 harness 变量 → 比较指标
2. ✅ 指标集：gate pass rate / rework 次数 / latency / token / cache-hit / stuck rate
3. 🟡 每次 evolver 变更自动跑 eval
4. 🟡 eval 结果持久化 + 可查询
5. 🟡 Harness 变更的 A/B 对比报告

---

## 优先级总结

| 优先级 | Plane | 主题 | 状态 |
|--------|-------|------|------|
| P0 | Harness | Context Contract 全面接入 | ✅ 完成 |
| P1 | Evidence | Run Artifact 统一 | ✅ 完成 |
| P2 | Harness | Reaction Engine | ✅ 基线 |
| P3 | Execution + Evidence | Preview & Sandbox | ⏭️ 延后 |
| P4 | Harness + Evolution | Skills / Policies | ✅ 格式 |
| P5 | Control | Control Tower UI | ✅ 基线 |
| P6 | Evolution | Harness Evals | ✅ 基线 |

---

## 不做的方向

明确排除以下方向，避免精力分散：

1. **不做 multi-agent 通信总线** — 默认 orchestrator-worker
2. **不做 graph-first workflow builder** — spec-first，不是 graph-first
3. **不做 AI IDE** — 控制面，不是编辑器
4. **不追"更聪明的 prompt"** — 先把 trace / artifacts / eval / gate 做扎实
5. **不做多个 builder 并行改同一片代码** — 一任务一隔离始终如此

---

## 变更日志

| 日期 | 变更 |
|------|------|
| 2026-03-18 | 初版 Roadmap v2，P0~P6 按 Plane 组织 |
| 2026-03-18 | Agent-First Decision Architecture 落地 |
| 2026-03-19 | CEO Credibility Flywheel 对齐；P3 延后；P4 仅格式 |
| 2026-03-20 | P0~P6 全部基线完成；架构债务清理完成；增加 Milestone Tracker + Linear 映射 |
