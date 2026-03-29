# SON-264 Runtime Responsibility Split

`SON-264 Exploratory Acceptance` 需要把“谁控制过程”和“谁提供语义判断”拆开。否则 exploratory 很容易退化成两种坏形态之一：

- 纯 prompt freestyle，覆盖和结论都不可重复
- 纯硬编码脚本，只能复用 workflow acceptance，发现不了更高层 UX 问题

这次的运行时拆分采用四层结构。

## 1. Campaign Compiler

职责：
- 把验收范围编译成 exploratory campaign
- 生成 seed routes、allowed expansions、预算和 stop conditions
- 选择 critique focus

特点：
- 以 deterministic 规则为主
- 可以注入范围特定参数
- 不直接驱动浏览器

是否需要 LLM：
- 默认不需要
- 只在后续版本里允许作为可选 advisory 输入

## 2. Harness Runtime

职责：
- 执行 browser replay
- 控制 route budget / interaction budget / evidence budget
- 维护 visited routes 和 stop policy
- 决定哪些交互类型允许执行
- 产出结构化 `browser_evidence`

特点：
- 必须由代码硬控
- 是 exploratory acceptance 的总控
- 不允许把原始浏览器控制权交给 LLM

是否需要 LLM：
- 不需要

## 3. Exploration Advisor

职责：
- 在 harness 给出的候选分支里做优先级排序
- 判断哪条相邻 surface 更像值得继续探索的 UX/IA 可疑点
- 帮助 harness 在预算内挑“下一步看哪里”

特点：
- 只能在候选集合内做建议
- 不能自己发 raw browser commands
- 不能突破 campaign 边界

是否需要 LLM：
- 需要

## 4. Critique Evaluator

职责：
- 读取 campaign、browser evidence、artifacts
- 生成 exploratory findings / held findings / issue proposals
- 区分 broken flow 与非阻断 UX critique

特点：
- 必须输出结构化 schema
- 必须服从 filing policy / hold policy
- 不能把 taste-level critique 直接升级成自动 filing

是否需要 LLM：
- 需要

## Responsibility Rule

简单规则：

- 安全、范围、预算、停机条件：Harness 负责
- 下一步优先级、语义理解、UX critique：LLM 负责

这意味着 `SON-264` 不是 “prompt 更长一点”，也不是 “再写一套脚本”。它是：

- deterministic harness
- bounded LLM reasoning

## With Existing Acceptance Modes

当前 acceptance taxonomy 的边界：

- `Verification Acceptance`
  - route script schema
  - 证明声明功能是否通过

- `Workflow Acceptance`
  - route script schema
  - 证明 operator workflow 能否端到端完成

- `Exploratory Acceptance`
  - bounded exploration schema
  - 证明在受控范围内能否从用户视角发现 IA / terminology / discoverability / context continuity 问题

所以 `SON-264` 不是替代 workflow acceptance，而是在它之上增加一个更偏人视角的 bounded layer。
