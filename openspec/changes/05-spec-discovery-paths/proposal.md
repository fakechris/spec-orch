# 变更提案：Spec 发现路径 — 模板库与示例反推

> **Change**: 05-spec-discovery-paths | **源 Issue**: SON-101, SON-104

## 为何要做

sdd-landscape-and-positioning 将「Spec 模板库」和「示例反推」列为美诺悖论化解路径 2 和 4，当前均未充分实现。实现这两条路径可：

- 降低用户写 spec 的认知负担：选模板填空比从零写容易
- 利用已有资产：`docs/specs/` 内大量 spec 可复用为模板
- 满足「我要类似这个」的常见需求：用户有参考示例时，AI 反推可快速产出初版 spec

## 变更内容

1. **模板库（SON-101）**  
   - `mission create <title> --template <mission_id>`：从 `MissionService.get_mission(template_id)` 读取 spec，复制结构到新 mission。  
   - 模板字段：Goal、Scope、Acceptance Criteria、Constraints、Interface Contracts 等 section；title 替换为 `<title>`，其余可保留或清空（可配置）。  
   - 模板来源：`docs/specs/<mission_id>/spec.md`，即已有 mission 的 spec。

2. **示例反推（SON-104）**  
   - `mission create <title> --from-example <path>`：读取本地文件（JSON、Markdown、纯文本），提取内容，调用 LLM 反推为结构化 spec。  
   - `mission create <title> --from-url <url>`：拉取 URL 内容（支持 GitHub Issue、Markdown 等），同上反推。  
   - 反推 prompt：输入为「参考示例内容 + 目标 title」，输出为 spec.md 格式（Goal、Scope、AC 等）。

3. **MissionService 扩展**  
   - `create_mission_from_template(title, template_id, ...)`：内部调用 `get_mission(template_id)`，复制 spec 结构。  
   - `create_mission_from_example(title, example_content: str, ...)`：调用 LLM 反推，写入 spec。  
   - `create_mission()` 保持原样，作为默认路径。

4. **CLI 参数**  
   - `--template`、`--from-example`、`--from-url` 互斥；若同时指定，优先级：`--template` > `--from-example` > `--from-url`，或报错（实现选择）。

5. **与 Conductor 的关系**  
   - 模板和示例反推为**独立入口**，不经过 Conductor。用户通过 CLI 直接创建；Conductor 的对话式发现仍为路径 1，三者互补。

## 不做（Out of Scope）

- 实现路径 3（翻译者）、5（渐进精化）、6（AI 自生成+人审批）的增强。
- Spec Registry 或远程模板库。
- 模板版本管理、模板审核工作流。

## 影响范围

| 模块 | 影响 |
|------|------|
| `mission_service.py` | 新增 `create_mission_from_template`、`create_mission_from_example` |
| `cli.py` | `mission create` 增加 `--template`、`--from-example`、`--from-url` |
| 新增 | `spec_reverse_engineer.py` 或类似：封装 LLM 反推逻辑 |
| 配置 | 可选：反推 prompt 模板路径、LLM 模型选择 |
