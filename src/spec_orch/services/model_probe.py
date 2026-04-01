from __future__ import annotations

import json
import re
from typing import Any

import httpx

from spec_orch.services.litellm_profile import (
    normalize_litellm_model,
    resolve_configured_or_fallback_env,
)

_FENCED_JSON_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)


def evaluate_probe_output(case_name: str, raw_output: str) -> dict[str, Any]:
    text = raw_output.strip()
    result: dict[str, Any] = {
        "name": case_name,
        "ok": False,
        "raw_output": raw_output,
    }

    if case_name == "exact_text":
        expected = "FIREWORKS_OK"
        if text == expected:
            result["ok"] = True
            result["normalized_output"] = expected
            return result
        result["failure_reason"] = f"Expected exact output {expected!r}"
        return result

    if case_name == "strict_json":
        parsed = _parse_json_object(text)
        if parsed is None:
            result["failure_reason"] = "Output was not a valid JSON object"
            return result
        result["ok"] = True
        result["parsed_payload"] = parsed
        result["normalized_output"] = json.dumps(parsed, ensure_ascii=False, sort_keys=True)
        return result

    if case_name in {"fenced_json", "acceptance_json"}:
        parsed = _parse_fenced_json_object(text)
        if parsed is None:
            result["failure_reason"] = "Output did not contain a valid ```json fenced block"
            return result
        if case_name == "acceptance_json":
            required = {
                "status",
                "summary",
                "confidence",
                "evaluator",
                "findings",
                "issue_proposals",
                "artifacts",
            }
            missing = sorted(required - set(parsed))
            if missing:
                result["failure_reason"] = (
                    "Acceptance JSON payload missing required keys: " + ", ".join(missing)
                )
                return result
        result["ok"] = True
        result["parsed_payload"] = parsed
        result["normalized_output"] = json.dumps(parsed, ensure_ascii=False, sort_keys=True)
        return result

    raise ValueError(f"Unknown probe case: {case_name!r}")


def probe_model_compliance(
    *,
    model: str,
    transport: str = "litellm",
    api_type: str = "anthropic",
    api_key: str | None = None,
    api_base: str | None = None,
    api_key_env: str | None = None,
    api_base_env: str | None = None,
    max_tokens: int = 400,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    resolved_api_key: str | None = api_key or resolve_configured_or_fallback_env(
        api_key_env,
        api_type=api_type,
        kind="api_key",
    )
    resolved_api_base: str | None = api_base or resolve_configured_or_fallback_env(
        api_base_env,
        api_type=api_type,
        kind="api_base",
    )
    resolved_api_key = resolved_api_key or None
    resolved_api_base = resolved_api_base or None
    results: list[dict[str, Any]] = []

    for case_name, prompt in _probe_cases():
        try:
            raw_output = _invoke_model(
                model=model,
                transport=transport,
                api_type=api_type,
                api_key=resolved_api_key,
                api_base=resolved_api_base,
                prompt=prompt,
                max_tokens=max_tokens,
                timeout_seconds=timeout_seconds,
            )
            evaluation = evaluate_probe_output(case_name, raw_output)
        except Exception as exc:
            evaluation = {
                "name": case_name,
                "ok": False,
                "failure_reason": str(exc),
                "error_type": type(exc).__name__,
            }
        results.append(evaluation)

    passed = sum(1 for item in results if item.get("ok") is True)
    failed = len(results) - passed
    return {
        "model": model,
        "api_type": api_type,
        "transport": transport,
        "api_key_env": api_key_env or "",
        "api_base_env": api_base_env or "",
        "api_key_present": bool(resolved_api_key),
        "api_base_present": bool(resolved_api_base),
        "results": results,
        "summary": {
            "passed": passed,
            "failed": failed,
            "total": len(results),
        },
    }


def _probe_cases() -> list[tuple[str, str]]:
    return [
        (
            "exact_text",
            "Reply with exactly: FIREWORKS_OK\nDo not add any other text.",
        ),
        (
            "strict_json",
            (
                "Reply with a single JSON object only. No markdown, no prose.\n"
                '{"status":"pass","summary":"ok"}'
            ),
        ),
        (
            "fenced_json",
            (
                "Reply with one short markdown sentence, then a ```json fenced block only.\n"
                'The JSON should be: {"status":"pass","summary":"The run passed.",'
                '"confidence":0.9,"evaluator":"probe","findings":[],'
                '"issue_proposals":[],"artifacts":{}}'
            ),
        ),
        (
            "acceptance_json",
            (
                "Return two parts in this order:\n"
                "1. A short markdown acceptance review\n"
                "2. A JSON object in a ```json fenced block\n\n"
                "The JSON must include: status, summary, confidence, evaluator, "
                "tested_routes, findings, issue_proposals, artifacts.\n"
                'Use this exact finding summary: "Transcript entry is weak".'
            ),
        ),
    ]


def _invoke_model(
    *,
    model: str,
    transport: str,
    api_type: str,
    api_key: str,
    api_base: str,
    prompt: str,
    max_tokens: int,
    timeout_seconds: float,
) -> str:
    if transport == "litellm":
        return _invoke_litellm(
            model=model,
            api_type=api_type,
            api_key=api_key,
            api_base=api_base,
            prompt=prompt,
            max_tokens=max_tokens,
            timeout_seconds=timeout_seconds,
        )
    if transport == "anthropic-http":
        return _invoke_anthropic_http(
            model=model,
            api_key=api_key,
            api_base=api_base,
            prompt=prompt,
            max_tokens=max_tokens,
            timeout_seconds=timeout_seconds,
        )
    raise ValueError(f"Unsupported transport: {transport!r}")


def _invoke_litellm(
    *,
    model: str,
    api_type: str,
    api_key: str,
    api_base: str,
    prompt: str,
    max_tokens: int,
    timeout_seconds: float,
) -> str:
    import litellm

    response = litellm.completion(
        model=normalize_litellm_model(model, api_type=api_type),
        api_key=api_key or None,
        api_base=api_base or None,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=max_tokens,
        timeout=timeout_seconds,
    )
    return _extract_message_content(response)


def _invoke_anthropic_http(
    *,
    model: str,
    api_key: str,
    api_base: str,
    prompt: str,
    max_tokens: int,
    timeout_seconds: float,
) -> str:
    if not api_key:
        raise RuntimeError("anthropic-http transport requires api_key")
    if not api_base:
        raise RuntimeError("anthropic-http transport requires api_base")
    response = httpx.post(
        api_base.rstrip("/") + "/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    content = payload.get("content", [])
    if not isinstance(content, list):
        return ""
    text_parts: list[str] = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            text_parts.append(str(item.get("text", "")))
    return "\n".join(part for part in text_parts if part)


def _extract_message_content(response: Any) -> str:
    choices = getattr(response, "choices", None)
    if not choices:
        return ""
    first = choices[0]
    message = getattr(first, "message", None)
    if message is None:
        return ""
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if text:
                    parts.append(str(text))
        return "\n".join(parts)
    return str(content)


def _parse_json_object(text: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _parse_fenced_json_object(text: str) -> dict[str, Any] | None:
    match = _FENCED_JSON_RE.search(text)
    if not match:
        return None
    return _parse_json_object(match.group(1).strip())
