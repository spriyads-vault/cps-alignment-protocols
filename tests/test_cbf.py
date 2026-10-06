import numpy as np
import pytest

from quadtank_control.plant import MIN_PHASE, NON_MIN_PHASE, simulate_hold
from quadtank_control.safety import CBFConfig, CBFFilter

PLANTS = [MIN_PHASE, NON_MIN_PHASE]


def test_passes_through_a_safe_command_unchanged():
    f = CBFFilter(MIN_PHASE)
    r = f.filter(MIN_PHASE.h0, MIN_PHASE.v0)
    assert r.voltages == pytest.approx(MIN_PHASE.v0)
    assert not r.intervened and r.feasible


def test_cuts_an_unsafe_command():
    f = CBFFilter(MIN_PHASE)
    r = f.filter((17.0, 17.0, 6.0, 6.0), (10.0, 10.0))
    assert r.intervened
    assert max(r.voltages) < 10.0
    assert f.margins((17.0, 17.0, 6.0, 6.0), r.voltages).min() >= -1e-6


@pytest.mark.parametrize("p", PLANTS)
@pytest.mark.parametrize(
    ("h", "v_des"),
    [
        ((15.0, 14.0, 4.0, 3.0), (10.0, 10.0)),
        ((16.5, 12.0, 5.0, 2.0), (9.0, 3.0)),
        ((12.0, 16.5, 2.0, 5.0), (3.0, 9.0)),
        ((17.0, 17.0, 8.0, 8.0), (6.0, 6.0)),
    ],
)
def test_matches_brute_force_projection(p, h, v_des):
    """The SLSQP answer must be feasible and about as close to v_des as the best grid point."""
    f = CBFFilter(p)
    r = f.filter(h, v_des)
    grid = np.arange(0.0, p.v_max + 1e-9, 0.25)
    best = np.inf
    for v1 in grid:
        for v2 in grid:
            if f.margins(h, (float(v1), float(v2))).min() >= 0.0:
                best = min(best, float(np.hypot(v1 - v_des[0], v2 - v_des[1])))
    got = float(np.hypot(r.voltages[0] - v_des[0], r.voltages[1] - v_des[1]))
    if np.isfinite(best):
        assert r.feasible
        assert f.margins(h, r.voltages).min() >= -1e-6
        # Grid spacing 0.25 allows the grid optimum to sit up to ~0.18 V off the true one.
        assert got <= best + 0.2
    else:
        assert not r.feasible


@pytest.mark.parametrize("p", PLANTS)
@pytest.mark.parametrize("seed", range(5))
def test_forward_invariance_under_adversarial_commands(p, seed):
    """With the exact model and no delay, the safe set is never left."""
    rng = np.random.default_rng(seed)
    cfg = CBFConfig()
    f = CBFFilter(p, cfg)
    h = np.array(p.h0)
    worst = 0.0
    for _ in range(120):
        v_des = tuple(float(x) for x in rng.choice([0.0, 10.0, rng.uniform(0, 10)], size=2))
        r = f.filter(tuple(h), v_des)  # type: ignore[arg-type]
        h, _, _ = simulate_hold(p, h, np.array(r.voltages), cfg.horizon)
        worst = max(worst, float(h.max()))
    assert worst <= cfg.h_safe + 1e-3


def test_config_validation():
    with pytest.raises(ValueError, match="gamma"):
        CBFConfig(gamma=0.0)
    with pytest.raises(ValueError, match="horizon"):
        CBFConfig(horizon=0.0)
