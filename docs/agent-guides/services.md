# 启动服务

## Overview

本指南描述 dashboard、daemon 和 evolution 相关服务怎么启动，以及 operator 应该把哪些 surface 当成 canonical 工作面。

## When to Use

- 要启动 dashboard / daemon
- 要做 supervised mission 调试
- 要跑 canonical acceptance 前的服务准备
- 要确认 operator 应该看哪个 workbench surface

## Dashboard (Web UI)

```bash
spec-orch dashboard              # 默认 http://127.0.0.1:8420
spec-orch dashboard --port 8080  # 自定义端口
```

需要 `pip install 'spec-orch[dashboard]'`（含 fastapi, uvicorn, websockets）。

## Daemon (后台处理 Linear issue)

```bash
spec-orch daemon start     # 前台启动，轮询 Linear
spec-orch daemon start --live-mission-workers  # 前台实时展示 mission worker 事件
spec-orch daemon health    # 检查 heartbeat
spec-orch daemon dlq       # 查看死信队列
```

需要 `SPEC_ORCH_LINEAR_TOKEN` 和 `SPEC_ORCH_LLM_API_KEY`。

如果要启用 mission round supervisor，还需要在 `spec-orch.toml` 中配置 `[supervisor]`，并提供对应模型的 API key。

如果要在 round review 前加浏览器/截图类检查，可再配置 `[supervisor.visual_evaluator]`。推荐先用 `adapter = "command"`，把 Playwright 或自定义脚本挂进去。

如果要调试 supervised mission，建议前台启动 daemon 并加 `--live-mission-workers`。这样 packet worker 的 activity log 会实时打印到 stderr，同时仍然落盘到各自 workspace。

更完整的实操与观测手册见：

- `docs/guides/supervised-mission-e2e-playbook.md`
- `docs/guides/operator-console.md`

如果当前目标是做重构后的稳定性验收，优先用：

```bash
./tests/e2e/issue_start_smoke.sh --full
./tests/e2e/mission_start_acceptance.sh --full
./tests/e2e/dashboard_ui_acceptance.sh --full
./tests/e2e/exploratory_acceptance_smoke.sh --full
./tests/e2e/update_stability_acceptance_status.sh
```

前两者覆盖 issue 和 fresh mission/milestone 启动主链，后两者覆盖
dashboard/UI 主 surface 和 post-run exploratory acceptance smoke。最后一个命令把
现有 canonical 报告刷新成统一状态页。

Dashboard 现在已经进入 operator-console 形态，首页主要看三块：

- `Inbox`：paused / failed / approval-needed mission triage
- `Mission Detail`：当前 mission、packets、latest round、transcript
- `Context Rail`：approval workspace、transcript inspector、artifact links

除此之外，Mission Detail 里现在还有独立的：

- `Approvals`
- `Visual QA`
- `Costs`

workbench cutover 后，operator 侧应优先使用：

- `Execution` 处理 active work / queue / runtimes / browser / terminal
- `Judgment` 处理 acceptance evidence / compare / candidate findings / review state
- `Learning` 处理 promotion / memory / archive lineage

`Acceptance` 仍然保留，但它现在是 raw acceptance artifact 的兼容入口，不再是 canonical review surface。

其中 approval workspace 已经支持直接发送预设 guidance：

- `Approve`
- `Request revision`
- `Ask follow-up`

这些动作会通过 dashboard API 直接写回 paused mission 的 `/btw` 注入链路，不需要先切到 CLI。

实现代码现在在 `src/spec_orch/dashboard/` 包下；顶层 `src/spec_orch/dashboard.py` 只保留兼容导出。

完整的 operator workbench 使用说明见：

- `docs/guides/operator-console.md`

## 关键点

- Dashboard 和 Daemon 是**独立进程**，但共享同一个 `.env` 文件
- 所有环境变量由 CLI 入口点自动加载，不需要每个进程单独设置
- 在项目根目录执行命令（与 `spec-orch.toml` 同级）
- 建议统一用 Python 3.13 环境执行本项目命令，例如 `uv run --python 3.13 ...`

## Rules

- dashboard 和 daemon 是独立进程，但必须读同一套配置和共享 `.env` 回退逻辑。
- operator 侧优先使用 `Execution / Judgment / Learning`，不要把 `Acceptance` 当主入口。
- 做 acceptance/hardening 时，先确保服务启动方式和 workspace/base 没漂。

## Common Rationalizations

- “dashboard 起来了就算环境正常”
  - 不够。daemon、LLM auth、shared env fallback 也必须一致。
- “Acceptance tab 还能看，就先继续用旧 surface”
  - 不对。它现在只是兼容入口，不是 canonical review surface。
- “只看一个进程的日志就够了”
  - 不够。很多问题是 dashboard / daemon / worker 三层状态错位。

## Red Flags

- dashboard 能开，daemon 心跳不更新
- 不同 worktree 各自读不同 `.env`
- operator 在旧 surface 和新 workbench 间来回切，导致状态判断不一致

## Verification

- `spec-orch preflight`
- `spec-orch daemon health`
- 打开 dashboard 并确认 `Execution / Judgment / Learning` surface 可访问
- 如果跑 supervised mission，再确认 worker telemetry 和 dashboard state 对得上

## Evolution 管线

```bash
spec-orch evolution status   # 查看策略、计数器、最近 cycle
spec-orch eval run           # 离线评估
spec-orch eval degradation   # 质量退化检测
```
