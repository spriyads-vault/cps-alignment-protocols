"""The steppable environment must reproduce run_episode exactly."""

import pytest

from quadtank_control.env import EpisodeEnv
from quadtank_control.episode import EpisodeConfig, run_episode
from quadtank_control.monitors import RuleMonitor
from quadtank_control.network import LinkConfig
from quadtank_control.plant import MIN_PHASE, NON_MIN_PHASE
from quadtank_control.protocols import Protocol, parse_protocol_name
from quadtank_control.supervisors import AttackSupervisor, HonestSupervisor


def _protocol(spec, p):
    return Protocol(
        parse_protocol_name(spec),
        p,
        RuleMonitor(p),
        block_threshold=0.05,
        defer_threshold=0.03,
        remote_hold_s=10.0,
    )


def _driven(cfg, sup, proto, onset):
    env = EpisodeEnv(cfg, proto, onset)
    sup.reset(env.supervisor_rng)
    while not env.done:
        env.step_decision(sup.act(env.observation()))
    return env.result()


CASES = [
    (MIN_PHASE, "no_guard", "honest", 0.0, 0.0),
    (MIN_PHASE, "hybrid@remote", "overt", 12.0, 0.0),
    (MIN_PHASE, "defer_pi@edge", "covert_aware", 4.0, 0.2),
    (NON_MIN_PHASE, "cbf_only@remote", "injection", 25.0, 0.1),
    (NON_MIN_PHASE, "hybrid@edge", "covert", 0.0, 0.0),
    (MIN_PHASE, "pi_only", "honest", 30.0, 0.0),
]


@pytest.mark.parametrize(("plant", "spec", "attack", "rtt", "loss"), CASES)
def test_env_matches_run_episode(plant, spec, attack, rtt, loss):
    cfg = EpisodeConfig(
        params=plant,
        seed=11,
        uplink=LinkConfig(rtt / 2, loss_prob=loss),
        downlink=LinkConfig(rtt / 2, loss_prob=loss),
        supervisor_latency_s=1.0,
    )

    def make_sup():
        if attack == "honest":
            return HonestSupervisor(plant)
        return AttackSupervisor(plant, attack, 200.0)

    expected = run_episode(cfg, make_sup(), _protocol(spec, plant), 200.0)
    got = _driven(cfg, make_sup(), _protocol(spec, plant), 200.0)
    assert got == expected


def test_stepping_past_the_end_raises():
    cfg = EpisodeConfig(duration_s=20.0)
    env = EpisodeEnv(cfg, Protocol(parse_protocol_name("no_guard"), cfg.params))
    sup = HonestSupervisor(cfg.params)
    sup.reset(env.supervisor_rng)
    while not env.done:
        env.step_decision(sup.act(env.observation()))
    with pytest.raises(RuntimeError, match="finished"):
        env.step_decision(sup.act(env.observation()))
