# Three-Scheduler Comparison

This folder contains plots and comparison tables for the proposed combined scheduler against:

1. `radix_static` (static)
2. `paper_fine_grained` (fixed-size chunks dynamically dispatched)
3. `novelty_cost_gated_steal` (proposed combined policy)

## Files

- `grid_all_schedulers_R*.png`: all three schedulers at every skew in the exploratory grid, one plot per input size.
- `confirmation_large_z175.png`, `confirmation_small_z175.png`: all three schedulers in each eight-seed high-skew confirmation.
- `paired_gain_vs_static_all_conditions.png`, `paired_gain_vs_fixed_dynamic_all_conditions.png`: every paired condition with 95% intervals; positive gain means faster proposed-policy E2E.
- `wins_vs_both_baselines.png`: filtered view of conditions where both paired intervals are above zero. Read it together with the unfiltered plots and the report; it is not a full-results summary.
- `three_scheduler_metrics.csv`, `paired_gain_vs_baselines.csv`: source values for the plots.
- `conditions_faster_than_both_baselines.csv`: rows in the filtered win plot, with seed counts and intervals.
- `WEIGHTS_AND_THREE_SCHEDULER_REPORT.md`: interpretation, experiment scope, and how the cost coefficients and settings were obtained.

## Interpretation

These compare implementations in this repository. `paper_fine_grained` is a fixed-chunk baseline inspired by the reference paper, not the original paper's implementation or a reproduction of its reported performance. Do not claim these figures show that the project beats the paper.

The strongest supported statement is conditional: at the measured `z=1.75` confirmation points, the combined policy was faster than these two repository baselines. It was not shown to outperform the budgeted policy beyond uncertainty in the large confirmation, and exploratory grid cells have only three seeds and are post hoc. The complete report and ablations remain in [`../../../FINAL_REPORT.md`](../../../FINAL_REPORT.md).
