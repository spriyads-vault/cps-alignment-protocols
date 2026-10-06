# cps-alignment-protocols

AI-control red-team evaluation on a simulated quadruple-tank process. Question:
how much network delay can a hybrid of an LLM monitor and a physics safety
filter tolerate before an untrusted LLM supervisor can cause a safety violation?

Read `PREREGISTRATION.md` first.

## Status

Step 1 of 5 done: plant, PI baseline, tests.

## Run

    uv sync
    uv run pytest
