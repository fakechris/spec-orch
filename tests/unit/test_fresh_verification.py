from __future__ import annotations


def test_build_fresh_verification_commands_emits_stronger_typescript_checks() -> None:
    from spec_orch.services.fresh_verification import build_fresh_verification_commands

    commands = build_fresh_verification_commands(
        ["src/contracts/mission_types.ts", "src/contracts/artifact_types.ts"]
    )

    assert set(commands) >= {
        "scaffold_exists",
        "typescript_contract_tokens",
        "typescript_schema_surface",
    }
    assert commands["scaffold_exists"][:2] == ["{python}", "-c"]
    assert commands["typescript_contract_tokens"][:2] == ["{python}", "-c"]
    assert commands["typescript_schema_surface"][:2] == ["{python}", "-c"]
    assert "mission_types.ts" in commands["scaffold_exists"][2]
    assert "artifact_types.ts" in commands["typescript_contract_tokens"][2]
    assert "Schema" in commands["typescript_schema_surface"][2]


def test_build_fresh_verification_commands_returns_empty_for_empty_scope() -> None:
    from spec_orch.services.fresh_verification import build_fresh_verification_commands

    assert build_fresh_verification_commands([]) == {}
