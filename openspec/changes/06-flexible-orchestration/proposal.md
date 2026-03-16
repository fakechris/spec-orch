# 变更提案：灵活编排 — Gate 动态检查与多格式导入

> **Change**: 06-flexible-orchestration | **源 Issue**: SON-103, SON-105

## 为何要做

sdd-landscape-and-positioning 明确建议：DMA 流程检查改用 Skill/Hook 而非硬编码；与行业方案兼容（Spec Kit、Kiro、Tessl）而非自创格式。当前 Gate 与 spec 格式均不符合此方向。实现本 change 可：

- 使 Gate 可扩展，新增检查无需改代码
- 降低与 Kiro、Spec Kit 用户的协作成本
- 为「pipeline 步骤描述为 Skill」的长期目标铺路

## 变更内容

1. **Gate 动态检查（SON-103）**  
   - 定义 `GateCheckSkill` 协议：Skill 提供 `id`、`description`、`run(gate_input) -> CheckResult`。  
   - `GateService` 支持从 Skill 注册表加载条件，替代部分硬编码；内置条件（spec_exists、builder 等）保留为默认 Skill 实现。  
   - `gate.policy.yaml` 的 `conditions` 可引用 Skill id；若为内置名则走原有逻辑，若为 Skill id 则调用 Skill。  
   - 可选：LLM 编排「在给定 context 下应执行哪些检查」，用于复杂策略；首版可仅实现 Skill 注册，LLM 编排为后续。

2. **多格式导入（SON-105）**  
   - 新增 `spec import --format <format> --path <path>` CLI。  
   - 支持格式：`spec-kit`（.specify/ 目录）、`ears`（EARS 句式 Markdown）、`bdd`（Gherkin .feature）、`tessl`（若格式公开）。  
   - 每种格式有对应 Parser，输出统一 `SpecStructure`（Goal、Scope、AC、Constraints 等）。  
   - 导入后调用 `MissionService.create_mission_from_structure()` 或等价，写入 `docs/specs/`。

3. **SpecStructure 统一模型**  
   - 定义 `SpecStructure` dataclass：`goal: str`、`scope: str`、`acceptance_criteria: list[str]`、`constraints: list[str]`、`raw_sections: dict`。  
   - 各 Parser 输出 `SpecStructure`；`MissionService` 接收并序列化为 spec.md。

4. **与 ComplianceEngine 的关系**  
   - Gate 的「compliance」条件继续由 ComplianceEngine 评估；本 change 不修改 ComplianceEngine。  
   - Gate 的「可扩展条件」与 Compliance 的「契约」为不同概念：前者是 gate 通过条件，后者是 builder 输出合规。

## 不做（Out of Scope）

- 实现完整的 LLM 编排（首版 Skill 为同步调用，无 LLM 选检查）。
- Tessl Spec Registry 的远程拉取。
- 导出为 Spec Kit/EARS 格式（仅导入）。

## 影响范围

| 模块 | 影响 |
|------|------|
| `gate_service.py` | 重构：条件评估从硬编码改为「内置 + Skill 注册」 |
| 新增 | `gate_skill_protocol.py`、`gate_builtin_skills.py` |
| 新增 | `spec_import/` 或 `spec_parsers/`：各格式 Parser |
| `mission_service.py` | 新增 `create_mission_from_structure(spec_structure)` |
| `cli.py` | 新增 `spec import` 命令 |
| 配置 | `gate.policy.yaml` 扩展：conditions 可引用 Skill |
