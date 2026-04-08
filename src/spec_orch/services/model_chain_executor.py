"""Shared model-chain fallback executor for LiteLLM-based adapters.

Provides ``execute_with_fallback`` which iterates through a list of
``ResolvedLiteLLMProfile`` entries, retries transient errors with
exponential back-off, and raises immediately on fatal errors.  Once a
profile exhausts its retries (transient-only), execution falls through
to the next profile in the chain.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any, TypeVar

from spec_orch.services.litellm_profile import ResolvedLiteLLMProfile

logger = logging.getLogger(__name__)
T = TypeVar("T")

_TRANSIENT_MARKERS: tuple[str, ...] = (
    "overloaded_error",
    "rate limit",
    "rate_limit",
    "429",
    "529",
    "temporarily unavailable",
    "service unavailable",
    "server overloaded",
    "try again later",
)

_FATAL_MARKERS: tuple[str, ...] = (
    "invalid x-api-key",
    "authentication_error",
    "unauthorized",
    "forbidden",
    "invalid api key",
    "missing_api_base",
)


def is_transient_litellm_error(
    exc: Exception,
    *,
    extra_fatal_types: tuple[type[Exception], ...] = (),
) -> bool:
    """Return *True* when *exc* looks like a transient LiteLLM error.

    Parameters
    ----------
    exc:
        The exception to classify.
    extra_fatal_types:
        Additional exception types that should always be treated as fatal
        (e.g. adapter-specific hard-deadline timeouts).
    """
    if extra_fatal_types and isinstance(exc, extra_fatal_types):
        return False
    if isinstance(exc, TimeoutError):
        return True
    message = str(exc).lower()
    if any(marker in message for marker in _FATAL_MARKERS):
        return False
    return any(marker in message for marker in _TRANSIENT_MARKERS)


def execute_with_fallback(
    *,
    profiles: list[ResolvedLiteLLMProfile],
    call_fn: Callable[..., T],
    base_kwargs: dict[str, Any],
    max_retries: int = 2,
    retry_backoff_seconds: float = 1.0,
    role_name: str = "unknown",
    extra_fatal_types: tuple[type[Exception], ...] = (),
) -> T:
    """Execute a LiteLLM call with model-chain fallback.

    Iterates through *profiles* in order.  For each usable profile the
    executor merges profile-specific keys (``model``, ``api_key``,
    ``api_base``) into *base_kwargs* and calls *call_fn*.

    * **Transient errors** are retried up to *max_retries* times with
      exponential back-off (``retry_backoff_seconds * 2 ** attempt``).
      When retries are exhausted the executor moves to the next profile.
    * **Fatal errors** (auth failures, missing keys, or any type listed
      in *extra_fatal_types*) are raised immediately.

    Raises the last captured exception when all profiles are exhausted.
    """
    if not profiles:
        raise RuntimeError(f"No model profile configured for {role_name}")

    last_exc: Exception | None = None
    for profile in profiles:
        if not profile.is_usable:
            logger.debug(
                "Skipping unusable profile %s for %s",
                profile.slot,
                role_name,
            )
            continue

        kwargs = dict(base_kwargs)
        kwargs["model"] = profile.model
        kwargs["api_key"] = profile.api_key or None
        kwargs["api_base"] = profile.api_base or None

        attempt = 0
        while True:
            try:
                return call_fn(**kwargs)
            except Exception as exc:
                last_exc = exc
                if attempt < max_retries and is_transient_litellm_error(
                    exc, extra_fatal_types=extra_fatal_types
                ):
                    attempt += 1
                    if retry_backoff_seconds > 0:
                        time.sleep(retry_backoff_seconds * (2**attempt))
                    continue
                if not is_transient_litellm_error(exc, extra_fatal_types=extra_fatal_types):
                    raise
                break  # retries exhausted on transient error → next profile

    if last_exc is not None:
        raise last_exc
    raise RuntimeError(f"No usable model profile for {role_name}")
