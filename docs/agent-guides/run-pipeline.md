# 运行 Pipeline

## 单次运行

```bash
spec-orch run --source fixture                    # 用 fixture issue 测试
spec-orch run --issue-id "SON-123"                # 处理具体 issue
spec-orch run --source fixture --codex-executable codex  # 指定 builder
```

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

## Spec 管理

```bash
spec-orch discuss --issue-id "SON-123"   # 与 LLM 讨论 issue
spec-orch plan --issue-id "SON-123"      # 生成 spec
spec-orch readiness --issue-id "SON-123" # 检查 spec 就绪度
```
