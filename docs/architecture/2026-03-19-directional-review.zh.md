# SpecOrch 方向性深度拷问：我们对了吗？

> 日期: 2026-03-19
> 基于: 10 篇前沿 AI 工程化文献 + 项目现状交叉审视
> 前置: [七层架构](seven-planes.md) / [全局状态盘点](../plans/2026-03-18-overall-status-and-roadmap.md)
> English version: [English](2026-03-19-directional-review.md)

---

## 参考文献索引

| # | 文章 | 作者 | 核心主张 |
|---|------|------|---------|
| 1 | The Machine that Builds the Machine | Dan McAteer | 300 行工作流文件 + Symphony 编排 = 36 小时 / 26 任务 / 27 PR |
| 2 | The Intention Layer | Simon Taylor | 注意力经济 → 意图经济，agent 需要原生支付协议 |
| 3 | The Anatomy of an Agent Harness | Viv | Agent = Model + Harness，同一模型改 harness 从 Top 30 到 Top 5 |
| 4 | Harness Engineering: Same Old Story | marv1nnnnn | Harness 每季度缩小，真正杠杆是代码可验证性 |
| 5 | A Sufficiently Detailed Spec Is Code | Gabrielle Miller | 足够详细的 spec 本质上就是代码，Garbage in / Garbage out |
| 6 | 5 Agent Skill Design Patterns (ADK) | — | Tool Wrapper / Generator / Reviewer / Inversion / Pipeline 五种模式 |
| 7 | Why Your AI Agent Skills Rot | — | 路由混淆 / 模型漂移 / 基准腐化三大失效模式，监控 > 优化 |
| 8 | The Spec Is the New Code (SDD Guide) | — | SDD 四步法，MercadoLibre 向 20,000 名开发者推广 |
| 9 | The Harness Is Everything | — | ACI 设计带来 64% 性能提升，上下文窗口是整个工作意识 |
| 10 | Claude + Obsidian Memory Stack | — | 三层记忆架构（Session / Knowledge Graph / Ingestion），记忆是注意力的操作系统 |

---

## 一、四个信号的收束

10 篇文章收束为四个彼此冲突的信号：

**信号 A — Harness 是一切（乐观派）**

文献 3/9/1 都在说：harness 优化能产生巨大回报。同一个 Opus 4.6 仅改 harness
就从 Terminal Bench Top 30 跃升到 Top 5。McAteer 的 300 行工作流文件是他整个
系统的核心资产。ACI 设计带来 64% 相对性能提升。

**信号 B — Harness 正在消亡（怀疑派）**

文献 4 直接挑战上述观点：Pi 用最小 harness（无 sub-agent、无 plan mode、无 MCP）
就能交付真实软件。核心等式：agent = model + harness → harness shrinks → agent ≈ model。
所有花哨组件都在做同一件事——给 agent 一个明确的正确/错误信号。

**信号 C — Spec 是新代码（建设派）**

文献 8/1 认为 SDD 是正道。MercadoLibre 向 2 万开发者推广 SDD。McAteer 说结果定义
能力 > 编码能力。GitHub Spec Kit 77k stars。

**信号 D — Spec 就是代码（解构派）**

文献 5 是对 SDD 最尖锐的批评。足够详细的 spec 在认知负荷上与代码无异。
YAML 这种极其详细的 spec，大多数实现仍不完全符合。Flakiness + Slop 是两个硬伤。

---

## 二、四个根本性张力

### 张力 1：七层太重了吗？

**问题**: 我们有 Contract / Task / Harness / Execution / Evidence / Control / Evolution
七个平面和 65+ 命令。文献 4 说 Pi（最小 harness）已能交付软件。

**拷问**:
- 七层中哪些在模型变强后会被吃掉？
- 如果单次准确率从 60% 提升到 95%，Gate/Evidence/Evolution 是否还有价值？

**判断**: Gate 和 Evidence 不会被吃掉。模型变强解决"单次执行正确性"，但不解决
"证明给人看"和"组织级治理"。即使 agent 每次都对，你仍然需要：

- 合规审计追踪（Evidence 层本质价值）
- 人类验收的结构化界面（Control 层本质价值）
- 策略沉淀和进化（Evolution 层本质价值）

**但 Task 和 Harness 平面的大量复杂性确实可能被模型能力吃掉。**

**方向调整**: 把七层简化为"骨架三层"：

```text
Contract（意图冻结）──→ Execution（隔离执行）──→ Evidence（证明完成）
```

Task / Harness / Control / Evolution 视为三层的增强模块，可选加载而非必须路径。

---

### 张力 2：Spec 的粒度甜蜜点

**问题**: 文献 8 说 spec 是核心。文献 5 说写到够细就是代码。文献 1 说
他的 300 行工作流文件是"写给 AI 的系统提示"。

**拷问**:
- spec 应该详细到什么程度？
- Spec freeze 后的 spec 是给 AI 读还是给人读？

**现实检验**: McAteer 实际写的不是传统规范，而是"可执行意图 + 验收标准 + 约束"。
这恰好避开了 Miller 的批评——不需要精确到每一行代码，只需定义
"做什么、怎样算对、什么不能做"。

**方向调整**: Spec 定位为 **IAC（Intent + Acceptance + Constraints）**：

| 组成 | 内容 | 格式 |
|------|------|------|
| Intent | 用一段话描述要达成什么 | 自然语言 |
| Acceptance | 验收标准 | Given/When/Then（可直接转测试） |
| Constraints | 不能做什么、必须遵守什么 | 列表 |

不追求"精确到可替代代码"。

---

### 张力 3：写死的太多，LLM 决策的太少

**问题**: 项目探测中 Python 用 mypy / pytest / pip 是写死的。流程三选一
（Full/Standard/Hotfix）也是写死的。

**来自文献的指引**:
- 文献 9：Harness 定义认知架构。写死 = 确定性轨道 = 可预测
- 文献 4：所有组件都在做一件事——给 agent 明确的正确/错误信号
- 文献 6 Pipeline 模式：门控是硬性的，步骤内容是灵活的
- 文献 1 实践：流程拓扑硬编码，流程内容 LLM 生成

**方向调整 — 重新定义"骨架硬、肌肉软"的边界**:

**硬编码（骨架）**:
- Pipeline 拓扑（步骤顺序和依赖关系）
- Gate 条件评估逻辑
- Artifact 格式契约（JSON schema）
- 安全护栏（不能删 main、不能 force push）

**LLM 驱动（肌肉）**:
- 项目检测（读项目结构后判断，不是写死 Python/Node 规则）
- 验证命令推断（看项目配置后推荐，不是写死 pytest）
- Spec 生成和补全
- 任务拆分粒度
- Review 关注点
- 进化方向建议

**混合态（关节）**:
- 流程选择：骨架提供候选，LLM 推荐，人确认
- 工具链推断：LLM 推断，用户 confirm 后写入配置，下次不再推断

---

### 张力 4：Skill 退化 vs Skill 缺失

**问题**: 文献 7 警告 skill 会静默退化。但我们连 skill 子系统都还没有。

**来自文献的指引**:
- 文献 6：skill 是结构化的工作方法，不是 prompt 片段
- 文献 7：监控 > 优化。路由审计 / 模型金丝雀 / 评判模型
- 文献 10：记忆是注意力的操作系统

**方向调整**:
- Skill 层暂缓。先把 ContextAssembler 接通所有 LLM 节点
- 当前的 prompt / policy / evolver 已经是 "proto-skills"，不需另起炉灶
- 建 skill 之前先建 skill 退化检测——这是文献 7 的核心教训

---

## 三、结论性判断

### 方向对了吗？

**大方向对了，但复杂度超标了。**

核心理念（spec-first + gate-first + evidence-driven + evolution）在 10 篇文献中
都得到了验证。文献 8、1、9 都在说同一件事：结构化意图 + 确定性轨道 + 可验证输出。

但我们正在犯一个经典错误：**在产品被验证之前就把架构做得太重**。七层、65+ 命令、
12 个 LLM 节点、6 个 Evolver——这是企业级设计，但我们连一个外部用户的完整闭环
都没跑通。

### 三个最关键的调整

1. **收缩核心环路**：MVP 核心环路 = `Spec（IAC）→ Execute（隔离）→ Verify（gate + evidence）`。其他层是增强模块。
2. **LLM 化关键决策点**：项目检测、工具链推断、验证命令推荐全部改为 LLM 推断 + 人类确认。当前 project_detector 规则逻辑降级为 fallback。
3. **上下文治理优先于一切**：Phase 13（ContextAssembler 全面接入）是真正的 P0。比 skill 体系、dashboard 增强、A2A 协议都重要。文献 9 说得最清楚：上下文窗口不是 RAM，是整个工作意识。

---

## 四、行动排序

| 优先级 | 方向 | 理由 |
|--------|------|------|
| P0 | ContextAssembler 接入所有 LLM 节点 | Harness 核心价值在上下文治理 |
| P0 | 项目检测改为 LLM 推断 + fallback | 解决"写死太多"的根本问题 |
| P1 | Spec 格式标准化为 IAC | 避免"spec 太详细 = 代码"的陷阱 |
| P1 | 外部用户端到端闭环验证 | 验证产品假设 |
| P2 | Run trace + eval harness | 性能跃迁靠 trace 驱动 |
| P2 | Skill 退化检测 | 先检测再建设 |
| P3 | Skill 体系 | 等 Context 和 IAC 稳定后再建 |
| P3 | Dashboard / Control Tower | 等核心环路稳定后再做 UX |

---

## 五、与现有路线图的关系

本文不替代 [全局路线图](../plans/2026-03-18-overall-status-and-roadmap.md)，
而是在其上层补充方向性约束：

- Phase 13（ContextAssembler 全面接入）**确认为最高优先级**，与现有路线图一致
- **新增**：项目检测 LLM 化（当前 project_detector 的写死逻辑降级为 fallback）
- **新增**：Spec 格式标准化为 IAC（Intent + Acceptance + Constraints）
- **降级**：Skill 体系建设从 P1 降到 P3，先做上下文治理
- **降级**：Dashboard / Control Tower 从 P2 降到 P3，先跑通核心环路

---

## 六、执行状态快照（2026-03-19）

本节用于跟踪上文方向性调整是否已真正落地到代码与执行系统（Linear）。

### 6.1 与「更早路线图」的关系（避免误读）

| 文档 | 角色 | 是否被 3/19 替代？ |
|------|------|-------------------|
| [全局状态与路线图（2026-03-18）](../plans/2026-03-18-overall-status-and-roadmap.md) | Phase 13~16、Gap 清单、执行顺序 | **不替代**。3/19 是在其上的**方向性约束**（收缩范围、CEO 飞轮、优先级重排）。 |
| [上下文治理 / Context Contract（2026-03-17）](context-contract-design.md) | 12 节点 context、分 Phase 改造 | **不替代**。其中 **Phase 0~1（Assembler + 节点接入 + manifest）** 已与 Phase 13 / `SON-174` 主线对齐并大体落地；**Phase 2~3（进化管线案例化、统一 lifecycle、全自动触发）** 仍为深度待办。 |
| [System Design v0](spec-orch-system-design-v0.md) | 2026-03-07 初版系统设计 | **历史文档**，权威架构以 pipeline / 现行代码为准。口语中的「v0.6 方向」多指 **上下文治理 + Phase 13** 这条线，而非该 v0 文件的版本号。 |

**结论**：**最新战略叙述以本文（3/19）+ CEO Credibility Flywheel 为准**；但 **§四「行动排序」里的每一项并不等于都已做完**——下表单独列出**仍未完成或仅部分完成**的方向性条目。

### 6.2 方向性落地表（已完成项）

| 方向项 | 状态 | 证据 |
|--------|------|------|
| 项目检测改为 LLM 优先 + rules fallback | ✅ 已完成 | Linear Epic `SON-175` 与 `SON-181~184` 已完成 |
| Spec 格式标准化为 IAC | ✅ 已完成 | Linear Epic `SON-176` 与 `SON-185~188` 已完成 |
| ContextAssembler 全面接入所有 LLM 节点 | ✅ 已完成 | Linear Epic `SON-174`，`SON-177~180` 已通过 PR `#85~87` 合并 |
| 统一 Run Artifact Schema（P1 基线） | ✅ 已完成 | `SON-194`~`SON-200` 已合入；`run_artifact/*` 为权威源，`artifact_manifest.json` 为兼容桥 |
| Reaction Engine（P2）基线 | ✅ 已完成 | 规则、`get_pr_signal`、daemon 闭环、`params` / `requeue_ready`、`.spec_orch/reactions_trace.jsonl` 等已合入（如 PR `#95`/`#96`）；与 **Harness 级 eval** 仍不同，见 6.3 |
| README / 用户侧 init 文档与新行为同步 | ✅ 已完成 | `README.md` / `README.zh.md` 已补 `--offline`、`--reconfigure` |
| 飞轮后续路线（P1/P2/P5/P6/P4-format）是否已映射到 Linear Epic | ✅ 已完成 | 规划类 Epic `SON-189~193` 已创建并打上 `epic` 标签 |

### 6.3 方向性未完成 / 仅部分完成（对照 §四行动排序与 CEO 范围）

以下与 **「3/19 表格里全是 ✅」** 不是一回事——战略上已选定，**工程上仍待交付**：

| 来源 | 方向 | 状态 | 说明 |
|------|------|------|------|
| §四 P1 | **外部用户端到端闭环验证** | ❌ 未做 | 产品假设验证；与内部 dogfood 不同 |
| §四 P2 | **Run trace + eval harness** | ✅ 基线完成 | `EvalRunner` + `spec-orch eval` CLI 已合入（PR `#99`，`SON-202`） |
| §四 P2 | **Skill 退化检测** | ❌ 未做 | 文献 7：监控先于建设；尚未独立成体系 |
| §四 P3 | **Skill 体系** | ✅ P4 格式完成 | `SkillManifest` schema + loader 已合入（PR `#100`，`SON-203`）；运行时仍延后 |
| §四 P3 | **Dashboard / Control Tower** | ✅ 基线完成 | Control Tower API 已合入（PR `#101`，`SON-204`） |
| CEO 飞轮 | **P4 Skill Format Definition（仅格式）** | ✅ 已完成 | PR `#100`，**SON-192** Done |
| CEO 飞轮 | **P5 Control Tower UI** | ✅ 已完成 | PR `#101`，**SON-193** Done |
| CEO 飞轮 | **P6 Harness Evals** | ✅ 已完成 | PR `#99`，**SON-190** Done |
| [context-contract-design](context-contract-design.md) | **Phase 2~3（进化案例化、统一 lifecycle、全自动触发）** | ✅ 已完成 | PR #106~#110：LifecycleEvolver protocol、ContextAssembler 全面接入、案例驱动改造、EvolutionPolicy engine |
| [全局路线图 Phase 14+](../plans/2026-03-18-overall-status-and-roadmap.md) | **Daemon 生产健壮性、Hotfix、冲突解决等** | 🟡 部分 | 如 **SON-46** 等仍在 Backlog |

**「七层 → 骨架三层」**：属架构叙事与渐进简化，**不是**单一可勾选工单；随 Control 面与文档收敛逐步体现。

### 6.4 当前整体结论与建议优先级（2026-03-23 更新）

1. **大方向**：3/19 与 CEO 文档定义的 **Credibility Flywheel + SELECTIVE_EXPANSION** 仍是主线。
2. **CEO 飞轮 P0→P6 全部基线落地**：P0 Context Contract ✅ → P1 Unified Artifact ✅ → P2 Reaction Engine ✅ → P4 Skill Format ✅ → P5 Control Tower ✅ → P6 Harness Evals ✅（PR `#99~101`）。
3. **剩余缺口**：**外部用户端到端验证**、**Skill 退化检测**、**context-contract Phase 2~3 深度**、**Phase 14 生产级 Daemon（SON-46）**。
4. **建议下一批优先级**：(a) **外部验证**（从 dogfood 到真实用户）；(b) **SON-46 daemon 健壮性**（无人值守前提）；(c) **Skill 退化检测**（监控优先）。

### CEO Review 同步（2026-03-19）

信息来源：
`~/.gstack/projects/fakechris-spec-orch/ceo-plans/2026-03-19-credibility-flywheel.md`

CEO 文档确认当前路线为 `SELECTIVE_EXPANSION` 模式下的 **Credibility Flywheel**。

已接受范围：

- P0：Context Contract 全量接入（`SON-174` / `SON-177~180`）
- P1：统一 Run Artifact Schema
- P2：Reaction Engine
- P5：Control Tower UI
- P6：Harness Evals
- P4（部分）：Skill Format Definition（不包含完整 Runtime）

明确延后 / 跳过：

- Preview interface abstraction
- Sandbox abstraction
- Full Skill Runtime
- 在 P0/P1 稳定前的大规模外部 beta 扩张

执行含义：

1. 保持选择性扩展：先完成 Context Governance（`SON-174`、`SON-177~180`），再进入飞轮后续阶段。
2. 规划 Epic 必须对齐 P0/P1/P2/P5/P6 与 P4-format-only，不新增未获批主线。
3. 把 P0->P1->P6 视为持续闭环，而非一次性串行阶段。
