from __future__ import annotations

from pathlib import Path

from spec_orch.services.reaction_engine import (
    ReactionEngine,
    interpolate_template,
    parse_reactions_yaml,
    validate_reactions_file,
)


def test_reaction_engine_default_rules() -> None:
    engine = ReactionEngine(Path("/tmp/nonexistent-repo"))
    actions = [r.action for r in engine.rules]
    assert "auto_merge" in actions
    assert "comment_ci_failed" in actions
    assert "comment_changes_requested" in actions


def test_reaction_engine_evaluate_approved_and_green(tmp_path: Path) -> None:
    engine = ReactionEngine(tmp_path)
    decisions = engine.evaluate(
        {
            "review_decision": "APPROVED",
            "checks_passed": True,
            "checks_failed": False,
            "mergeable": True,
        }
    )
    assert any(d.action == "auto_merge" for d in decisions)
    assert all(isinstance(d.params, dict) for d in decisions)


def test_reaction_engine_recipe_override(tmp_path: Path) -> None:
    recipe = tmp_path / ".spec_orch" / "reactions.yaml"
    recipe.parent.mkdir(parents=True)
    recipe.write_text(
        """
reactions:
  - name: only-ci
    trigger: ci_failed
    action: comment_ci_failed
"""
    )
    engine = ReactionEngine(tmp_path)
    assert [r.name for r in engine.rules] == ["only-ci"]


def test_parse_reactions_yaml_warns_on_unknown_trigger() -> None:
    raw = {
        "reactions": [
            {
                "name": "bad",
                "trigger": "unknown",
                "action": "noop",
            }
        ]
    }
    rules, errs = parse_reactions_yaml(raw)
    assert rules  # still ingested
    assert any("unknown trigger" in e for e in errs)


def test_validate_reactions_file_missing(tmp_path: Path) -> None:
    p = tmp_path / "nope.yaml"
    issues = validate_reactions_file(p)
    assert any("not found" in i for i in issues)


def test_interpolate_template() -> None:
    s = interpolate_template(
        "PR {pr_number} {issue_id} {mergeable}",
        {"pr_number": 3, "issue_id": "X-1", "mergeable": False},
    )
    assert s == "PR 3 X-1 False"


def test_reaction_params_roundtrip_in_decision(tmp_path: Path) -> None:
    recipe = tmp_path / ".spec_orch" / "reactions.yaml"
    recipe.parent.mkdir(parents=True)
    recipe.write_text(
        """
reactions:
  - name: merge-it
    trigger: approved_and_green
    action: auto_merge
    params:
      merge_method: merge
"""
    )
    engine = ReactionEngine(tmp_path)
    dec = engine.evaluate(
        {
            "review_decision": "APPROVED",
            "checks_passed": True,
            "checks_failed": False,
            "mergeable": True,
        }
    )
    assert dec[0].params.get("merge_method") == "merge"
