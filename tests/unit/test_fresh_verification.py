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
        "typescript_typecheck",
        "typescript_lint_smoke",
        "typescript_import_smoke",
    }
    assert commands["scaffold_exists"][:2] == ["{python}", "-c"]
    assert commands["typescript_contract_tokens"][:2] == ["{python}", "-c"]
    assert commands["typescript_schema_surface"][:2] == ["{python}", "-c"]
    assert commands["typescript_typecheck"][0] == "tsc"
    assert commands["typescript_lint_smoke"][:2] == ["{python}", "-c"]
    assert commands["typescript_import_smoke"][:2] == ["{python}", "-c"]
    assert "mission_types.ts" in commands["scaffold_exists"][2]
    assert "artifact_types.ts" in commands["typescript_contract_tokens"][2]
    assert "Schema" in commands["typescript_schema_surface"][2]
    assert "--moduleResolution" in commands["typescript_typecheck"]
    assert "trailing_whitespace" in commands["typescript_lint_smoke"][2]
    assert "import_smoke.ts" in commands["typescript_import_smoke"][-1]


def test_build_fresh_verification_commands_returns_empty_for_empty_scope() -> None:
    from spec_orch.services.fresh_verification import build_fresh_verification_commands

    assert build_fresh_verification_commands([]) == {}


def test_build_fresh_verification_commands_rejects_out_of_repo_scope_paths() -> None:
    from spec_orch.services.fresh_verification import build_fresh_verification_commands

    invalid_scopes = [
        ["/tmp/evil.ts"],
        ["../escape.ts"],
        ["src/contracts/ok.ts", "../escape.ts"],
    ]

    for files_in_scope in invalid_scopes:
        try:
            build_fresh_verification_commands(files_in_scope)
        except ValueError as exc:
            assert "files_in_scope" in str(exc)
        else:
            raise AssertionError(f"Expected invalid scope to fail: {files_in_scope!r}")


def test_build_import_smoke_module_rewrites_paths_relative_to_import_smoke_file() -> None:
    from spec_orch.services.fresh_verification import _build_import_smoke_module

    module = _build_import_smoke_module(
        ["src/contracts/mission_types.ts", "src/contracts/nested/artifact_types.tsx"],
        "src/contracts/import_smoke.ts",
    )

    assert "import * as contract_1 from './mission_types';" in module
    assert "import * as contract_2 from './nested/artifact_types';" in module
