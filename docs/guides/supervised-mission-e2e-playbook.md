# Supervised Mission E2E Playbook

> 面向真实试跑的操作手册：如何启动一个 supervised mission、如何看每一轮发生了什么、以及如何把可观测性保持在可调试状态。

---

## 1. 适用场景

这份手册适用于下面这种链路：

```text
Mission spec -> plan.json -> daemon -> ACPX/Codex workers -> supervisor round review
```

也就是：

- 你已经有一个 mission spec
- 你希望 daemon 自动执行 `wave -> round review -> next action`
- 你希望能同时看到：
  - worker 原始事件
  - orchestrator 事件
  - supervisor 每轮决策

如果只是跑单个 issue，不需要这份手册，直接看 `docs/agent-guides/run-pipeline.md`。

---

## 2. 前置条件

### 运行环境

建议统一用 Python 3.13：

```bash
uv run --python 3.13 spec-orch --version
```

还需要：

```bash
node --version
npx --version
gh --version
git --version
```

### 环境变量

至少准备：

```bash
export SPEC_ORCH_LINEAR_TOKEN="lin_api_xxx"
export MINIMAX_API_KEY="xxx"
```

如果 `[supervisor]` 或 `[builder]` 用别的 provider，就换成对应的 key。

### `spec-orch.toml`

最小可用配置：

```toml
[issue]
source = "linear"

[verification]
lint = ["{python}", "-m", "ruff", "check", "src/"]
typecheck = ["{python}", "-m", "mypy", "src/"]
test = ["{python}", "-m", "pytest", "-q"]
build = ["{python}", "-c", "print('build ok')"]

[builder]
adapter = "acpx_codex"
model = "gpt-5-codex"
permissions = "full-auto"
timeout_seconds = 1800

[supervisor]
adapter = "litellm"
model = "minimax/MiniMax-M2.5"
api_key_env = "MINIMAX_API_KEY"
max_rounds = 12

[supervisor.visual_evaluator]
adapter = "command"
command = ["{python}", "tools/visual_eval.py", "{input_json}", "{output_json}"]
timeout_seconds = 120

[acceptance_evaluator]
adapter = "litellm"
model = "MiniMax-M2.7-highspeed"
api_key_env = "MINIMAX_API_KEY"
api_base_env = "MINIMAX_ANTHROPIC_BASE_URL"
auto_file_issues = false
min_confidence = 0.85
min_severity = "high"

[daemon]
live_mission_workers = true
```

关键点：

- `[builder]` 决定 mission worker 用什么 agent
- `[supervisor]` 决定每轮 review/decision 用什么模型
- `[supervisor.visual_evaluator]` 决定 round review 前是否额外跑视觉/浏览器检查
- `[acceptance_evaluator]` 决定 round 结束后是否跑独立验收评估，以及是否自动提交 Linear follow-up issue
- `[daemon].live_mission_workers = true` 只是默认值，第一次试跑更推荐直接在命令行加 `--live-mission-workers`

如果你暂时不接视觉检查，这段可以完全省略。

如果你要先做一条真实 smoke 路径，仓库里现在有现成脚本：

```bash
./tests/e2e/supervised_mission_minimax.sh
MINIMAX_API_KEY=$MINIMAX_API_KEY ./tests/e2e/supervised_mission_minimax.sh --full
```

---

## 3. 首选流程：从 Dashboard 启动 Mission

现在推荐的入口已经不是“先改文件、再跑一串 CLI”，而是：

```text
Dashboard -> Mission Launcher -> Approve & Plan -> Create/Bind Linear -> Launch
```

打开 dashboard：

```text
http://127.0.0.1:8420
```

然后点击右上角：

- `+ New Mission`

这会打开 `Mission Launcher` 侧栏。按这个顺序做：

1. `Refresh Readiness`
   - 确认 `Config / Dashboard / Linear / Planner / Builder` 都 ready
2. 填写：
   - `Mission title`
   - `Mission id` 可选
   - `Intent`
   - `Acceptance criteria`
   - `Constraints`
3. 点击 `Create Draft`
   - 会自动创建 `docs/specs/<mission_id>/spec.md`
4. 点击 `Approve & Plan`
   - 会自动冻结 mission 并生成 `plan.json`
5. 二选一：
   - `Create Linear Issue`
   - `Bind Existing Issue`
6. 点击 `Launch Mission`
   - dashboard 会调用 launcher API，把 mission 送进 lifecycle/daemon 流程

这条路径是现在推荐的最小可视化 E2E。

## Workflow Replay E2E vs Fresh Acpx Mission E2E

这两条链路现在必须分开理解：

- `Workflow Replay E2E`
  - 基于已有 mission / round / artifacts
  - 重点证明 dashboard/operator workflow 可稳定操作、可回放、可修复
- `Fresh Acpx Mission E2E`
  - 从一个全新 mission 开始
  - 重点证明 fresh bootstrap -> approve/plan -> launch -> runner pickup -> fresh round -> post-run replay

不要把 replay 成功误认为 fresh pipeline 已证明。

### 什么时候跑 Workflow Replay E2E

适合：

- dashboard/operator console 新交互刚修完
- acceptance harness 新 campaign 或 selector contract 刚改完
- 想复验一个已知 mission surface 是否还能稳定通过

### 什么时候跑 Fresh Acpx Mission E2E

适合：

- 想证明一条 brand-new mission 能真实跑通
- 想验证 launcher / lifecycle / daemon / builder / post-run acceptance 的整链闭环
- 准备把 workflow proof 提升成 pipeline freshness proof

第一条可执行脚本：

```bash
./tests/e2e/fresh_acpx_mission_smoke.sh
MINIMAX_API_KEY=$MINIMAX_API_KEY MINIMAX_ANTHROPIC_BASE_URL=$MINIMAX_ANTHROPIC_BASE_URL \
  ./tests/e2e/fresh_acpx_mission_smoke.sh --full
```

---

## 4. CLI 回退流程：手动创建一个可试跑的 Mission

### 4.1 创建 mission

```bash
uv run --python 3.13 spec-orch mission create "Supervisor E2E Smoke" --id supervisor-e2e-smoke
```

会生成：

```text
docs/specs/supervisor-e2e-smoke/spec.md
```

### 4.2 编辑 spec

建议第一条真实试跑把范围压小：

- 只改 1-2 个文件
- 只包含 1-2 条 acceptance criteria
- 不要跨多个子系统

### 4.3 approve + plan

```bash
uv run --python 3.13 spec-orch mission approve supervisor-e2e-smoke
uv run --python 3.13 spec-orch plan supervisor-e2e-smoke
uv run --python 3.13 spec-orch plan-show supervisor-e2e-smoke
uv run --python 3.13 spec-orch pipeline supervisor-e2e-smoke
```

确认 `plan.json` 已经出现：

```text
docs/specs/supervisor-e2e-smoke/plan.json
```

---

## 5. 让 Daemon 识别这是一个 Mission

daemon 识别 mission 的规则是：

- issue description 里写了 `mission: <mission_id>`
- 且 `docs/specs/<mission_id>/plan.json` 存在

所以创建一个 Linear issue，description 里至少带这一段：

```text
mission: supervisor-e2e-smoke
```

第一次试跑不要搞复杂自动流转，直接让这个 issue 进入 daemon 会消费的状态。

---

## 6. 启动 E2E 试跑

第一次一定前台跑，不要后台化：

```bash
uv run --python 3.13 spec-orch daemon start --live-mission-workers
```

这条命令会同时给你两层信息：

- daemon 自己的推进日志
- mission worker 的实时 activity 流

如果一切接通，执行路径会是：

```text
daemon
  -> detect mission
  -> dispatch wave packets
  -> workers run in packet workspaces
  -> supervisor reviews round artifacts
  -> decision: continue / retry / replan_remaining / ask_human / stop
```

---

## 7. 一次试跑里到底该看什么

把观测分成三层，不要把所有文件混在一起看。

如果你同时开着 dashboard，可以按下面这三个 surface 看：

- `Inbox`
  - 先看有没有 `approval` / `paused` / `failed`
- `Mission Detail`
  - 看当前 packet、latest round、transcript 过滤后的时间线
- `Acceptance`
  - 看独立 acceptance evaluator 的结论、findings、以及是否提了 follow-up issue
- `Context Rail`
  - 看 `Approval workspace`、`Transcript inspector`、artifact path
  - approval request 出现时，可以直接点击 `Approve` / `Request revision` / `Ask follow-up`

换句话说：

- CLI 更适合原始排查
- dashboard 更适合 operator 视角的持续监督
- 当 round 进入 `ask_human` 时，优先从 dashboard 的 approval workspace 介入；它会把预设 guidance 直接写回 mission 的 `/btw` 注入链路

### 7.1 Layer 1: 原始 worker 输出

路径：

```text
docs/specs/<mission_id>/workers/<packet_id>/telemetry/incoming_events.jsonl
```

这层回答的是：

- Codex/ACPX 实际吐了哪些事件
- 有没有 tool call
- 有没有 agent message
- 有没有中间 result/error

直接看：

```bash
uv run --python 3.13 spec-orch mission logs <mission_id> <packet_id> --raw
```

也可以手动 tail：

```bash
tail -f docs/specs/<mission_id>/workers/<packet_id>/telemetry/incoming_events.jsonl
```

### 7.2 Layer 2: orchestrator / normalized events

路径：

```text
docs/specs/<mission_id>/workers/<packet_id>/telemetry/events.jsonl
```

这层回答的是：

- packet 什么时候 started
- packet 什么时候 completed
- builder 事件怎么被标准化
- 失败时 orchestrator 记录了什么

直接看：

```bash
uv run --python 3.13 spec-orch mission logs <mission_id> <packet_id> --events
```

按事件过滤：

```bash
uv run --python 3.13 spec-orch mission logs <mission_id> <packet_id> --events --filter mission_packet_completed
```

### 7.3 Layer 3: 面向人类的活动流

路径：

```text
docs/specs/<mission_id>/workers/<packet_id>/telemetry/activity.log
```

这层最适合快速理解当前 packet 在干什么。

直接看：

```bash
uv run --python 3.13 spec-orch mission logs <mission_id> <packet_id>
```

实时看：

```bash
tail -f docs/specs/<mission_id>/workers/<packet_id>/telemetry/activity.log
```

### 7.4 Layer 4: round 决策层

路径：

```text
docs/specs/<mission_id>/rounds/round-XX/
```

每轮最重要的三个文件：

- `round_summary.json`
- `round_decision.json`
- `supervisor_review.md`

这一层回答的是：

- 本轮跑了哪些 packet
- supervisor 怎么理解结果
- 为什么继续、重试、改计划、暂停

建议按这个顺序看：

1. `round_summary.json`
2. `supervisor_review.md`
3. `round_decision.json`

---

## 8. 推荐的一次完整观测姿势

第一次真实试跑，推荐开 3 个终端。

### 终端 A

跑 daemon：

```bash
uv run --python 3.13 spec-orch daemon start --live-mission-workers
```

### 终端 B

盯当前最关键 packet：

```bash
tail -f docs/specs/<mission_id>/workers/<packet_id>/telemetry/activity.log
```

或者：

```bash
uv run --python 3.13 spec-orch mission logs <mission_id> <packet_id> --events
```

### 终端 C

盯 round 目录：

```bash
watch -n 2 'ls -R docs/specs/<mission_id>/rounds | tail -40'
```

如果不用 `watch`，就每轮结束后手动打开：

```bash
cat docs/specs/<mission_id>/rounds/round-01/round_decision.json
cat docs/specs/<mission_id>/rounds/round-01/supervisor_review.md
```

---

## 9. 如何判断这次 E2E 是成功的

最小成功标准不是“功能做完了”，而是下面这条链路成立：

1. daemon 正确识别 issue 是 mission
2. wave packet 被 dispatch 到独立 worker workspace
3. worker telemetry 落盘完整
4. supervisor 读到 artifacts 并产出 `round_decision.json`
5. daemon 按 decision 继续下一轮或暂停

如果你想做更严格验收，再加两条：

6. verification 全通过
7. `supervisor_review.md` 的判断与你人工判断一致

---

## 10. 怎么把可观测性保持好

真正的问题通常不是“没有日志”，而是日志结构散、现场丢失、或者第一时间没保住。建议固定这几条纪律。

### 10.1 第一轮永远前台跑

不要一上来后台化 daemon。前台跑有两个价值：

- 你能立刻看到卡在哪一层
- `--live-mission-workers` 会把 worker activity 直接打到终端

建议：

```bash
uv run --python 3.13 spec-orch daemon start --live-mission-workers
```

### 10.2 永远保留 packet workspace

观测的核心现场在：

```text
docs/specs/<mission_id>/workers/<packet_id>/
```

不要在问题没看清前清理这些目录。这里面至少要保住：

- `builder_report.json`
- `telemetry/incoming_events.jsonl`
- `telemetry/events.jsonl`
- `telemetry/activity.log`

### 10.3 出问题先分层，不要直接看富文本总结

排查顺序建议固定：

1. `activity.log`
2. `events.jsonl`
3. `incoming_events.jsonl`
4. `round_summary.json`
5. `supervisor_review.md`

也就是先看机器执行事实，再看 supervisor 的解释。

### 10.4 每个 mission 先跑小 plan

一次上来就给 10 个 packet，会把观测面直接放大。第一次试跑建议：

- 1 wave
- 1-2 packets
- 小文件改动

这样你更容易看清 round loop 是不是健康。

### 10.5 把 “暂停点” 当成一等信号

如果 `round_decision.json` 出现：

- `ask_human`
- `retry`
- `replan_remaining`

不要只看结论，必须同时看：

- `supervisor_review.md`
- 当前 packet 的 `events.jsonl`
- 当前 packet 的 `activity.log`

因为这里正是调 prompt、调 plan、调 routing 的高价值点。

### 10.6 观测文件优先级

实际调试时，优先级可以固定成：

```text
activity.log > events.jsonl > incoming_events.jsonl > supervisor_review.md
```

原因：

- `activity.log` 最快判断卡住没
- `events.jsonl` 最适合程序化分析
- `incoming_events.jsonl` 最接近原始 agent 输出
- `supervisor_review.md` 最适合复盘，不适合先判 root cause

### 10.7 每轮结束都做一次人工抽样

建议每轮至少人工抽查 1 个 packet：

- 看 raw events
- 看 normalized events
- 看 round decision

这样能尽早发现：

- worker prompt 质量不对
- supervisor 误判
- event 映射不全

---

## 10. 常用命令速查

```bash
# 创建 mission
uv run --python 3.13 spec-orch mission create "Supervisor E2E Smoke" --id supervisor-e2e-smoke

# approve + 生成计划
uv run --python 3.13 spec-orch mission approve supervisor-e2e-smoke
uv run --python 3.13 spec-orch plan supervisor-e2e-smoke
uv run --python 3.13 spec-orch plan-show supervisor-e2e-smoke
uv run --python 3.13 spec-orch pipeline supervisor-e2e-smoke

# 前台启动 daemon，并实时看 mission worker
uv run --python 3.13 spec-orch daemon start --live-mission-workers

# 查看 packet activity
uv run --python 3.13 spec-orch mission logs supervisor-e2e-smoke pkt-1

# 查看 raw worker events
uv run --python 3.13 spec-orch mission logs supervisor-e2e-smoke pkt-1 --raw

# 查看 normalized orchestrator events
uv run --python 3.13 spec-orch mission logs supervisor-e2e-smoke pkt-1 --events

# 手动 tail
tail -f docs/specs/supervisor-e2e-smoke/workers/pkt-1/telemetry/activity.log
tail -f docs/specs/supervisor-e2e-smoke/workers/pkt-1/telemetry/incoming_events.jsonl
```

---

## 11. 推荐试跑顺序

如果你准备拿这个去跑真实任务，建议按这个顺序上量：

1. `1 mission / 1 wave / 1 packet`
2. `1 mission / 1 wave / 2 packets`
3. `1 mission / 多轮 retry/replan`
4. `多个 mission 并行`

不要一上来直接冲多 mission 并发，否则你在调的是系统复杂度，不是在调 supervised mission 本身。
