# Remote-CBF threshold scaling study

`cbf_only@remote` against the overt attack, 10 episodes per cell (seeds 10000 to 10009), 16 effective delays from
0 to 60 s, both plants, 2,300 episodes. d* is the interpolated delay where the overflow rate first exceeds 0.10.
Predictions P6 to P10 were committed before the run (PREREGISTRATION.md, amendment A4, commit a7980ee).

| hold s | gamma | barrier cm | min-phase d* | non-min-phase d* |
|---|---|---|---|---|
| 4 | 0.5 | 18 | 4.2 | 6.2 |
| 10 | 0.5 | 18 | 12.0 | 12.2 |
| 20 | 0.5 | 18 | 24.4 | 18.2 |
| 10 | 0.3 | 18 | 20.4 | 16.2 |
| 10 | 0.8 | 18 | 8.2 | 8.2 |
| 10 | 0.5 | 17 | 12.2 | 14.2 |
| 10 | 0.5 | 16 | 16.2 | 16.2 |

## Predictions

| | prediction | result |
|---|---|---|
| P6 | d* at hold 20 exceeds d* at hold 4, both plants | **Held.** 24.4 against 4.2, and 18.2 against 6.2 |
| P7 | d*/hold between 0.5 and 2.5 | **Held.** Ratios 1.06, 1.20, 1.22 (minimum-phase) and 1.55, 1.22, 0.91 (non-minimum-phase) |
| P8 | d* does not increase with gamma, and is smaller at 0.8 than at 0.3 | **Held.** 20.4, 12.0, 8.2 and 16.2, 12.2, 8.2 |
| P9 | baseline within 3 s of experiment 3 | **Held.** 12.0 against 12.3 and 12.2 against 12.4 |
| P10 | each 1 cm of tightening adds 1.5 to 6 s, and 2 cm adds at least 4 s | **Failed as written.** Total clause held (+4.2 s and +4.0 s). Per-centimetre clause failed once: minimum-phase 18 to 17 cm added 0.2 s |

The P10 failure is partly a measurement limit. Delays move in 2 s steps (commands land on plant steps), so a
1 cm change cannot be resolved finer than about 2 s, and the minimum-phase values step 12.2 then 16.2, not
smoothly. Averaged over the two centimetres the gain is about 2 s per centimetre on both plants, inside the
predicted band. A fair reading is that the average effect was right and the per-centimetre claim was too fine
for this grid. The prediction is recorded as failed because that is what it said.

## Reading it

- The remote filter's delay budget is about one hold period: 1.0 to 1.5 times the hold in 5 of 6 cells, and 0.9
  times in the sixth. A longer hold buys more tolerance, since the filter reasons about a longer window.
- A looser barrier (larger gamma) cuts the budget sharply: 20.4 s to 8.2 s on the minimum-phase plant.
- Tightening the barrier by 2 cm buys about 4 s. That is the practical lever if the filter has to sit away from the
  plant: spend margin to buy delay tolerance.
- This is consistent with the extra-exposure mechanism (a delay D adds exposure beyond the window the filter
  judged), but it does not prove it. It shows the dependencies the mechanism predicts.

## Limits

- Ten episodes per cell. Interpolated d* values near the 0.10 line move by a step or two with a single episode.
- One attack (maximum pumping), one filter design, one plant model. The filter falls back to pumps off about half
  the time at a 10 s hold even with no delay, which is a weakness of this design, not a general fact.
- Tightening lowers the filter's barrier but not the 20 cm rim, so part of the gain is simply more room before
  overflow.
- The mechanism hypothesis was formed after seeing experiment 3, so only the predictions are prospective.
