# PRD: 灵活编排 — Gate 动态检查与多格式导入

> **Linear**: SON-103, SON-105 | **Change**: 06-flexible-orchestration | **依赖**: 无

## 背景

sdd-landscape-and-positioning 指出：DMA 流程检查应改用 Skill/Hook 而非硬编码；同时 spec-orch 应兼容行业标准格式（Spec Kit、Kiro EARS、Tessl、BDD），而非自创格式。

当前 Gate 的 pre-checks（spec_exists、spec_approved、builder、verification 等）全部硬编码在 `GateService.evaluate()` 中，每新增一个条件需改代码。Compliance 规则虽已 YAML 化，但 Gate 条件本身仍为固定枚举。行业玩家（Spec Kit、Kiro、Tessl）各有其 spec 格式，用户若从这些工具迁移或协作，需手动转换。

## 问题

1. **Gate 条件硬编码**：`ALL_KNOWN_CONDITIONS` 与 `evaluate()` 中的 if 分支一一对应，扩展需改代码、发版。
2. **无 Skill 驱动**：sdd 建议将 pipeline 步骤描述为 Skill，用 Conductor 编排；Gate 检查尚未采用此模式。
3. **格式孤岛**：spec-orch 仅支持自有 Markdown spec，无法直接导入 Spec Kit（.specify/）、Kiro EARS、Tessl、BDD 等格式。
4. **协作成本高**：与使用 Kiro、Spec Kit 的团队协作时，需人工翻译 spec。

## 目标

- **SON-103**：Gate pre-checks 从硬编码改为 Skill 描述 + LLM 编排；新增条件可通过 Skill 注册，无需改 GateService 代码。
- **SON-105**：支持导入 Spec Kit、Kiro EARS、Tessl、BDD 等格式，转换为 spec-orch 的 `spec.md` 结构。
- 保持现有 Gate 行为兼容：默认条件下，行为与当前一致。

## 非目标

- 不替换 Gate 的评估逻辑核心；仅将「条件枚举」改为「可扩展的 Skill 注册」。
- 不实现完整的 Tessl Spec Registry 集成；仅支持「导入单文件/目录并转换」。
- 不改变 ComplianceEngine 的 YAML 契约机制；Gate 与 Compliance 为不同层次。

## 用户场景

### 场景 1：Skill 驱动的 Gate 检查

用户新增一个 Skill `gate-check-security-scan`，描述为「检查是否有安全扫描通过记录」。Gate 在评估时，通过 Skill 描述发现该检查，调用对应实现（或 LLM 编排），将结果纳入 gate 条件。无需修改 `gate_service.py`。

### 场景 2：导入 Spec Kit spec

用户执行 `spec import --format spec-kit --path .specify/`。系统读取 `spec.md`、`plan.md` 等，转换为 spec-orch 的 Goal、Scope、AC 结构，输出到 `docs/specs/<mission_id>/spec.md`。

### 场景 3：导入 EARS 需求

用户执行 `spec import --format ears --path requirements.ears.md`。系统解析 EARS 句式（WHEN...THE SYSTEM SHALL...），转换为 Acceptance Criteria 列表。

### 场景 4：导入 BDD feature

用户执行 `spec import --format bdd --path features/login.feature`。系统解析 Gherkin，转换为 spec 的 AC 与场景描述。

## 成功指标

- Gate 支持通过 Skill 注册新条件，`gate.policy.yaml` 可引用 Skill 名作为条件。
- 至少支持 Spec Kit、EARS 两种格式的导入；BDD、Tessl 可为首版可选。
- 导入后的 spec 可被 MissionService、RunController 正常消费。
- 默认配置下，Gate 行为与当前完全一致，无回归。

## 风险

- **Skill 与 Gate 的契约**：Skill 描述需明确「如何判断 pass/fail」，避免模糊。缓解：Skill 输出结构化结果（passed: bool, reason: str）。
- **格式转换损失**：不同格式语义不同，转换可能丢失信息。缓解：转换后保留原始引用，支持人工校对。
- **LLM 编排延迟**：若 Gate 每次评估都调 LLM 选检查，可能变慢。缓解：Skill 注册时预解析，LLM 仅用于「条件组合逻辑」等复杂场景。
