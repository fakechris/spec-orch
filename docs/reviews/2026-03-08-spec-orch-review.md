# SpecOrch 项目 Review & 建议

> 日期: 2026-03-08
> 范围: 项目方向、实现细节、Codex 集成策略、Next Phase Plan

---

## 一、项目定位与方向

### 1.1 SpecOrch 是什么

SpecOrch 是一个 **issue-driven, stage-gated delivery pipeline**，用固定的 `spec→build→verify→review→gate→merge` 阶段来编排 AI 代理（Codex/Claude）完成软件交付。

核心架构假设：
- `Linear` 是任务控制面
- `Obsidian` 是知识面
- `Orchestrator` 是运行时控制中心
- `Codex`/`Claude`/浏览器代理是执行适配器
- `Spec` + `Gate` 定义完成标准和可合并性

### 1.2 在同类项目中的定位

| 项目 | Stars | 编排模型 | 验证策略 | Issue 驱动 | 生命周期 |
|------|-------|---------|---------|-----------|---------|
| OpenHands | 68.7k | 动态委托 | 自我验证+委托 | ✅ | 开放循环 |
| MetaGPT | 64.9k | 角色扮演 SOP | QA Agent | ❌ | PM→QA |
| Aider | 41.6k | 人工结对 | Lint + /test | ❌ | REPL |
| SWE-agent | 18.7k | 单 Agent + Reviewer | Reviewer LLM | ✅ | 重试循环 |
| Plandex | 15.1k | Plan + sandbox | 自动调试循环 | ❌ | 累积 diff |
| Agentless | 2.0k | 固定三阶段 | 测试重排序 | ✅ | 定位→修复→验证 |
| Orchestrator | 1.3k | 分层两级 | Explorer 验证 | ❌ | 编排→委托 |
| **SpecOrch** | - | 固定多阶段管线 | 结构化 Gate | ✅ | spec→build→verify→review→gate→merge |

### 1.3 独特价值

**Gate 层是 SpecOrch 的独特价值点。** 所有开源项目中没有一个实现了机器强制的合并门禁。大多数项目要么自动提交 patch（SWE-agent/Agentless），要么完全靠人审（Aider/Plandex）。一个结构化、可审计的 gate 层是生产级系统的正确模式。

### 1.4 与 OpenAI Agents SDK 的关系

OpenAI Agents SDK（原名 Swarm 的演进）解决的是 agent 定义、handoff、guardrails 和 run loop 的问题，是一个 **agent runtime framework**。SpecOrch 不是竞争者，而是更高层的 **delivery orchestration system**，可以在内部使用 Agents SDK 作为 agent 调度层。

### 1.5 方向性风险

| 风险 | 说明 | 建议 |
|------|------|------|
| Codex 协议深度耦合 | `codex_harness_builder_adapter.py` 900+ 行深度耦合 Codex JSON-RPC 协议 | 改用 `codex exec` 模式（详见第三节） |
| 受众限制 | Linear/Obsidian 作为架构假设而非可选适配器 | 将 Linear/Obsidian 视为 adapter，引入 IssueSource/KnowledgeSync 接口 |
| 单一 builder 绑定 | RunController 硬编码 CodexHarnessBuilderAdapter | 提取 BuilderAdapter Protocol |

---

## 二、实现细节 Review

### 2.1 做得好的

| 方面 | 评价 |
|------|------|
| **Domain Model** | `models.py` 干净，用 `dataclass(slots=True)` 是好的 Python 3.13 惯用写法 |
| **GateService** | 纯函数，逻辑清晰，易测试，30 行完成核心判定 |
| **Worktree isolation** | per-issue git worktree 是正确的隔离策略 |
| **Telemetry** | 文件级 JSONL telemetry 是务实的 v1 选择，与 OTel 兼容 |
| **TDD discipline** | 23 个测试全部通过，覆盖了核心路径 |
| **Builder contract compliance** | 检测 agent 是否在首个 action 前叙述，是独特的 agent 质量度量 |
| **Artifact 设计** | `task.spec.md` + `progress.md` + `explain.md` + `report.json` 的分层设计合理 |
| **依赖极简** | 运行时仅依赖 typer，避免了过度依赖 |

### 2.2 需要改进的

#### P0: RunController 是 God Object

**文件**: `src/spec_orch/services/run_controller.py` (570 行)

`run_issue`、`review_issue`、`accept_issue` 三个方法各自有大量重复的 gate→explain→report 写入逻辑。

**建议**: 提取 `_finalize_run()` 共用方法：

```python
def _finalize_run(self, *, issue, workspace, run_id, builder, review,
                  verification, accepted_by, acceptance_status):
    gate = self.gate_service.evaluate(...)
    self._log_gate_event(...)
    explain = self.artifact_service.write_explain_report(...)
    report = self._write_report(...)
    return gate, explain, report
```

#### P0: 没有 BuilderAdapter 抽象

架构文档定义了 Agent Router，但实现中 RunController 直接硬编码了 `CodexHarnessBuilderAdapter`。

**建议**: 引入 Protocol：

```python
class BuilderAdapter(Protocol):
    ADAPTER_NAME: str
    AGENT_NAME: str
    def run(self, *, issue: Issue, workspace: Path,
            run_id: str | None = None, ...) -> BuilderResult: ...
```

#### P0: 没有 IssueSource 抽象

`_load_fixture()` 直接在 RunController 里读文件系统，当 fixture 不存在时返回硬编码默认 Issue（"Build MVP runner"）。引入 Linear 后会更混乱。

**建议**: 提取为接口：

```python
class IssueSource(Protocol):
    def load(self, issue_id: str) -> Issue: ...

class FixtureIssueSource:
    def __init__(self, fixtures_dir: Path): ...

class LinearIssueSource:
    def __init__(self, client: LinearClient): ...
```

#### P1: report.json schema 是隐式的

完全靠 dict 构建。`_builder_from_report` / `_verification_from_report` / `_review_from_report` 三个方法本质是手动反序列化。

**建议**: 用 dataclass 定义 `ReportSchema`，替换手动 dict 构建和解析。

#### P1: 验证步骤硬编码

`VerificationService.STEP_NAMES = ("lint", "typecheck", "test", "build")` 且 `VerificationSummary` 的四个 `_passed` 字段也是硬编码的。加 `install` 或 `security_scan` 需改多处。

**建议**: 改为动态步骤列表，`VerificationSummary` 用 `dict[str, bool]` 代替四个显式字段。

#### P2: pyproject.toml 缺少未来依赖声明

P0-alpha 计划里提到 `httpx`（Linear client），需要在使用前加入 dependencies。

---

## 三、Codex 集成策略（关键发现）

### 3.1 现状问题

`codex_harness_builder_adapter.py` 有 **941 行**，其中 `_CodexHarnessSession` 类约 700 行，手工实现了：

- JSON-RPC 消息帧（`_write_message` / `_read_message`）
- 请求-响应匹配（`_request` 方法 + id 追踪）
- 进程生命周期管理（subprocess.Popen + context manager）
- 多层超时策略（idle / stalled / absolute timeout）
- 活跃度监控（protocol / output / progress 三级心跳）
- Server-initiated request 处理（approval 自动应答）
- 原始 I/O 录制（raw_harness_in/out/err）
- 结构化事件解析与录制（incoming_events.jsonl）
- 状态快照写入（harness_state.json）
- Agent message fragment 聚合

### 3.2 市场上没有成熟的 Python Codex app-server client

| 选项 | 语言 | 说明 | 适合 SpecOrch? |
|------|------|------|---------------|
| `@openai/codex-sdk` (官方) | TypeScript | 不调 app-server JSON-RPC，spawn `codex exec --experimental-json` 读 JSONL | ❌ Python 项目 |
| `codex exec` (CLI 模式) | 任何语言 | 非交互模式，stdout 输出 JSONL 事件流 | ✅ **推荐** |
| `codex app-server` (JSON-RPC) | 任何语言 | 当前做法，手写 client | ⚠️ 可以但太重 |
| Python Codex SDK | Python | **不存在** | ❌ |

### 3.3 关键发现：官方 SDK 不用 app-server

OpenAI 官方 TypeScript SDK（`@openai/codex-sdk`，~500 行）的做法是：

```typescript
// 实际实现只有这么简单
const child = spawn("codex", ["exec", "--experimental-json", ...]);
child.stdin.write(prompt);
child.stdin.end();
for await (const line of readline(child.stdout)) {
    yield line;  // 每行是一个 JSONL 事件
}
```

它**完全不碰 app-server JSON-RPC 协议**。所有复杂度（JSON-RPC 帧、thread 管理、approval 流、timeout）都由 `codex exec` 内部处理。

### 3.4 API 成熟度对比

| 接口 | 成熟度 | 说明 |
|------|--------|------|
| `codex exec` | **Stable** | 官方推荐用于 CI/CD 和自动化 |
| `codex app-server` | **Experimental** | 官方文档明确标注实验性 |

### 3.5 推荐重构：用 `codex exec` 替换 `_CodexHarnessSession`

**预计从 941 行降到 ~150 行**，同时获得更好的稳定性。

核心改动：

```python
class CodexExecBuilderAdapter:
    """Builder adapter using `codex exec --experimental-json`."""
    
    ADAPTER_NAME = "codex_exec"
    AGENT_NAME = "codex"
    
    def run(self, *, issue: Issue, workspace: Path, run_id: str | None,
            event_logger=None) -> BuilderResult:
        if not issue.builder_prompt:
            return self._skipped_result(workspace)
        
        command = [
            self.executable, "exec",
            "--experimental-json",
            "--sandbox", "workspace-write",
            "--skip-git-repo-check",
            issue.builder_prompt,
        ]
        
        process = subprocess.Popen(
            command, cwd=workspace,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        process.stdin.close()
        
        items = []
        final_message = ""
        usage = None
        
        for line in process.stdout:
            event = json.loads(line.strip())
            self._record_event(event, workspace, run_id)
            
            match event.get("type"):
                case "item.completed":
                    items.append(event["item"])
                    if event["item"]["type"] == "agent_message":
                        final_message = event["item"].get("text", "")
                case "turn.completed":
                    usage = event.get("usage")
                case "turn.failed":
                    # handle failure
                    pass
        
        exit_code = process.wait()
        # ... build and return BuilderResult
```

**保留的能力**：
- Telemetry（从 JSONL stdout 写入 `incoming_events.jsonl`）
- Builder contract compliance（对事件流做相同检查）
- Builder report 写入（相同格式）

**不再需要的**：
- JSON-RPC 帧处理（~100 行）
- 请求-响应匹配和 id 追踪（~50 行）
- 三层超时策略（~80 行 → `codex exec` 内部处理）
- Approval 自动应答（~30 行 → `--sandbox workspace-write` 处理）
- 进程活跃度监控和状态快照（~150 行 → `codex exec` 内部处理）
- Agent message fragment 聚合（~30 行 → `item.completed` 直接给完整文本）

---

## 四、Next Phase Plan

基于当前代码状态和 P0-Alpha Dogfood Plan，建议调整后的执行计划：

### Phase N1: 内部重构（为 Linear ingress 做准备）

| 任务 | 说明 | 优先级 |
|------|------|--------|
| 用 `codex exec` 重写 builder adapter | 941 行 → ~150 行，详见第三节 | P0 |
| 提取 `IssueSource` 接口 | `FixtureIssueSource` + 未来 `LinearIssueSource`，从 RunController 解耦 | P0 |
| 提取 `BuilderAdapter` Protocol | `codex_exec` / `pi_codex` 都实现同一接口 | P0 |
| 提取 `_finalize_run()` | 消除 run/review/accept 三处的 gate→explain→report 重复 | P1 |
| 给 report.json 定义 ReportSchema | 替换手动 dict 构建和解析 | P1 |

**验收标准**: 23 个测试继续全部通过，`run-issue` / `review-issue` / `accept-issue` 行为不变。

### Phase N2: Linear Ingress（原 P0-1）

| 任务 | 说明 |
|------|------|
| SPC-L1: Linear client + auth | `httpx` based，token 从 env 读取 |
| SPC-L2: `LinearIssueSource` | 实现 `IssueSource` 接口 |
| SPC-L3: Issue field mapping | title, description, labels → `Issue` model |
| 添加 `--source linear\|fixture` CLI flag | 显式选择 issue 来源 |

### Phase N3: Daemon Loop（原 P0-4，建议提前）

**理由**: daemon loop 是 "SpecOrch 变成真正 orchestrator" 的转折点。有了 daemon 后 write-back 才有真实使用场景。

| 任务 | 说明 |
|------|------|
| `spec-orch daemon` command | poll → claim → run → record 循环 |
| per-issue lockfile | 防止重复执行 |
| `spec-orch rerun` | 按 issue ID 重跑 |

### Phase N4: Write-back（原 P0-3）

daemon 运行一段时间后再实现 Linear / PR write-back。

### Phase N5: 长期方向

| 方向 | 建议 |
|------|------|
| **Config 管理** | 引入 `spec_orch.toml` 或 `.spec-orch/config.yaml`，替代散落的 CLI flags |
| **Claude Review adapter** | 用 Claude API + structured output 生成 `ReviewSummary` |
| **Web dashboard** | FastAPI + HTMX 页面展示 run 状态和 explain reports |
| **Agent runtime 抽象** | 考虑引入 OpenAI Agents SDK 或类似框架作为 agent 调度层 |

---

## 五、总结

### 方向判断

SpecOrch 方向正确。Gate 层是独特且有价值的差异化。固定阶段管线比开放 agent loop 更适合生产级软件交付。

### 最大杠杆点

用 `codex exec --experimental-json` 替换当前的 app-server JSON-RPC 手写客户端。这是**单次 ROI 最高的重构**：
- 代码量减少 ~800 行
- 从 Experimental API 迁移到 Stable API
- 与 OpenAI 官方 SDK 采用相同架构模式
- 消除最大的维护负担和协议耦合风险

### 第二杠杆点

在追加 Linear 之前做一轮内部接口提取（IssueSource / BuilderAdapter / _finalize_run），让 RunController 不再是 God Object，为多 issue source 和多 builder adapter 做好准备。
