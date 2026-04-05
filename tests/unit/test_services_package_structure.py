from __future__ import annotations

from pathlib import Path


def _source(repo_relative_path: str) -> str:
    repo_root = Path(__file__).resolve().parents[2]
    return (repo_root / repo_relative_path).read_text(encoding="utf-8")


def test_services_subpackages_expose_canonical_module_lists() -> None:
    from spec_orch.services import builders, context, evolution

    assert builders.__all__ == [
        "acpx_builder_adapter",
        "adapter_factory",
        "claude_code_builder_adapter",
        "codex_exec_builder_adapter",
        "droid_builder_adapter",
        "opencode_builder_adapter",
    ]
    assert context.__all__ == [
        "context_assembler",
        "context_ranker",
        "node_context_registry",
    ]
    assert evolution.__all__ == [
        "config_evolver",
        "evolution_policy",
        "evolution_trigger",
        "flow_policy_evolver",
        "gate_policy_evolver",
        "intent_evolver",
        "plan_strategy_evolver",
        "promotion_registry",
        "prompt_evolver",
        "signal_bridge",
        "skill_evolver",
    ]


def test_service_shims_remain_logic_free_reexports() -> None:
    shim_expectations = {
        "src/spec_orch/services/adapter_factory.py": "from spec_orch.services.builders.adapter_factory import",
        "src/spec_orch/services/acpx_builder_adapter.py": "from spec_orch.services.builders.acpx_builder_adapter import",
        "src/spec_orch/services/claude_code_builder_adapter.py": (
            "from spec_orch.services.builders.claude_code_builder_adapter import"
        ),
        "src/spec_orch/services/codex_exec_builder_adapter.py": (
            "from spec_orch.services.builders.codex_exec_builder_adapter import"
        ),
        "src/spec_orch/services/droid_builder_adapter.py": (
            "from spec_orch.services.builders.droid_builder_adapter import"
        ),
        "src/spec_orch/services/opencode_builder_adapter.py": (
            "from spec_orch.services.builders.opencode_builder_adapter import"
        ),
        "src/spec_orch/services/context_assembler.py": (
            "from spec_orch.services.context.context_assembler import"
        ),
        "src/spec_orch/services/context_ranker.py": (
            "from spec_orch.services.context.context_ranker import"
        ),
        "src/spec_orch/services/node_context_registry.py": (
            "from spec_orch.services.context.node_context_registry import"
        ),
        "src/spec_orch/services/config_evolver.py": (
            "from spec_orch.services.evolution.config_evolver import"
        ),
        "src/spec_orch/services/evolution_policy.py": (
            "from spec_orch.services.evolution.evolution_policy import"
        ),
        "src/spec_orch/services/evolution_trigger.py": (
            "from spec_orch.services.evolution.evolution_trigger import"
        ),
        "src/spec_orch/services/flow_policy_evolver.py": (
            "from spec_orch.services.evolution.flow_policy_evolver import"
        ),
        "src/spec_orch/services/gate_policy_evolver.py": (
            "from spec_orch.services.evolution.gate_policy_evolver import"
        ),
        "src/spec_orch/services/intent_evolver.py": (
            "from spec_orch.services.evolution.intent_evolver import"
        ),
        "src/spec_orch/services/plan_strategy_evolver.py": (
            "from spec_orch.services.evolution.plan_strategy_evolver import"
        ),
        "src/spec_orch/services/prompt_evolver.py": (
            "from spec_orch.services.evolution.prompt_evolver import"
        ),
    }

    for path, import_line in shim_expectations.items():
        source = _source(path)
        assert import_line in source
        assert "def " not in source
        assert "class " not in source
