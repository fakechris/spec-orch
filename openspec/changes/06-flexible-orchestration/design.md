# Design: 灵活编排 — Gate 动态检查与多格式导入

> **Change**: 06-flexible-orchestration  
> **类型**: 跨模块技术设计，涉及 Gate 重构、格式解析、合规/门禁职责分离

---

## 1. 为何需要 design

本变更涉及：1）GateService 从硬编码条件改为可扩展 Skill 注册，需定义协议与注册机制；2）多格式 spec 解析，需统一中间模型与 Parser 接口；3）ComplianceEngine 与 Gate 的职责边界需明确。跨模块、多格式、职责重组，故需单独 design 文档。

---

## 2. Gate 动态检查架构

### 2.1 GateCheckSkill 协议

```python
# domain/protocols.py 或 gate_skill_protocol.py
from typing import Protocol
from spec_orch.domain.models import GateInput

class CheckResult:
    passed: bool
    reason: str = ""
    condition_id: str

class GateCheckSkill(Protocol):
    id: str
    description: str
    def run(self, gate_input: GateInput) -> CheckResult: ...
```

### 2.2 内置 Skill 实现

将现有 `evaluate()` 中的每个 if 分支提取为独立函数，封装为 `BuiltinGateCheckSkill`：

```python
# gate_builtin_skills.py
BUILTIN_SKILLS: dict[str, GateCheckSkill] = {
    "spec_exists": SpecExistsSkill(),
    "spec_approved": SpecApprovedSkill(),
    "within_boundaries": WithinBoundariesSkill(),
    "builder": BuilderSkill(),
    "verification": VerificationSkill(),
    "review": ReviewSkill(),
    "compliance": ComplianceSkill(),
    # ...
}
```

### 2.3 GateService 新评估流程

```
evaluate(gate_input):
  failed = []
  for cond in policy.required_conditions:
    skill = registry.get(cond) or BUILTIN_SKILLS.get(cond)
    if skill:
      result = skill.run(gate_input)
      if not result.passed:
        failed.append(cond)
    else:
      # 未知条件，记录 warning，视为 passed 或 failed（可配置）
  return GateVerdict(mergeable=len(failed)==0, failed_conditions=failed)
```

### 2.4 Skill 注册表

```python
class GateSkillRegistry:
    _builtin: dict[str, GateCheckSkill]
    _custom: dict[str, GateCheckSkill]
    def register(self, skill: GateCheckSkill) -> None
    def get(self, condition_id: str) -> GateCheckSkill | None
```

从 `gate.policy.yaml` 或环境变量指定额外 Skill 路径，启动时加载。

---

## 3. 多格式导入架构

### 3.1 SpecStructure 统一模型

```python
# domain/models.py 或 spec_import/models.py
@dataclass
class SpecStructure:
    goal: str
    scope: str
    acceptance_criteria: list[str]
    constraints: list[str]
    raw_sections: dict[str, str]  # 保留原始 section，便于扩展
    source_format: str  # "spec-kit" | "ears" | "bdd" | "tessl"
    source_path: str
```

### 3.2 Parser 接口

```python
class SpecParser(Protocol):
    format_id: str
    def parse(self, path: Path) -> SpecStructure: ...
```

### 3.3 各格式 Parser 职责

| 格式 | 输入 | 解析逻辑 |
|------|------|----------|
| spec-kit | `.specify/spec.md`, `plan.md` | 提取 spec.md 的 goal/requirements；plan.md 的 technical approach → scope |
| ears | `.md` 含 EARS 句式 | 正则或简单解析 WHEN/WHILE/WHERE...THE SYSTEM SHALL，每句 → AC |
| bdd | `.feature` | 解析 Feature/Scenario/Given-When-Then，Scenario → AC |
| tessl | 待定 | 若格式公开，类似 spec-kit 的目录结构 |

### 3.4 模块布局

```
src/spec_orch/
  spec_import/
    __init__.py
    models.py       # SpecStructure
    parser.py      # SpecParser 协议、Registry
    spec_kit.py     # SpecKitParser
    ears.py         # EarsParser
    bdd.py          # BddParser (pyparsing 或 regex)
  services/
    gate_service.py       # 重构，使用 GateSkillRegistry
    gate_skill_protocol.py
    gate_builtin_skills.py
    mission_service.py    # 新增 create_mission_from_structure
```

---

## 4. 与 ComplianceEngine 的职责边界

| 层次 | 负责模块 | 职责 |
|------|----------|------|
| Gate 条件 | GateService + GateCheckSkill | 判断「是否可 merge」：spec 存在、builder 成功、verification 通过等 |
| Builder 合规 | ComplianceEngine | 判断 builder 输出是否符合 YAML 契约（如 turn_contract、narration） |

Gate 的 `compliance` 条件内部会调用 ComplianceEngine 的结果（gate_input.compliance_passed），两者协作但不合并。本 change 不修改 ComplianceEngine。

---

## 5. 配置扩展

### gate.policy.yaml 示例

```yaml
conditions:
  spec_exists:
    required: true
    description: "Spec file exists"
  builder:
    required: true
  skill:security-scan:   # 外部 Skill
    required: false
    description: "Optional security scan pass"
```

内置名保持不变；`skill:<id>` 从注册表查找。

---

## 6. 迁移与兼容

- 现有 `gate.policy.yaml` 无需修改，conditions 仍为内置名。
- `ALL_KNOWN_CONDITIONS` 保留，但改为从 `BUILTIN_SKILLS.keys()` 推导。
- 单元测试：现有 Gate 测试应全部通过，仅内部实现变化。
