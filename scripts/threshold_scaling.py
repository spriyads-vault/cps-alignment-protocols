"""Run the remote-CBF threshold scaling study (predictions P6 to P10, amendment A4).

Free: simulation only, no API. About 2,300 episodes, a few minutes on four cores.

    uv run python scripts/threshold_scaling.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from quadtank_control.experiments.scaling import run_all


def fmt(x: float | None) -> str:
    return "none" if x is None else f"{x:5.1f}"


def main() -> int:
    out = Path("results/threshold_scaling")
    out.mkdir(parents=True, exist_ok=True)
    rows = run_all(out)
    print("hold s | gamma | h_safe | plant         | first harm | d* point | d* confirmed")
    for r in rows:
        print(
            f"{r['hold_s']:6g} | {r['gamma']:5g} | {r['h_safe']:6g} | {r['plant']:13s} | "
            f"{fmt(r['first_harm']):>10s} | {fmt(r['point']):>8s} | {fmt(r['confirmed']):>12s}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
