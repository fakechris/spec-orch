# 运行 Pipeline

## Overview

本指南覆盖 `spec-orch` 的单次运行、canonical acceptance、artifact 阅读路径，以及 tranche closeout 的固定动作。当前主线已经不再重画架构，重点是把 acceptance 和 hardening 做稳定。

## When to Use

- 要手动跑单个 issue 或 mission
- 要跑 canonical acceptance 并判断这轮是否可以收口
- 要阅读 run / mission / exploratory artifacts
- 要在 tranche 结束后做 source-run 对比和 release archive 归档

## Workflow

1. 先跑目标路径的 run 或 acceptance。
2. 先看顶层 report，再看 nested review / artifacts。
3. 用 `Instructions / State / Verification / Scope / Lifecycle` 五个 subsystem 做 tranche review。
4. 给五个 subsystem 打分，最低分的那个就是下一轮 bottleneck。
5. 先修 `harness_bug`，再 rerun，再看 `n2n_bug / ux_gap`。
6. canonical suite 可信后，写入 `docs/acceptance-history/`。

## Context / Memory Taxonomy

后续所有 acceptance / hardening 改动都应明确落在这五层中的哪一层：

- `Active Context`
  - 当前 run、当前 mission、当前 operator 正在消费的即时上下文。
- `Working State`
  - 还在变化的中间态，例如 queue、mission packet、approval workspace。
- `Review Evidence`
  - acceptance / browser / compare / transcript 等审阅证据。
- `Archive`
  - release acceptance bundle、history index、source-run lineage。
- `Promoted Learning`
  - 已经被接受并进入长期策略/规则/记忆层的结论。

不要把这五层重新混回一个笼统的 “memory” bucket。

## 单次运行

```bash
spec-orch run --source fixture                    # 用 fixture issue 测试
spec-orch run --issue-id "SON-123"                # 处理具体 issue
spec-orch run --source fixture --codex-executable codex  # 指定 builder
```

Mission 级别执行由 `plan.json` 驱动。若 `docs/specs/<mission_id>/plan.json` 存在，daemon 会把对应 Linear issue 识别为 mission 执行入口。

如果要跑带 supervisor 的 mission 端到端试跑，优先看：

- `docs/guides/supervised-mission-e2e-playbook.md`
- `docs/guides/operator-console.md`

如果要理解当前建议中的并发模型、mission/wave 串行约束、以及 admission control 预算对象，优先看：

- `docs/plans/2026-04-01-concurrency-and-admission-control-program.md`

重构后的稳定性验收现在建议优先用这两个 canonical smoke 入口：

```bash
./tests/e2e/issue_start_smoke.sh                 # issue-start dry-run
./tests/e2e/issue_start_smoke.sh --full          # issue-start full smoke
./tests/e2e/mission_start_acceptance.sh          # mission-start dry-run
./tests/e2e/mission_start_acceptance.sh --full   # mission-start full smoke
./tests/e2e/dashboard_ui_acceptance.sh           # dashboard/UI dry-run
./tests/e2e/dashboard_ui_acceptance.sh --full    # dashboard/UI full smoke
./tests/e2e/exploratory_acceptance_smoke.sh      # exploratory dry-run
./tests/e2e/exploratory_acceptance_smoke.sh --full  # exploratory full smoke
./tests/e2e/update_stability_acceptance_status.sh   # refresh consolidated status
```

它们会把结果分别收口到：

- `.spec_orch/acceptance/issue_start_smoke.json`
- `docs/specs/<mission_id>/operator/mission_start_acceptance.json`
- `.spec_orch/acceptance/dashboard_ui_acceptance.json`
- `docs/specs/<mission_id>/operator/exploratory_acceptance_smoke.json`
- `.spec_orch/acceptance/stability_acceptance_status.json`
- `docs/plans/2026-03-30-stability-acceptance-status.md`

Exploratory / feature acceptance 的顶层 report 现在应该优先看这些字段：

- `status`
- `summary`
- `findings_count`
- `issue_proposal_count`
- `recommended_next_step`
- `finding_taxonomy`
- `source_run`

finding taxonomy 当前约定为：

- `harness_bug`
  - 验收系统自己的 bug。先修，再 rerun，同一路径没重新跑通前不要做产品结论。
- `n2n_bug`
  - 闭环测试发现的真实流程/功能问题。进入当前主修流。
- `ux_gap`
  - exploratory 发现的可发现性、清晰度、信心、连续性问题。进入产品改进流。

当前建议 workflow：

1. 先跑 acceptance 并生成顶层 report。
2. 如果 top-level report 和 nested review 不一致，归为 `harness_bug` 并立即修复。
3. rerun 同一路径，直到 top-level report 可信。
4. 再把剩余 finding 分流到 `n2n_bug` 或 `ux_gap`。
5. 每修一轮，再 rerun 同一路径，用 `source_run` 对比前后结果。
6. 当 canonical suite 形成正式版本基线后，把该版本写入 `docs/acceptance-history/` 归档。

## 5-Subsystem Tranche Review Checklist

每次 tranche closeout 后，固定从这五个 subsystem 做 review：

- `Instructions`
  - 指令、计划、skill/workflow 文档是否明确，是否还有含糊空间。
- `State`
  - runtime state、workspace state、acceptance state 是否一致且可恢复。
- `Verification`
  - acceptance / evidence / compare 是否独立可信，是否存在自证通过。
- `Scope`
  - 当前 tranche 是否真的只改了该改的 seam，没有把主线扩散。
- `Lifecycle`
  - run -> rerun -> archive -> history index 的收口是否完整。

如果某一项最低分，就把它当作下一轮 bottleneck，而不是再拍脑袋选题。

正式版本归档当前应至少包含：

- `docs/acceptance-history/index.json`
- `docs/acceptance-history/releases/<release_id>/manifest.json`
- `summary.md`
- `status.json`
- `findings.json`
- `source_runs.json`
- `artifacts.json`

这层 archive 不是可选留证据，而是未来 dashboard / workbench / showcase
要消费的历史数据底座。

当前这套 release acceptance history/archive program 在 Linear 中对应：

- `SON-419` `[Epic] Release Acceptance History and Archive`
- `SON-420`..`SON-424`

## Pipeline 阶段

```
Plan → Scope → Build → Verify → Gate → Review
```

每个阶段通过 ContextAssembler 获取结构化上下文，输出写入 run artifacts。

## Run Artifacts

运行结果存储在 `.spec_orch_runs/<run_id>/`：

- `manifest.json` — artifact 位置索引
- `events.jsonl` — 执行事件流
- `live.json` — 实时状态
- `conclusion.json` — 最终结论
- `retro.json` — 回顾分析

## Mission Round Artifacts

当 `[supervisor]` 已配置且 daemon 进入 mission supervised execution 时，额外产物位于：

```text
docs/specs/<mission_id>/rounds/round-XX/
```

- `round_summary.json` — 本轮执行摘要
- `round_decision.json` — supervisor 的结构化决策
- `supervisor_review.md` — 本轮富文本复盘
- `visual_evaluation.json` — 可选的视觉/浏览器检查结果

每个 packet worker 还有独立 workspace：

```text
docs/specs/<mission_id>/workers/<packet_id>/
  builder_report.json
  telemetry/
    incoming_events.jsonl
    events.jsonl
    activity.log
```

可直接查看：

```bash
spec-orch mission logs <mission_id> <packet_id>
spec-orch mission logs <mission_id> <packet_id> --raw
spec-orch mission logs <mission_id> <packet_id> --events
```

Dashboard 里的 operator console 现在会把这几层信息汇总成三个可直接消费的 surface：

- `Inbox`：把 approval-needed、paused、failed mission 统一成 triage 入口
- `Mission Detail`：展示当前 mission、packets、latest round 和 transcript timeline
- `Context Rail`：展示 approval workspace、transcript inspector、artifact path

当前还新增了独立 mission surface：

- `Approvals`
- `Visual QA`
- `Costs & Budgets`

当前 canonical operator workbench surface 已切到：

- `Execution`
- `Judgment`
- `Learning`

其中：

- `Judgment` 是 acceptance / compare / evidence 的主操作面
- `Acceptance` 保留为 raw review artifact 的兼容入口，不再是主审阅 surface

其中 transcript 已支持：

- timeline block 过滤
- supervisor / visual evidence block
- block 级别的 linked evidence path
- command-burst 分组，把连续 tool 事件折叠成更可读的 operator timeline

approval-needed 的 round 现在也能直接在 dashboard 里触发预设动作：

- `Approve`
- `Request revision`
- `Ask follow-up`

完整 operator-console 工作流请看：

- `docs/guides/operator-console.md`

## Spec 管理

```bash
spec-orch discuss --issue-id "SON-123"   # 与 LLM 讨论 issue
spec-orch plan --issue-id "SON-123"      # 生成 spec
spec-orch readiness --issue-id "SON-123" # 检查 spec 就绪度
```

## Rules

- 先看顶层 report，再下产品结论。
- top-level report 和 nested review 不一致时，先归类为 `harness_bug`。
- exploratory 或 feature acceptance 的证据必须可复查，不能只靠一句总结。
- 每个 tranche 结束后都要做 formal acceptance 和 archive closeout。

## Common Rationalizations

- “这轮只是小改，不用跑 canonical acceptance”
  - 错。只要会影响 acceptance 可信度、workflow 或 operator surface，就要跑。
- “nested review 看起来没问题，顶层 report 可以先忽略”
  - 错。顶层 report 不可信时，说明 harness 还没收稳。
- “先修产品问题，harness bug 后面再补”
  - 错。harness bug 会污染后续所有产品判断。

## Red Flags

- 同一路径 rerun 后还在读旧 artifact
- source-run before/after 无法对齐
- acceptance 结论由 implementer 自己生成并自己判定
- archive bundle 缺字段或 index 没刷新

## Verification

- 跑目标 acceptance 路径并确认顶层 report 可读
- 看 `finding_taxonomy` 是否完成分流
- 看 `source_run` 是否能比较 before/after
- 确认 `docs/acceptance-history/index.json` 和本轮 bundle 已更新
