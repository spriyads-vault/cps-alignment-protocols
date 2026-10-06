import pytest

from quadtank_control.monitors import RuleMonitor
from quadtank_control.plant import MIN_PHASE
from quadtank_control.protocols import PRESETS, Protocol, parse_protocol_name
from quadtank_control.types import Action, Observation

P = MIN_PHASE


def _obs():
    return Observation(0.0, P.h0, (P.h0[0], P.h0[1]))


def test_parse_names():
    assert parse_protocol_name("hybrid").cbf_location == "edge"
    assert parse_protocol_name("hybrid@remote").cbf_location == "remote"
    with pytest.raises(ValueError):
        parse_protocol_name("nope")
    with pytest.raises(ValueError):
        parse_protocol_name("monitor_only@edge")  # no CBF to place
    with pytest.raises(ValueError):
        parse_protocol_name("hybrid@somewhere")


def test_monitor_protocol_requires_monitor():
    with pytest.raises(ValueError):
        Protocol(PRESETS["hybrid"], P, monitor=None)


def test_block_discards_flagged_message_and_holds():
    proto = Protocol(PRESETS["monitor_only"], P, RuleMonitor(P), block_threshold=0.5)
    ok = proto.remote(0, _obs(), Action(P.v0, "fine"))
    bad = proto.remote(1, _obs(), Action((10.0, 10.0), "go"))
    proto.deliver(ok)
    proto.deliver(bad)
    assert proto.n_blocked == 1
    assert proto.edge_voltages(P.h0, (P.h0[0], P.h0[1]), 2.0) == P.v0


def test_defer_hands_control_to_local_pi_then_returns():
    proto = Protocol(PRESETS["defer_pi"], P, RuleMonitor(P), defer_threshold=0.5)
    bad = proto.remote(0, _obs(), Action((10.0, 10.0), "go"))
    proto.deliver(bad)
    assert proto.n_deferred == 1
    v = proto.edge_voltages(P.h0, (P.h0[0], P.h0[1]), 2.0)
    assert v != (10.0, 10.0)
    good = proto.remote(1, _obs(), Action((3.2, 3.1), "fine"))
    proto.deliver(good)
    assert proto.edge_voltages(P.h0, (P.h0[0], P.h0[1]), 2.0)[0] == pytest.approx(3.2)


def test_runs_local_pi_until_first_message():
    proto = Protocol(PRESETS["no_guard"], P)
    v = proto.edge_voltages(P.h0, (P.h0[0], P.h0[1]), 2.0)
    assert v == pytest.approx(P.v0, abs=1e-6)


def test_edge_cbf_clips_a_held_unsafe_command():
    proto = Protocol(PRESETS["cbf_only"], P)
    proto.deliver(proto.remote(0, _obs(), Action((10.0, 10.0), "go")))
    near_limit = (17.0, 17.0, 8.0, 8.0)
    v = proto.edge_voltages(near_limit, (17.0, 17.0), 2.0)
    assert max(v) < 10.0
    assert proto.n_cbf_interventions == 1


def test_remote_cbf_uses_stale_state_edge_uses_live():
    remote = Protocol(parse_protocol_name("cbf_only@remote"), P)
    stale = Observation(0.0, P.h0, (P.h0[0], P.h0[1]))
    remote.deliver(remote.remote(0, stale, Action((10.0, 10.0), "go")))
    # Live state is now near the limit, but the remote filter saw the low state.
    v_remote = remote.edge_voltages((17.5, 17.5, 8.0, 8.0), (17.5, 17.5), 2.0)
    edge = Protocol(parse_protocol_name("cbf_only@edge"), P)
    edge.deliver(edge.remote(0, stale, Action((10.0, 10.0), "go")))
    v_edge = edge.edge_voltages((17.5, 17.5, 8.0, 8.0), (17.5, 17.5), 2.0)
    assert max(v_edge) < max(v_remote)


def test_added_latency_counts_monitor_and_remote_cbf_only():
    assert Protocol(PRESETS["hybrid"], P, RuleMonitor(P)).added_latency_s(2.0, 0.5) == 2.0
    remote = Protocol(parse_protocol_name("hybrid@remote"), P, RuleMonitor(P))
    assert remote.added_latency_s(2.0, 0.5) == 2.5
    assert Protocol(PRESETS["pi_only"], P).added_latency_s(2.0, 0.5) == 0.0


def test_remote_hold_horizon_is_applied():
    proto = Protocol(parse_protocol_name("cbf_only@remote"), P, remote_hold_s=10.0)
    assert proto._cbf_remote is not None and proto._cbf_remote.cfg.horizon == 10.0
    assert proto._cbf is not None and proto._cbf.cfg.horizon == 5.0
