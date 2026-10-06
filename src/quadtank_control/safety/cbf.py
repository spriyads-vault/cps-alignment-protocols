"""Discrete-time control barrier function (CBF) safety filter.

Safe set: every tank height at or below h_safe. For each tank i the barrier is
B_i(h) = h_safe - h_i. A command v, held for `horizon` seconds, is admissible when
the nominal model predicts

    B_i(h_next(v)) >= (1 - gamma) * B_i(h)        for i = 1..4

(Agrawal and Sreenath, 2017). The filter returns the admissible command closest
to the desired one in Euclidean distance. It reads only voltages and heights,
never text, so it cannot be prompt-injected. It is also blind to harm that stays
inside the safe set.

Assumptions: the filter has the exact plant model (A2) and sees all four heights (A1).
The state it reasons from may be stale if the filter runs far from the plant.

The prediction is a black-box simulation, so the projection is solved with SLSQP.
Heights are a monotone function of the voltages (the plant is cooperative), which
keeps the feasible set well-behaved. tests/test_cbf.py checks the solver against a
brute-force grid search.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize

from ..plant import QuadTankParams, simulate_hold
from ..types import Heights, Voltages

_FEASIBLE_TOL = 1e-6


@dataclass(frozen=True)
class CBFConfig:
    h_safe: float = 18.0
    gamma: float = 0.5  # in (0, 1]. Larger is looser.
    horizon: float = 5.0  # seconds the command is assumed to be held
    substep: float = 1.0  # prediction RK4 step

    def __post_init__(self) -> None:
        if not 0.0 < self.gamma <= 1.0:
            raise ValueError("gamma must be in (0, 1]")
        if self.horizon <= 0.0:
            raise ValueError("horizon must be positive")


@dataclass(frozen=True)
class FilterResult:
    voltages: Voltages
    intervened: bool
    feasible: bool  # False: no admissible command found, fell back to pumps off


class CBFFilter:
    def __init__(self, model: QuadTankParams, cfg: CBFConfig = CBFConfig()) -> None:
        self.model = model
        self.cfg = cfg

    def margins(self, h: Heights, v: Voltages) -> np.ndarray:
        """Constraint slack per tank. Admissible when every entry is >= 0."""
        h_arr = np.asarray(h, dtype=float)
        h_next, _, _ = simulate_hold(
            self.model, h_arr, np.asarray(v, dtype=float), self.cfg.horizon, self.cfg.substep
        )
        b_now = self.cfg.h_safe - h_arr
        b_next = self.cfg.h_safe - h_next
        return b_next - (1.0 - self.cfg.gamma) * b_now

    def filter(self, h: Heights, v_des: Voltages) -> FilterResult:
        v_max = self.model.v_max
        v0 = np.clip(np.asarray(v_des, dtype=float), 0.0, v_max)
        if self.margins(h, (float(v0[0]), float(v0[1]))).min() >= -_FEASIBLE_TOL:
            return FilterResult((float(v0[0]), float(v0[1])), v_des != tuple(v0), True)

        res = minimize(
            lambda v: float(np.sum((v - v0) ** 2)),
            x0=v0,
            jac=lambda v: 2.0 * (v - v0),
            bounds=[(0.0, v_max), (0.0, v_max)],
            constraints=[
                {"type": "ineq", "fun": lambda v: self.margins(h, (float(v[0]), float(v[1])))}
            ],
            method="SLSQP",
            options={"ftol": 1e-10, "eps": 1e-4, "maxiter": 100},
        )
        v = np.clip(res.x, 0.0, v_max)
        if self.margins(h, (float(v[0]), float(v[1]))).min() >= -_FEASIBLE_TOL:
            return FilterResult((float(v[0]), float(v[1])), True, True)
        # Solver failed or the problem is infeasible. Pumps off drains the tanks fastest.
        return FilterResult((0.0, 0.0), True, False)
