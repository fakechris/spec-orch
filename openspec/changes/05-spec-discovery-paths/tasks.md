# 任务清单：Spec 发现路径 — 模板库与示例反推

> **Change**: 05-spec-discovery-paths | **无 design.md**：本变更为增量功能添加（模板复制、示例反推），不涉及跨模块架构重构、新协议、格式解析或合规引擎重组。MissionService 与 CLI 的扩展为线性叠加，故跳过 design 阶段。详见文末说明。

## 前置

- [ ] 无强依赖；可与 Change 04、06 并行。

## 实现任务

### 1. 模板库（SON-101）

- [ ] `MissionService.create_mission_from_template(title, template_id, mission_id=None)`：读取模板 spec，复制结构，创建新 mission。
- [ ] CLI `mission create` 增加 `--template` 参数，解析后调用 `create_mission_from_template`。
- [ ] 模板不存在时抛出 `FileNotFoundError` 或等价，CLI 捕获并友好提示。
- [ ] 单元测试：从 self-evolution 模板创建新 mission，验证 spec 结构正确。

### 2. 示例反推（SON-104）

- [ ] 新增 `spec_reverse_engineer.py`（或 `mission_service` 内方法）：`reverse_engineer_spec(content: str, title: str) -> str`。
- [ ] 反推 prompt：输入 content + title，输出 Goal、Scope、AC、Constraints 的 Markdown。
- [ ] 复用 `LiteLLMPlannerAdapter` 或现有 LLM 配置。
- [ ] `MissionService.create_mission_from_example(title, example_content, mission_id=None)`：调用反推，写入 spec。
- [ ] CLI `mission create` 增加 `--from-example <path>`：读取文件，解析 JSON/MD/TXT，调用 `create_mission_from_example`。
- [ ] CLI `mission create` 增加 `--from-url <url>`：拉取 URL 内容（requests 或 httpx），调用反推。
- [ ] 单元测试：mock LLM，验证反推输出格式正确。
- [ ] 单元测试：`--from-example` 指向不存在的文件时报错。

### 3. 参数互斥与默认行为

- [ ] 校验 `--template`、`--from-example`、`--from-url` 互斥；冲突时报错。
- [ ] 无上述参数时，调用原有 `create_mission`，行为不变。

### 4. 文档与配置

- [ ] 更新 CLI help：`mission create --help` 展示新参数及示例。
- [ ] 可选：反推 prompt 模板可配置路径。

## 验收

- [ ] 满足 spec.md 中 R1–R6、S6.1–S6.3。
- [ ] `mission create "Test" --template self-evolution` 可手动验证。
- [ ] `mission create "Test" --from-example fixtures/issues/SPC-P0-1.json` 可手动验证（需 LLM 可用）。
- [ ] 无新增 linter 错误，现有测试通过。

## 设计说明（为何无 design.md）

本变更包含两项独立、增量的功能：1）模板复制 — 读取已有 spec 并复制结构；2）示例反推 — LLM 将参考内容转为 spec。两者均为 MissionService 与 CLI 的线性扩展，不涉及新模块拓扑、格式解析协议或合规引擎重组。实现路径清晰，spec + tasks 即可指导开发，无需单独 design 文档。
