"""Command line: python -m quadtank_control.experiments.cli run configs/exp1.yaml"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from ..config import load_config
from .report import write_report
from .runner import build_scenarios, rebuild_summary, run_experiment


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="quadtank-experiments")
    sub = ap.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="run an experiment config and write results")
    run.add_argument("config", type=Path)
    run.add_argument("--out", type=Path, default=Path("results"))
    run.add_argument("--dry-run", action="store_true", help="print the grid size and exit")
    summ = sub.add_parser(
        "summarise", help="rebuild summary.json and report.md from saved episodes, no simulation"
    )
    summ.add_argument("config", type=Path)
    summ.add_argument("--out", type=Path, default=Path("results"))
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    if args.cmd == "summarise":
        rebuild_summary(cfg, args.out / cfg.name)
        write_report(cfg, args.out / cfg.name)
        print(f"rebuilt {args.out / cfg.name}")
        return 0
    n = len(build_scenarios(cfg))
    print(f"{cfg.name}: {n} episodes")
    if args.dry_run:
        return 0
    out = args.out / cfg.name
    t0 = time.time()
    rows = run_experiment(cfg, out)
    write_report(cfg, out)
    print(f"done: {len(rows)} episodes in {time.time() - t0:.0f}s -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
