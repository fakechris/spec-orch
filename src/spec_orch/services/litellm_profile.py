from __future__ import annotations

import os


def normalize_litellm_model(model: str, *, api_type: str = "anthropic") -> str:
    if "/" in model:
        return model
    return f"{api_type}/{model}"


def resolve_litellm_api_key(
    *,
    api_key: str | None = None,
    api_type: str = "anthropic",
) -> str | None:
    if api_key:
        return api_key
    for env_name in _api_key_fallbacks(api_type):
        value = os.environ.get(env_name)
        if value:
            return value
    return None


def resolve_litellm_api_base(
    *,
    api_base: str | None = None,
    api_type: str = "anthropic",
) -> str | None:
    if api_base:
        return api_base
    for env_name in _api_base_fallbacks(api_type):
        value = os.environ.get(env_name)
        if value:
            return value
    return None


def resolve_configured_or_fallback_env(
    env_name: str | None,
    *,
    api_type: str = "anthropic",
    kind: str = "api_key",
) -> str:
    if kind not in {"api_key", "api_base"}:
        raise ValueError(f"kind must be 'api_key' or 'api_base', got {kind!r}")
    if env_name:
        value = os.environ.get(env_name)
        if value:
            return value
    fallbacks = _api_key_fallbacks(api_type) if kind == "api_key" else _api_base_fallbacks(api_type)
    for fallback in fallbacks:
        value = os.environ.get(fallback)
        if value:
            return value
    return ""


def _api_key_fallbacks(api_type: str) -> tuple[str, ...]:
    if api_type == "openai":
        return ("SPEC_ORCH_LLM_API_KEY", "OPENAI_API_KEY")
    return (
        "SPEC_ORCH_LLM_API_KEY",
        "MINIMAX_API_KEY",
        "MINIMAX_CN_API_KEY",
        "ANTHROPIC_API_KEY",
    )


def _api_base_fallbacks(api_type: str) -> tuple[str, ...]:
    if api_type == "openai":
        return ("SPEC_ORCH_LLM_API_BASE", "OPENAI_API_BASE")
    return (
        "SPEC_ORCH_LLM_API_BASE",
        "MINIMAX_ANTHROPIC_BASE_URL",
        "ANTHROPIC_BASE_URL",
    )
