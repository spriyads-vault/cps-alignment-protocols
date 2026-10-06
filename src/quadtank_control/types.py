"""Plain data types shared across supervisors, monitors, protocols and the episode loop."""

from __future__ import annotations

from dataclasses import dataclass

Heights = tuple[float, float, float, float]
Voltages = tuple[float, float]


@dataclass(frozen=True)
class Observation:
    """What the supervisor and monitor see at one decision step."""

    t: float  # simulated seconds
    heights: Heights  # all four tank heights, cm (assumption A1)
    ref: tuple[float, float]  # target heights for tanks 1 and 2, cm
    tool_text: str = ""  # untrusted free-text channel (operator notes, sensor annotations)


@dataclass(frozen=True)
class Action:
    """One supervisor decision: pump voltages plus the free-text reasoning shown to the monitor."""

    voltages: Voltages
    rationale: str = ""
