import numpy as np
import pytest

from quadtank_control.network import Link, LinkConfig


def test_fixed_delay_no_loss():
    link = Link(LinkConfig(delay_s=2.5), np.random.default_rng(0))
    assert [link.transit() for _ in range(5)] == [2.5] * 5


def test_total_loss_drops_everything():
    link = Link(LinkConfig(loss_prob=1.0), np.random.default_rng(0))
    assert all(link.transit() is None for _ in range(20))


def test_loss_rate_is_close_to_configured():
    link = Link(LinkConfig(loss_prob=0.2), np.random.default_rng(1))
    dropped = sum(link.transit() is None for _ in range(5000))
    assert dropped / 5000 == pytest.approx(0.2, abs=0.03)


def test_same_seed_same_sequence():
    cfg = LinkConfig(delay_s=1.0, jitter_s=0.5, loss_prob=0.3)
    a = [Link(cfg, np.random.default_rng(7)).transit() for _ in range(1)]
    la, lb = Link(cfg, np.random.default_rng(7)), Link(cfg, np.random.default_rng(7))
    assert [la.transit() for _ in range(50)] == [lb.transit() for _ in range(50)]
    assert a[0] is None or a[0] >= 1.0


def test_rejects_bad_config():
    with pytest.raises(ValueError, match="non-negative"):
        LinkConfig(delay_s=-1.0)
    with pytest.raises(ValueError, match="loss_prob"):
        LinkConfig(loss_prob=1.5)
