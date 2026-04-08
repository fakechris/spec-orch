"""Tests for the shared model-chain fallback executor."""

from __future__ import annotations

import pytest

from spec_orch.services.litellm_profile import ResolvedLiteLLMProfile
from spec_orch.services.model_chain_executor import (
    execute_with_fallback,
    is_transient_litellm_error,
)


def _make_profile(
    slot: str = "primary",
    model: str = "anthropic/claude-3-haiku",
    api_key: str = "sk-test",
    api_base: str = "",
    api_key_env: str = "",
    api_base_env: str = "",
    api_type: str = "anthropic",
) -> ResolvedLiteLLMProfile:
    return ResolvedLiteLLMProfile(
        model=model,
        api_type=api_type,
        api_key=api_key,
        api_base=api_base,
        api_key_env=api_key_env,
        api_base_env=api_base_env,
        slot=slot,
    )


# ── is_transient_litellm_error ──────────────────────────────────────


class TestIsTransientLitellmError:
    def test_timeout_error_is_transient(self):
        assert is_transient_litellm_error(TimeoutError("timed out")) is True

    def test_rate_limit_is_transient(self):
        assert is_transient_litellm_error(Exception("rate limit exceeded")) is True

    def test_429_is_transient(self):
        assert is_transient_litellm_error(Exception("HTTP 429")) is True

    def test_overloaded_is_transient(self):
        assert is_transient_litellm_error(Exception("overloaded_error")) is True

    def test_auth_error_is_fatal(self):
        assert is_transient_litellm_error(Exception("authentication_error")) is False

    def test_invalid_api_key_is_fatal(self):
        assert is_transient_litellm_error(Exception("invalid api key")) is False

    def test_generic_error_is_not_transient(self):
        assert is_transient_litellm_error(Exception("something unexpected")) is False

    def test_extra_fatal_types_override(self):
        class CustomTimeout(Exception):
            pass

        exc = CustomTimeout("hard deadline")
        # Without extra_fatal_types, it's not transient (no markers match)
        assert is_transient_litellm_error(exc) is False
        # With extra_fatal_types, explicitly fatal
        assert is_transient_litellm_error(exc, extra_fatal_types=(CustomTimeout,)) is False

    def test_extra_fatal_types_blocks_timeout(self):
        """A TimeoutError subclass listed in extra_fatal_types is fatal."""

        class HardDeadline(TimeoutError):
            pass

        exc = HardDeadline("deadline")
        assert is_transient_litellm_error(exc) is True  # normally transient
        assert is_transient_litellm_error(exc, extra_fatal_types=(HardDeadline,)) is False


# ── execute_with_fallback ───────────────────────────────────────────


class TestExecuteWithFallback:
    def test_single_profile_success(self):
        result = execute_with_fallback(
            profiles=[_make_profile()],
            call_fn=lambda **kw: "ok",
            base_kwargs={"messages": []},
            role_name="test",
        )
        assert result == "ok"

    def test_call_fn_receives_profile_overrides(self):
        captured: dict = {}

        def spy(**kw):
            captured.update(kw)
            return "done"

        execute_with_fallback(
            profiles=[_make_profile(model="openai/gpt-4", api_key="key1", api_base="http://base")],
            call_fn=spy,
            base_kwargs={"messages": [{"role": "user", "content": "hi"}], "temperature": 0.5},
            role_name="test",
        )
        assert captured["model"] == "openai/gpt-4"
        assert captured["api_key"] == "key1"
        assert captured["api_base"] == "http://base"
        assert captured["temperature"] == 0.5

    def test_fallback_to_second_profile_on_fatal_error(self):
        """Fatal error on first profile should raise immediately, not fallback."""
        call_count = 0

        def failing_then_ok(**kw):
            nonlocal call_count
            call_count += 1
            if kw["model"] == "anthropic/model-a":
                raise Exception("authentication_error")
            return "fallback-ok"

        with pytest.raises(Exception, match="authentication_error"):
            execute_with_fallback(
                profiles=[
                    _make_profile(slot="primary", model="anthropic/model-a"),
                    _make_profile(slot="fallback-1", model="anthropic/model-b"),
                ],
                call_fn=failing_then_ok,
                base_kwargs={},
                role_name="test",
            )
        assert call_count == 1  # fatal error stops immediately

    def test_retry_on_transient_then_succeed(self):
        attempts = 0

        def flaky(**kw):
            nonlocal attempts
            attempts += 1
            if attempts < 2:
                raise Exception("rate limit exceeded")
            return "recovered"

        result = execute_with_fallback(
            profiles=[_make_profile()],
            call_fn=flaky,
            base_kwargs={},
            max_retries=2,
            retry_backoff_seconds=0,
            role_name="test",
        )
        assert result == "recovered"
        assert attempts == 2

    def test_retry_exhaustion_falls_to_next_profile(self):
        call_models: list[str] = []

        def always_transient_on_first(**kw):
            call_models.append(kw["model"])
            if kw["model"] == "anthropic/model-a":
                raise Exception("rate limit exceeded")
            return "second-ok"

        result = execute_with_fallback(
            profiles=[
                _make_profile(slot="primary", model="anthropic/model-a"),
                _make_profile(slot="fallback-1", model="anthropic/model-b"),
            ],
            call_fn=always_transient_on_first,
            base_kwargs={},
            max_retries=1,
            retry_backoff_seconds=0,
            role_name="test",
        )
        assert result == "second-ok"
        # primary attempted 1 initial + 1 retry = 2, then fallback 1
        assert call_models.count("anthropic/model-a") == 2
        assert call_models.count("anthropic/model-b") == 1

    def test_all_profiles_fail_raises_last_exception(self):
        def always_fail(**kw):
            raise Exception(f"rate limit on {kw['model']}")

        with pytest.raises(Exception, match="rate limit on anthropic/model-b"):
            execute_with_fallback(
                profiles=[
                    _make_profile(slot="primary", model="anthropic/model-a"),
                    _make_profile(slot="fallback-1", model="anthropic/model-b"),
                ],
                call_fn=always_fail,
                base_kwargs={},
                max_retries=0,
                retry_backoff_seconds=0,
                role_name="test",
            )

    def test_unusable_profiles_are_skipped(self):
        call_models: list[str] = []

        def capture(**kw):
            call_models.append(kw["model"])
            return "ok"

        unusable = _make_profile(
            slot="primary",
            model="anthropic/model-a",
            api_key="",
            api_key_env="MISSING_KEY",
        )
        assert not unusable.is_usable

        result = execute_with_fallback(
            profiles=[
                unusable,
                _make_profile(slot="fallback-1", model="anthropic/model-b"),
            ],
            call_fn=capture,
            base_kwargs={},
            role_name="test",
        )
        assert result == "ok"
        assert call_models == ["anthropic/model-b"]

    def test_empty_profiles_raises_runtime_error(self):
        with pytest.raises(RuntimeError, match="No model profile configured for planner"):
            execute_with_fallback(
                profiles=[],
                call_fn=lambda **kw: "ok",
                base_kwargs={},
                role_name="planner",
            )

    def test_all_unusable_profiles_raises_runtime_error(self):
        unusable = _make_profile(
            slot="primary",
            model="anthropic/model-a",
            api_key="",
            api_key_env="MISSING_KEY",
        )

        with pytest.raises(RuntimeError, match="No usable model profile for test"):
            execute_with_fallback(
                profiles=[unusable],
                call_fn=lambda **kw: "ok",
                base_kwargs={},
                role_name="test",
            )

    def test_extra_fatal_types_respected(self):
        class HardDeadline(TimeoutError):
            pass

        def raise_deadline(**kw):
            raise HardDeadline("hard deadline exceeded")

        with pytest.raises(HardDeadline):
            execute_with_fallback(
                profiles=[
                    _make_profile(slot="primary"),
                    _make_profile(slot="fallback-1", model="anthropic/model-b"),
                ],
                call_fn=raise_deadline,
                base_kwargs={},
                max_retries=2,
                retry_backoff_seconds=0,
                role_name="test",
                extra_fatal_types=(HardDeadline,),
            )

    def test_api_key_cleared_when_empty(self):
        """Profile with empty api_key should explicitly set None to prevent credential leak."""
        captured: dict = {}

        def spy(**kw):
            captured.update(kw)
            return "done"

        execute_with_fallback(
            profiles=[_make_profile(api_key="", api_base="")],
            call_fn=spy,
            base_kwargs={"messages": []},
            role_name="test",
        )
        assert captured["api_key"] is None
        assert captured["api_base"] is None
