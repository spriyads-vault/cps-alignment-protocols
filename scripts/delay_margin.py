"""Model-based prediction of the delay at which the HONEST supervisor's loop goes unstable.

Linearises the plant at its operating point, discretises it at the plant step, closes the
loop with the honest PI supervisor (sampled every supervisor period, command held, one-way
commands delayed by the round-trip time), and finds the smallest round-trip delay at which
the closed loop's one-period map has spectral radius >= 1.

Scope: this predicts when the supervisor's own control loop loses stability, which confounds
the attack thresholds (prediction P5). It does NOT predict the remote-CBF overflow threshold
(P3). That filter is nonlinear and has no closed-form margin here.

Run: uv run python scripts/delay_margin.py
"""

from __future__ import annotations

import numpy as np
from scipy.linalg import expm

from quadtank_control.control import DecentralisedPI
from quadtank_control.plant import MIN_PHASE, NON_MIN_PHASE, QuadTankParams, derivatives

DT = 2.0  # plant step, as in EpisodeConfig
PERIOD = 10.0  # supervisor period


def linearise(p: QuadTankParams) -> tuple[np.ndarray, np.ndarray]:
    h0, v0 = np.array(p.h0), np.array(p.v0)
    eps = 1e-5
    a = np.zeros((4, 4))
    b = np.zeros((4, 2))
    for i in range(4):
        d = np.zeros(4)
        d[i] = eps
        a[:, i] = (derivatives(p, h0 + d, v0) - derivatives(p, h0 - d, v0)) / (2 * eps)
    for i in range(2):
        d = np.zeros(2)
        d[i] = eps
        b[:, i] = (derivatives(p, h0, v0 + d) - derivatives(p, h0, v0 - d)) / (2 * eps)
    return a, b


def spectral_radius(p: QuadTankParams, rtt_s: float) -> float:
    """Spectral radius of the closed loop over one supervisor period.

    A command computed at step 0 of period q is delivered at step `r` of period q + m, where
    lag = ceil(rtt / DT) plant steps, m = lag // steps_per_period and r = lag % steps_per_period.
    State: plant deviation x, integrator z, held command, and the m commands still in transit.
    """
    a, b = linearise(p)
    ad = expm(a * DT)
    bd = np.linalg.solve(a, (ad - np.eye(4)) @ b)
    pi = DecentralisedPI.supervisor_like(p)
    spp = round(PERIOD / DT)
    lag = int(np.ceil(rtt_s / DT - 1e-9))
    m_per, r = divmod(lag, spp)
    n = 8 + 2 * m_per

    def period_map(s: np.ndarray) -> np.ndarray:
        x, z, held = s[:4].copy(), s[4:6].copy(), s[6:8].copy()
        queue = [s[8 + 2 * i : 10 + 2 * i].copy() for i in range(m_per)]
        # decision at step 0, from the state the supervisor sees now
        for i in range(2):
            j = 1 - i if pi.swapped else i
            z[i] += pi.ki[i] * (-x[j]) * PERIOD
        new = np.array([pi.kp[i] * (-x[1 - i if pi.swapped else i]) + z[i] for i in range(2)])
        for k in range(spp):
            if k == r:
                held = new.copy() if m_per == 0 else queue[0].copy()
            x = ad @ x + bd @ held
        if m_per > 0:
            queue = [*queue[1:], new]
        return np.concatenate([x, z, held, *queue]) if m_per else np.concatenate([x, z, held])

    m = np.zeros((n, n))
    for c in range(n):
        e = np.zeros(n)
        e[c] = 1.0
        m[:, c] = period_map(e)
    eig = np.linalg.eigvals(m)
    if all(k == 0.0 for k in pi.ki):
        # With no integral action z never moves. Its two unit eigenvalues are bookkeeping.
        eig = np.delete(eig, np.argsort(np.abs(eig - 1.0))[:2])
    return float(np.max(np.abs(eig)))


def threshold(p: QuadTankParams, grid: np.ndarray) -> float | None:
    prev_r, prev_d = None, None
    for d in grid:
        r = spectral_radius(p, float(d))
        if r >= 1.0:
            if prev_r is None or prev_d is None:
                return float(d)
            return float(prev_d + (1.0 - prev_r) * (d - prev_d) / (r - prev_r))
        prev_r, prev_d = r, d
    return None


if __name__ == "__main__":
    grid = np.arange(0.0, 122.0, 2.0)
    for name, p in (("min_phase", MIN_PHASE), ("non_min_phase", NON_MIN_PHASE)):
        rho0 = spectral_radius(p, 0.0)
        d = threshold(p, grid)
        shown = f"{d:.1f} s" if d is not None else "none up to 120 s"
        print(
            f"{name}: spectral radius at zero delay {rho0:.3f}; honest loop unstable from rtt {shown}"
        )
