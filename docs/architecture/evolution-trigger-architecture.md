# 进化管线架构分析：LLM 决策点审计 + 触发模型选型

> 日期: 2026-03-17
> 状态: 分析完成，待讨论决策
> 来源: ClawHub Self-Improving Agent 调研 + spec-orch 代码审计
> 前置文档:
> - [编排大脑设计](orchestration-brain-design.md)
> - [Skill-Driven vs Spec-Driven](skill-driven-vs-spec-driven.md)
> - [ClawHub Self-Improving Agent](https://clawhub.ai/xiucheng/xiucheng-self-improving-agent)
> - [MemRL 论文](https://arxiv.org/abs/2601.03192)
> - [longmans/self-evolve 插件](https://github.com/longmans/self-evolve)

## 一、当前系统 LLM 决策点全景

通过代码审计确认的所有 LLM 调用点：

### 执行管线（Pipeline）— 7 个调用点

| # | 位置 | LLM 上下文来源 | 自动触发? |
|---|------|--------------|----------|
| P1 | `ReadinessChecker._llm_check()` | issue description + evidence_context (历史 run 统计) | 自动 (daemon) |
| P2 | `Planner.plan()` — DRAFT→SPEC | issue + existing spec snapshot | 自动 (advance) |
| P3 | `Planner.answer_questions()` | issue + snapshot with questions | 自动 (advance_to_completion) |
| P4 | Builder 外部进程 (codex/opencode) | PREAMBLE + builder_prompt | 自动 |
| P5 | `LLMReviewAdapter._call_llm()` | git diff (<=60k) + task.spec.md (<=10k) | 自动 (若启用 llm reviewer) |
| P6 | `Scoper.scope()` | mission spec + constraints + file_tree + evidence + hints | 自动 (lifecycle) |
| P7 | `Conductor.classify_intent()` | 最近 6 轮对话 + 待分类消息 | 自动 (但接口不匹配，退回规则分类) |

### 进化管线（Evolution）— 5 个调用点

| # | 位置 | LLM 上下文来源 | 自动触发? |
|---|------|--------------|----------|
| E1 | `PromptEvolver.evolve()` | active prompt + 成功率统计 | **仅 CLI** |
| E2 | `HarnessSynthesizer.synthesize()` | 现有 contracts + 最近 N 次 failure 数据 | **仅 CLI** |
| E3 | `PlanStrategyEvolver.analyze()` | plan outcomes + evidence summary | **仅 CLI** |
| E4 | `PolicyDistiller.distill()` | 重复任务模式 | **仅 CLI** |
| E5 | `IntentEvolver.evolve()` | classifier prompt + 错误模式 | **仅 CLI (且接口不匹配)** |

**关键发现：执行管线基本自动化，进化管线完全手动。每个 LLM 调用点各自构建局部上下文，没有统一的上下文总线。**

### 上下文来源图

```
                                report.json
                                    │
                    ┌───────────────┼───────────────────┐
                    ▼               ▼                   ▼
              EvidenceAnalyzer  deviations.jsonl   builder_events.jsonl
                    │               │                   │
         ┌─────────┼──────────┐    │              ┌────┘
         ▼         ▼          ▼    ▼              ▼
    PlanStrategy  Policy    Harness          PromptEvolver
    Evolver(E3)   Distiller Synthesizer      (E1)
                  (E4)      (E2)
         │         │          │                   │
         ▼         ▼          ▼                   ▼
    scoper_hints  policies/  compliance.    prompt_history
    .json         *.py       contracts.yaml  .json
```

每个 Evolver 只看自己需要的数据切片。没有全局上下文窗口。

### 已知的接口缺陷

1. **`IntentEvolver.evolve()`** 使用 `planner.invoke()`，但 `LiteLLMPlannerAdapter` 未实现此方法，会触发 `AttributeError`。
2. **`Conductor.classify_intent()`** 使用 `planner.chat_completion()`，同样未实现，退回到纯规则分类。
3. **`record_flow_transition()`** 是 stub 函数（空函数），Flow Evolver 无法获取升降级数据。

## 一点五、当前决策点 authority inventory

为了后续接入 `decision_core`，当前决策点先按 authority 分三类：

### rule_owned

- flow router 的静态降级与分类回退
- gate / verification 的规则判定
- readiness / config / environment 类确定性检查

### llm_owned

- supervisor round review 与 `RoundDecision`
- scoper / planner / review adapter 等模型裁量节点
- evolver 分析与蒸馏节点

### human_required

- `ask_human` 触发的 approvals queue
- 需要 operator 明确批准或澄清的 launch / rollout 决策

这一步的目的不是重新设计整个系统，而是先把“谁在做决定”从运行日志和对象边界上分清。

## 二、外部框架对比

### ClawHub / OpenClaw 的模型："个体 Agent 的自我改善"

ClawHub 的 Self-Improving Agent 是一个**单 Agent 级别**的自我改善系统：

- **SOUL.md** — Agent 的"宪法"，定义人格、价值观、行为边界。每次推理开始时读取。
- **improvement_log.md** — 对话质量分析日志，记录错误、知识缺口、最佳实践。
- **self-evolve 插件** (longmans/self-evolve) — 基于 [MemRL 论文 (arXiv 2601.03192)](https://arxiv.org/abs/2601.03192)，用强化学习信号驱动 episodic memory 的持续更新。

核心循环：`对话 → 质量评估 → 记录 learnings → 晋升到 SOUL.md → 下次对话更好`

### spec-orch 的模型："编排系统的自我进化"

spec-orch 是一个**系统级别**的自我进化编排器：

- **7 个 Evolver** — 分别进化不同维度（prompt、plan strategy、compliance rules、policies、intent、flow、gate）
- **4 层 Memory** — Working / Episodic / Semantic / Procedural
- **Evidence 驱动** — 每次 run 产生结构化制品（report.json、deviations.jsonl），作为进化输入

核心循环：`执行 → Evidence → EvidenceAnalyzer → 7 个 Evolver 各自优化 → 下次执行更好`

### 核心对比

| 维度 | ClawHub Self-Improving | spec-orch Evolution |
|------|----------------------|-------------------|
| **进化粒度** | 单 Agent 对话质量 | 系统级编排策略（prompt、plan、gate、compliance） |
| **进化机制** | RL Q-value + embedding 检索 | LLM 分析 + A/B 测试 + 统计阈值 |
| **存储** | Markdown 文件 (SOUL.md, learnings) | JSON + YAML + Markdown |
| **自动化程度** | Hook 驱动，自动触发 | **CLI 手动触发为主，自动化缺口大** |
| **学术基础** | MemRL (arXiv 2601.03192) | SEW, MetaAgent, Live-SWE-agent, VIGIL |
| **开放性** | ClawHub Skill 生态，可安装 | 封闭实现，内嵌于 Python 代码 |

### 值得借鉴的

1. **自动触发机制** — self-evolve 通过 Hook (`before_prompt_build`, `agent_end`) 自动触发，我们的进化管线完全手动
2. **SOUL.md 式系统人格锚定** — 我们的行为准则散落在 `gate.policy.yaml`、`compliance.contracts.yaml`、各 adapter PREAMBLE、`flow_mapping.yaml` 中
3. **MemRL Q-value 检索** — 两阶段检索（语义相似度 + Q-value 排序）比我们的纯 tag-based recall 更精准

### 不值得借鉴的

1. **对话质量分析** — spec-orch 不是对话系统，质量指标已有结构化度量
2. **Agent 自我修改人格文件** — 编排器自改 gate policy 有安全退化风险
3. **RL Q-value 在 SWE 管线中未验证** — 多步 pipeline 的 credit assignment 问题更复杂

## 三、三种进化触发模型的 Trade-off 分析

### 模型 A: Hook 驱动（类 ClawHub self-evolve）

```
run_issue() 完成
    │
    ├──[hook: post_run]──→ PromptEvolver.record_run()
    │                      auto_promote_if_ready()
    │
    ├──[hook: every_n_runs]──→ HarnessSynthesizer.synthesize()
    │                          PlanStrategyEvolver.analyze()
    │
    └──[hook: post_gate]──→ MemoryService.record_gate_result()
                            FlowTransitionEvent → Memory
```

| 优点 | 缺点 |
|------|------|
| 实现简单，改动小 | 触发点和调用链写死在代码里 |
| 确定性——每次 run 后一定执行 | 不能跳过/延迟/合并 evolution |
| 成本可预测 | 灵活性低：新增 Evolver 需要改代码 |
| 不引入新的 LLM 调用 | 没有"智能判断是否值得进化" |

### 模型 B: Agent 驱动（类 Pimono/全局大脑）

```
run_issue() 完成
    │
    └──→ EvolutionAgent.think()
           │
           │ context: 全部 run history + 全部 evolver 状态 + 系统配置
           │
           ├── "PromptEvolver 最近 5 次 run 都成功了，值得晋升"
           ├── "HarnessSynthesizer 上次合成的规则误报率高，暂不触发"
           ├── "发现新的 failure pattern，优先调 PolicyDistiller"
           └── "当前处于低负载时段，可以跑完整 evolution cycle"
```

| 优点 | 缺点 |
|------|------|
| 最灵活——Agent 自主决定做什么 | 每次 run 后多一个 LLM 调用（成本增加） |
| 能做"是否值得进化"的智能判断 | Agent 推理不确定，可能遗漏关键进化 |
| 自然支持优先级排序和冲突处理 | 需要构建全局上下文（可能很大） |
| 新增 Evolver 只需更新 Agent prompt | 更难审计和 debug |
| 与 Conductor 架构一致（LLM 做路由） | "Agent 决定如何改进自己"有安全隐患 |

### 模型 C: 配置驱动（spec-orch.toml policy）

```toml
[evolution]
auto_record_run = true
prompt_auto_promote = true
synthesize_every_n_runs = 10
strategy_analyze_every_n_runs = 20
policy_distill_enabled = false

[evolution.gates]
min_runs_before_evolve = 5
max_evolution_cost_per_cycle_usd = 0.50
```

```
run_issue() 完成
    │
    └──→ EvolutionPolicy.evaluate(config, run_stats)
           │
           ├── auto_record_run=true → PromptEvolver.record_run()
           ├── run_count % 10 == 0 → HarnessSynthesizer.synthesize()
           ├── run_count % 20 == 0 → PlanStrategyEvolver.analyze()
           └── policy_distill_enabled=false → skip
```

| 优点 | 缺点 |
|------|------|
| 用户可控——改 toml 即可调整策略 | 没有"智能判断"，只是定时触发 |
| 确定性 + 灵活性的折中 | 配置项可能膨胀 |
| 不引入新的 LLM 调用 | 不能根据 run 结果动态调整策略 |
| 成本上限可配 (max_cost) | 配置不当可能导致进化过于激进或不足 |
| 对 Daemon 模式天然友好 | — |

### 模型对比总结

| 维度 | A: Hook | B: Agent | C: Config |
|------|---------|----------|-----------|
| **灵活性** | 低 | 最高 | 中 |
| **确定性** | 最高 | 低 | 高 |
| **成本** | 最低 | 最高（每次 run 多一个 LLM call） | 低 |
| **实现复杂度** | 低 | 高 | 中 |
| **新增 Evolver 成本** | 改代码 | 改 Agent prompt | 改代码 + 改 toml schema |
| **安全性** | 安全（代码控制） | 有风险（Agent 自主决策） | 安全（配置控制） |
| **审计性** | 好 | 差 | 好 |

### 建议路径（待讨论）

**Phase 1: C（配置驱动）先行** — 解决"进化管线完全手动"的核心问题，实现最小可用自动化。
**Phase 2: 评估 B（Agent 驱动）的必要性** — 积累足够的自动进化数据后，判断"智能调度"是否有价值。
**Phase 3: 如果 B 有价值，在 C 的基础上增加 Agent 决策层** — C 作为 fallback/safety net，Agent 作为增强。

## 四、与 Pimono Agent 模式的根本区别

| 维度 | Pimono / Agent 模式 | spec-orch 当前 | spec-orch + Model C |
|------|-------------------|---------------|---------------------|
| **决策者** | 一个 LLM 在 thinking loop 中决定所有事 | 代码 if/else 决定 | toml config + 代码 policy engine |
| **上下文** | 全局窗口（Agent 看到一切） | 12 个局部切片（各 Evolver 各看各的） | 同现状，但触发时机可配 |
| **改行为** | 改 prompt / skill 描述 | 改 Python 代码 | 改 toml（触发策略）+ 改代码（Evolver 逻辑） |
| **成本** | 每步都调 LLM | 固定 12 个点 | 固定 12 个点，频率可控 |
| **适合场景** | 探索型任务、不确定需求 | 固定工程流水线 | 固定流水线 + 可配的持续改进 |

关键差异：Pimono 的核心假设是"LLM 足够聪明，可以在全局上下文中做出比人类规则更好的调度决策"。
spec-orch 的核心假设是"工程流水线需要确定性，LLM 只在特定节点做特定决策"。

这两个假设并不矛盾——可以共存。Model C 先固化"什么时候进化"的策略，
积累数据后再评估是否需要 Agent 来做"进化什么、如何进化"的智能决策。

## 五、待创建的 Linear Issues

| Issue | 类型 | 前置 |
|-------|------|------|
| Epic: 进化管线自动化与架构选型 | Epic | — |
| 分析文档: LLM 决策点审计 + 三种模型 trade-off | docs | — (本文档) |
| spec-orch.toml `[evolution]` schema 设计 | feature | 分析文档 |
| EvolutionPolicy engine: 按配置触发 Evolver | feature | schema 设计 |
| 修复 `record_flow_transition` stub | bugfix | — |
| 修复 IntentEvolver / Conductor 接口不匹配 | bugfix | — |
| 评估 ORCHESTRATOR.md 概念 | research | — |
| 评估 MemRL Q-value for Memory recall | research | — |
