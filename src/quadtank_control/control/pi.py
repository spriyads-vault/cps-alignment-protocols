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
    def for_plant(cls, params: QuadTankParams) -> DecentralisedPI:
        """Gains found by hand-tuning on a +2/-2 cm step. Non-minimum-phase needs
        low gain and swapped pairing, otherwise it goes unstable."""
        if params.minimum_phase:
            return cls(params)
        return cls(params, kp=(0.5, 0.5), ki=(0.005, 0.005), swapped=True)

    @classmethod
    def supervisor_like(cls, params: QuadTankParams) -> DecentralisedPI:
        """Gains for a controller running at the 10 s supervisor period.

        Found by grid search on dev seeds 0 to 2 (never on evaluation seeds): lowest
        tracking error subject to max height below 16 cm at zero delay and no overflow
        at a 10 s round trip. Minimum-phase kp 1.5 goes unstable at a 10 s round trip,
        so even an honest supervisor loses to delay.
        """
        if params.minimum_phase:
            return cls(params, kp=(1.0, 1.0), ki=(0.002, 0.002))
        return cls(params, kp=(0.2, 0.2), ki=(0.0, 0.0), swapped=True)

    def reset(self) -> None:
        self._integral = [0.0, 0.0]

    def command(
        self,
        ref: tuple[float, float],
        measured: tuple[float, float],
        dt: float,
        feedforward: tuple[float, float] | None = None,
    ) -> tuple[float, float]:
        ff = feedforward if feedforward is not None else self.params.v0
        out = []
        for i in range(2):
            j = 1 - i if self.swapped else i  # which tank this pump regulates
            err = ref[j] - measured[j]
            u_ff = ff[i]
            # Provisional integral, then clamp so total output stays in [0, v_max].
            integ = self._integral[i] + self.ki[i] * err * dt
            u = u_ff + self.kp[i] * err + integ
            u_clamped = min(max(u, 0.0), self.params.v_max)
            if u == u_clamped:
                self._integral[i] = integ
            out.append(u_clamped)
        return out[0], out[1]

    def proportional(
        self,
        ref: tuple[float, float],
        measured: tuple[float, float],
        feedforward: tuple[float, float] | None = None,
    ) -> tuple[float, float]:
        """Stateless P-only command. Used by monitors as a cheap expected action."""
        ff = feedforward if feedforward is not None else self.params.v0
        out = []
        for i in range(2):
            j = 1 - i if self.swapped else i
            u = ff[i] + self.kp[i] * (ref[j] - measured[j])
            out.append(min(max(u, 0.0), self.params.v_max))
        return out[0], out[1]
