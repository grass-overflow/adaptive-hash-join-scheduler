# Adaptive Hash Join: Implementation and Evidence

C++17/OpenMP radix-partitioned hash join with a sequential correctness reference, static and dynamic scheduling baselines, bounded adaptive probe tasks, empirical partition-work estimation, and an experimental cost-gated stealing policy.

## Evidence status

The current source passes strict GCC/OpenMP compilation, `--self-test`, and all current benchmark correctness checks. It does **not** establish global algorithmic novelty or a consistent win over the strongest simpler scheduler.

In the fresh-seed large high-skew confirmation (`R=250k`, `S=4M`, `z=1.75`, four threads, eight seeds), the full method was 20.08% faster than static scheduling and 16.35% faster than fixed-size fine-grained scheduling. It was essentially tied with `novelty_budgeted`: −0.16% mean paired gain (95% interval −0.88% to +0.57%). In the small high-skew confirmation, it beat static and fixed chunks but did not establish an advantage over coarse dynamic, budgeted, or cost-aware ablations. The multi-skew grid includes regressions. Do not claim the method beats every scheduler or all skew levels.

See [`FINAL_REPORT.md`](./FINAL_REPORT.md) for the precise claim boundary, all headline comparisons, ablations, limitations, and answers to the original evaluation questions. See [`PAPER_REPRODUCTION_AND_NOVELTY.md`](./PAPER_REPRODUCTION_AND_NOVELTY.md) for the reference-paper comparison.

## Build and correctness tests

```powershell
g++ -O3 -std=c++17 -Wall -Wextra -Wpedantic -Werror -fopenmp src\main.cpp -o hashjoin.exe
.\hashjoin.exe --self-test
```

The self-test covers duplicate keys, empty inputs, extreme skew, 1/2/4 threads, concurrent joins, and all schedulers.

## Reproduce the retained current-source experiments

The result directories already contain raw per-repetition CSVs, summary CSVs, paired comparisons, metric summaries, and plots:

- [`results/consolidated_results_and_plots/`](./results/consolidated_results_and_plots/): one-folder copy of all result files and plots, retaining each experiment's folder structure.
- [`results/consolidated_results_and_plots/three_scheduler_comparison/`](./results/consolidated_results_and_plots/three_scheduler_comparison/): curated static vs fixed-chunk dynamic vs proposed-policy plots, paired comparisons, and coefficient-selection explanation.
- [`results/adaptive_linear_cost_final_grid/`](./results/adaptive_linear_cost_final_grid/): 3 sizes × 4 skew values, three seeds, three repetitions; 864 raw rows.
- [`results/adaptive_linear_cost_final_z175/`](./results/adaptive_linear_cost_final_z175/): large `z=1.75` confirmation; eight seeds × seven repetitions; 448 raw rows.
- [`results/adaptive_linear_cost_final_small_z175/`](./results/adaptive_linear_cost_final_small_z175/): small `z=1.75` confirmation; eight seeds × seven repetitions; 448 raw rows.

To generate fresh reruns, select unused output directories:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_current_source_grid.ps1 -OutputDir results\adaptive_linear_cost_final_grid_rerun -SeedStart 2901
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_z175_targeted_confirmation.ps1 -OutputDir results\adaptive_linear_cost_final_z175_rerun -SeedStart 3901
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_small_skew_confirmation.ps1 -OutputDir results\adaptive_linear_cost_final_small_z175_rerun -SeedStart 4301 -Skew 1.75
```

Each runner compiles the current source with strict warnings, runs `--self-test`, checks benchmark joins against the sequential reference, writes raw and summary CSVs, and invokes `scripts\analyze_experiments.py`. Existing raw data are not overwritten.

## Scheduler variants

`sequential_reference`, `radix_static`, `radix_dynamic_coarse`, `paper_fine_grained`, `novelty_budgeted`, `cost_aware_no_steal`, `cost_aware_ungated_steal`, and `novelty_cost_gated_steal`.

The empirical cost model uses measured build time per build tuple and sampled probe work to rank candidate partitions. Build is already complete when probe work is split. The “cache migration” value is a contention proxy from atomic-flag locking, not a hardware cache-migration measurement. These are implementation and evaluation details, not evidence of global novelty.
