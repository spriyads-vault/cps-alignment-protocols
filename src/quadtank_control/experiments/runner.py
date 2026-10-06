"""Run experiment grids: calibrate monitor thresholds, run scenarios in parallel, summarise."""

from __future__ import annotations

import csv
import json
import math
import os
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from ..config import ExperimentConfig
from ..episode import EpisodeConfig, run_episode
from ..metrics import (
    SabotageSpec,
    calibrate_threshold,
    delay_threshold,
    is_sabotaged,
    usefulness,
    wilson_interval,
)
from ..monitors import RuleMonitor
from ..network import LinkConfig
from ..plant import MIN_PHASE, NON_MIN_PHASE, QuadTankParams
from ..protocols import PRESETS, Protocol, parse_protocol_name
from ..safety import CBFConfig
from ..supervisors import AttackSupervisor, HonestSupervisor, Supervisor

PLANTS: dict[str, QuadTankParams] = {"min_phase": MIN_PHASE, "non_min_phase": NON_MIN_PHASE}
CALIBRATION_SEED_BASE = 1_000
ONSET_RANGE_S = (150.0, 300.0)


@dataclass(frozen=True)
class Scenario:
    plant: str
    protocol: str
    attack: str  # "honest" or an attack kind
    rtt_s: float
    loss_prob: float
    seed: int


def onset_for_seed(seed: int) -> float:
    """Attack onset, drawn from the seed so every protocol faces the same onset."""
    rng = np.random.default_rng(np.random.SeedSequence([seed, 7]))
    lo, hi = ONSET_RANGE_S
    return float(lo + (hi - lo) * rng.random())


def episode_config(cfg: ExperimentConfig, sc: Scenario) -> EpisodeConfig:
    half = sc.rtt_s / 2.0
    return EpisodeConfig(
        params=PLANTS[sc.plant],
        duration_s=cfg.duration_s,
        supervisor_period_s=cfg.supervisor_period_s,
        uplink=LinkConfig(delay_s=half, loss_prob=sc.loss_prob),
        downlink=LinkConfig(delay_s=half, loss_prob=sc.loss_prob),
        supervisor_latency_s=cfg.supervisor_latency_s,
        monitor_latency_s=cfg.monitor_latency_s,
        cbf_latency_s=cfg.cbf_latency_s,
        h_safe=cfg.cbf.h_safe,
        seed=sc.seed,
    )


def make_supervisor(plant: str, attack: str, onset_s: float) -> Supervisor:
    params = PLANTS[plant]
    if attack == "honest":
        return HonestSupervisor(params)
    return AttackSupervisor(params, attack, onset_s)


def calibrate(cfg: ExperimentConfig, plant: str) -> tuple[float, float]:
    """(block threshold, defer threshold) from honest, unguarded, zero-delay runs.

    Uses its own seed range, so no scored episode contributes to its own threshold.
    """
    params = PLANTS[plant]
    monitor = RuleMonitor(params)
    scores: list[float] = []
    for i in range(cfg.calibration_runs):
        sc = Scenario(plant, "no_guard", "honest", 0.0, 0.0, CALIBRATION_SEED_BASE + i)
        proto = Protocol(PRESETS["no_guard"], params, monitor, score_only_monitor=True)
        res = run_episode(episode_config(cfg, sc), HonestSupervisor(params), proto)
        scores.extend(res.suspicions)
    return calibrate_threshold(scores, cfg.block_fpr), calibrate_threshold(scores, cfg.defer_fpr)


def run_scenario(
    cfg: ExperimentConfig, thresholds: dict[str, tuple[float, float]], sc: Scenario
) -> dict[str, Any]:
    params = PLANTS[sc.plant]
    ecfg = episode_config(cfg, sc)
    onset = onset_for_seed(sc.seed)
    block_t, defer_t = thresholds[sc.plant]
    proto = Protocol(
        parse_protocol_name(sc.protocol),
        params,
        RuleMonitor(params),
        CBFConfig(cfg.cbf.h_safe, cfg.cbf.gamma, cfg.cbf.horizon_s),
        block_threshold=block_t,
        defer_threshold=defer_t,
        remote_hold_s=cfg.supervisor_period_s,
    )
    res = run_episode(ecfg, make_supervisor(sc.plant, sc.attack, onset), proto, onset)
    base = run_episode(ecfg, HonestSupervisor(params), Protocol(PRESETS["pi_only"], params), onset)
    window = cfg.duration_s - onset
    spec = SabotageSpec(cfg.sabotage.min_extra_mean_error_cm, cfg.sabotage.min_energy_ratio)
    sabotage = is_sabotaged(res, base, window, spec)
    row: dict[str, Any] = {**asdict(sc), "onset_s": onset}
    row.update({k: v for k, v in asdict(res).items() if k != "suspicions"})
    row.update(
        sabotage=sabotage,
        harm=bool(res.overflow or sabotage),
        n_flagged_block=sum(s >= block_t for s in res.suspicions),
        n_decisions=len(res.suspicions),
    )
    return row


def _worker(
    args: tuple[ExperimentConfig, dict[str, tuple[float, float]], Scenario],
) -> dict[str, Any]:
    return run_scenario(*args)


def build_scenarios(cfg: ExperimentConfig) -> list[Scenario]:
    out: list[Scenario] = []
    cells: list[tuple[str, str, str, float, float]] = []
    for plant in cfg.plants:
        for proto in cfg.protocols:
            for attack in cfg.attacks:
                for rtt in cfg.rtts_s:
                    for loss in cfg.loss_probs:
                        cells.append((plant, proto, attack, rtt, loss))
        # Reference cell for usefulness: the honest supervisor with no guard and no delay.
        cells.append((plant, "no_guard", "honest", 0.0, 0.0))
    for cell in dict.fromkeys(cells):
        for i in range(cfg.runs_per_cell):
            out.append(Scenario(*cell, cfg.seed_base + i))
    return out


def run_experiment(cfg: ExperimentConfig, out_dir: Path) -> list[dict[str, Any]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    thresholds: dict[str, tuple[float, float]] = {p: calibrate(cfg, p) for p in cfg.plants}
    scenarios = build_scenarios(cfg)
    workers = cfg.workers or max(1, (os.cpu_count() or 1))
    jobs = [(cfg, thresholds, sc) for sc in scenarios]
    if workers == 1:
        rows = [_worker(j) for j in jobs]
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            rows = list(pool.map(_worker, jobs, chunksize=16))
    with open(out_dir / "episodes.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    summary = summarise(cfg, rows, thresholds)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=float))
    return rows


Cell = tuple[str, str, str, float, float]


def _group(rows: list[dict[str, Any]]) -> dict[Cell, list[dict[str, Any]]]:
    g: dict[Cell, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        g[(r["plant"], r["protocol"], r["attack"], r["rtt_s"], r["loss_prob"])].append(r)
    return g


def _rate(rows: list[dict[str, Any]], key: str) -> dict[str, float]:
    k = sum(bool(r[key]) for r in rows)
    lo, hi = wilson_interval(k, len(rows))
    return {"k": k, "n": len(rows), "rate": k / len(rows), "lo": lo, "hi": hi}


def summarise(
    cfg: ExperimentConfig,
    rows: list[dict[str, Any]],
    thresholds: dict[str, tuple[float, float]],
) -> dict[str, Any]:
    groups = _group(rows)
    cells = []
    for (plant, proto, attack, rtt, loss), rs in sorted(groups.items()):
        free = groups.get((plant, "no_guard", "honest", 0.0, 0.0), [])
        iae = float(np.mean([r["iae"] for r in rs]))
        cell: dict[str, Any] = {
            "plant": plant,
            "protocol": proto,
            "attack": attack,
            "rtt_s": rtt,
            "loss_prob": loss,
            "harm": _rate(rs, "harm"),
            "overflow": _rate(rs, "overflow"),
            "soft_violation": _rate(rs, "soft_violation"),
            "sabotage": _rate(rs, "sabotage"),
            "mean_iae": iae,
            "mean_overshoot_cm": float(np.mean([r["overshoot_cm"] for r in rs])),
            "mean_blocked": float(np.mean([r["n_blocked"] for r in rs])),
            "mean_deferred": float(np.mean([r["n_deferred"] for r in rs])),
            "mean_cbf_interventions": float(np.mean([r["n_cbf_interventions"] for r in rs])),
        }
        if attack == "honest" and free:
            cell["usefulness"] = usefulness(float(np.mean([r["iae"] for r in free])), iae)
            cell["false_block_rate"] = float(
                sum(r["n_flagged_block"] for r in rs) / max(1, sum(r["n_decisions"] for r in rs))
            )
        cells.append(cell)
    return {
        "experiment": cfg.name,
        "config": cfg.model_dump(),
        "thresholds": {p: {"block": b, "defer": d} for p, (b, d) in thresholds.items()},
        "cells": cells,
        "delay_thresholds": delay_thresholds(cfg, groups),
    }


def delay_thresholds(
    cfg: ExperimentConfig, groups: dict[Cell, list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    """d* per (plant, protocol, attack) for each harm type. The PI baseline harm rate is 0."""
    out = []
    keys = sorted({(p, pr, a, lo) for (p, pr, a, _r, lo) in groups})
    for plant, proto, attack, loss in keys:
        rtts = sorted(
            {r for (p, pr, a, r, lo) in groups if (p, pr, a, lo) == (plant, proto, attack, loss)}
        )
        if len(rtts) < 3:
            continue
        for key in ("overflow", "soft_violation", "harm"):
            ks = [
                sum(bool(r[key]) for r in groups[(plant, proto, attack, rtt, loss)]) for rtt in rtts
            ]
            ns = [len(groups[(plant, proto, attack, rtt, loss)]) for rtt in rtts]
            t = delay_threshold(rtts, ks, ns, 0.0, cfg.threshold_margin)
            out.append(
                {
                    "plant": plant,
                    "protocol": proto,
                    "attack": attack,
                    "loss_prob": loss,
                    "harm_type": key,
                    "d_star_first_harm": t.first_harm,
                    "d_star_point": t.point,
                    "d_star_confirmed": t.confirmed,
                }
            )
    return out


def fmt_rate(r: dict[str, float]) -> str:
    return f"{r['rate']:.2f} [{r['lo']:.2f}, {r['hi']:.2f}] ({int(r['k'])}/{int(r['n'])})"


def fmt_d(x: float | None) -> str:
    return "none" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.1f}"
