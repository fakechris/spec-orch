# PRD: Spec 发现路径 — 模板库与示例反推

> **Linear**: SON-101, SON-104 | **Change**: 05-spec-discovery-paths | **依赖**: 无

## 背景

sdd-landscape-and-positioning.md 定义了「美诺悖论」的六条化解路径，其中两条与 spec-orch 直接相关：

- **路径 2：Spec 模板库** — 选模板→填空→可执行 spec（当前 mission template 可增强）
- **路径 4：示例反推** — 「我要类似这个」→ AI 反推 spec（未实现，高价值方向）

当前 `mission create` 仅支持从空白骨架创建，用户需手动填写 Goal、Scope、Acceptance Criteria。若能从已有 spec 模板或参考示例快速生成，可显著降低「写 spec 付出的能量」。

## 问题

1. **模板不可复用**：已有 `docs/specs/*/spec.md` 无法作为新 mission 的模板，用户每次从零写。
2. **无 `--template` 参数**：`mission create` 不支持指定模板，无法「基于 X 创建类似的 Y」。
3. **示例反推缺失**：用户提供参考示例（代码、文档、Issue 描述）时，系统无法自动反推为结构化 spec。
4. **美诺悖论未缓解**：用户「不理解才来找 AI」，但写 spec 又需要先理解；模板和示例可降低认知门槛。

## 目标

- **SON-101**：建立 Spec 模板库，支持 `mission create --template <id>` 从已有 spec 创建新 mission。
- **SON-104**：实现示例反推 — 用户提供参考示例（文件路径或 URL），AI 反推 Goal、Scope、AC 等，生成可执行 spec。
- 两条路径均为**增量能力**，不改变现有 `mission create` 默认行为。

## 非目标

- 不实现完整的六条路径（翻译者、渐进精化等由后续 change 负责）。
- 不替换 Conductor 的对话式发现；模板与示例为**补充**路径。
- 不实现 Spec Registry（Tessl 风格）；模板库为本地 `docs/specs/` 内已有 spec。

## 用户场景

### 场景 1：基于模板创建

用户执行 `mission create "支付退款优化" --template self-evolution`。系统从 `docs/specs/self-evolution/spec.md` 读取模板，复制结构（Goal、Scope、AC、Constraints 等），将 title 替换为「支付退款优化」，生成新 mission 的 spec 骨架，用户仅需填空关键差异。

### 场景 2：示例反推

用户执行 `mission create "导出 CSV 编码修复" --from-example fixtures/issues/SPC-P0-1.json`。系统读取该 Issue 的 `summary`、`builder_prompt` 等，LLM 反推为结构化 spec（Goal、Scope、AC），写入新 mission 的 `spec.md`。

### 场景 3：URL 示例反推

用户执行 `mission create "登录页重构" --from-url https://github.com/org/repo/issues/42`。系统拉取 Issue 内容（若可访问），LLM 反推 spec 并创建 mission。

## 成功指标

- `mission create --template <id>` 能正确从已有 mission 复制结构并创建新 mission。
- `mission create --from-example <path>` 能读取本地文件并反推 spec，输出可读、可执行的 spec.md。
- `mission create --from-url <url>` 在 URL 可访问时能反推；不可访问时有明确错误提示。
- 默认 `mission create <title>` 行为不变，无 `--template` 或 `--from-example` 时仍创建空白骨架。

## 风险

- **模板质量**：若模板本身不完整，复制后仍需大量修改。缓解：模板需人工标注或审核。
- **反推准确性**：LLM 反推可能遗漏或曲解。缓解：输出可编辑，用户可 approve 前修改。
- **URL 拉取**：私有 repo、认证等需额外支持。缓解：首版仅支持公开 URL 或本地路径。
