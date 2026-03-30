# SON-265 Dashboard Critique Rubric Design

## Goal

把 `SON-264` 的 bounded exploratory runtime 从“能跑 exploratory”推进到“能稳定产出高质量、可讨论的人类视角 critique”。

第一版明确只服务于 dashboard / operator console，不追求跨页面通用。

## Why SON-264 Is Not Enough

`SON-264` 已经证明：

- harness 可以 bounded 地探索 dashboard surface
- evaluator 可以在 runtime 中提出至少一类真实 UX critique
- internal 和 fresh ACPX 两条 exploratory 闭环都能跑通

但它还不够：

- critique 仍偏单点补丁，主要围绕 transcript packet discovery
- evaluator 仍然带有明显的 verification bias
- 当前输出结构更像 “finding / proposal” 的变体，而不是 dashboard operator review 语言
- 如果没有明显的 broken flow，模型仍容易滑回 “页面能跑，所以没问题”

`SON-265` 的目标不是把 exploratory 做得更广，而是让它先变得更像一个有判断力的 operator。

## Product Question

`SON-265` 要回答的问题是：

> 即使 dashboard 表面上可操作，一个第一次接手 mission 的 operator 是否能快速理解：
>
> - 我现在在哪个 surface
> - 下一步应该看哪里
> - 哪个证据最重要
> - 为什么这个 surface 值得信任或值得继续追问

这和 `Workflow Acceptance` 的问题不同：

- workflow acceptance: `can the flow complete?`
- exploratory acceptance: `does the product make sense while the flow completes?`

## Scope

第一版 rubric 只覆盖 dashboard / operator console 的以下体验层：

1. surface orientation
2. evidence discoverability
3. terminology clarity
4. task continuity
5. operator confidence / trust signaling

第一版明确不做：

- 跨产品通用 taxonomy
- 纯视觉 polish critique
- accessibility / performance audit
- broad social or operator feedback ingestion

## Dashboard-Specific Critique Axes

### 1. Surface Orientation

判断 operator 进入一个 surface 后，是否能快速回答：

- 当前是 overview、transcript、approvals、acceptance、visual、costs 中的哪一类
- 这个 surface 的主要任务是什么
- 关键对象是什么：mission、packet、approval、artifact 还是 issue

典型问题：

- tab 虽然切换成功，但页面主区没有明显说明当前上下文
- route 已变，但主要内容没有突出说明“为什么我现在在这里”
- context rail 和主面板表达的优先级相互冲突

### 2. Evidence Discoverability

判断 operator 是否能自然发现“下一层有用证据在哪里”。

重点看：

- transcript 中 packet entry 是否显式
- acceptance / visual / costs 是否能顺利形成 evidence ladder
- empty-state 是否说明“没有看到内容时下一步该做什么”

典型问题：

- filter 可操作，但 packet selection 不显眼
- surface 存在数据，但 operator 不知道从哪里进入
- internal-route 按钮存在，但语义太弱，像实现细节不是用户任务

### 3. Terminology Clarity

判断 dashboard 的命名是否以 operator 任务为中心，而不是以实现细节为中心。

重点看：

- button / tab / badge / labels 是否表达用户意图
- technical terms 是否缺少业务解释
- 同一个概念是否被多个名称表达

典型问题：

- “review”, “acceptance”, “decision”, “approval” 等概念边界混淆
- context rail 用的是工件语言，主区用的是 operator 语言，来回切换成本高

### 4. Task Continuity

判断 operator 从一个 surface 切换到相邻 surface 时，是否保持连续心智模型。

重点看：

- 从 mission overview 进入 deeper evidence 时是否自然
- 从 transcript / visual / costs 回到 decision surface 时是否保留上下文
- launcher、detail pane、context rail 是否形成连续工作流

典型问题：

- 页面能切，但切完像进入另一个产品
- 没有明确“下一步建议动作”
- 关键信息必须通过多次试探才能拼起来

### 5. Operator Confidence / Trust Signaling

判断页面是否给出足够信号，让 operator 知道：

- 哪些结论可信
- 哪些信息还只是候选
- 哪个 action 会产生不可逆影响

典型问题：

- 结果状态变化了，但页面没有解释原因
- evidence 足够弱，却表现得像最终结论
- operator 不清楚“现在是建议、待确认，还是最终判定”

## Evidence Threshold

`SON-265` 不要求所有 critique 都是 hard failure，但也不允许纯主观吐槽。

第一版采用三档证据阈值：

### A. High-confidence critique

满足：

- route / interaction / state transition 证据明确
- expected vs actual 可具体表达
- 问题可重复观察

输出：

- finding
- held proposal 或 direct proposal，取决于 filing policy

### B. Held critique candidate

满足：

- evidence 指向真实 UX friction
- 但问题更偏理解成本 / discoverability / terminology
- 需要 operator judgment 再确认是否值得 filing

输出：

- held finding / held proposal
- 必须附带 route、evidence refs、why-it-matters

### C. Insufficient critique

满足任一：

- 只有模糊直觉，没有 interaction evidence
- 只是单次 flaky timeout
- 没法表达用户任务层的 expected / actual

输出：

- 不直接变成 finding
- summary 说明为什么未达阈值
- recommended next step 给出下一轮该怎么补证据

## Output Shape Direction

`SON-265` 不应该把 exploratory critique 继续压成 workflow 风格的 bug 报告。

建议的第一版输出方向：

- 保留现有 `findings` / `issue_proposals`
- 增加 dashboard-operator 语言：
  - `critique_axis`
  - `operator_task`
  - `why_it_matters`
  - `hold_reason`

如果暂时不扩 schema，至少要在 summary / details / proposal summary 中稳定编码这些字段语义。

## Runtime Expectations

第一版 runtime 成功标准不是“找很多问题”，而是：

1. internal exploratory run 至少能稳定提出 1 条高质量 critique candidate
2. fresh ACPX exploratory run 至少能复现同类 critique，或提出另一条同等级 critique
3. 零 finding 时，summary 必须明确解释：
   - 为什么没形成 critique
   - 还缺什么证据
4. evaluator 不再把 generic browser-error 作为 exploratory 结论的默认落点

## Relationship To SON-266

`SON-265` 负责：

- critique rubric
- evidence threshold
- operator-facing articulation quality

`SON-266` 再负责：

- held queue 的正式产品化
- filing / review / feedback loop

所以第一版 `SON-265` 可以先不引入完整 held queue UI，只要先把 held critique 作为稳定的 evaluator 输出语义跑通。

## Recommended Implementation Slice

第一批实现建议只做三件事：

1. prompt rubric 强化
2. evaluator result normalization / synthesis 强化
3. dashboard dogfood calibration fixture 扩充

先不要：

- 做全站 taxonomy
- 做新的 browser autonomy
- 做 operator feedback capture

## Done When

`SON-265` 第一版可认为完成，当且仅当：

- internal exploratory dashboard pass 能稳定给出高质量 held critique
- fresh ACPX exploratory pass 能稳定给出同级别 critique
- critique 不再只是 transcript 特例，而是能覆盖至少两类 axis
- summary / finding / proposal 文本能被人一眼看懂“这为什么值得改”
