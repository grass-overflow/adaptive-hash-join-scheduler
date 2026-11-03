# Three-scheduler comparison and empirical parameter method

## What this comparison is (and is not)

This report compares the repository's `novelty_cost_gated_steal` implementation with two repository baselines: `radix_static` and `paper_fine_grained` (fixed-size chunks dynamically dispatched). It is not a reproduction-vs-paper head-to-head: `paper_fine_grained` is a code baseline inspired by the reference paper, run on this project’s implementation, compiler, and PC. These measurements do not justify saying that this project beats the original paper.

The proposed scheduler is the combined implementation: sampled cost estimation, bounded cost-weighted task allocation with a heuristic split-benefit check, and owner-local queues with threshold-gated stealing. Its results must be reported as the combined policy. They do not show that each component is independently novel, and the comparisons here do not replace the budgeted/no-steal/ungated ablations in the full evidence report.

## Plot inventory

- `grid_all_schedulers_R*.png`: all three schedulers at all four skew values for each exploratory input size. Nothing is filtered out.
- `confirmation_large_z175.png` and `confirmation_small_z175.png`: all three schedulers in both eight-seed high-skew confirmations.
- `paired_gain_vs_static_all_conditions.png` and `paired_gain_vs_fixed_dynamic_all_conditions.png`: every current-grid and confirmation comparison, with paired 95% bootstrap intervals. Positive gain means the proposed policy is faster; intervals crossing zero are inconclusive.
- `wins_vs_both_baselines.png`: winning conditions only, with all three bars in each condition. The full, unfiltered condition plots above and paired-gain plots should be read alongside it.
- `conditions_faster_than_both_baselines.csv`: only conditions whose two paired intervals are both above zero. These are selected views, not a full-results replacement; exploratory-grid cells have only three seeds and were inspected across several conditions.

`three_scheduler_metrics.csv` and `paired_gain_vs_baselines.csv` retain the plotted median E2E values and paired comparison statistics.

## Selected confirmation outcomes (not universal claims)

At `R=250k`, `S=4M`, `z=1.75`, four threads, the proposed policy's median E2E was 32.176 ms versus 40.271 ms static and 38.746 ms fixed-chunk dynamic. Paired mean gains were +20.08% vs static (95% interval +19.45% to +20.74%) and +16.35% vs fixed chunks (+15.15% to +17.48%), across eight fresh seeds. It was not faster than `novelty_budgeted` beyond uncertainty (−0.16%, interval −0.88% to +0.57%); see the full report.

At `R=20k`, `S=320k`, `z=1.75`, proposed median E2E was 4.283 ms versus 4.701 ms static and 4.629 ms fixed-chunk dynamic. Paired mean gains were +7.53% and +7.91%, respectively. It was slower by point estimate than coarse dynamic and the budgeted policy, and those comparisons were inconclusive. This is not proof that it wins a whole skew range.

## How coefficients and parameters were obtained

There are two different things sometimes called “weights”; they must not be conflated:

1. **Per-run cost coefficients in the implementation.** The build coefficient is measured as `alpha = measured build-phase seconds / number of build tuples`. The probe coefficient is measured from repeated timing of sampled probe rows; individual candidate partitions adjust this using sampled linear-probing slot counts relative to the sampled average. Thus candidate ranking approximates `alpha * |R_i| + beta_i * |S_i|`. These are measured anew per run, not coefficients learned by a statistical regression over a training corpus. Build has already completed before probe tasks are formed, so the build term ranks candidates but does not split or parallelize the build phase.
2. **Scheduler settings.** The evaluation held `chunk-size=256`, `tasks-per-thread=4`, `split-factor=3`, `cost-samples=16`, `queue-batch-size=1`, and `steal-threshold-multiplier=4` fixed. These were selected by empirical screening/sweeps performed during development. They were not obtained by formal statistical fitting or online optimization. Fresh seed ranges were then used for the confirmations, but the high-skew operating point was selected after exploratory results; this is not an untouched preregistered evaluation set.

The split-benefit calculation estimates the reduction in probe work from parallel chunks and subtracts an estimated queue-operation cost. It is a heuristic, not a fitted makespan model. The stealing threshold includes the measured atomic-flag lock acquisition time, a two-worker contention delta, and a configured multiple of measured probe-row time. The so-called cache-migration value is only a contention proxy; no hardware cache-to-cache counter was measured.

In the large confirmation, median measured coefficients were approximately `alpha=9.25 ns/build tuple` and `beta=6.27 ns/probe tuple`; in the small confirmation, approximately `alpha=23.77 ns/build tuple` and `beta=6.63 ns/probe tuple`. They vary with workload and runtime measurement; they are not universal constants or learned “optimal weights.”

## Evidence boundary

All plots and CSVs were generated from the retained analyzer summaries under `results/adaptive_linear_cost_final_*`. The full current-source evidence and limitations are in `../../FINAL_REPORT.md`. Static/fixed-dynamic wins are conditional measured results. The broad research novelty of the combination remains unestablished, and no result here demonstrates beating the original paper.
