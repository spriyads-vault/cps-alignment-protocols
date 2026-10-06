import pytest

from quadtank_control.control import DecentralisedPI
from quadtank_control.plant import MIN_PHASE, NON_MIN_PHASE, QuadTank


@pytest.mark.parametrize("p", [MIN_PHASE, NON_MIN_PHASE])
def test_pi_tracks_step_without_overflow(p):
    """Gate for the whole simulation: if this fails the sim is wrong."""
    plant = QuadTank(p)
    pi = DecentralisedPI.for_plant(p)
    ref = (p.h0[0] + 2.0, p.h0[1] - 2.0)
    overflow = False
    for _ in range(600):
        info = plant.step(pi.command(ref, plant.measure(), 5.0), 5.0)
        overflow |= info.overflow
    assert not overflow
    assert plant.measure() == pytest.approx(ref, abs=0.2)


def test_pi_output_is_clamped_and_does_not_wind_up():
    p = MIN_PHASE
    pi = DecentralisedPI.for_plant(p)
    for _ in range(1000):  # unreachable reference
        u = pi.command((100.0, 100.0), (10.0, 10.0), 5.0)
        assert u == (p.v_max, p.v_max)
    assert pi._integral == [0.0, 0.0]
