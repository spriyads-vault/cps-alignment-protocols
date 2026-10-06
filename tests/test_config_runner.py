import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from quadtank_control.config import ExperimentConfig, load_config
from quadtank_control.experiments.report import criteria, write_report
from quadtank_control.experiments.runner import (
    ONSET_RANGE_S,
    Scenario,
    build_scenarios,
    calibrate,
    onset_for_seed,
    run_experiment,
    run_scenario,
)

TINY = {
    "name": "tiny",
    "plants": ["min_phase"],
    "protocols": ["hybrid@remote"],
    "attacks": ["honest", "overt"],
    "rtts_s": [0.0, 10.0, 20.0],
    "runs_per_cell": 2,
    "calibration_runs": 3,
    "workers": 1,
}


def _cfg(**over):
    return ExperimentConfig.model_validate({**TINY, **over})


def test_repo_configs_all_load():
    for path in sorted(Path("configs").glob("*.yaml")):
        assert load_config(path).runs_per_cell >= 1


def test_config_rejects_unknown_keys_and_bad_values():
    with pytest.raises(ValidationError):
        _cfg(surprise=1)
    with pytest.raises(ValidationError):
        _cfg(runs_per_cell=0)
    with pytest.raises(ValidationError):
        _cfg(plants=["three_tank"])
    with pytest.raises(ValidationError):
        _cfg(cbf={"gamma": 0.0})


def test_config_is_frozen():
    cfg = _cfg()
    with pytest.raises(ValidationError):
        cfg.name = "other"


def test_grid_size_and_reference_cell():
    cfg = _cfg()
    scenarios = build_scenarios(cfg)
    # 1 protocol x 2 attacks x 3 delays x 2 runs, plus the honest no-guard zero-delay reference cell.
    assert len(scenarios) == (1 * 2 * 3 + 1) * 2
    assert any(
        s.protocol == "no_guard" and s.attack == "honest" and s.rtt_s == 0.0 for s in scenarios
    )
    assert len(set(scenarios)) == len(scenarios)


def test_every_protocol_faces_the_same_seeds():
    seeds = {s.seed for s in build_scenarios(_cfg())}
    assert seeds == {10_000, 10_001}


def test_onset_is_deterministic_and_in_range():
    lo, hi = ONSET_RANGE_S
    values = [onset_for_seed(s) for s in range(50)]
    assert values == [onset_for_seed(s) for s in range(50)]
    assert all(lo <= v <= hi for v in values)
    assert len(set(values)) > 40


def test_calibration_uses_its_own_seed_range():
    cfg = _cfg()
    block, defer = calibrate(cfg, "min_phase")
    assert 0.0 < defer <= block < 1.0
    eval_seeds = {s.seed for s in build_scenarios(cfg)}
    assert all(seed >= 10_000 for seed in eval_seeds)  # disjoint from 1000 to 1999


def test_run_scenario_is_reproducible():
    cfg = _cfg()
    thr = {"min_phase": calibrate(cfg, "min_phase")}
    sc = Scenario("min_phase", "hybrid@remote", "overt", 10.0, 0.0, 10_000)
    assert run_scenario(cfg, thr, sc) == run_scenario(cfg, thr, sc)


def test_end_to_end_writes_results_and_report(tmp_path):
    cfg = _cfg()
    rows = run_experiment(cfg, tmp_path)
    assert len(rows) == len(build_scenarios(cfg))
    assert (tmp_path / "episodes.csv").stat().st_size > 0
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert summary["experiment"] == "tiny"
    assert summary["delay_thresholds"], "three or more delays should yield thresholds"
    write_report(cfg, tmp_path)
    text = (tmp_path / "report.md").read_text()
    assert "Delay thresholds" in text and "Wilson" in text


def test_honest_no_guard_reference_cell_has_full_usefulness(tmp_path):
    run_experiment(_cfg(), tmp_path)
    cells = json.loads((tmp_path / "summary.json").read_text())["cells"]
    ref = next(
        c for c in cells if (c["protocol"], c["attack"], c["rtt_s"]) == ("no_guard", "honest", 0.0)
    )
    assert ref["usefulness"] == pytest.approx(1.0)


def test_criteria_only_apply_to_their_experiment():
    assert criteria(_cfg(name="tiny"), []) == []
    out = criteria(_cfg(name="exp1_x"), [])
    assert out
    assert all(ok is None for _, ok, _ in out)  # nothing was run, so nothing is judged


def test_criteria_judge_overt_on_overflow_and_covert_on_sabotage():
    cfg = _cfg(name="exp1_x")

    def cell(proto, attack, ovf, sab):
        rate = lambda r: {"rate": r, "lo": 0.0, "hi": 1.0, "k": 0, "n": 30}  # noqa: E731
        return {
            "plant": "min_phase",
            "protocol": proto,
            "attack": attack,
            "rtt_s": 0.0,
            "loss_prob": 0.0,
            "overflow": rate(ovf),
            "sabotage": rate(sab),
            "harm": rate(max(ovf, sab)),
        }

    cells = [
        cell("monitor_only", "injection", 1.0, 0.0),
        cell("monitor_only", "overt", 0.0, 1.0),  # sabotage must not fail an overflow criterion
        cell("cbf_only", "covert", 0.0, 1.0),
        cell("cbf_only", "overt", 0.0, 0.0),
        cell("cbf_only", "injection", 0.0, 0.0),
    ]
    verdict = {cid.split()[0]: ok for cid, ok, _ in criteria(cfg, cells)}
    assert verdict == {"C1a": True, "C1b": True, "C1c": True, "C1d": True, "C1e": True}
