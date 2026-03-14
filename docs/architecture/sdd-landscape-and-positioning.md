# SDD 行业全景与 SpecOrch 定位

> 日期: 2026-03-14
> 来源: 综合 agent-spec 项目研究、SDD 运动分析、spec-orch 实践反思
> Linear: SON-97, SON-98

## 一、SDD (Spec-Driven Development) 行业全景

### 1.1 行业玩家对比

| 产品/项目 | 背景 | 核心思路 | SDD 级别 | 状态 |
|-----------|------|---------|----------|------|
| **GitHub Spec Kit** | GitHub 官方开源 | 四阶段门控: Specify → Plan → Tasks → Implement | Level 1-2 | 开源, 76K+ stars |
| **AWS Kiro** | Amazon IDE | EARS 需求语法 + Given/When/Then 验收标准 | Level 2 | Preview, $19-200/月 |
| **Tessl** | 前 Snyk CEO 创办 | Spec-as-Source: spec 是源码，代码是生成物 | Level 3 | 封测, Spec Registry 开放 |
| **agent-spec** | 张汉东 | AI 原生 BDD/spec 验证工具 | Level 2-3 | 开源, 62 stars |
| **SuperSpec** | 社区项目 | Kubernetes 风格 YAML + BDD 评估 | Level 1 | 开源 |
| **specs.md** | 社区项目 | Vendor-agnostic spec 格式标准 | Level 2 | 开源 |
| **SpecOrch** | 本项目 | 自进化交付编排 + Gate 层 + 闭环改进 | Level 2 + Evolution | 开发中 |

### 1.2 Martin Fowler / ThoughtWorks 的三级分类

| 级别 | 定义 | 代表 | spec-orch 位置 |
|------|------|------|----------------|
| **Level 1: Spec-First** | 先写 spec 再写代码，完成后 spec 可能不管 | GitHub Spec Kit 基础用法 | 已超越 |
| **Level 2: Spec-Anchored** | spec 是活文档，代码变更时同步更新 | Kiro, Spec Kit 全功能 | **当前位置** |
| **Level 3: Spec-as-Source** | spec 是唯一源码，代码是生成物 | Tessl | 理想方向（需模型能力支撑） |

### 1.3 Spec vs Skill 的本质区分

来自 agent-spec 项目的研究（张汉东）：

- **Skill** = HOW（怎么做）— 可打包、传播、复用的执行知识
- **Spec** = WHAT + WHY（做什么、为什么做）— 需要理解、判断、品味

核心洞察：Skill 是可选的加速器（有更好，没有也行），Spec 是必需的方向盘（没有它 AI 不知道往哪开）。agent-spec 用一个视频证明了这一点——仅凭 BDD spec，没用任何 skill 文件，Claude Code 就生成了完整的视频代码。

但这个论断有其局限性（见第三节）。

## 二、美诺悖论与 Spec 发现路径

### 2.1 美诺悖论的 AI 版本

> 你必须已经理解一个东西，才能精确地要求 AI 帮你处理它。
> 但你来找 AI，恰恰因为你还不理解。

这个悖论解释了为什么"写 spec 付出的能量还是很多的"——写 spec 的过程本质是**认知澄清**过程。

### 2.2 六条化解路径与 SpecOrch 映射

| 路径 | 含义 | SpecOrch 对应 | 状态 |
|------|------|--------------|------|
| 1. 对话式发现 | 聊天→收敛→隐式 spec | **Conductor** (Explore→Crystallize) | PR #39 已合并 |
| 2. Spec 模板库 | 选模板→填空→可执行 spec | mission template (部分) | 可增强 |
| 3. 翻译者服务 | 专家→精确 spec | DMA 角色 (依赖 LLM 上下文) | 部分 |
| 4. 示例反推 | "我要类似这个"→AI 反推 spec | **未实现** | 高价值方向 |
| 5. 渐进精化 | v0.1→v0.2→v0.3 螺旋上升 | 用户实际工作流 (未系统化) | 可增强 |
| 6. AI 自生成+人审批 | AI 草拟→人说对/不对 | Conductor propose→approve | PR #39 已合并 |

## 三、文章盲区与实战校正

### 3.1 "Spec > Skill" 的局限

文章核心论断"Spec 比 Skill 更重要"在理论上成立，但在实践中有三个盲区：

**盲区 1: Spec 解决方向，不解决质量**

> Spec 给了一个质量上界，但实际质量还取决于模型能力、context window 管理、
> 中间检查点、测试覆盖率。"spec 也不一定能保证质量"是真实的实战体感。

**盲区 2: Spec 深度依赖模型能力**

Tessl 的 Spec Registry（10,000+ 预置 spec）就是为了弥补这个缺口——模型在执行 spec 时需要更好的上下文。据称性能提升 3.3x。Spec 写得好只解决了方向问题，模型是否能精确执行仍然是独立变量。

**盲区 3: 流程僵化的代价**

spec-orch 的实践暴露了一个具体问题：开发者在验收阶段提出新需求，系统无法动态分流。纯 Spec-Driven（硬编码 pipeline）的灵活性不足以应对真实开发中的意图漂移。

### 3.2 我们的实战发现

| 发现 | 详情 | 启示 |
|------|------|------|
| DMA 跳过流程 | Conductor Agent 开发中跳过了 Linear Issue 创建 | 流程约束不能只靠上下文，需要机器强制 |
| CC 新实例"又干净又简单" | 粗粒度任务直接起新 CC 实例比复杂编排更实用 | spec-orch 的价值在跨 session 连续性，不是单 session 替代 |
| Quality 不稳定 | planning with files 跑 2 天可以，但质量波动大 | Spec 是必要条件，不是充分条件 |
| 用户 CC 工作流已经是 SDD | design → planning → phase coding = Spec-Anchored Level 2 | spec-orch 应增强而非替代这个工作流 |

## 四、SpecOrch 在 SDD 光谱上的定位

```
                    灵活性（对话/探索）
                         ▲
                         │
          Vibe Coding ●  │
                         │
            CC 裸跑 ●    │
                         │
        CC + Skills ●    │  ● Conductor (spec-orch 新增)
                         │
     CC + Planning  ●    │     ● Kiro steering
        with Files       │
                         │        ● spec-orch (当前核心)
      用户 CC 工作流 ●   │
                         │           ● GitHub Spec Kit
                         │
                         │              ● Tessl (Spec-as-Source)
                         │
                         │                 ● agent-spec (BDD 纯粹派)
                         └──────────────────────────────────────→
                                    结构性（spec/约束）
```

### SpecOrch 独特价值（vs 行业玩家）

| 维度 | Spec Kit / Kiro / Tessl | SpecOrch |
|------|------------------------|----------|
| Gate 层 | 无 | 结构化多条件门禁 (唯一) |
| 自进化 | 无 | Evidence→Rules→Prompts→Policies 闭环 (唯一) |
| Memory | 无 | 跨 session 知识连续性 |
| 意图路由 | Kiro steering (有限) | Conductor 渐进形式化 |
| 审计链路 | 部分 | 全链路: spec→plan→build→gate→retro |

### SpecOrch 不应做什么

与 Spec Kit / Kiro / Tessl 重叠的部分无需重做：
- 不需要自创 spec 格式（兼容行业标准）
- 不需要做 Spec Registry（Tessl 已有 10K+）
- 不需要做 IDE 插件（Kiro 已做）

## 五、"Talk Freely, Execute Strictly" — 混合架构

### 5.1 核心原则

> 对话层应像跟同事聊天一样灵活。
> 执行层应像 CI/CD pipeline 一样严格。
> Conductor 是两者之间的桥梁。

### 5.2 三层架构

```
┌─────────────────────────────────────────────────┐
│  Layer 1: Flexible Interaction (Skill-Driven)   │
│  ● Conductor Agent — intent classification       │
│  ● Conversational spec discovery (6 paths)       │
│  ● Dynamic work item creation & drift detection  │
│  描述为 Skill，可快速调整无需改代码              │
└─────────────────┬───────────────────────────────┘
                  │ progressive formalization
┌─────────────────▼───────────────────────────────┐
│  Layer 2: Structured Execution (Spec-Driven)    │
│  ● Approve → Plan → Promote → Execute → Retro   │
│  ● Gate 门禁 + Compliance 合规检查               │
│  ● Evidence 收集 + 审计链路                      │
│  确定性保证，可测试可审计                        │
└─────────────────┬───────────────────────────────┘
                  │ evidence feedback
┌─────────────────▼───────────────────────────────┐
│  Layer 3: Closed-Loop Evolution                  │
│  ● Evidence → Rules → Prompts → Policies         │
│  ● Memory 跨 session 知识连续性                  │
│  每次运行改进下一次                              │
└─────────────────────────────────────────────────┘
```

### 5.3 与行业方案对比

| 方案 | Spec Kit | Kiro | Tessl | SpecOrch |
|------|----------|------|-------|----------|
| Layer 1 | 无 | steering (有限) | 无 | Conductor |
| Layer 2 | Specify→Plan→Tasks→Implement | EARS→Design→Tasks | Spec-as-Source | Approve→Plan→Promote→Execute→Gate |
| Layer 3 | 无 | 无 | Spec Registry (外部) | Evidence→Evolution (内生) |
| 闭环 | 否 | 否 | 部分 | **是** |

## 六、下一步方向

### 短期（务实）
1. 把 Conductor 在实际使用中跑起来，收集 intent 分类准确率
2. 建立 Spec 模板库——模板化已有 spec
3. DMA 流程检查改用 Skill/Hook 而非硬编码

### 中期（架构）
4. 观察 Spec Kit / Kiro / Tessl 演进，考虑兼容其 spec 格式
5. 实现路径 4（示例反推 spec）
6. 将 pipeline 步骤描述为 Skill，用 Conductor 编排

### 长期（等模型进步）
7. Spec-as-Source (Level 3) 当模型执行能力足够稳定时推进
8. AI 自生成 Spec + 人类审批 作为默认交互模式

## References

- [agent-spec](https://github.com/ZhangHanDong/agent-spec) — AI-native BDD/spec verification
- [GitHub Spec Kit](https://github.com/github/spec-kit) — 4-phase SDD toolkit
- [AWS Kiro](https://kiro.directory) — EARS-based agentic IDE
- [Tessl](https://tessl.io) — Spec-as-Source platform + Spec Registry
- [Martin Fowler: Understanding SDD](https://martinfowler.com/articles/exploring-gen-ai/sdd-3-tools.html) — Three levels of SDD
- [ThoughtWorks: Spec-Driven Development](https://thoughtworks.medium.com/spec-driven-development-d85995a81387) — SDD as 2025 key practice
- Spec vs Skill 深度解析 (PDF, 2026-03-13) — 美诺悖论 + SDD 运动全景
- "Talk Freely, Execute Strictly" (arxiv 2603.06394)
