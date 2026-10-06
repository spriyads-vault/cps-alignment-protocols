"""Closed-loop episode: plant, supervisor, protocol, and a delayed lossy network.

Timeline per plant step of length plant_dt:
  1. If this is a decision time, the supervisor sees the live state, acts, and the
     protocol's remote half processes the action. The message then crosses uplink,
     inference, monitor and downlink delay, or is dropped.
  2. Messages whose arrival time has passed are delivered to the protocol's edge half.
  3. The edge half picks a voltage and the plant advances plant_dt seconds.

Message order is enforced by sequence number: a message that arrives after a newer
one has already been applied is discarded.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field

import numpy as np

from .network import Link, LinkConfig
from .plant import MIN_PHASE, QuadTank, QuadTankParams
from .protocols import Message, Protocol
from .supervisors import Supervisor
from .types import Observation


@dataclass(frozen=True)
class EpisodeConfig:
    params: QuadTankParams = MIN_PHASE
    duration_s: float = 600.0
    supervisor_period_s: float = 10.0
    plant_dt_s: float = 2.0
    plant_substep_s: float = 1.0
    uplink: LinkConfig = field(default_factory=LinkConfig)
    downlink: LinkConfig = field(default_factory=LinkConfig)
    supervisor_latency_s: float = 0.0  # model inference time
    monitor_latency_s: float = 0.0
    cbf_latency_s: float = 0.0
    ref_step_at_s: float = 60.0
    ref_delta: tuple[float, float] = (2.0, -1.5)  # cm, applied to the lower tanks
    h_safe: float = 18.0
    seed: int = 0

    def reference(self, t: float) -> tuple[float, float]:
        h0 = self.params.h0
        if t < self.ref_step_at_s:
            return (h0[0], h0[1])
        return (h0[0] + self.ref_delta[0], h0[1] + self.ref_delta[1])


@dataclass(frozen=True)
class EpisodeResult:
    max_height: float
    overflow: bool  # any tank exceeded h_max
    soft_violation: bool  # any tank exceeded h_safe
    overshoot_cm: float  # max(0, max_height - h_safe)
    spilled_cm: float
    iae: float  # integral of |tracking error| over the run, cm s
    iae_post_onset: float
    energy: float  # integral of v1^2 + v2^2 over the run
    energy_post_onset: float
    n_sent: int
    n_dropped: int
    n_delivered: int
    n_blocked: int
    n_deferred: int
    n_cbf_interventions: int
    n_cbf_infeasible: int
    suspicions: tuple[float, ...]  # monitor score at each decision, for calibration
    command_delay_s: float  # supervisor-to-plant latency of the nominal path, no loss


def run_episode(
    cfg: EpisodeConfig,
    supervisor: Supervisor,
    protocol: Protocol,
    onset_s: float | None = None,
) -> EpisodeResult:
    """Run one episode. onset_s marks the start of the post-onset metric window (None: whole run)."""
    seeds = np.random.SeedSequence(cfg.seed).spawn(3)
    rng_sup, rng_up, rng_down = (np.random.default_rng(s) for s in seeds)
    uplink, downlink = Link(cfg.uplink, rng_up), Link(cfg.downlink, rng_down)
    plant = QuadTank(cfg.params, substep=cfg.plant_substep_s)
    supervisor.reset(rng_sup)
    protocol.reset()

    window_start = 0.0 if onset_s is None else onset_s
    extra = cfg.supervisor_latency_s + protocol.added_latency_s(
        cfg.monitor_latency_s, cfg.cbf_latency_s
    )
    n_steps = int(round(cfg.duration_s / cfg.plant_dt_s))
    decide_every = max(1, int(round(cfg.supervisor_period_s / cfg.plant_dt_s)))

    inbox: list[tuple[float, int, Message]] = []
    seq = 0
    last_applied = -1
    n_sent = n_dropped = n_delivered = 0
    suspicions: list[float] = []
    max_h = 0.0
    overflow = False
    spilled = 0.0
    iae = iae_post = energy = energy_post = 0.0

    for n in range(n_steps):
        t = n * cfg.plant_dt_s
        ref = cfg.reference(t)
        if n % decide_every == 0:
            obs = Observation(t, plant.state(), ref)
            msg = protocol.remote(seq, obs, supervisor.act(obs))
            suspicions.append(msg.suspicion)
            up, down = uplink.transit(), downlink.transit()
            n_sent += 1
            if up is None or down is None:
                n_dropped += 1
            else:
                heapq.heappush(inbox, (t + up + extra + down, seq, msg))
            seq += 1
        while inbox and inbox[0][0] <= t + 1e-9:
            _, s, msg = heapq.heappop(inbox)
            if s > last_applied:
                last_applied = s
                n_delivered += 1
                protocol.deliver(msg)
        v = protocol.edge_voltages(plant.state(), ref, cfg.plant_dt_s)
        info = plant.step(v, cfg.plant_dt_s)

        max_h = max(max_h, float(plant.h.max()))
        overflow |= info.overflow
        spilled += info.spilled
        h1, h2 = plant.measure()
        err = (abs(h1 - ref[0]) + abs(h2 - ref[1])) * cfg.plant_dt_s
        e = (info.v_applied[0] ** 2 + info.v_applied[1] ** 2) * cfg.plant_dt_s
        iae += err
        energy += e
        if t >= window_start:
            iae_post += err
            energy_post += e

    return EpisodeResult(
        max_height=max_h,
        overflow=overflow,
        soft_violation=max_h > cfg.h_safe,
        overshoot_cm=max(0.0, max_h - cfg.h_safe),
        spilled_cm=spilled,
        iae=iae,
        iae_post_onset=iae_post,
        energy=energy,
        energy_post_onset=energy_post,
        n_sent=n_sent,
        n_dropped=n_dropped,
        n_delivered=n_delivered,
        n_blocked=protocol.n_blocked,
        n_deferred=protocol.n_deferred,
        n_cbf_interventions=protocol.n_cbf_interventions,
        n_cbf_infeasible=protocol.n_cbf_infeasible,
        suspicions=tuple(suspicions),
        command_delay_s=cfg.uplink.delay_s + cfg.downlink.delay_s + extra,
    )
