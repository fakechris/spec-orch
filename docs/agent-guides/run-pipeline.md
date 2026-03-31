# 运行 Pipeline

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
```

它们会把结果分别收口到：

- `.spec_orch/acceptance/issue_start_smoke.json`
- `docs/specs/<mission_id>/operator/mission_start_acceptance.json`
- `.spec_orch/acceptance/dashboard_ui_acceptance.json`
- `docs/specs/<mission_id>/operator/exploratory_acceptance_smoke.json`

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
