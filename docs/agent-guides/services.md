# 启动服务

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

## 关键点

- Dashboard 和 Daemon 是**独立进程**，但共享同一个 `.env` 文件
- 所有环境变量由 CLI 入口点自动加载，不需要每个进程单独设置
- 在项目根目录执行命令（与 `spec-orch.toml` 同级）
- 建议统一用 Python 3.13 环境执行本项目命令，例如 `uv run --python 3.13 ...`

## Evolution 管线

```bash
spec-orch evolution status   # 查看策略、计数器、最近 cycle
spec-orch eval run           # 离线评估
spec-orch eval degradation   # 质量退化检测
```
