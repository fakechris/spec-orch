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

## Spec 管理

```bash
spec-orch discuss --issue-id "SON-123"   # 与 LLM 讨论 issue
spec-orch plan --issue-id "SON-123"      # 生成 spec
spec-orch readiness --issue-id "SON-123" # 检查 spec 就绪度
```
