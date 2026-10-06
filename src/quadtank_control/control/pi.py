"""Decentralised PI controller: the trusted fallback and the usefulness baseline.

Two independent loops, pump 1 -> h1 and pump 2 -> h2 (or swapped, which the
non-minimum-phase plant needs), each with the steady-state
voltage as feedforward and a clamped integrator (anti-windup).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..plant import QuadTankParams


@dataclass
class DecentralisedPI:
    params: QuadTankParams
    kp: tuple[float, float] = (3.0, 3.0)  # V per cm
    ki: tuple[float, float] = (0.05, 0.05)  # V per (cm s)
    swapped: bool = False  # True: pump 1 drives h2 and pump 2 drives h1
    _integral: list[float] = field(default_factory=lambda: [0.0, 0.0])

    @classmethod
    def for_plant(cls, params: QuadTankParams) -> "DecentralisedPI":
        """Gains found by hand-tuning on a +2/-2 cm step. Non-minimum-phase needs
        low gain and swapped pairing, otherwise it goes unstable."""
        if params.minimum_phase:
            return cls(params)
        return cls(params, kp=(0.5, 0.5), ki=(0.005, 0.005), swapped=True)

    def reset(self) -> None:
        self._integral = [0.0, 0.0]

    def command(
        self,
        ref: tuple[float, float],
        measured: tuple[float, float],
        dt: float,
    ) -> tuple[float, float]:
        out = []
        for i in range(2):
            j = 1 - i if self.swapped else i  # which tank this pump regulates
            err = ref[j] - measured[j]
            u_ff = self.params.v0[i]
            # Provisional integral, then clamp so total output stays in [0, v_max].
            integ = self._integral[i] + self.ki[i] * err * dt
            u = u_ff + self.kp[i] * err + integ
            u_clamped = min(max(u, 0.0), self.params.v_max)
            if u == u_clamped:
                self._integral[i] = integ
            out.append(u_clamped)
        return out[0], out[1]
