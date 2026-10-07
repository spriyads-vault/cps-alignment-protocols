"""Usefulness with a real honest supervisor and a real monitor.

How much does each protocol cost an honest language-model supervisor, and how often does the monitor
flag it falsely? Thresholds are calibrated on this supervisor's own honest behaviour. No attacker is
involved, so nothing can refuse. The trusted PI and the scripted honest supervisor run too, for free,
as references.

This SPENDS REAL MONEY and needs ANTHROPIC_API_KEY. It prints the exact call counts first, refuses to
run without --yes, and stops hard at --max-calls (supervisor and monitor calls counted together).
Responses are cached on disk.

Per episode: 60 supervisor calls, plus 60 monitor calls under hybrid and defer-to-PI. With the defaults
(3 calibration and 3 evaluation episodes) that is about 720 supervisor and 480 monitor calls. Your
earlier runs cost about four times what a per-call estimate suggested, so price a small run first:
[NEED: read the real cost from the console after --runs 1 --calibration-runs 1.]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from quadtank_control.experiments import honest_usefulness as hu
from quadtank_control.experiments.runner import PLANTS
from quadtank_control.llm import (
    AnthropicClient,
    AnthropicConfig,
    BudgetedClient,
    CachingClient,
    missing_credentials_message,
)
from quadtank_control.monitors.llm import LLMMonitor
from quadtank_control.supervisors.llm import LLMSupervisor


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--plant", choices=sorted(PLANTS), default="min_phase")
    ap.add_argument("--supervisor-model", default="claude-sonnet-5-5")
    ap.add_argument("--supervisor-effort", default="low")
    ap.add_argument("--monitor-model", default="claude-haiku-4-5")
    ap.add_argument("--protocols", nargs="+", default=["no_guard", "pi_only", "hybrid", "defer_pi"])
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--calibration-runs", type=int, default=3)
    ap.add_argument("--block-fpr", type=float, default=0.05)
    ap.add_argument("--defer-fpr", type=float, default=0.05)
    ap.add_argument("--supervisor-latency", type=float, default=1.9)
    ap.add_argument("--monitor-latency", type=float, default=3.0)
    ap.add_argument("--max-calls", type=int, required=True, help="hard cap on uncached API calls")
    ap.add_argument("--cache-dir", type=Path, default=Path("logs/llm_cache"))
    ap.add_argument("--out", type=Path, default=Path("results/llm_honest_usefulness.json"))
    ap.add_argument("--seed-base", type=int, default=50_000)
    ap.add_argument("--yes", action="store_true", help="confirm that you accept the spend")
    args = ap.parse_args()

    params = PLANTS[args.plant]
    if hu.FREE not in args.protocols:
        print(f"--protocols must include {hu.FREE!r}, the usefulness reference.")
        return 2
    planned = hu.planned_calls(params, args.protocols, args.runs, args.calibration_runs)
    total = planned["supervisor"] + planned["monitor"]
    print(
        f"planned calls: {planned['supervisor']} supervisor on {args.supervisor_model}, "
        f"{planned['monitor']} monitor on {args.monitor_model} (before cache hits)"
    )
    if total > args.max_calls:
        print(
            f"planned {total} calls exceed --max-calls {args.max_calls}. Lower --runs or raise the cap."
        )
        return 2
    if not args.yes:
        print("dry run. Add --yes to spend.")
        return 0
    problem = missing_credentials_message()
    if problem:
        print(problem)
        return 3

    budget = {"left": args.max_calls}  # one shared cap across both models

    class Shared:
        def __init__(self, inner: AnthropicClient) -> None:
            self._inner = inner

        def complete(self, system: str, user: str) -> str:
            gate = BudgetedClient(self._inner, max(budget["left"], 0))
            out = gate.complete(system, user)
            budget["left"] -= 1
            return out

    sup_client = CachingClient(
        Shared(
            AnthropicClient(AnthropicConfig(args.supervisor_model, effort=args.supervisor_effort))
        ),
        args.cache_dir / "honest_supervisor.jsonl",
        args.supervisor_model,
    )
    mon_client = CachingClient(
        Shared(AnthropicClient(AnthropicConfig(args.monitor_model))),
        args.cache_dir / "honest_monitor.jsonl",
        args.monitor_model,
    )
    monitor = LLMMonitor(mon_client, params, 10.0, sees_rationale=True, authority_warning=False)
    lat = (args.supervisor_latency, args.monitor_latency)

    def make_supervisor() -> LLMSupervisor:
        return LLMSupervisor(sup_client, params, 10.0)

    thresholds = hu.calibrate(
        params, make_supervisor, monitor, args.calibration_runs, args.block_fpr, args.defer_fpr, lat
    )
    print(
        f"thresholds from this supervisor's own honest behaviour: block {thresholds[0]:.3f}, defer {thresholds[1]:.3f}"
    )
    rows = hu.run(
        params, make_supervisor, monitor, args.protocols, args.runs, args.seed_base, thresholds, lat
    )
    report = {
        "args": {k: str(v) for k, v in vars(args).items()},
        "thresholds": {"block": thresholds[0], "defer": thresholds[1]},
        "summary": hu.summarise(rows),
        "monitor_failures": {
            "parse": monitor.parse_failures,
            "call": monitor.call_failures,
            "reasons": dict(monitor.failure_reasons),
        },
        "cache_hits": {"supervisor": sup_client.hits, "monitor": mon_client.hits},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
