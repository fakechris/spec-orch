from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

_LITELLM_PROVIDER_PREFIXES = {
    "anthropic",
    "openai",
    "azure",
    "azure_ai",
    "bedrock",
    "cohere",
    "gemini",
    "google",
    "groq",
    "mistral",
    "ollama",
    "openrouter",
    "vertex_ai",
}


def normalize_litellm_model(model: str, *, api_type: str = "anthropic") -> str:
    provider, _, _rest = model.partition("/")
    if provider in _LITELLM_PROVIDER_PREFIXES:
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


@dataclass(frozen=True)
class ResolvedLiteLLMProfile:
    model: str
    api_type: str
    api_key: str
    api_base: str
    api_key_env: str
    api_base_env: str
    slot: str

    def to_kwargs(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "api_key": self.api_key or None,
            "api_base": self.api_base or None,
        }


def resolve_role_litellm_profile_chain(
    raw: dict[str, Any],
    *,
    section_name: str,
    default_model: str = "",
    default_api_type: str = "anthropic",
) -> list[ResolvedLiteLLMProfile]:
    section_cfg = _as_dict(raw.get(section_name))
    llm_cfg = _as_dict(raw.get("llm"))

    explicit_chain = str(section_cfg.get("model_chain", "")).strip()
    if explicit_chain:
        return _resolve_named_chain(raw, explicit_chain, default_api_type=default_api_type)

    explicit_model_ref = str(section_cfg.get("model_ref", "")).strip()
    if explicit_model_ref:
        resolved = _resolve_named_model(
            raw,
            explicit_model_ref,
            slot="primary",
            default_api_type=default_api_type,
        )
        return [resolved] if resolved is not None else []

    if _has_inline_litellm_config(section_cfg):
        return resolve_litellm_profile_chain(
            section_cfg,
            default_model=default_model,
            default_api_type=default_api_type,
        )

    inherited_chain = str(llm_cfg.get("default_model_chain", "")).strip()
    if inherited_chain:
        return _resolve_named_chain(raw, inherited_chain, default_api_type=default_api_type)

    inherited_model_ref = str(llm_cfg.get("default_model_ref", "")).strip()
    if inherited_model_ref:
        resolved = _resolve_named_model(
            raw,
            inherited_model_ref,
            slot="primary",
            default_api_type=default_api_type,
        )
        return [resolved] if resolved is not None else []

    return resolve_litellm_profile_chain(
        section_cfg,
        default_model=default_model,
        default_api_type=default_api_type,
    )


def resolve_role_litellm_settings(
    raw: dict[str, Any],
    *,
    section_name: str,
    default_model: str = "",
    default_api_type: str = "anthropic",
) -> dict[str, Any]:
    section_cfg = _as_dict(raw.get(section_name))
    chain = resolve_role_litellm_profile_chain(
        raw,
        section_name=section_name,
        default_model=default_model,
        default_api_type=default_api_type,
    )
    primary = chain[0] if chain else None
    return {
        "model": primary.model if primary is not None else default_model,
        "api_type": primary.api_type if primary is not None else default_api_type,
        "api_key": primary.api_key if primary is not None else "",
        "api_base": primary.api_base if primary is not None else "",
        "api_key_env": primary.api_key_env if primary is not None else "",
        "api_base_env": primary.api_base_env if primary is not None else "",
        "model_chain": chain,
        "token_command": section_cfg.get("token_command"),
    }


def resolve_litellm_profile_chain(
    cfg: dict[str, Any],
    *,
    default_model: str = "",
    default_api_type: str = "anthropic",
) -> list[ResolvedLiteLLMProfile]:
    profiles: list[ResolvedLiteLLMProfile] = []
    primary = _resolve_profile(
        cfg,
        slot="primary",
        default_model=default_model,
        default_api_type=default_api_type,
    )
    if primary is not None:
        profiles.append(primary)
    raw_fallbacks = cfg.get("fallbacks", [])
    if isinstance(raw_fallbacks, list):
        for idx, raw in enumerate(raw_fallbacks, start=1):
            if not isinstance(raw, dict):
                continue
            resolved = _resolve_profile(
                raw,
                slot=f"fallback-{idx}",
                default_model="",
                default_api_type=default_api_type,
            )
            if resolved is not None:
                profiles.append(resolved)
    return profiles


def _resolve_profile(
    cfg: dict[str, Any],
    *,
    slot: str,
    default_model: str,
    default_api_type: str,
) -> ResolvedLiteLLMProfile | None:
    api_type = str(cfg.get("api_type", default_api_type)).strip().lower() or default_api_type
    model = str(cfg.get("model", default_model)).strip() or default_model
    if not model:
        return None
    api_key_env = str(cfg.get("api_key_env", "")).strip()
    api_base_env = str(cfg.get("api_base_env", "")).strip()
    api_key = resolve_configured_or_fallback_env(
        api_key_env or None,
        api_type=api_type,
        kind="api_key",
    )
    api_base = resolve_configured_or_fallback_env(
        api_base_env or None,
        api_type=api_type,
        kind="api_base",
    )
    return ResolvedLiteLLMProfile(
        model=normalize_litellm_model(model, api_type=api_type),
        api_type=api_type,
        api_key=api_key,
        api_base=api_base,
        api_key_env=api_key_env,
        api_base_env=api_base_env,
        slot=slot,
    )


def _resolve_named_chain(
    raw: dict[str, Any],
    chain_name: str,
    *,
    default_api_type: str,
) -> list[ResolvedLiteLLMProfile]:
    chains = _as_dict(raw.get("model_chains"))
    chain_cfg = _as_dict(chains.get(chain_name))
    if not chain_cfg:
        raise ValueError(f"Unknown model chain: {chain_name!r}")

    primary_ref = str(chain_cfg.get("primary", "")).strip()
    if not primary_ref:
        raise ValueError(f"Model chain {chain_name!r} is missing a primary model")

    profiles: list[ResolvedLiteLLMProfile] = []
    primary = _resolve_named_model(
        raw,
        primary_ref,
        slot="primary",
        default_api_type=default_api_type,
    )
    if primary is None:
        raise ValueError(
            f"Primary model {primary_ref!r} in chain {chain_name!r} could not be resolved"
        )
    profiles.append(primary)

    raw_fallbacks = chain_cfg.get("fallbacks", [])
    if isinstance(raw_fallbacks, list):
        for idx, entry in enumerate(raw_fallbacks, start=1):
            model_ref = _coerce_model_ref(entry)
            if not model_ref:
                continue
            resolved = _resolve_named_model(
                raw,
                model_ref,
                slot=f"fallback-{idx}",
                default_api_type=default_api_type,
            )
            if resolved is not None:
                profiles.append(resolved)
    return profiles


def _resolve_named_model(
    raw: dict[str, Any],
    model_ref: str,
    *,
    slot: str,
    default_api_type: str,
) -> ResolvedLiteLLMProfile | None:
    models = _as_dict(raw.get("models"))
    model_cfg = _as_dict(models.get(model_ref))
    if not model_cfg:
        raise ValueError(f"Unknown model reference: {model_ref!r}")
    return _resolve_profile(
        model_cfg,
        slot=slot,
        default_model="",
        default_api_type=default_api_type,
    )


def _has_inline_litellm_config(cfg: dict[str, Any]) -> bool:
    return any(
        key in cfg
        for key in (
            "model",
            "api_key_env",
            "api_base_env",
            "fallbacks",
            "api_key",
            "api_base",
        )
    )


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _coerce_model_ref(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return str(value.get("ref", "")).strip()
    return ""


def _api_key_fallbacks(api_type: str) -> tuple[str, ...]:
    if api_type == "openai":
        return ("SPEC_ORCH_LLM_API_KEY", "OPENAI_API_KEY")
    return (
        "SPEC_ORCH_LLM_API_KEY",
        "MINIMAX_API_KEY",
        "MINIMAX_CN_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
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
