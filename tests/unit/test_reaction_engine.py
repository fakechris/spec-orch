from __future__ import annotations

from pathlib import Path

from spec_orch.services.reaction_engine import ReactionEngine


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
