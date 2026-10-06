"""Protocols with a real language-model monitor in the loop, against scripted attackers.

Runs block-and-hold (hybrid) and defer-to-PI, each with the CBF, with Claude Haiku 4.5 as the
monitor, against honest, overt, injection and monitor-aware covert supervisors. Measures overflow
and sabotage. This is the real-monitor version of experiment 2, which used a surrogate that is
blind to authority claims by construction.

The attackers are scripted, so no model is asked to attack. Measured latencies (supervisor 1.9 s,
monitor 3.0 s) enter as simulated delay.

This SPENDS REAL MONEY and needs ANTHROPIC_API_KEY. It prints the exact call count first, refuses
to run without --yes, and stops hard at --max-calls. Responses are cached on disk.

The price per call is unmeasured. [NEED: read the real cost from the console after run 2.]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from quadtank_control.experiments.real_monitor_protocol import (
    calibrate_thresholds,
    planned_calls,
    run_cells,
    summarise_cells,
)
from quadtank_control.experiments.runner import PLANTS
from quadtank_control.llm import AnthropicClient, AnthropicConfig, BudgetedClient, CachingClient
from quadtank_control.monitors.llm import LLMMonitor


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--plant", choices=sorted(PLANTS), default="min_phase")
    ap.add_argument("--monitor-model", default="claude-haiku-4-5")
    ap.add_argument("--protocols", nargs="+", default=["hybrid", "defer_pi"])
    ap.add_argument(
        "--attacks", nargs="+", default=["honest", "overt", "injection", "covert_aware"]
    )
    ap.add_argument("--runs", type=int, default=3, help="episodes per protocol and attack")
    ap.add_argument("--calibration-runs", type=int, default=5)
    ap.add_argument("--supervisor-latency", type=float, default=1.9)
    ap.add_argument("--monitor-latency", type=float, default=3.0)
    ap.add_argument("--max-calls", type=int, required=True, help="hard cap on uncached API calls")
    ap.add_argument("--cache-dir", type=Path, default=Path("logs/llm_cache"))
    ap.add_argument("--out", type=Path, default=Path("results/llm_monitor_protocol.json"))
    ap.add_argument("--seed-base", type=int, default=40_000)
    ap.add_argument("--yes", action="store_true", help="confirm that you accept the spend")
    args = ap.parse_args()

    params = PLANTS[args.plant]
    planned = planned_calls(
        params, len(args.protocols), len(args.attacks), args.runs, args.calibration_runs
    )
    print(f"planned monitor calls: {planned} on {args.monitor_model} (before cache hits)")
    if planned > args.max_calls:
        print(f"planned calls exceed --max-calls {args.max_calls}. Lower --runs or raise the cap.")
        return 2
    if not args.yes:
        print("dry run. Add --yes to spend.")
        return 0

    raw = BudgetedClient(AnthropicClient(AnthropicConfig(args.monitor_model)), args.max_calls)
    client = CachingClient(raw, args.cache_dir / "monitor_protocol.jsonl", args.monitor_model)
    monitor = LLMMonitor(client, params, 10.0, sees_rationale=True, authority_warning=False)
    lat = (args.supervisor_latency, args.monitor_latency)

    thresholds = calibrate_thresholds(params, monitor, args.calibration_runs, 0.01, 0.05, lat)
    print(
        f"thresholds from {args.calibration_runs} honest episodes: block {thresholds[0]:.3f}, defer {thresholds[1]:.3f}"
    )
    rows = run_cells(
        params, monitor, args.protocols, args.attacks, args.runs, args.seed_base, thresholds, lat
    )
    report = {
        "args": {k: str(v) for k, v in vars(args).items()},
        "thresholds": {"block": thresholds[0], "defer": thresholds[1]},
        "cells": summarise_cells(rows),
        "failures": {
            "parse": monitor.parse_failures,
            "call": monitor.call_failures,
            "reasons": dict(monitor.failure_reasons),
        },
        "cache_hits": client.hits,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
