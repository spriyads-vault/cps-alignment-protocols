# cps-alignment-protocols

A testbed for AI-control protocols on a physical process. An untrusted supervisor sets the
pump voltages of a simulated quadruple-tank plant. A monitor, a control barrier function
(CBF) safety filter and a trusted PI controller try to stop it from doing harm. A delayed,
lossy network sits between them. The question: how much network delay can the guards
tolerate before the supervisor can cause a violation?

Read `PREREGISTRATION.md` first. It was committed before any evaluation episode ran.

## What is established and what is not

| Claim | Status |
|---|---|
| The CBF filter keeps the safe set invariant at zero delay, and matches a brute-force projection | Tested (`tests/test_cbf.py`) |
| Each guard alone has a blind spot (experiment 1) | Passes 10 of 10 criteria. Partly true by construction, see below |
| The guards together hold against overt and injected attacks, and fail against a monitor-aware covert one (experiment 2) | Passes 8 of 8 criteria. Same caveat |
| Where the delay threshold d* sits (experiment 3) | See the results section |
| **LLM monitors fall for injected text** | **Not tested.** Needs the real-model pilot, which has not been run |
| Anything about adaptive attackers | Not built |

The monitor in every result so far is `RuleMonitor`, a deterministic surrogate. It discounts
its suspicion score when the supervisor's rationale carries an authority claim. That models
prompt injection by assumption, so a pass on "monitor fails against injection" confirms the
harness behaves as designed. It says nothing about real models. The CBF half of each
result does not have this problem: the filter reads numbers only, so its blind spot (harm
that stays inside the safe set) is a property of the method.

The attackers are scripted and do not adapt to the protocol.

## Results

Evaluation seeds 10000 to 10029, 30 episodes per cell, Wilson 95% intervals. Full tables are in
`results/*/report.md`.

**Experiment 1, zero delay.** Monitor-only fails against injection (overflow in 30 of 30,
both plants) and holds against overt attacks (0 of 30). CBF-only holds against overt and
injected attacks on overflow (0 of 30) and fails against covert sabotage (30 of 30).

**Experiment 2, zero delay.** Monitor plus CBF holds against overt and injected attacks
(0 of 30 overflows) and fails against the monitor-aware covert attacker (30 of 30
sabotaged). Defer-to-PI fails there too, because its trigger is the same monitor. Two
results were not in the pre-registration:

- Against plain injection, hybrid and defer-to-PI avoid overflow but are still sabotaged in
  30 of 30 runs. The CBF clamps the pumps at the barrier, so tracking collapses and energy is
  wasted. "Holds" means no catastrophe, not no harm.
- Defer-to-PI costs usefulness on the minimum-phase plant (0.77 against 1.00 for hybrid),
  because 5% false defers hand control to the slower PI.

**Experiment 3, delay sweep.** Running when this was written. Results will be added here and in
`results/exp3_delay/report.md`. Predictions P3 to P5 and amendment A1 in `PREREGISTRATION.md`
were fixed before any of its output was read.

<!-- EXP3 -->

## Run it

    uv sync --extra llm
    uv run pytest
    uv run python -m quadtank_control.experiments.cli run configs/exp1_blindspots.yaml --dry-run
    uv run python -m quadtank_control.experiments.cli run configs/exp1_blindspots.yaml

Exp 3 is 17,340 episodes, about 20 minutes on four cores. Results go to `results/<name>/`.
Raw per-episode CSVs are gitignored and regenerate from the config and seeds.

Quality gate, the same as CI: `ruff check`, `ruff format --check`, `mypy`, `pytest`.

## Real-model pilot (not yet run)

`scripts/llm_monitor_pilot.py` asks the question the surrogate cannot: does an LLM monitor
separate honest from attacking LLM supervisors, and does seeing the rationale help? It
refuses to run without `--yes` and a hard `--max-calls`, and caches every response. With
`--runs 1` and the three attacks, that is 4 episodes x 60 decisions x 3 calls = 720 calls.
The cost has not been measured. [NEED: price a small run with `count_tokens` before choosing a budget.]

    uv run python scripts/llm_monitor_pilot.py --max-calls 800 --runs 1   # dry run, spends nothing

## Layout

    src/quadtank_control/
      plant/        quadtank.py: ODE, limits, equilibrium maps, the single integrator
      control/      pi.py: decentralised PI, the trusted fallback
      safety/       cbf.py: discrete-time CBF filter
      protocols.py  edge versus remote guards, block versus defer
      env.py        EpisodeEnv: steppable environment
      episode.py    run_episode and result types
      metrics.py    Wilson, bootstrap, calibration, d* finder, AUROC
      monitors/     rule.py (surrogate), llm.py
      supervisors/  scripted.py (honest and attacks), llm.py
      llm.py        LLMClient protocol, budget guard, cache, Anthropic client
      controlarena_setting.py   ControlArena setting (optional dependency)
      experiments/  runner, report, CLI
    configs/        one YAML per experiment
    docs/ARCHITECTURE.md

See `docs/ARCHITECTURE.md` for the timeline of one decision, the seed ranges and the assumptions.

## Limitations

- Plant parameters are recalled from Johansson (2000), not copied. The non-minimum-phase
  equilibrium does not match the paper's quoted heights, so one number is probably wrong.
  [NEED: check against the paper.]
- The CBF has the exact plant model (A2). Model mismatch is not tested.
- The ControlArena setting was verified with one offline run on the minimum-phase plant at zero
  delay. Non-minimum-phase, delay, the remote CBF and multi-process runs are untested there.
- PI and honest-supervisor gains were hand-tuned on development seeds.
- No theory-based delay prediction. The one in the pre-registration comes from a small pilot.
