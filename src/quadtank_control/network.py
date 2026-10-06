"""One-way network link with fixed delay, optional jitter, and Bernoulli loss.

All randomness comes from a caller-supplied numpy Generator so a run is
reproducible from its seed. Time is simulated seconds.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class LinkConfig:
    delay_s: float = 0.0
    jitter_s: float = 0.0  # uniform in [0, jitter_s] added to the delay
    loss_prob: float = 0.0

    def __post_init__(self) -> None:
        if self.delay_s < 0 or self.jitter_s < 0:
            raise ValueError("delay and jitter must be non-negative")
        if not 0.0 <= self.loss_prob <= 1.0:
            raise ValueError("loss_prob must be in [0, 1]")


class Link:
    def __init__(self, cfg: LinkConfig, rng: np.random.Generator) -> None:
        self.cfg = cfg
        self._rng = rng

    def transit(self) -> float | None:
        """Seconds a message takes to cross, or None if it is dropped."""
        if self.cfg.loss_prob > 0.0 and self._rng.random() < self.cfg.loss_prob:
            return None
        jitter = self._rng.uniform(0.0, self.cfg.jitter_s) if self.cfg.jitter_s > 0.0 else 0.0
        return self.cfg.delay_s + float(jitter)
