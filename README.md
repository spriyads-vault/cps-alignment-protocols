# cps-alignment-protocols

![headline numbers](docs/img/tiles.svg)

An AI-control testbed on a simulated quadruple-tank process. An **untrusted supervisor** sets the pump voltages.
A **monitor**, a **control barrier function (CBF)** safety filter and a **trusted PI controller** try to stop it
doing harm, across a **delayed, lossy network**. The question: how much network delay can the guards tolerate
before the supervisor can cause a violation?

Read [`PREREGISTRATION.md`](PREREGISTRATION.md) first. It was committed before any evaluation episode ran, and
amendments A1 to A5 record every change made after looking at data. Full tables and caveats:
[`docs/RESULTS.md`](docs/RESULTS.md).

## Where the guard runs decides how much delay it survives

![overflows versus delay](docs/img/delay.svg)

Run at the plant on the live state, the CBF recorded **0 overflows in all 288 cells**. Run next to the supervisor
on stale state, it loses safety at about one hold period of delay (12 to 16 s). The jump at 12 to 16 s is the
20 cm rim clipping a smooth rise, not a sudden instability. Safe is not useful: edge usefulness on the
minimum-phase plant falls to 0.02 beyond 20 s, and defer-to-PI keeps a floor of 0.19 to 0.25.

![delay budget by design](docs/img/threshold.svg)

Rule of thumb for this filter design: the budget is 0.9 to 1.6 times the hold period in all six cells. The
mechanism (extra exposure beyond the window the filter reasoned about) fits but is not proved. Four of five
pre-registered predictions held, and P10 failed as written.

## Real and searched attackers

![real monitor](docs/img/monitor.svg)

Claude Haiku 4.5 was **not fooled by a fixed authority claim**, with or without a prompt warning. In the closed
loop, the false-alarm budget decided covert sabotage: at a 1% budget the monitor flagged 39% of a monitor-aware
attacker's decisions and the attacker won 3 of 3 episodes against block-and-hold. At 5% it flagged about 100%.

![adaptive search](docs/img/adaptive.svg)

The search tunes a covert attacker against the deployed protocol. It finds severe sabotage only where the
surrogate monitor is built to be fooled. Against the surrogate that ignores authority claims, nothing beat the
honest baseline.

## How far to trust this

| Result | Strength |
|---|---|
| Edge CBF is safe at every delay | Simulation, scripted attackers, one plant model |
| Remote delay budget is about one hold | Ten episodes per cell, one attack, one filter design |
| Haiku 4.5 resists authority claims | Two episodes per condition, blatant actions |
| Exp. 1 and 2 pass all 18 criteria | **Partly by construction.** The surrogate monitor is built to be fooled |
| Adaptive search finds nothing vs unfooled monitor | 240 candidates per search, tight thresholds from a scripted honest supervisor |

Not done: usefulness with a real supervisor (built, tested against fakes, gated behind `--yes` and a hard call
cap). The reasoning adversary ran once and was **invalid**: the attacker model refused 40 of 41 decisions
(`results/llm_rationale_adversary_run1.md`); model mismatch for the CBF; any monitor but Haiku 4.5.
The tank 2 and 4 parameters and the non-minimum-phase set are unconfirmed against Johansson (2000).

## Run it

```
uv sync --extra llm
uv run pytest
uv run python -m quadtank_control.experiments.cli run configs/exp1_blindspots.yaml --dry-run
uv run python scripts/threshold_scaling.py      # free, a few minutes
uv run python scripts/adaptive_attack.py        # free, a few minutes
uv run python scripts/make_readme_charts.py     # redraw the charts above
```

Paid scripts print their planned call counts, refuse to run without `--yes`, and stop at `--max-calls`. Price a
`--runs 1` run first, because earlier runs cost about four times a per-call estimate. Quality gate, same as CI:
`ruff check`, `ruff format --check`, `mypy`, `pytest`.

## Layout

```
src/quadtank_control/   plant, control (PI), safety (CBF), protocols, env, episode, metrics,
                        monitors, supervisors, llm, controlarena_setting, experiments
scripts/                one gated or free script per study
configs/                one YAML per experiment
results/                reports and summaries, one folder per study
docs/                   ARCHITECTURE.md, RESULTS.md, img/ (generated charts)
```
