# 需求规格：灵活编排 — Gate 动态检查与多格式导入

> **Change**: 06-flexible-orchestration | **依赖**: 无

## 1. Gate 动态检查（SON-103）

| 需求 | 描述 |
|------|------|
| **R1.1** GateCheckSkill 协议 | 定义 `GateCheckSkill`：`id: str`、`description: str`、`run(gate_input: GateInput) -> CheckResult`。`CheckResult` 含 `passed: bool`、`reason: str`。 |
| **R1.2** 内置条件 Skill 化 | 将 spec_exists、spec_approved、builder、verification、review、compliance 等实现为内置 Skill，注册到 GateService。 |
| **R1.3** 外部 Skill 注册 | GateService 支持 `register_skill(skill: GateCheckSkill)`；`gate.policy.yaml` 的 conditions 可引用 Skill id。 |
| **R1.4** 评估逻辑 | `evaluate()` 遍历 `required_conditions`，对每个条件：若为内置名则调用对应内置 Skill，若为 Skill id 则调用注册的 Skill；汇总 failed_conditions。 |
| **R1.5** 向后兼容 | 未配置 Skill 时，行为与当前 GateService 完全一致。 |

## 2. 多格式导入（SON-105）

| 需求 | 描述 |
|------|------|
| **R2.1** CLI | `spec import --format <format> --path <path> [--mission-id <id>]`。 |
| **R2.2** SpecStructure | 统一模型：`goal`、`scope`、`acceptance_criteria`、`constraints`、`raw_sections`。 |
| **R2.3** Spec Kit 解析 | `--format spec-kit`：读取 `.specify/spec.md`、`plan.md`，提取目标、范围、任务，映射到 SpecStructure。 |
| **R2.4** EARS 解析 | `--format ears`：解析 EARS 句式（WHEN...THE SYSTEM SHALL、WHILE...、WHERE...），每条转为 AC。 |
| **R2.5** BDD 解析 | `--format bdd`：解析 Gherkin Feature/Scenario/Given-When-Then，转为 AC 与场景描述。 |
| **R2.6** Tessl 解析 | `--format tessl`：若格式公开，解析并转换；否则首版可跳过。 |
| **R2.7** 输出 | 导入后创建 mission，写入 `docs/specs/<mission_id>/spec.md`；或仅输出 SpecStructure 到 stdout（可选 `--dry-run`）。 |

## 3. MissionService 扩展

| 需求 | 描述 |
|------|------|
| **R3.1** create_mission_from_structure | `create_mission_from_structure(title, spec_structure: SpecStructure, mission_id=None) -> Mission`。 |
| **R3.2** 序列化 | 将 SpecStructure 序列化为现有 spec.md 格式（Goal、Scope、AC、Constraints 等 section）。 |

## 4. 配置与注册

| 需求 | 描述 |
|------|------|
| **R4.1** gate.policy.yaml | conditions 项可包含 `skill:<skill_id>`，如 `skill:security-scan`。 |
| **R4.2** Skill 发现 | 支持从 `$CODEX_HOME/skills` 或项目内 `skills/` 加载符合 GateCheckSkill 的 Skill。 |
| **R4.3** 内置优先 | 若条件名与内置名相同，优先走内置逻辑，保证兼容。 |

## 5. 边界场景

| 场景 | 处理策略 |
|------|----------|
| **S5.1** Skill 运行失败 | 视为该条件 failed，reason 记录异常信息。 |
| **S5.2** 未知格式 | `--format` 不支持时报错，列出支持的格式。 |
| **S5.3** 解析部分失败 | 尽可能提取有效内容，无效部分记录 warning；或整体失败（实现选择）。 |
| **S5.4** 空 spec | 导入后 spec 为空时，仍创建 mission，spec 为最小骨架。 |
