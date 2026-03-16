# 需求规格：Spec 发现路径 — 模板库与示例反推

> **Change**: 05-spec-discovery-paths | **依赖**: 无

## 1. 模板库（SON-101）

| 需求 | 描述 |
|------|------|
| **R1.1** CLI 参数 | `mission create <title> --template <mission_id>`。 |
| **R1.2** 模板来源 | 从 `MissionService.get_mission(template_id)` 读取，即 `docs/specs/<mission_id>/spec.md`。 |
| **R1.3** 复制逻辑 | 复制 spec 的 section 结构（Goal、Scope、AC、Constraints、Interface Contracts）；主标题替换为 `<title>`。 |
| **R1.4** 占位符 | 模板中的具体内容可保留为「参考」，或替换为占位符 `<!-- describe -->`；实现可选择，需文档说明。 |
| **R1.5** 模板不存在 | `template_id` 对应 mission 不存在时，报错并退出，提示可用 `mission list` 查看。 |

## 2. 示例反推（SON-104）

| 需求 | 描述 |
|------|------|
| **R2.1** 本地文件 | `mission create <title> --from-example <path>`：读取本地文件内容，支持 `.json`、`.md`、`.txt`。 |
| **R2.2** JSON 解析 | 若为 JSON（如 Issue fixture），提取 `summary`、`builder_prompt`、`acceptance_criteria` 等字段作为反推输入。 |
| **R2.3** URL | `mission create <title> --from-url <url>`：拉取 URL 内容；支持 GitHub Issue API、Raw Markdown 等。 |
| **R2.4** 反推输出 | LLM 输出结构化 spec，包含 Goal、Scope、Acceptance Criteria、Constraints；格式与现有 spec.md 一致。 |
| **R2.5** 反推失败 | LLM 不可用或超时时，降级为空白骨架，记录 warning。 |
| **R2.6** 文件/URL 不存在 | 明确报错，不创建 mission。 |

## 3. 参数互斥与优先级

| 需求 | 描述 |
|------|------|
| **R3.1** 互斥 | `--template`、`--from-example`、`--from-url` 最多指定一个。 |
| **R3.2** 冲突处理 | 若指定多个，报错并提示正确用法。 |
| **R3.3** 默认行为 | 无上述参数时，与现有 `mission create` 一致：创建空白骨架。 |

## 4. MissionService 接口

| 需求 | 描述 |
|------|------|
| **R4.1** create_mission_from_template | `create_mission_from_template(title, template_id, mission_id=None) -> Mission`。 |
| **R4.2** create_mission_from_example | `create_mission_from_example(title, example_content: str, mission_id=None) -> Mission`。 |
| **R4.3** 复用 create_mission | 内部复用 `create_mission` 的目录创建、meta 写入；仅 spec 内容来源不同。 |

## 5. 反推服务

| 需求 | 描述 |
|------|------|
| **R5.1** 模块 | 新增 `spec_reverse_engineer.py` 或置于 `mission_service` 内；封装 LLM 调用。 |
| **R5.2** 输入 | 接收 `content: str`、`title: str`；可选 `content_type: str`（json/markdown/text）以优化 prompt。 |
| **R5.3** 输出 | 返回完整 spec 文本（Markdown），可直接写入 `spec.md`。 |
| **R5.4** LLM 配置 | 复用现有 `LiteLLMPlannerAdapter` 或等价配置，不引入新依赖。 |

## 6. 边界场景

| 场景 | 处理策略 |
|------|----------|
| **S6.1** 模板 spec 为空 | 视为无效模板，报错。 |
| **S6.2** 示例内容过长 | 截断至合理长度（如 8K tokens）后反推，记录 truncation。 |
| **S6.3** URL 需要认证 | 首版不支持；报错提示使用 `--from-example` 配合本地导出。 |
