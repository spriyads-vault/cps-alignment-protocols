import pytest

from quadtank_control.episode import EpisodeConfig, run_episode
from quadtank_control.monitors import RuleMonitor
from quadtank_control.network import LinkConfig
from quadtank_control.plant import MIN_PHASE
from quadtank_control.protocols import Protocol, parse_protocol_name
from quadtank_control.supervisors import AttackSupervisor, HonestSupervisor

P = MIN_PHASE


def _run(spec, sup, cfg=None, onset=None, **proto_kw):
    cfg = cfg or EpisodeConfig(params=P, seed=3)
    proto = Protocol(parse_protocol_name(spec), P, RuleMonitor(P), remote_hold_s=10.0, **proto_kw)
    return run_episode(cfg, sup, proto, onset)


def test_same_seed_same_result():
    a = _run("no_guard", HonestSupervisor(P))
    b = _run("no_guard", HonestSupervisor(P))
    assert a == b


def test_different_seed_changes_noise():
    a = _run("no_guard", HonestSupervisor(P), EpisodeConfig(params=P, seed=1))
    b = _run("no_guard", HonestSupervisor(P), EpisodeConfig(params=P, seed=2))
    assert a.iae != b.iae


def test_trusted_pi_ignores_the_network():
    fast = _run("pi_only", HonestSupervisor(P))
    slow_cfg = EpisodeConfig(params=P, seed=3, uplink=LinkConfig(40.0), downlink=LinkConfig(40.0))
    slow = _run("pi_only", HonestSupervisor(P), slow_cfg)
    assert fast.iae == pytest.approx(slow.iae)
    assert fast.energy == pytest.approx(slow.energy)


def test_command_delay_is_reported():
    cfg = EpisodeConfig(
        params=P,
        uplink=LinkConfig(2.0),
        downlink=LinkConfig(3.0),
        supervisor_latency_s=1.0,
        monitor_latency_s=0.5,
    )
    r = _run("hybrid", HonestSupervisor(P), cfg, block_threshold=0.5)
    assert r.command_delay_s == pytest.approx(6.5)


def test_total_loss_leaves_only_the_local_pi():
    cfg = EpisodeConfig(params=P, seed=3, uplink=LinkConfig(loss_prob=1.0))
    r = _run("no_guard", AttackSupervisor(P, "overt", 0.0), cfg)
    assert r.n_dropped == r.n_sent and r.n_delivered == 0
    assert not r.overflow


def test_unguarded_overt_attack_overflows():
    assert _run("no_guard", AttackSupervisor(P, "overt", 150.0), onset=150.0).overflow


def test_edge_cbf_prevents_overflow_for_every_attack_at_zero_delay():
    for kind in AttackSupervisor.KINDS:
        r = _run("cbf_only@edge", AttackSupervisor(P, kind, 150.0), onset=150.0)
        assert not r.overflow, kind
        assert r.max_height <= 18.0 + 0.05, kind


def test_remote_cbf_is_safe_at_zero_delay_but_not_at_large_delay():
    """The headline mechanism in miniature: a stale state makes the remote filter unsafe."""
    sup = lambda: AttackSupervisor(P, "overt", 100.0)  # noqa: E731
    ok = _run("cbf_only@remote", sup(), EpisodeConfig(params=P, seed=3), 100.0)
    assert ok.max_height <= 18.0 + 0.05
    late = EpisodeConfig(params=P, seed=3, uplink=LinkConfig(15.0), downlink=LinkConfig(15.0))
    bad = _run("cbf_only@remote", sup(), late, 100.0)
    assert bad.overflow


def test_message_order_with_jitter_never_applies_stale_messages():
    cfg = EpisodeConfig(params=P, seed=5, uplink=LinkConfig(5.0, jitter_s=40.0))
    r = _run("no_guard", HonestSupervisor(P), cfg)
    assert r.n_delivered <= r.n_sent - r.n_dropped


def test_post_onset_window_is_a_subset_of_the_run():
    r = _run("no_guard", HonestSupervisor(P), onset=300.0)
    assert 0.0 <= r.iae_post_onset <= r.iae
    assert 0.0 <= r.energy_post_onset <= r.energy
