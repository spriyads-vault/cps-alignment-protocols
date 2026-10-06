"""Quadruple-tank process (Johansson, 2000).

Pumps 1 and 2 feed tanks through valves that split flow between a lower tank
and the diagonally opposite upper tank. Tanks 3 and 4 drain into tanks 1 and 2.
Controlled outputs are the lower tank heights h1 and h2.

    dh1/dt = -a1/A1 sqrt(2g h1) + a3/A1 sqrt(2g h3) + g1 k1 v1 / A1
    dh2/dt = -a2/A2 sqrt(2g h2) + a4/A2 sqrt(2g h4) + g2 k2 v2 / A2
    dh3/dt = -a3/A3 sqrt(2g h3) + (1 - g2) k2 v2 / A3
    dh4/dt = -a4/A4 sqrt(2g h4) + (1 - g1) k1 v1 / A4

With g1 + g2 > 1 the plant is minimum phase. With g1 + g2 < 1 it has a right
half plane zero (non-minimum phase), which makes delay hurt more.

Units: cm, s, V.

[NEED: confirm every number below against Johansson 2000 before any result is
reported. They are recalled from the paper, not copied from it. Known gap: with
these parameters the non-minimum-phase equilibrium at v = 3.15 V is about
(13.3, 14.4, 4.9, 5.6) cm, not the (12.6, 13.0, 4.8, 4.9) cm quoted in the
paper, so one of the recalled numbers is probably wrong. Heights here are
derived from the voltages, so the model is at least self-consistent.]
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

G = 981.0  # cm/s^2


@dataclass(frozen=True)
class QuadTankParams:
    A: tuple[float, float, float, float]  # tank cross-sections, cm^2
    a: tuple[float, float, float, float]  # outlet cross-sections, cm^2
    k: tuple[float, float]  # pump gains, cm^3/(V s)
    gamma: tuple[float, float]  # valve split ratios
    h_max: float = 20.0  # tank height, cm. Overflow above this.
    v_max: float = 10.0  # pump voltage ceiling, V
    v0: tuple[float, float] = (3.0, 3.0)

    @property
    def h0(self) -> tuple[float, float, float, float]:
        """Operating point: the exact equilibrium for v0 under these parameters."""
        return tuple(float(x) for x in equilibrium_heights(self, self.v0))

    @property
    def minimum_phase(self) -> bool:
        return self.gamma[0] + self.gamma[1] > 1.0

    def time_constants(self) -> tuple[float, float, float, float]:
        """T_i = A_i / a_i * sqrt(2 h_i / g) at the operating point."""
        return tuple(
            A / a * np.sqrt(2.0 * h / G)
            for A, a, h in zip(self.A, self.a, self.h0)
        )


MIN_PHASE = QuadTankParams(
    A=(28.0, 32.0, 28.0, 32.0),
    a=(0.071, 0.057, 0.071, 0.057),
    k=(3.33, 3.35),
    gamma=(0.70, 0.60),
    v0=(3.0, 3.0),
)

NON_MIN_PHASE = QuadTankParams(
    A=(28.0, 32.0, 28.0, 32.0),
    a=(0.071, 0.057, 0.071, 0.057),
    k=(3.33, 3.35),
    gamma=(0.43, 0.34),
    v0=(3.15, 3.15),
)


@dataclass(frozen=True)
class StepInfo:
    overflow: bool  # any tank exceeded h_max during this step
    spilled: float  # cm of height lost to spill, summed over tanks
    v_applied: tuple[float, float]  # voltages after saturation


def equilibrium_heights(p: QuadTankParams, v: tuple[float, float]) -> np.ndarray:
    """Steady-state heights for constant pump voltages, in closed form.

    Upper tanks first (inflow = outflow), then lower tanks, which also receive
    the upper tank outflow.
    """
    v1, v2 = v
    g1, g2 = p.gamma
    q3 = (1.0 - g2) * p.k[1] * v2  # inflow to tank 3, cm^3/s
    q4 = (1.0 - g1) * p.k[0] * v1
    q1 = g1 * p.k[0] * v1 + q3  # tank 3 drains into tank 1
    q2 = g2 * p.k[1] * v2 + q4
    q = np.array([q1, q2, q3, q4])
    a = np.array(p.a)
    # outflow = a * sqrt(2 g h) = q  ->  h = (q / a)^2 / (2 g)
    return (q / a) ** 2 / (2.0 * G)


def derivatives(p: QuadTankParams, h: np.ndarray, v: np.ndarray) -> np.ndarray:
    """dh/dt for heights h (cm) and pump voltages v (V)."""
    return np.array(_deriv(p, tuple(float(x) for x in h), (float(v[0]), float(v[1]))))


def _deriv(
    p: QuadTankParams, h: tuple[float, ...], v: tuple[float, float]
) -> tuple[float, float, float, float]:
    """Scalar-float dynamics. Plain floats beat numpy on 4-element vectors by about 5x."""
    A, a, k, g = p.A, p.a, p.k, p.gamma
    s0 = math.sqrt(2.0 * G * max(h[0], 0.0))
    s1 = math.sqrt(2.0 * G * max(h[1], 0.0))
    s2 = math.sqrt(2.0 * G * max(h[2], 0.0))
    s3 = math.sqrt(2.0 * G * max(h[3], 0.0))
    return (
        -a[0] / A[0] * s0 + a[2] / A[0] * s2 + g[0] * k[0] * v[0] / A[0],
        -a[1] / A[1] * s1 + a[3] / A[1] * s3 + g[1] * k[1] * v[1] / A[1],
        -a[2] / A[2] * s2 + (1.0 - g[1]) * k[1] * v[1] / A[2],
        -a[3] / A[3] * s3 + (1.0 - g[0]) * k[0] * v[0] / A[3],
    )


def simulate_hold(
    p: QuadTankParams,
    h: np.ndarray,
    v: np.ndarray,
    dt: float,
    substep: float = 0.1,
) -> tuple[np.ndarray, bool, float]:
    """Advance dt seconds with voltages held (zero-order hold), using RK4.

    Voltages are saturated to [0, v_max]. Water above h_max spills and the height
    stays at the rim. Returns (new heights, overflowed, spilled height in cm).
    The guards call this too, so plant and predictor can never drift apart.
    """
    vs = (
        min(max(float(v[0]), 0.0), p.v_max),
        min(max(float(v[1]), 0.0), p.v_max),
    )
    n = max(1, int(round(dt / substep)))
    step = dt / n
    half = 0.5 * step
    hh = tuple(float(x) for x in h)
    overflow = False
    spilled = 0.0
    for _ in range(n):
        k1 = _deriv(p, hh, vs)
        k2 = _deriv(p, tuple(x + half * d for x, d in zip(hh, k1)), vs)
        k3 = _deriv(p, tuple(x + half * d for x, d in zip(hh, k2)), vs)
        k4 = _deriv(p, tuple(x + step * d for x, d in zip(hh, k3)), vs)
        nxt = []
        for i in range(4):
            x = hh[i] + step / 6.0 * (k1[i] + 2.0 * k2[i] + 2.0 * k3[i] + k4[i])
            x = max(x, 0.0)
            if x > p.h_max:
                overflow = True
                spilled += x - p.h_max
                x = p.h_max
            nxt.append(x)
        hh = tuple(nxt)
    return np.array(hh), overflow, spilled


def equilibrium_voltages(p: QuadTankParams, h_lower: tuple[float, float]) -> np.ndarray:
    """Pump voltages that hold the lower tanks at h_lower in steady state.

    Solves the 2x2 flow balance. Not clipped: a result outside [0, v_max] means
    the reference is unreachable. Singular only when gamma1 + gamma2 == 1.
    """
    g1, g2 = p.gamma
    k1, k2 = p.k
    q = np.array(p.a[:2]) * np.sqrt(2.0 * G * np.asarray(h_lower, dtype=float))
    m = np.array([[g1 * k1, (1.0 - g2) * k2], [(1.0 - g1) * k1, g2 * k2]])
    return np.linalg.solve(m, q)


class QuadTank:
    """Simulated plant. Time is simulated seconds, never wall-clock."""

    def __init__(
        self,
        params: QuadTankParams = MIN_PHASE,
        h_init: tuple[float, float, float, float] | None = None,
        substep: float = 0.1,
    ) -> None:
        self.p = params
        self.substep = substep
        self.h = np.array(h_init if h_init is not None else params.h0, dtype=float)
        self.t = 0.0

    def step(self, v: tuple[float, float], dt: float) -> StepInfo:
        """Advance dt seconds with pump voltages held constant (zero-order hold)."""
        v_sat = np.clip(np.asarray(v, dtype=float), 0.0, self.p.v_max)
        self.h, overflow, spilled = simulate_hold(self.p, self.h, v_sat, dt, self.substep)
        self.t += dt
        return StepInfo(overflow, spilled, (float(v_sat[0]), float(v_sat[1])))

    def measure(self) -> tuple[float, float]:
        """The two lower tank heights, the controlled outputs."""
        return float(self.h[0]), float(self.h[1])

    def state(self) -> tuple[float, float, float, float]:
        """All four heights. Guards and supervisor are assumed to see these (A1)."""
        return (float(self.h[0]), float(self.h[1]), float(self.h[2]), float(self.h[3]))
