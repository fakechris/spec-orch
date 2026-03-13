from spec_orch.domain.compliance import ComplianceEngine, pre_action_narration_rule
from spec_orch.domain.models import BuilderEvent


def _evt(kind: str, text: str = "", **kwargs) -> BuilderEvent:
    return BuilderEvent(timestamp="2026-03-11T00:00:00Z", kind=kind, text=text, **kwargs)


def test_engine_compliant_when_first_action_is_command() -> None:
    events = [
        _evt("command_start", "ls -la"),
        _evt("command_end", "ls -la", exit_code=0),
        _evt("message", "Done."),
    ]
    engine = ComplianceEngine()
    result = engine.evaluate(events)
    assert result["compliant"] is True
    assert result["first_action_seen"] is True
    assert result["first_action_kind"] == "command_start"


def test_engine_noncompliant_when_narration_before_action() -> None:
    events = [
        _evt("message", "I will read the repo and plan my approach."),
        _evt("command_start", "ls"),
    ]
    engine = ComplianceEngine()
    result = engine.evaluate(events)
    assert result["compliant"] is False
    assert len(result["violations"]) >= 1
    assert result["first_action_seen"] is True


def test_engine_narration_after_action_is_ok() -> None:
    events = [
        _evt("command_start", "pytest"),
        _evt("command_end", "pytest", exit_code=0),
        _evt("message", "I will now explain the plan for the next step."),
    ]
    engine = ComplianceEngine()
    result = engine.evaluate(events)
    assert result["compliant"] is True


def test_engine_empty_events() -> None:
    engine = ComplianceEngine()
    result = engine.evaluate([])
    assert result["compliant"] is True
    assert result["first_action_seen"] is False


def test_engine_file_change_as_first_action() -> None:
    events = [
        _evt("file_change", file_path="src/a.py"),
        _evt("message", "Updated file."),
    ]
    engine = ComplianceEngine()
    result = engine.evaluate(events)
    assert result["compliant"] is True
    assert result["first_action_seen"] is True
    assert result["first_action_kind"] == "file_change"


def test_engine_custom_rule() -> None:
    def no_errors_rule(events):
        return [{"kind": e.kind, "text": e.text} for e in events if e.kind == "error"]

    engine = ComplianceEngine(rules=[no_errors_rule])
    events = [_evt("error", "something broke")]
    result = engine.evaluate(events)
    assert result["compliant"] is False


def test_pre_action_narration_rule_standalone() -> None:
    events = [
        _evt("message", "First I will set up the environment."),
        _evt("command_start", "npm install"),
    ]
    violations = pre_action_narration_rule(events)
    assert len(violations) == 1
    assert "I will" in violations[0]["pattern"]
