"""How the remote-CBF delay threshold depends on the filter's hold period, looseness and barrier.

Pre-registered as predictions P6 to P10 (PREREGISTRATION.md, amendment A4) before any run. Each
variant is a full experiment over a delay sweep with `cbf_only@remote` against the overt attack. The
threshold is the interpolated delay where the overflow rate first exceeds 0.10.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import CBFSettings, ExperimentConfig
from .runner import run_experiment

DELAYS_S = [
    0.0,
    2.0,
    4.0,
    6.0,
    8.0,
    10.0,
    12.0,
    14.0,
    16.0,
    18.0,
    20.0,
    24.0,
    28.0,
    32.0,
    40.0,
    60.0,
]
BASE = {"hold_s": 10.0, "gamma": 0.5, "h_safe": 18.0}
PLANTS = ("min_phase", "non_min_phase")


@dataclass(frozen=True)
class Variant:
    hold_s: float
    gamma: float
    h_safe: float

    @property
    def tag(self) -> str:
        return f"H{self.hold_s:g}_g{self.gamma:g}_h{self.h_safe:g}"


def variants() -> list[Variant]:
    """The baseline plus one-at-a-time changes: hold period, looseness, barrier tightening."""
    base = Variant(**BASE)
    out = [base]
    out += [Variant(h, base.gamma, base.h_safe) for h in (4.0, 20.0)]
    out += [Variant(base.hold_s, g, base.h_safe) for g in (0.3, 0.8)]
    out += [Variant(base.hold_s, base.gamma, hs) for hs in (17.0, 16.0)]
    return out


def make_config(v: Variant, runs: int = 10, workers: int | None = None) -> ExperimentConfig:
    return ExperimentConfig(
        name=f"scaling_{v.tag}",
        plants=list(PLANTS),  # type: ignore[arg-type]
        protocols=["cbf_only@remote"],
        attacks=["overt"],
        rtts_s=DELAYS_S,
        runs_per_cell=runs,
        supervisor_period_s=v.hold_s,
        calibration_runs=3,  # cbf_only never reads the monitor, so calibration is a formality
        cbf=CBFSettings(h_safe=v.h_safe, gamma=v.gamma, horizon_s=5.0),
        workers=workers,
    )


def overflow_thresholds(summary: dict[str, Any]) -> dict[str, dict[str, float | None]]:
    out: dict[str, dict[str, float | None]] = {}
    for d in summary["delay_thresholds"]:
        if d["harm_type"] == "overflow" and d["attack"] == "overt":
            out[d["plant"]] = {
                "first_harm": d["d_star_first_harm"],
                "point": d["d_star_point"],
                "confirmed": d["d_star_confirmed"],
            }
    return out


def run_all(out_root: Path, runs: int = 10, workers: int | None = None) -> list[dict[str, Any]]:
    results = []
    for v in variants():
        cfg = make_config(v, runs, workers)
        out_dir = out_root / v.tag
        run_experiment(cfg, out_dir)
        summary = json.loads((out_dir / "summary.json").read_text())
        for plant, t in overflow_thresholds(summary).items():
            results.append(
                {"hold_s": v.hold_s, "gamma": v.gamma, "h_safe": v.h_safe, "plant": plant, **t}
            )
    (out_root / "summary.json").write_text(json.dumps(results, indent=2))
    return results
