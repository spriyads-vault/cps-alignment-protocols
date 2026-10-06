import math

import numpy as np
import pytest

from quadtank_control.metrics import (
    bootstrap_ci,
    calibrate_threshold,
    delay_threshold,
    first_crossing,
    usefulness,
    wilson_interval,
)


def test_wilson_zero_of_twenty_is_not_zero_width():
    lo, hi = wilson_interval(0, 20)
    assert lo == 0.0
    assert hi == pytest.approx(0.161, abs=0.005)  # the "rule of three" territory


def test_wilson_contains_point_estimate_and_is_ordered():
    for k, n in [(1, 10), (5, 10), (9, 10), (30, 30)]:
        lo, hi = wilson_interval(k, n)
        assert 0.0 <= lo <= k / n <= hi <= 1.0


def test_wilson_empty():
    assert wilson_interval(0, 0) == (0.0, 1.0)


def test_calibrated_threshold_respects_false_alarm_rate():
    rng = np.random.default_rng(0)
    scores = rng.random(1000)
    thr = calibrate_threshold(scores, 0.01)
    assert (scores >= thr).mean() <= 0.01


def test_calibrate_handles_ties_at_zero():
    scores = [0.0] * 95 + [0.1] * 5
    thr = calibrate_threshold(scores, 0.01)
    assert (np.array(scores) >= thr).mean() <= 0.01
    assert thr > 0.0


def test_calibrate_rejects_bad_input():
    with pytest.raises(ValueError, match="at least one"):
        calibrate_threshold([], 0.01)
    with pytest.raises(ValueError, match="fpr"):
        calibrate_threshold([0.1], 1.0)


def test_bootstrap_ci_brackets_the_mean():
    lo, hi = bootstrap_ci([1.0, 2.0, 3.0, 4.0, 5.0], seed=1)
    assert lo < 3.0 < hi


def test_bootstrap_empty_is_nan():
    lo, hi = bootstrap_ci([])
    assert math.isnan(lo) and math.isnan(hi)


def test_first_crossing_interpolates():
    assert first_crossing([0, 10, 20], [0.0, 0.0, 1.0], 0.5) == pytest.approx(15.0)
    assert first_crossing([0, 10], [0.0, 0.1], 0.5) is None
    assert first_crossing([0, 10], [0.9, 1.0], 0.5) == 0.0


def test_delay_threshold_orders_first_harm_point_confirmed():
    delays = [0, 5, 10, 20, 40]
    ks = [0, 1, 3, 12, 30]
    ns = [30] * 5
    t = delay_threshold(delays, ks, ns, 0.0, 0.1)
    assert t.first_harm == 5.0
    assert t.first_harm <= t.point <= t.confirmed


def test_delay_threshold_no_harm_anywhere():
    t = delay_threshold([0, 10, 20], [0, 0, 0], [30, 30, 30], 0.0, 0.1)
    assert t.first_harm is None and t.point is None and t.confirmed is None


def test_usefulness_bounds():
    assert usefulness(50.0, 100.0) == pytest.approx(0.5)
    assert usefulness(50.0, 25.0) == 1.0
    assert usefulness(50.0, 0.0) == 1.0
