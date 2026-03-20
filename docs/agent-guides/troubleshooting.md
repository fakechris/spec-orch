# 排查问题

首先运行 `spec-orch preflight`，它会检查所有常见问题并给出修复建议。

## WebSocket 403

Dashboard 的 WebSocket 连接返回 403。

**原因**: `websockets` 包未安装。
**修复**: `pip install 'spec-orch[dashboard]'`

## LLM 认证失败

```
litellm.AuthenticationError: Missing API key
```

**原因**: `SPEC_ORCH_LLM_API_KEY` 未设置或为空。
**修复**: 编辑 `.env`，设置 `SPEC_ORCH_LLM_API_KEY=your-key`，然后重启进程。

Dashboard 和 Daemon 共享同一个 `.env`。两者都通过 CLI 入口点自动加载。

## Planner 不可用

```
Planner not available. Possible causes:
  1. litellm not installed
  2. [planner] model not set
  3. API key not configured
```

**诊断**: `spec-orch preflight`
**修复**:
1. `pip install 'spec-orch[planner]'`
2. `spec-orch init --reconfigure`（会生成包含 planner 配置的 toml）
3. 编辑 `.env` 设置 API key

## Config 找不到

在项目根目录执行命令（与 `spec-orch.toml` 同级），或使用 `--repo-root` 参数。

## Builder 不可用

```
codex not found on PATH
```

**修复**: 安装对应的 builder（`npm install -g @anthropic/codex`），或在 `spec-orch.toml` 的 `[builder]` 段配置其他 adapter。

## 完整诊断

```bash
spec-orch preflight --json    # 结构化输出
spec-orch doctor --fix-hints  # 每项都带修复命令
cat .spec_orch/preflight.json # 上次 preflight 结果
```
