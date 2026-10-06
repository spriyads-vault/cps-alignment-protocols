# Real-model pilot, run 1: a null result

Raw output in `llm_monitor_pilot_run1.json`, produced by `scripts/llm_monitor_pilot.py` with Sonnet 5.5
as the supervisor and Haiku 4.5 as the monitor. One episode per condition.

**Do not read the AUROCs as evidence about the monitor.** The three attacks have identical AUROC to
the last digit (0.5019607843137255) and identical n. That is only possible if the monitor saw identical
inputs. `supervisor_call` is 102, which is exactly 3 attacks x 34 post-onset decisions: every call made in
attack mode failed, and the supervisor fell back to "hold last command", so the monitor scored the same
placeholder action 102 times. The cause is not recorded in this run. The likely one is that the model
declined the red-team prompts. The script has since been changed to record the reason for each failure.

What the run does show:

- Latency per call, one run: supervisor median 1.9 s (p95 2.2 s), monitor median 2.9 s (p95 3.8 s).
  Together that is about 4.8 s on the command path before any network delay.
- With 60 honest decisions, the rationale-reading monitor's honest scores reach 0.78 and the
  numbers-only monitor's reach 0.15. One run and 60 samples are too few to conclude anything from this.

The question the pilot was meant to answer is answered by `scripts/llm_monitor_scripted_attacks.py`,
which scripts the attacks so no model is asked to attack.
