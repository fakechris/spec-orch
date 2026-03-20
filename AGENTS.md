# spec-orch: LLM / Agent 操作指南

本文件专为 LLM agent（Claude Code、Cursor 等）设计，说明如何安装、配置、启动和诊断 spec-orch 系统。

## 一、安装

```bash
# 克隆 & 安装（推荐带 all extras）
git clone https://github.com/fakechris/spec-orch.git && cd spec-orch
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[all]"  # 包含 planner, dashboard, slack 所有依赖
```

`[all]` 包含 `fastapi`, `uvicorn`, `websockets`, `litellm`, `slack-bolt` 等。如果只需要核心功能：`pip install -e ".[dev]"`。

## 二、配置（关键步骤）

### 2.1 复制 .env 模板

```bash
cp .env.example .env
```

### 2.2 编辑 .env — 必填项

```env
# LLM API（必填 — daemon、dashboard、所有 LLM 调用都依赖此变量）
SPEC_ORCH_LLM_API_KEY=your-api-key-here
SPEC_ORCH_LLM_API_BASE=https://api.anthropic.com

# Linear（如需 daemon 自动处理 issue）
SPEC_ORCH_LINEAR_TOKEN=lin_api_xxxxxxxxxxxxxxxxxxxxx
```

**重要**：`.env` 文件由 CLI 启动时自动加载（`_load_dotenv`），所有 spec-orch 子命令（包括 `daemon`、`dashboard`）共享同一套环境变量。不需要手动 `export`。

### 2.3 spec-orch.toml（通常不需要修改）

默认 `spec-orch.toml` 已包含合理配置。关键段：

- `[planner]` — LLM 模型和 API 配置
- `[evolution]` — 进化管线触发策略
- `[linear]` — Linear 集成

## 三、启动

### 3.1 初始化项目

```bash
spec-orch init              # 生成 spec-orch.toml（如不存在）
spec-orch init --reconfigure # 重新配置已有项目
```

### 3.2 单次运行

```bash
spec-orch run --issue-id "SON-123"      # 处理单个 issue
spec-orch run --source fixture           # 用 fixture issue 测试
```

### 3.3 启动 Daemon（后台自动处理 issue）

```bash
spec-orch daemon start     # 前台启动
spec-orch daemon health    # 检查 heartbeat
spec-orch daemon dlq       # 查看死信队列
```

### 3.4 启动 Dashboard（Web UI）

```bash
spec-orch dashboard        # 默认 http://127.0.0.1:8420
spec-orch dashboard --port 8080
```

**Dashboard 和 Daemon 是独立进程**，但共享同一个 `.env`。只要 `.env` 配置正确，两者都能正常工作。

### 3.5 Evolution 管线

```bash
spec-orch evolution status  # 查看进化管线状态
spec-orch eval run          # 执行离线评估
spec-orch eval degradation  # 检测质量退化
```

## 四、常见问题诊断

### WebSocket 403

如果 dashboard 的 WebSocket 连接返回 403：
1. 确认 `websockets` 包已安装：`pip install websockets>=12`
2. 如果用 `pip install -e ".[dashboard]"` 安装，`websockets` 已包含
3. 尝试重启 dashboard

### LLM 认证失败（AuthenticationError）

```
litellm.AuthenticationError: Missing API key
```

原因：`.env` 中 `SPEC_ORCH_LLM_API_KEY` 未设置或为空。
修复：编辑 `.env`，填入有效的 API key，然后重启所有 spec-orch 进程。

### Daemon 和 Dashboard 环境变量不共享

这不应该发生 — 两者都通过 CLI 入口点启动，自动加载 `.env`。如果仍有问题：
1. 确认 `.env` 在项目根目录（与 `spec-orch.toml` 同级）
2. 确认启动命令在项目根目录执行
3. 运行 `spec-orch health` 检查配置是否被正确加载

## 五、架构简述

```
spec-orch run → RunController → [Planner → Scoper → Builder → Verifier → Gate → Reviewer]
                                    ↕ ContextAssembler (所有 LLM 节点共享上下文)
spec-orch daemon → SpecOrchDaemon → polls Linear → dispatches RunController
spec-orch dashboard → FastAPI → serves Web UI + WebSocket events
```

核心数据流：Issue → Spec → Plan → Build → Verify → Gate → Review → Merge/Fail
进化循环：Run Artifacts → EvalRunner → Evolvers → Improved Prompts/Rules/Hints
