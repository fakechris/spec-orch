from __future__ import annotations

import pytest


def test_resolve_configured_or_fallback_env_rejects_invalid_kind() -> None:
    from spec_orch.services.litellm_profile import resolve_configured_or_fallback_env

    with pytest.raises(ValueError, match="kind must be 'api_key' or 'api_base'"):
        resolve_configured_or_fallback_env(None, kind="apiKey")


def test_resolve_litellm_profile_chain_includes_primary_and_fallbacks(monkeypatch) -> None:
    from spec_orch.services.litellm_profile import resolve_litellm_profile_chain

    monkeypatch.setenv("MINIMAX_API_KEY", "minimax-key")
    monkeypatch.setenv("MINIMAX_ANTHROPIC_BASE_URL", "https://api.minimaxi.com/anthropic")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "fireworks-token")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.fireworks.ai/inference")

    chain = resolve_litellm_profile_chain(
        {
            "model": "MiniMax-M2.7-highspeed",
            "api_type": "anthropic",
            "api_key_env": "MINIMAX_API_KEY",
            "api_base_env": "MINIMAX_ANTHROPIC_BASE_URL",
            "fallbacks": [
                {
                    "model": "accounts/fireworks/routers/kimi-k2p5-turbo",
                    "api_type": "anthropic",
                    "api_key_env": "ANTHROPIC_AUTH_TOKEN",
                    "api_base_env": "ANTHROPIC_BASE_URL",
                }
            ],
        }
    )

    assert len(chain) == 2
    assert chain[0].model == "anthropic/MiniMax-M2.7-highspeed"
    assert chain[0].api_key == "minimax-key"
    assert chain[1].model == "anthropic/accounts/fireworks/routers/kimi-k2p5-turbo"
    assert chain[1].api_base == "https://api.fireworks.ai/inference"


def test_resolve_litellm_profile_chain_skips_fallback_without_model(monkeypatch) -> None:
    from spec_orch.services.litellm_profile import resolve_litellm_profile_chain

    monkeypatch.setenv("MINIMAX_API_KEY", "minimax-key")

    chain = resolve_litellm_profile_chain(
        {
            "model": "MiniMax-M2.7-highspeed",
            "api_key_env": "MINIMAX_API_KEY",
            "fallbacks": [
                {"api_key_env": "ANTHROPIC_AUTH_TOKEN"},
            ],
        }
    )

    assert len(chain) == 1


def test_resolve_litellm_api_key_falls_back_to_anthropic_auth_token(monkeypatch) -> None:
    from spec_orch.services.litellm_profile import resolve_litellm_api_key

    monkeypatch.delenv("SPEC_ORCH_LLM_API_KEY", raising=False)
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    monkeypatch.delenv("MINIMAX_CN_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "fw-token")

    assert resolve_litellm_api_key(api_type="anthropic") == "fw-token"


def test_resolve_role_litellm_settings_inherits_default_model_chain(monkeypatch) -> None:
    from spec_orch.services.litellm_profile import resolve_role_litellm_settings

    monkeypatch.setenv("MINIMAX_API_KEY", "minimax-key")
    monkeypatch.setenv("MINIMAX_ANTHROPIC_BASE_URL", "https://api.minimaxi.com/anthropic")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "fireworks-token")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.fireworks.ai/inference")

    raw = {
        "llm": {"default_model_chain": "reasoning"},
        "models": {
            "minimax": {
                "model": "MiniMax-M2.7-highspeed",
                "api_type": "anthropic",
                "api_key_env": "MINIMAX_API_KEY",
                "api_base_env": "MINIMAX_ANTHROPIC_BASE_URL",
            },
            "fireworks": {
                "model": "accounts/fireworks/routers/kimi-k2p5-turbo",
                "api_type": "anthropic",
                "api_key_env": "ANTHROPIC_AUTH_TOKEN",
                "api_base_env": "ANTHROPIC_BASE_URL",
            },
        },
        "model_chains": {
            "reasoning": {
                "primary": "minimax",
                "fallbacks": ["fireworks"],
            }
        },
        "planner": {},
    }

    settings = resolve_role_litellm_settings(raw, section_name="planner")

    assert settings["model"] == "anthropic/MiniMax-M2.7-highspeed"
    assert settings["api_key"] == "minimax-key"
    assert len(settings["model_chain"]) == 2
    assert (
        settings["model_chain"][1].model == "anthropic/accounts/fireworks/routers/kimi-k2p5-turbo"
    )


def test_resolve_role_litellm_settings_prefers_model_ref_over_global_default(monkeypatch) -> None:
    from spec_orch.services.litellm_profile import resolve_role_litellm_settings

    monkeypatch.setenv("MINIMAX_API_KEY", "minimax-key")
    monkeypatch.setenv("MINIMAX_ANTHROPIC_BASE_URL", "https://api.minimaxi.com/anthropic")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "fireworks-token")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.fireworks.ai/inference")

    raw = {
        "llm": {"default_model_chain": "reasoning"},
        "models": {
            "minimax": {
                "model": "MiniMax-M2.7-highspeed",
                "api_type": "anthropic",
                "api_key_env": "MINIMAX_API_KEY",
                "api_base_env": "MINIMAX_ANTHROPIC_BASE_URL",
            },
            "fireworks": {
                "model": "accounts/fireworks/routers/kimi-k2p5-turbo",
                "api_type": "anthropic",
                "api_key_env": "ANTHROPIC_AUTH_TOKEN",
                "api_base_env": "ANTHROPIC_BASE_URL",
            },
        },
        "model_chains": {
            "reasoning": {
                "primary": "minimax",
                "fallbacks": ["fireworks"],
            }
        },
        "acceptance_evaluator": {"model_ref": "fireworks"},
    }

    settings = resolve_role_litellm_settings(raw, section_name="acceptance_evaluator")

    assert settings["model"] == "anthropic/accounts/fireworks/routers/kimi-k2p5-turbo"
    assert len(settings["model_chain"]) == 1
    assert settings["model_chain"][0].slot == "primary"


def test_resolve_role_litellm_settings_ignores_standalone_api_type_for_default_chain(
    monkeypatch,
) -> None:
    from spec_orch.services.litellm_profile import resolve_role_litellm_settings

    monkeypatch.setenv("MINIMAX_API_KEY", "minimax-key")
    monkeypatch.setenv("MINIMAX_ANTHROPIC_BASE_URL", "https://api.minimaxi.com/anthropic")

    raw = {
        "llm": {"default_model_chain": "reasoning"},
        "models": {
            "minimax": {
                "model": "MiniMax-M2.7-highspeed",
                "api_type": "anthropic",
                "api_key_env": "MINIMAX_API_KEY",
                "api_base_env": "MINIMAX_ANTHROPIC_BASE_URL",
            }
        },
        "model_chains": {
            "reasoning": {
                "primary": "minimax",
            }
        },
        "planner": {"api_type": "anthropic"},
    }

    settings = resolve_role_litellm_settings(raw, section_name="planner")

    assert settings["model"] == "anthropic/MiniMax-M2.7-highspeed"
    assert len(settings["model_chain"]) == 1


def test_normalize_litellm_model_preserves_provider_prefixed_model() -> None:
    from spec_orch.services.litellm_profile import normalize_litellm_model

    assert normalize_litellm_model("google/gemini-pro", api_type="anthropic") == "google/gemini-pro"
