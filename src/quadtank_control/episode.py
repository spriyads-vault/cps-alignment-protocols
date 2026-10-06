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

from dataclasses import dataclass, field

from .network import LinkConfig
from .plant import MIN_PHASE, QuadTankParams
from .protocols import Protocol
from .supervisors import Supervisor


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
    from .env import EpisodeEnv  # local import: env.py needs this module's dataclasses

    env = EpisodeEnv(cfg, protocol, onset_s)
    supervisor.reset(env.supervisor_rng)
    while not env.done:
        env.step_decision(supervisor.act(env.observation()))
    return env.result()
