from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from ..types import Action, Observation


class Supervisor(ABC):
    """The untrusted component that sets pump voltages. Honest or attacking."""

    name: str = "supervisor"

    def reset(self, rng: np.random.Generator) -> None:  # noqa: B027 - optional hook
        """Called once at the start of each episode with that episode's generator."""

    @abstractmethod
    def act(self, obs: Observation) -> Action: ...
