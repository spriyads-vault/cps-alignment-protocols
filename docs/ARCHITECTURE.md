# Architecture

## Layers

Imports flow down this list. The leaf modules `types.py` and `network.py` import nothing
from the package and are used by several layers.

1. `plant/`: the quadruple tank. `simulate_hold` is the single integrator. The CBF
   predictor calls the same function, so the model the guard reasons with and the
   plant it protects cannot drift apart.
2. `control/`: decentralised PI. It is the trusted fallback and the usefulness baseline.
3. `safety/`: the discrete-time CBF filter. Reads voltages and heights only.
4. `types.py`, `network.py`: shared data types and the delayed, lossy link.
5. `monitors/`, `supervisors/`: the untrusted and trusted components behind two small
   interfaces. Scripted, parametric (`adaptive.py`), rationale-writing (`rationale_adversary.py`) and
   LLM versions of each implement the same one.
6. `protocols.py`: how the monitor, CBF and PI are wired. Block versus defer, edge versus remote.
7. `episode.py`, `env.py`: the closed loop. `EpisodeEnv` steps one decision at a time.
   `run_episode` drives it to the end.
8. `metrics.py`, `config.py`, `experiments/`: statistics, validated configs, the grid runner, and one module
   per study: `scaling` (remote-CBF threshold), `adaptive` (black-box attack search), `monitor_eval`
   (a real monitor on scripted attacks), `real_monitor_protocol` (a real monitor inside the protocols),
   `honest_usefulness`, `rationale_attack`.
9. `llm.py`, `controlarena_setting.py`: optional model access and the ControlArena adapter.

## One decision, in time order

```
plant at t ──obs──> supervisor ──action──> protocol.remote()
                                             monitor scores it
                                             CBF filters it (only when @remote, from the state above)
                                           │
                    uplink + inference + monitor + downlink delay, or dropped
                                           ▼
                          protocol.deliver() at the plant, arrival time <= now
                            block:  flagged message discarded, last command held
                            defer:  flagged message switches the local PI on
                                           │
                    every plant step: protocol.edge_voltages()
                            @edge: CBF re-checks the held command on the live state
                            @remote: uses the voltage computed from the stale state
                                           ▼
                                      plant.step()
```

The simulated clock is the only clock. Model latency enters as `supervisor_latency_s`.
Wall-clock time never touches the plant, so a delay sweep is reproducible and does not
depend on API load.

## Why edge and remote

Where the CBF runs decides what state it sees. At the plant it sees the live state. Next to
the supervisor it sees the state as it was when the supervisor looked, which is stale by the
time the command lands. Experiment 3 sweeps delay for both placements, because the placement,
not the filter, is what delay attacks. The remote filter must predict over the whole hold
(the supervisor period), otherwise it is unsafe even at zero delay.

## Seeds

- 0 to 999: development. Gains and the pilot used these.
- 1000 to 1999: monitor threshold calibration.
- 10000 up: evaluation.

An episode's randomness (honest noise, link loss and jitter) comes from `SeedSequence(seed)`.
The attack onset comes from `SeedSequence([seed, 7])`, so every protocol faces the same onset.

## Assumptions

- A1 Guards and supervisor see all four heights.
- A2 The CBF has the exact plant model. No mismatch ablation yet.
- A3 The monitor knows a sane controller for the task.
- The surrogate `RuleMonitor` is a stand-in with a built-in weakness. It is not evidence
  about LLM monitors.

## Extension points

- New attack: subclass `Supervisor`, add its name to `AttackSupervisor.KINDS` or register it
  in `experiments/runner.py::make_supervisor`.
- New protocol: add a `ProtocolSpec` to `PRESETS`.
- New attack family: give `ParametricAttacker` another knob and add its range to `BOUNDS`, then the search in
  `experiments/adaptive.py` tunes it with no other change.
- Real models: build `LLMSupervisor` and `LLMMonitor` over any `LLMClient`. Wrap with
  `BudgetedClient` and `CachingClient` before spending anything. Every script that spends has a dry run, a
  hard `--max-calls`, a credential check, and records why any call failed.
- Validity: a study whose attacker is a model must report the attacker's own failure rate and mark itself
  invalid when it is high (see `rationale_attack.summarise`). Pilot 1 measured a placeholder because it did not.
