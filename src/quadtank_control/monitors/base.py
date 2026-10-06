from __future__ import annotations

from abc import ABC, abstractmethod

from ..types import Action, Observation


class Monitor(ABC):
    """Scores how suspicious a supervisor action is, in [0, 1]. Higher is worse."""

    name: str = "monitor"

    @abstractmethod
    def suspicion(self, obs: Observation, action: Action) -> float: ...
