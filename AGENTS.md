# spec-orch: Agent 操作指南索引

本文件为 LLM agent（Claude Code、Cursor 等）提供快速导航。内容按场景拆分，按需加载。

## 操作指南

| 场景 | 文档 | 何时使用 |
|------|------|----------|
| 首次设置 | [docs/agent-guides/setup.md](docs/agent-guides/setup.md) | 安装、配置 .env、生成 spec-orch.toml |
| 启动服务 | [docs/agent-guides/services.md](docs/agent-guides/services.md) | 启动 daemon、dashboard、TUI |
| 运行 Pipeline | [docs/agent-guides/run-pipeline.md](docs/agent-guides/run-pipeline.md) | 处理 issue、运行 spec-orch run |
| 排查问题 | [docs/agent-guides/troubleshooting.md](docs/agent-guides/troubleshooting.md) | WebSocket 403、LLM 认证失败、依赖缺失 |

## 快速命令

```bash
spec-orch preflight           # 启动前自检（依赖 + 配置 + 连通性）
spec-orch init                # 生成 spec-orch.toml + 复制 .env
spec-orch doctor --fix-hints  # 详细诊断 + 修复建议
spec-orch run --source fixture # 用 fixture issue 测试 pipeline
spec-orch dashboard           # Web UI (默认 :8420)
spec-orch daemon start        # 后台自动处理 Linear issue
spec-orch evolution status    # 进化管线状态
```

## 架构速览

```
Issue → Spec(IAC) → Plan → Scope → Build → Verify → Gate → Review → Merge/Fail
                    ↕ ContextAssembler (所有 LLM 节点共享上下文)
Evolution: Run Artifacts → EvalRunner → Evolvers → Improved Prompts/Rules/Hints
```
