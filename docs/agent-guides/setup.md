# 首次设置

## 1. 安装

```bash
git clone https://github.com/fakechris/spec-orch.git && cd spec-orch
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[all]"   # 包含 planner + dashboard + slack 所有依赖
```

`[all]` 包含 `fastapi`, `uvicorn`, `websockets`, `litellm`, `slack-bolt`。

如果你是在多个 `git worktree` 之间切换，优先不要在每个 worktree 下各建一个
`.venv`。推荐把 `uv` 的环境固定到共享主仓目录，再从各个 worktree 复用：

```bash
shared_repo_root="$(cd "$(git rev-parse --git-common-dir)/.." && pwd)"
export UV_PROJECT_ENVIRONMENT="$shared_repo_root/.venv-py313"
uv sync --python 3.13 --extra dev
```

之后统一用：

```bash
UV_PROJECT_ENVIRONMENT="$shared_repo_root/.venv-py313" uv run --python 3.13 ruff check src/ tests/
UV_PROJECT_ENVIRONMENT="$shared_repo_root/.venv-py313" uv run --python 3.13 python -m pytest
```

这样新 worktree 不会重复创建本地 `.venv`，也能保证所有 agent / shell 命令都落到同一个
Python 3.13 开发环境。

## 2. 配置 .env

```bash
shared_repo_root="$(cd "$(git rev-parse --git-common-dir)/.." && pwd)"
cp .env.example "$shared_repo_root/.env"
```

编辑共享 `.env`，必填项：

```env
SPEC_ORCH_LLM_API_KEY=your-api-key-here
SPEC_ORCH_LLM_API_BASE=https://api.minimaxi.com/anthropic
```

可选项：

```env
SPEC_ORCH_LINEAR_TOKEN=lin_api_xxx   # daemon 需要
```

CLI、dashboard、doctor、formal acceptance harness 现在都会优先读取当前
worktree 的 `.env`；如果当前 worktree 没有，则自动回退到共享主仓目录
`$(cd "$(git rev-parse --git-common-dir)/.." && pwd)/.env`。

为了兼容旧配置，共享 `.env` 里的 `SPEC_ORCH_LLM_API_KEY` /
`SPEC_ORCH_LLM_API_BASE` 会自动桥接到新的 `MINIMAX_API_KEY` /
`MINIMAX_ANTHROPIC_BASE_URL`，所以新 worktree 不需要重复抄一份。

## 3. 初始化项目

```bash
spec-orch init                       # 交互式，生成 spec-orch.toml
spec-orch init --profile full -y     # 非交互式，完整配置
spec-orch init --offline             # 无 LLM 的纯规则检测
```

`init` 完成后会自动运行 `preflight` 自检。

## 4. 验证

```bash
spec-orch preflight          # 检查依赖、配置、环境变量
spec-orch preflight --try-llm  # 额外测试 LLM 连通性
spec-orch doctor --fix-hints # 详细诊断
```

`preflight` 结果保存在 `.spec_orch/preflight.json`，可随时读取。
