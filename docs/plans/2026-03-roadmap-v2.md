# Roadmap v2 — 按 Seven Planes 组织

> 制定于 2026-03-18，基于 v0.5.0 现状和战略分析。
> 参见 [Seven Planes 架构映射](../architecture/seven-planes.md)

---

## 当前状态总结

spec-orch v0.5.0 已完成：
- 7 个 Plane 全部有代码覆盖，其中 Contract / Task / Execution / Evolution 相对成熟
- ACPX 统一 adapter 层支持 15+ agents
- 项目 Profile 架构（`spec-orch init` + 可配置验证命令 + 可配置 issue 源）
- EODF 闭环自验证
- 900+ 单元测试

核心判断：**骨架已搭好，但各 Plane 之间的"最后一公里"连接未全面打通。**

---

## P0：Harness Plane 补课 — Context Contract 全面接入

**目标**：把 ContextAssembler 从"已建好但未全接"变成"每个 LLM 节点都用"。

### 关键任务

1. 所有 LLM 节点（ReadinessChecker、Planner、Scoper、IntentClassifier、Builder prompt 组装）
   统一走 ContextAssembler
2. 明确 context 分层顺序：project → spec → task → session → message
3. 确保 tool definitions 顺序稳定（为 prefix caching 做准备）
4. 将 prompt_history 的 active variant 注入 builder 运行时路径

### 依据

- 仓库自己的路线图已列为最高优先级
- context-contract-design.md 已把瓶颈和接口定义清楚
- Thariq "Prompt Caching Is Everything"：cache hit rate 要像 uptime 一样被监控

---

## P1：Evidence Plane — Run Artifact 与 Observability 统一

**目标**：让 run artifact 成为统一产品面，而非散落文件。

### 关键任务

1. 定义统一 run artifact schema：manifest / event-stream / live-snapshot / retro / conclusion
2. EventBus 升级：支持 API + SSE 推送 + 可查询历史
3. Dashboard 消费统一 schema，替代当前的定制读取
4. 基础 run history query（先 JSON 文件，后续可接 DuckDB）

### 依据

- Fabro 的 observability 文档（6 种 artifact 类型 + SQL 分析）
- LangChain："没有统一 trace，就没法做系统性改进"

---

## P2：Harness Plane — Reaction Engine

**目标**：让 spec-orch 不只是"执行一次 run"，而是能持续经营 PR 生命周期。

### 关键任务

1. 定义 reaction 配置格式（YAML recipe）
2. 内置反应：ci-failed → 自动修复、changes-requested → 自动回应、approved-and-green → 自动合并
3. 与 daemon review loop 集成
4. 用户可自定义 reaction recipe

### 依据

- Composio agent-orchestrator 的 reactions 一等对象
- Capy 的 repo config surface

---

## P3：Execution + Evidence — Preview & Sandbox Lane

**目标**：把 preview 从"可选门控条件"变成"真正可用的验收通道"。

### 关键任务

1. Preview provider abstraction（Vercel / Netlify / local）
2. Preview link 自动注入 Evidence Plane
3. Acceptance lane：spec checklist + preview + findings + deviation → 单一验收视图
4. 基础 sandbox 抽象（Docker container 执行）

### 依据

- Gate 已有 `preview` 条件，但未实际接入
- Capy：preview + diff 并排审查
- Fabro：sandbox provider + snapshot + network policy

---

## P4：Harness + Evolution — Skills / Policies Runtime 统一

**目标**：引入 repo-local skills 层，与现有 policy distillation 打通。

### 关键任务

1. 定义 skill 格式（instructions + scripts + resources 组合）
2. Skill loader 与 progressive disclosure
3. repo-level skill registry（`.spec-orch/skills/`）
4. Skill → Policy 蒸馏路径：高频 skill 自动固化为 deterministic policy
5. AGENTS.md 导入支持

### 依据

- Anthropic Skills：不是辅助 feature，是新的 context/workflow primitive
- OpenAI：repo-local skills + AGENTS.md + scripts + CI 优化后 merged PR +44%
- spec-orch 已有 policy distillation，skill 是自然上游

---

## P5：Control Plane — Control Tower UI 升级

**目标**：从"开发者状态页"升级为"运营控制塔"。

### 关键任务

1. Session-centric 视图（除 issue 维度外增加 session 维度）
2. Mission → Task Graph → Sessions → PRs → Gates 的层级导航
3. 成本 / token / cache-hit 监控面板
4. 卡住的 run 检测与告警
5. 移动端通知与轻审批（PWA 起步）

### 依据

- Lody：session-centric + 移动端 + 团队视图 + diff 审查
- Composio：fleet dashboard

---

## P6：Evolution Plane — Harness Evals

**目标**：让进化有据可依，而非凭感觉改 prompt。

### 关键任务

1. 定义 eval 框架：固定模型 + 固定任务集 + 改 harness 变量 → 比较指标
2. 指标集：gate pass rate / rework 次数 / latency / token / cache-hit / stuck rate
3. 每次 evolver 变更自动跑 eval
4. eval 结果持久化 + 可查询
5. Harness 变更的 A/B 对比报告

### 依据

- LangChain："模型不变，只改 harness"就能明显拉分
- OpenAI："prompt → captured run → checks → score"
- spec-orch 已有 gate / report / deviations / prompt history，差的是结构化 eval loop

---

## 优先级总结

| 优先级 | Plane | 主题 | 预期影响 |
|--------|-------|------|---------|
| P0 | Harness | Context Contract 全面接入 | 系统稳定性基础 |
| P1 | Evidence | Run Artifact 统一 | 可观测性 + 进化数据源 |
| P2 | Harness | Reaction Engine | PR 生命周期自动化 |
| P3 | Execution + Evidence | Preview & Sandbox | 验收体验飞跃 |
| P4 | Harness + Evolution | Skills / Policies | 工作法管理 |
| P5 | Control | Control Tower UI | 运营体验 |
| P6 | Evolution | Harness Evals | 进化可量化 |

---

## 不做的方向

明确排除以下方向，避免精力分散：

1. **不做 multi-agent 通信总线** — 默认 orchestrator-worker
2. **不做 graph-first workflow builder** — spec-first，不是 graph-first
3. **不做 AI IDE** — 控制面，不是编辑器
4. **不追"更聪明的 prompt"** — 先把 trace / artifacts / eval / gate 做扎实
5. **不做多个 builder 并行改同一片代码** — 一任务一隔离始终如此
