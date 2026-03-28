from __future__ import annotations

import pytest


def test_resolve_configured_or_fallback_env_rejects_invalid_kind() -> None:
    from spec_orch.services.litellm_profile import resolve_configured_or_fallback_env

    with pytest.raises(ValueError, match="kind must be 'api_key' or 'api_base'"):
        resolve_configured_or_fallback_env(None, kind="apiKey")
