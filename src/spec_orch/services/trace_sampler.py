"""Online evaluation trace sampler (Epic D2).

Routes runs to the evaluation queue based on configurable rules:
- Negative feedback: 100% sampling
- High-cost (token count above threshold): prioritized
- Post-change window: 48h full sampling after model/prompt changes
- Random baseline: configurable percentage for normal traffic
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SamplingRule:
    name: str
    check: str  # "negative_feedback" | "high_cost" | "post_change" | "random"
    sample_rate: float = 1.0
    threshold: float = 0.0


DEFAULT_RULES: list[SamplingRule] = [
    SamplingRule("negative_feedback", "negative_feedback", sample_rate=1.0),
    SamplingRule("high_cost", "high_cost", threshold=50000),
    SamplingRule("random_baseline", "random", sample_rate=0.15),
]


@dataclass
class TraceSampler:
    """Determines whether a completed run should be sampled for online eval."""

    rules: list[SamplingRule] = field(default_factory=lambda: list(DEFAULT_RULES))
    last_change_ts: float = 0.0
    post_change_window_s: float = 48 * 3600

    def should_sample(
        self,
        *,
        run_id: str,
        token_count: int = 0,
        has_negative_feedback: bool = False,
        verdict: str = "",
    ) -> tuple[bool, str]:
        """Return (should_sample, reason) for a completed run."""
        if has_negative_feedback:
            return True, "negative_feedback"

        if self.last_change_ts > 0:
            elapsed = time.time() - self.last_change_ts
            if elapsed < self.post_change_window_s:
                return True, "post_change_window"

        for rule in self.rules:
            if rule.check == "high_cost" and token_count > rule.threshold:
                return True, f"high_cost(tokens={token_count})"

            if rule.check == "random":
                import random

                if random.random() < rule.sample_rate:
                    return True, f"random({rule.sample_rate:.0%})"

        return False, ""

    def record_change(self) -> None:
        """Record a model/prompt change to trigger full sampling window."""
        self.last_change_ts = time.time()
