# Artifact Manifest

- [`src/main.cpp`](./src/main.cpp): join algorithms, empirical work estimation, bounded task allocation, atomic-flag private queues, stealing threshold, raw metrics, and self-tests.
- [`README.md`](./README.md): strict build/test commands, reproduction commands, and concise evidence status.
- [`FINAL_REPORT.md`](./FINAL_REPORT.md): novelty boundary, code mapping, experimental protocol/results, ablations, limitations, and answers to the requested questions.
- [`PAPER_REPRODUCTION_AND_NOVELTY.md`](./PAPER_REPRODUCTION_AND_NOVELTY.md): focused mapping to the reference paper and related-work boundary.
- [`scripts/run_current_source_grid.ps1`](./scripts/run_current_source_grid.ps1): current-source exploratory grid over three sizes and four skew levels.
- [`scripts/run_z175_targeted_confirmation.ps1`](./scripts/run_z175_targeted_confirmation.ps1): eight-seed large high-skew confirmation.
- [`scripts/run_small_skew_confirmation.ps1`](./scripts/run_small_skew_confirmation.ps1): configurable eight-seed confirmation for a selected small workload/skew.
- [`scripts/analyze_experiments.py`](./scripts/analyze_experiments.py): raw-data correctness validation, seed-paired bootstrap comparisons, metric summaries, and plots.
- [`tests/smoke.ps1`](./tests/smoke.ps1), [`scripts/run_smoke.sh`](./scripts/run_smoke.sh): smoke and correctness-test entry points.

## Current-source measured data

- [`results/consolidated_results_and_plots/`](./results/consolidated_results_and_plots/): complete copy of the result directory contents in one folder, preserving experiment subdirectories and historical/current distinctions.
- [`results/consolidated_results_and_plots/three_scheduler_comparison/`](./results/consolidated_results_and_plots/three_scheduler_comparison/): focused three-scheduler E2E plots, paired gains against static and fixed-chunk dynamic baselines, filtered win cases, source CSVs, and parameter/weight methodology report.
- [`results/adaptive_linear_cost_final_grid/`](./results/adaptive_linear_cost_final_grid/): 864 raw rows from three sizes, four skew values, three seeds per size, and three repetitions.
- [`results/adaptive_linear_cost_final_z175/`](./results/adaptive_linear_cost_final_z175/): 448 raw rows from eight independent seeds and seven repetitions at `R=250k`, `S=4M`, `z=1.75`.
- [`results/adaptive_linear_cost_final_small_z175/`](./results/adaptive_linear_cost_final_small_z175/): 448 raw rows from eight independent seeds and seven repetitions at `R=20k`, `S=320k`, `z=1.75`.

Each result set includes raw CSVs, summary CSVs, `analysis/comparison_summary.csv`, `analysis/metrics_summary.csv`, and comparison plots. The three current-source sets contain 1,760 raw rows total, and the runners/analyzer checked results against the sequential oracle. Previous result directories are historical and should not be combined with this current-source evidence.

## Verification and limits

- All three benchmark runners compiled the current source with `-O3 -std=c++17 -Wall -Wextra -Wpedantic -Werror -fopenmp` and passed `--self-test`.
- Correctness tests cover duplicates, empty inputs, extreme skew, 1/2/4 threads, concurrent joins, and all schedulers.
- Paired seed-level comparisons and per-run variability are retained in analysis outputs.
- Only one Windows machine and four OpenMP workers were tested. No Linux replication, race sanitizer, direct cache-line migration counter, memory measurement, or cold-start calibration measurement was performed.
- The full policy's large high-skew timing beat static and fixed-chunk baselines but was not faster than `novelty_budgeted` beyond uncertainty. Global algorithmic novelty is not established.

## Reference

C. Balkesen, J. Teubner, G. Alonso, and M. Tamer Özsu, “Main-Memory Hash Joins on Multi-Core CPUs: Tuning to the Underlying Hardware,” ICDE 2013, [DOI 10.1109/ICDE.2013.6544839](https://doi.org/10.1109/ICDE.2013.6544839).
