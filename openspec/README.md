# OpenSpec Migration: SON-100 + SON-106

将 Epic SON-100（混合架构）和 SON-106（编排大脑）的旧 issue 转为规范化的
spec-driven 工作流。

## Issue → Change 映射

| Change | 名称 | 源 Issues | 类型 | 依赖 |
|--------|------|-----------|------|------|
| 01 | scaffold-flow-engine | SON-107, SON-108, SON-109 | feature | 无 |
| 02 | conductor-fork | SON-110 | feature | 01 |
| 03 | muscle-evolvers | SON-111, SON-112, SON-113, SON-114 | feature | 01 |
| 04 | conductor-lifecycle | SON-98, SON-102 | feature | 02 |
| 05 | spec-discovery-paths | SON-101, SON-104 | feature | 无 |
| 06 | flexible-orchestration | SON-103, SON-105 | feature + infra | 01 |

## 未纳入 Change 的 Issue

| Issue | 原因 | 建议处理 |
|-------|------|---------|
| SON-97 | 架构探索/讨论，已沉淀为文档 | 标记 Done，产出即 sdd-landscape-and-positioning.md |
| SON-106 (Epic) | 元 issue，子 issue 已全部映射 | 跟踪用，不转 change |
| SON-100 (Epic) | 元 issue，子 issue 已全部映射 | 跟踪用，不转 change |

## 执行顺序建议

```
Phase A (基础设施):  01-scaffold-flow-engine
Phase B (并行):      02-conductor-fork  |  05-spec-discovery-paths
Phase C (依赖 A):    03-muscle-evolvers  |  06-flexible-orchestration
Phase D (依赖 B):    04-conductor-lifecycle
```

## 目录结构

每个 change 目录包含：
- `prd.md` — 轻量 PRD
- `proposal.md` — 变更提案
- `spec.md` — 需求规格（requirement + scenario）
- `design.md` — 技术设计（仅跨模块变更时提供）
- `tasks.md` — 可执行 checklist
