"""Frozen outputs from the code as committed before run_episode was rebuilt on EpisodeEnv.

If this fails after an intentional behaviour change, regenerate tests/golden/episodes.json
AND say so in the commit message: every number already published would change too.
"""

import json
from pathlib import Path

import pytest

from quadtank_control.config import ExperimentConfig
from quadtank_control.experiments.runner import Scenario, run_scenario

GOLDEN = json.loads(Path(__file__).parent.joinpath("golden", "episodes.json").read_text())
CFG = ExperimentConfig.model_validate(
    {
        "name": "golden",
        "plants": ["min_phase", "non_min_phase"],
        "protocols": ["hybrid"],
        "attacks": ["honest"],
        "rtts_s": [0.0],
        "runs_per_cell": 1,
    }
)
THRESHOLDS = {k: tuple(v) for k, v in GOLDEN["thresholds"].items()}


@pytest.mark.parametrize(
    "case", GOLDEN["cases"], ids=lambda c: f"{c['plant']}-{c['protocol']}-{c['attack']}"
)
def test_episode_matches_golden(case):
    sc = Scenario(
        case["plant"],
        case["protocol"],
        case["attack"],
        case["rtt_s"],
        case["loss_prob"],
        case["seed"],
    )
    row = run_scenario(CFG, THRESHOLDS, sc)
    for key, want in case.items():
        got = row[key]
        if isinstance(want, float):
            assert got == pytest.approx(want, abs=1e-5), key
        else:
            assert got == want, key
