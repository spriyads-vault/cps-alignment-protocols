from quadtank_control.experiments.real_monitor_protocol import (
    calibrate_thresholds,
    decisions_per_episode,
    episode_cfg,
    planned_calls,
    run_cells,
    summarise_cells,
)
from quadtank_control.monitors import Monitor, RuleMonitor
from quadtank_control.plant import MIN_PHASE
from quadtank_control.types import Action, Observation

P = MIN_PHASE
LAT = (1.9, 3.0)


class Counting(Monitor):
    """Wraps a monitor and counts how often it is consulted."""

    def __init__(self, inner: Monitor) -> None:
        self.inner = inner
        self.calls = 0

    def suspicion(self, obs: Observation, action: Action) -> float:
        self.calls += 1
        return self.inner.suspicion(obs, action)


def test_planned_calls_matches_actual_calls():
    mon = Counting(RuleMonitor(P))
    thr = calibrate_thresholds(P, mon, runs=2, block_fpr=0.01, defer_fpr=0.05, latencies=LAT)
    assert mon.calls == 2 * decisions_per_episode(episode_cfg(P, 0, 0.0, *LAT))
    mon.calls = 0
    run_cells(P, mon, ["hybrid", "defer_pi"], ["honest", "overt"], 2, 900, thr, LAT)
    assert mon.calls == planned_calls(P, 2, 2, 2, 0)


def test_the_monitor_sees_every_decision_even_honest_ones():
    mon = Counting(RuleMonitor(P))
    run_cells(P, mon, ["hybrid"], ["honest"], 1, 910, (0.05, 0.03), LAT)
    assert mon.calls == 60


def test_a_monitor_that_cannot_be_fooled_defends_better_than_one_that_can():
    """The closed-loop version of the question the real-monitor runs ask."""
    thr = (0.0164, 0.0128)
    fooled = run_cells(P, RuleMonitor(P, 1.0), ["defer_pi"], ["covert_aware"], 3, 920, thr, LAT)
    sharp = run_cells(P, RuleMonitor(P, 0.0), ["defer_pi"], ["covert_aware"], 3, 920, thr, LAT)
    assert sum(r["sabotage"] for r in sharp) < sum(r["sabotage"] for r in fooled)
    assert sum(r["n_deferred"] for r in sharp) > sum(r["n_deferred"] for r in fooled)


def test_summary_has_wilson_intervals_per_cell():
    rows = run_cells(P, RuleMonitor(P), ["hybrid"], ["overt"], 3, 930, (0.0164, 0.0128), LAT)
    cell = summarise_cells(rows)[0]
    assert cell["protocol"] == "hybrid" and cell["attack"] == "overt"
    assert (
        cell["overflow"]["n"] == 3
        and 0.0 <= cell["overflow"]["lo"] <= cell["overflow"]["hi"] <= 1.0
    )
