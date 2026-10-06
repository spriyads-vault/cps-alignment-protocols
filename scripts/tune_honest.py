import itertools

import numpy as np

from quadtank_control.episode import EpisodeConfig, run_episode
from quadtank_control.network import LinkConfig
from quadtank_control.plant import MIN_PHASE, NON_MIN_PHASE
from quadtank_control.protocols import PRESETS, Protocol
from quadtank_control.supervisors import HonestSupervisor


def ev(P, kp, ki, rtt, seed):
    cfg = EpisodeConfig(
        params=P, uplink=LinkConfig(rtt / 2), downlink=LinkConfig(rtt / 2), seed=seed
    )
    r = run_episode(
        cfg, HonestSupervisor(P, kp=(kp, kp), ki=(ki, ki)), Protocol(PRESETS["no_guard"], P)
    )
    return r


for P in (MIN_PHASE, NON_MIN_PHASE):
    print("min" if P.minimum_phase else "nonmin")
    rows = []
    for kp, ki in itertools.product(
        [0.2, 0.4, 0.7, 1.0, 1.5, 2.0], [0.0, 0.002, 0.005, 0.01, 0.02]
    ):
        rs0 = [ev(P, kp, ki, 0.0, s) for s in range(3)]
        rs10 = [ev(P, kp, ki, 10.0, s) for s in range(3)]
        rows.append(
            (
                kp,
                ki,
                np.mean([r.iae for r in rs0]),
                max(r.max_height for r in rs0),
                np.mean([r.iae for r in rs10]),
                max(r.max_height for r in rs10),
            )
        )
    rows.sort(key=lambda r: r[2])
    print(" kp   ki    iae0   maxh0  iae10  maxh10")
    for r in rows[:8]:
        print(f" {r[0]:.1f} {r[1]:.3f} {r[2]:7.1f} {r[3]:6.2f} {r[4]:7.1f} {r[5]:6.2f}")
