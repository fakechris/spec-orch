# 任务清单：灵活编排 — Gate 动态检查与多格式导入

> **Change**: 06-flexible-orchestration | **依赖 design.md**：本变更涉及跨模块架构（Gate 重构、格式解析、SpecStructure）、合规/门禁职责分离，故需 design.md 指导实现。见 `design.md`。

## 前置

- [ ] 无强依赖；可与 Change 04、05 并行。

## 实现任务

### 1. Gate 动态检查（SON-103）

- [ ] 定义 `GateCheckSkill` 协议与 `CheckResult`（见 design §2.1）。
- [ ] 实现 `GateSkillRegistry`，支持 builtin + custom 注册。
- [ ] 将现有 `evaluate()` 中每个条件提取为 `BuiltinGateCheckSkill` 实现（见 design §2.2）。
- [ ] 重构 `GateService.evaluate()`：遍历 conditions，从 registry 获取 Skill 并调用（见 design §2.3）。
- [ ] 扩展 `gate.policy.yaml` 解析：支持 `skill:<id>` 格式。
- [ ] 实现 Skill 从 `$CODEX_HOME/skills` 或项目 `skills/` 的加载逻辑（可选，首版可仅内置）。
- [ ] 单元测试：所有现有 Gate 测试通过；新增「自定义 Skill 注册并评估」测试。

### 2. 多格式导入（SON-105）

- [ ] 定义 `SpecStructure` 与 `SpecParser` 协议（见 design §3.1、§3.2）。
- [ ] 实现 `SpecKitParser`：解析 `.specify/spec.md`、`plan.md`。
- [ ] 实现 `EarsParser`：解析 EARS 句式，输出 SpecStructure。
- [ ] 实现 `BddParser`：解析 Gherkin .feature 文件。
- [ ] `MissionService.create_mission_from_structure(title, spec_structure, mission_id=None)`。
- [ ] CLI `spec import --format <format> --path <path> [--mission-id <id>] [--dry-run]`。
- [ ] 单元测试：各 Parser 对 fixture 文件解析正确；导入后 mission 可被 get_mission 读取。

### 3. 集成与文档

- [ ] 更新 `gate list-conditions`：可列出 Skill 注册的条件。
- [ ] 更新 README 或 docs：`spec import` 用法、支持格式、示例。
- [ ] 确保 ComplianceEngine 与 Gate 的 `compliance` 条件协作正确（见 design §4）。

## 验收

- [ ] 满足 spec.md 中 R1–R5、S5.1–S5.4。
- [ ] 满足 design.md 中的架构与模块布局。
- [ ] 现有 Gate 与 mission 相关测试全部通过。
- [ ] `spec import --format spec-kit --path .specify/` 可手动验证（需 fixture）。
- [ ] 无新增 linter 错误。
