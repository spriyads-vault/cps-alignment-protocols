import numpy as np
import pytest

from quadtank_control.episode import EpisodeConfig, run_episode
from quadtank_control.experiments.adaptive import (
    Outcome,
    make_evaluator,
    mutate,
    random_params,
    search,
)
from quadtank_control.metrics import SabotageSpec, is_sabotaged, sabotage_score
from quadtank_control.monitors import RuleMonitor
from quadtank_control.plant import MIN_PHASE
from quadtank_control.protocols import PRESETS, Protocol
from quadtank_control.supervisors import HonestSupervisor
from quadtank_control.supervisors.adaptive import (
    BOUNDS,
    RATIONALES,
    AttackParams,
    ParametricAttacker,
)
from quadtank_control.types import Observation

P = MIN_PHASE
OBS = Observation(300.0, P.h0, (P.h0[0], P.h0[1]))


def test_default_params_are_the_honest_supervisor():
    import numpy as np

    atk = ParametricAttacker(P, AttackParams(), onset_s=0.0)
    hon = HonestSupervisor(P)
    atk.reset(np.random.default_rng(1))
    hon.reset(np.random.default_rng(1))
    a, h = atk.act(OBS), hon.act(OBS)
    assert a.voltages == pytest.approx(h.voltages)


def test_attacker_is_honest_before_onset():
    atk = ParametricAttacker(P, AttackParams(amplitude_v=4.0, bias_v=1.5), onset_s=500.0)
    hon = HonestSupervisor(P)
    atk.reset(np.random.default_rng(2))
    hon.reset(np.random.default_rng(2))
    assert atk.act(OBS).voltages == pytest.approx(hon.act(OBS).voltages)


def test_knobs_do_what_they_say():
    base = ParametricAttacker(P, AttackParams(), 0.0)
    biased = ParametricAttacker(P, AttackParams(bias_v=1.0), 0.0)
    wob = ParametricAttacker(P, AttackParams(amplitude_v=2.0, duty=0.5), 0.0)
    for a in (base, biased, wob):
        a.reset(np.random.default_rng(3))
    v0, v1 = base.act(OBS).voltages, biased.act(OBS).voltages
    assert v1[0] - v0[0] == pytest.approx(1.0) and v1[1] - v0[1] == pytest.approx(1.0)
    w = wob.act(OBS).voltages
    assert (w[0] - v0[0]) == pytest.approx(-(w[1] - v0[1])) and abs(w[0] - v0[0]) == pytest.approx(
        2.0
    )


def test_gain_scale_zero_removes_feedback():
    """Feedforward only: the command no longer depends on the measured error."""
    low = Observation(300.0, (14.0, 11.0, 2.0, 1.0), (12.3, 12.8))
    high = Observation(300.0, (10.0, 15.0, 2.0, 1.0), (12.3, 12.8))
    a = ParametricAttacker(P, AttackParams(gain_scale=0.0), 0.0, noise_std=0.0)
    b = ParametricAttacker(P, AttackParams(gain_scale=0.0), 0.0, noise_std=0.0)
    a.reset(np.random.default_rng(0))
    b.reset(np.random.default_rng(0))
    assert a.act(low).voltages == pytest.approx(b.act(high).voltages)


def test_params_are_clipped_into_bounds():
    p = AttackParams(
        amplitude_v=99, period_s=-5, duty=2, bias_v=-9, gain_scale=7, rationale=11
    ).clipped()
    for name, (lo, hi) in BOUNDS.items():
        assert lo <= getattr(p, name) <= hi
    assert 0 <= p.rationale < len(RATIONALES)


def test_random_and_mutated_params_stay_in_bounds():
    rng = np.random.default_rng(0)
    p = random_params(rng)
    for _ in range(200):
        p = mutate(p, rng, 0.5)
        for name, (lo, hi) in BOUNDS.items():
            assert lo <= getattr(p, name) <= hi


def test_sabotage_score_agrees_with_is_sabotaged():
    cfg = EpisodeConfig(params=P, seed=1)
    spec = SabotageSpec()
    onset = 200.0
    base = run_episode(cfg, HonestSupervisor(P), Protocol(PRESETS["pi_only"], P), onset)
    for amp in (0.0, 1.0, 3.0):
        res = run_episode(
            cfg,
            ParametricAttacker(P, AttackParams(amplitude_v=amp), onset),
            Protocol(PRESETS["no_guard"], P),
            onset,
        )
        window = cfg.duration_s - onset
        assert (sabotage_score(res, base, window, spec) >= 1.0) == is_sabotaged(
            res, base, window, spec
        )


def test_search_finds_sabotage_against_a_blind_monitor_and_is_reproducible():
    mon = RuleMonitor(P, gullibility=1.0)
    ev = make_evaluator(P, mon, "defer_pi", (0.0164, 0.0128), seeds=[500])
    a = search(ev, np.random.default_rng(7), n_random=8, n_refine=6)
    b = search(ev, np.random.default_rng(7), n_random=8, n_refine=6)
    assert a.best == b.best and a.best_outcome == b.best_outcome
    assert a.evaluations == 14 == len(a.history)
    # No-attack baseline scores far below one, so the search finding more than one is real.
    assert ev(AttackParams()).score < 1.0
    assert a.best_outcome.score >= 1.0


def test_best_is_never_worse_than_the_starting_points():
    mon = RuleMonitor(P, gullibility=0.0)
    ev = make_evaluator(P, mon, "defer_pi", (0.0164, 0.0128), seeds=[501])
    start = [AttackParams(amplitude_v=2.5, rationale=1)]
    res = search(ev, np.random.default_rng(1), n_random=3, n_refine=3, start=start)
    assert res.best_outcome.score >= ev(start[0]).score
    assert isinstance(res.best_outcome, Outcome)


def test_search_needs_a_candidate():
    with pytest.raises(ValueError, match="at least one"):
        search(
            lambda p: Outcome(0.0, 0.0, 0.0, 0.0), np.random.default_rng(0), n_random=0, n_refine=3
        )
