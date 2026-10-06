import numpy as np
import pytest
from hypothesis import given, settings, strategies as st

from quadtank_control.plant import (
    MIN_PHASE,
    NON_MIN_PHASE,
    QuadTank,
    equilibrium_heights,
)

PLANTS = [MIN_PHASE, NON_MIN_PHASE]


@pytest.mark.parametrize("p", PLANTS)
def test_equilibrium_is_a_fixed_point(p):
    plant = QuadTank(p)
    h_before = plant.h.copy()
    plant.step(p.v0, 200.0)
    assert np.allclose(plant.h, h_before, atol=1e-6)


@pytest.mark.parametrize("p", PLANTS)
def test_converges_to_closed_form_equilibrium(p):
    v = (p.v0[0] + 0.5, p.v0[1] - 0.5)
    plant = QuadTank(p, h_init=(5.0, 5.0, 2.0, 2.0))
    plant.step(v, 4000.0)
    assert np.allclose(plant.h, equilibrium_heights(p, v), atol=1e-3)


def test_time_constants_match_johansson():
    # Paper quotes 62, 90, 23, 30 s. [NEED: confirm against the paper itself]
    t = MIN_PHASE.time_constants()
    assert np.allclose(t, (62.0, 90.0, 23.0, 30.0), atol=1.5)


def test_phase_flags():
    assert MIN_PHASE.minimum_phase
    assert not NON_MIN_PHASE.minimum_phase


def test_overflow_is_flagged_and_clipped():
    plant = QuadTank(MIN_PHASE)
    flagged = False
    for _ in range(200):
        info = plant.step((10.0, 10.0), 5.0)
        flagged |= info.overflow
    assert flagged
    assert plant.h.max() <= MIN_PHASE.h_max + 1e-9


def test_voltage_saturates():
    plant = QuadTank(MIN_PHASE)
    info = plant.step((-5.0, 99.0), 1.0)
    assert info.v_applied == (0.0, MIN_PHASE.v_max)


@settings(max_examples=50, deadline=None)
@given(
    v1=st.floats(0.0, 10.0),
    v2=st.floats(0.0, 10.0),
    dt=st.floats(0.1, 20.0),
)
def test_heights_stay_in_bounds(v1, v2, dt):
    plant = QuadTank(MIN_PHASE)
    plant.step((v1, v2), dt)
    assert (plant.h >= 0.0).all()
    assert (plant.h <= MIN_PHASE.h_max + 1e-9).all()


@pytest.mark.parametrize("p", PLANTS)
def test_water_mass_balance(p):
    """Stored volume change equals pump inflow minus outflow through tanks 1 and 2.

    Tanks 3 and 4 drain into tanks 1 and 2, so their outflow is internal.
    """
    from quadtank_control.plant.quadtank import G

    v = (p.v0[0], p.v0[1] + 0.3)
    plant = QuadTank(p)
    h_start = plant.h.copy()
    dt, n = 1.0, 60
    inflow = (p.k[0] * v[0] + p.k[1] * v[1]) * dt * n
    outflow = 0.0
    for _ in range(n):
        outflow += sum(
            p.a[i] * np.sqrt(2 * G * plant.h[i]) * dt for i in (0, 1)
        )
        plant.step(v, dt)
    stored = float(np.dot(p.A, plant.h - h_start))
    assert stored == pytest.approx(inflow - outflow, rel=0.05, abs=2.0)


@pytest.mark.parametrize("p", PLANTS)
def test_equilibrium_voltages_round_trip(p):
    from quadtank_control.plant import equilibrium_voltages

    target = (p.h0[0] + 1.5, p.h0[1] - 1.0)
    v = equilibrium_voltages(p, target)
    h = equilibrium_heights(p, (float(v[0]), float(v[1])))
    assert (h[0], h[1]) == pytest.approx(target, abs=1e-9)


def test_simulate_hold_does_not_mutate_input():
    from quadtank_control.plant import simulate_hold

    h = np.array(MIN_PHASE.h0)
    before = h.copy()
    simulate_hold(MIN_PHASE, h, np.array([5.0, 5.0]), 10.0)
    assert np.array_equal(h, before)
