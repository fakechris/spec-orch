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


def test_legacy_shim_files_have_been_removed() -> None:
    """Verify that backward-compatible re-export shim files no longer exist."""
    repo_root = Path(__file__).resolve().parents[2]
    removed_shims = [
        "src/spec_orch/services/adapter_factory.py",
        "src/spec_orch/services/acpx_builder_adapter.py",
        "src/spec_orch/services/claude_code_builder_adapter.py",
        "src/spec_orch/services/codex_exec_builder_adapter.py",
        "src/spec_orch/services/droid_builder_adapter.py",
        "src/spec_orch/services/opencode_builder_adapter.py",
        "src/spec_orch/services/context_assembler.py",
        "src/spec_orch/services/context_ranker.py",
        "src/spec_orch/services/node_context_registry.py",
        "src/spec_orch/services/config_evolver.py",
        "src/spec_orch/services/evolution_policy.py",
        "src/spec_orch/services/evolution_trigger.py",
        "src/spec_orch/services/flow_policy_evolver.py",
        "src/spec_orch/services/gate_policy_evolver.py",
        "src/spec_orch/services/intent_evolver.py",
        "src/spec_orch/services/plan_strategy_evolver.py",
        "src/spec_orch/services/prompt_evolver.py",
        "src/spec_orch/domain/task_contract.py",
    ]
    for path in removed_shims:
        assert not (repo_root / path).exists(), f"shim file should be removed: {path}"
