from __future__ import annotations

import json

from typer.testing import CliRunner

from spec_orch.cli import app
from spec_orch.services.model_probe import evaluate_probe_output


def test_evaluate_probe_output_exact_text() -> None:
    result = evaluate_probe_output("exact_text", "FIREWORKS_OK")

    assert result["ok"] is True
    assert result["normalized_output"] == "FIREWORKS_OK"


def test_evaluate_probe_output_strict_json() -> None:
    result = evaluate_probe_output("strict_json", '{"status":"pass","summary":"ok"}')

    assert result["ok"] is True
    assert result["parsed_payload"]["status"] == "pass"
    assert result["parsed_payload"]["summary"] == "ok"


def test_evaluate_probe_output_fenced_json() -> None:
    raw = """Run passed.

```json
{"status":"pass","summary":"The run passed.","confidence":0.9,"evaluator":"probe","findings":[],"issue_proposals":[],"artifacts":{}}
```"""
    result = evaluate_probe_output("fenced_json", raw)

    assert result["ok"] is True
    assert result["parsed_payload"]["evaluator"] == "probe"


def test_evaluate_probe_output_acceptance_json() -> None:
    raw = """Acceptance review complete.

```json
{"status":"warn","summary":"One UX gap found.","confidence":0.82,"evaluator":"probe","tested_routes":["/"],"findings":[{"severity":"medium","summary":"Transcript entry is weak","details":"","expected":"","actual":"","route":"/?tab=transcript","artifact_paths":{},"critique_axis":"evidence_discoverability","operator_task":"open transcript evidence","why_it_matters":"Operators can stall."}],"issue_proposals":[],"artifacts":{}}
```"""
    result = evaluate_probe_output("acceptance_json", raw)

    assert result["ok"] is True
    assert result["parsed_payload"]["status"] == "warn"
    assert result["parsed_payload"]["findings"][0]["summary"] == "Transcript entry is weak"


def test_evaluate_probe_output_reports_failure_reason() -> None:
    result = evaluate_probe_output("strict_json", "I will return JSON soon.")

    assert result["ok"] is False
    assert "valid json object" in result["failure_reason"].lower()


def test_model_probe_cli_json_output(monkeypatch) -> None:
    runner = CliRunner()

    def fake_probe_model_compliance(**kwargs):
        return {
            "model": kwargs["model"],
            "transport": kwargs["transport"],
            "results": [
                {"name": "exact_text", "ok": True},
                {"name": "strict_json", "ok": False, "failure_reason": "not valid json object"},
            ],
            "summary": {"passed": 1, "failed": 1, "total": 2},
        }

    monkeypatch.setattr(
        "spec_orch.cli.diag_commands.probe_model_compliance",
        fake_probe_model_compliance,
    )

    result = runner.invoke(
        app,
        [
            "model-probe",
            "--model",
            "accounts/fireworks/routers/kimi-k2p5-turbo",
            "--transport",
            "litellm",
            "--json",
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["model"] == "accounts/fireworks/routers/kimi-k2p5-turbo"
    assert payload["summary"]["failed"] == 1
    assert payload["results"][1]["name"] == "strict_json"
