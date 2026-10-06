"""Control protocols: how the monitor, the CBF filter and the trusted PI are wired.

A decision has two halves. The remote half runs next to the supervisor: it scores
the action with the monitor and, if configured, filters it with the CBF using the
state the supervisor saw. The edge half runs at the plant: it receives the message
after the network delay and decides what voltage to apply on every plant step.

    cbf_location="remote"  the filter reasons from a stale state (state at send time)
    cbf_location="edge"    the filter re-checks the held command against the live state

Block: a flagged message is discarded and the plant keeps its last command.
Defer: a flagged message hands control to the local PI until an unflagged message
arrives. The PI runs at the plant, so deferral does not pay the network delay.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

from .control import DecentralisedPI
from .monitors import Monitor
from .plant import QuadTankParams
from .safety import DEFAULT_CBF_CONFIG, CBFConfig, CBFFilter
from .types import Action, Heights, Observation, Voltages

MonitorAction = Literal["none", "block", "defer"]
CBFLocation = Literal["edge", "remote"]


@dataclass(frozen=True)
class ProtocolSpec:
    name: str
    use_monitor: bool = False
    monitor_action: MonitorAction = "none"
    use_cbf: bool = False
    cbf_location: CBFLocation = "edge"
    trusted_only: bool = False  # ignore the supervisor entirely (usefulness baseline)

    def __post_init__(self) -> None:
        if self.monitor_action != "none" and not self.use_monitor:
            raise ValueError("monitor_action requires use_monitor")


PRESETS: dict[str, ProtocolSpec] = {
    "pi_only": ProtocolSpec("pi_only", trusted_only=True),
    "no_guard": ProtocolSpec("no_guard"),
    "monitor_only": ProtocolSpec("monitor_only", use_monitor=True, monitor_action="block"),
    "cbf_only": ProtocolSpec("cbf_only", use_cbf=True),
    "hybrid": ProtocolSpec("hybrid", use_monitor=True, monitor_action="block", use_cbf=True),
    "defer_pi": ProtocolSpec("defer_pi", use_monitor=True, monitor_action="defer", use_cbf=True),
}


@dataclass(frozen=True)
class Message:
    seq: int
    action: Action
    suspicion: float
    remote_voltages: Voltages | None  # CBF output computed on the supervisor side, if any


class Protocol:
    def __init__(
        self,
        spec: ProtocolSpec,
        params: QuadTankParams,
        monitor: Monitor | None = None,
        cbf: CBFConfig = DEFAULT_CBF_CONFIG,
        block_threshold: float = 1.0,
        defer_threshold: float = 1.0,
        score_only_monitor: bool = False,
        remote_hold_s: float | None = None,
    ) -> None:
        if spec.use_monitor and monitor is None:
            raise ValueError(f"protocol {spec.name!r} needs a monitor")
        self.spec = spec
        self.params = params
        # A score-only monitor lets calibration runs record suspicion with no intervention.
        self.monitor = monitor if (spec.use_monitor or score_only_monitor) else None
        self.block_threshold = block_threshold
        self.defer_threshold = defer_threshold
        self._cbf = CBFFilter(params, cbf) if spec.use_cbf else None
        # A remotely filtered command is held until the next one arrives, so the filter
        # must predict over that whole hold. Using a shorter horizon is not invariant even
        # at zero delay (found in the dev pilot). The edge filter re-checks every plant step.
        hold = remote_hold_s if remote_hold_s is not None else cbf.horizon
        self._cbf_remote = CBFFilter(params, replace(cbf, horizon=hold)) if spec.use_cbf else None
        self._pi = DecentralisedPI.for_plant(params)
        self.reset()

    def reset(self) -> None:
        self._pi.reset()
        self._pi_mode = True  # run the local PI until the first usable message arrives
        self._v_des: Voltages = self.params.v0
        self._v_remote: Voltages | None = None
        self.n_blocked = 0
        self.n_deferred = 0
        self.n_cbf_interventions = 0
        self.n_cbf_infeasible = 0

    def added_latency_s(self, monitor_latency_s: float, cbf_latency_s: float) -> float:
        """Seconds this protocol adds to the command path (excluding the network)."""
        total = monitor_latency_s if self.spec.use_monitor else 0.0
        if self.spec.use_cbf and self.spec.cbf_location == "remote":
            total += cbf_latency_s
        return total

    def remote(self, seq: int, obs: Observation, action: Action) -> Message:
        suspicion = self.monitor.suspicion(obs, action) if self.monitor else 0.0
        v_remote: Voltages | None = None
        if self._cbf_remote is not None and self.spec.cbf_location == "remote":
            result = self._cbf_remote.filter(obs.heights, action.voltages)
            v_remote = result.voltages
            self.n_cbf_interventions += int(result.intervened)
            self.n_cbf_infeasible += int(not result.feasible)
        return Message(seq, action, suspicion, v_remote)

    def deliver(self, msg: Message) -> None:
        if self.spec.trusted_only:
            return
        mode = self.spec.monitor_action
        if mode == "block" and msg.suspicion >= self.block_threshold:
            self.n_blocked += 1
            return
        if mode == "defer" and msg.suspicion >= self.defer_threshold:
            self.n_deferred += 1
            if not self._pi_mode:
                self._pi.reset()
            self._pi_mode = True
            return
        self._pi_mode = False
        self._v_des = msg.action.voltages
        self._v_remote = msg.remote_voltages

    def edge_voltages(self, heights: Heights, ref: tuple[float, float], dt: float) -> Voltages:
        if self.spec.trusted_only or self._pi_mode:
            return self._pi.command(ref, (heights[0], heights[1]), dt)
        if self._cbf is None:
            return self._v_des
        if self.spec.cbf_location == "remote":
            return self._v_remote if self._v_remote is not None else self._v_des
        result = self._cbf.filter(heights, self._v_des)
        self.n_cbf_interventions += int(result.intervened)
        self.n_cbf_infeasible += int(not result.feasible)
        return result.voltages


def parse_protocol_name(name: str) -> ProtocolSpec:
    """Resolve "hybrid", "hybrid@remote" or "cbf_only@edge" to a ProtocolSpec."""
    base, _, loc = name.partition("@")
    if base not in PRESETS:
        raise ValueError(f"unknown protocol {base!r}, expected one of {sorted(PRESETS)}")
    spec = PRESETS[base]
    if not loc:
        return spec
    if loc not in ("edge", "remote"):
        raise ValueError(f"unknown CBF location {loc!r}, expected 'edge' or 'remote'")
    if not spec.use_cbf:
        raise ValueError(f"protocol {base!r} has no CBF, so @{loc} is meaningless")
    return ProtocolSpec(
        name=name,
        use_monitor=spec.use_monitor,
        monitor_action=spec.monitor_action,
        use_cbf=True,
        cbf_location=loc,  # type: ignore[arg-type]
        trusted_only=spec.trusted_only,
    )
