# 首次设置

## 1. 安装

```bash
git clone https://github.com/fakechris/spec-orch.git && cd spec-orch
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[all]"   # 包含 planner + dashboard + slack 所有依赖
```

`[all]` 包含 `fastapi`, `uvicorn`, `websockets`, `litellm`, `slack-bolt`。

## 2. 配置 .env

```bash
cp .env.example .env
```

编辑 `.env`，必填项：

```env
SPEC_ORCH_LLM_API_KEY=your-api-key-here      # 所有 LLM 调用依赖此变量
SPEC_ORCH_LLM_API_BASE=https://api.anthropic.com
```

可选项：

```env
SPEC_ORCH_LINEAR_TOKEN=lin_api_xxx   # daemon 需要
```

`.env` 由 CLI 启动时自动加载，所有子命令共享。不需要手动 `export`。

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
