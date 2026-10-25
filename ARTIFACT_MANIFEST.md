# Artifact Manifest

## Core Engine & Architecture
- [`src/main.cpp`](./src/main.cpp): Complete C++17/OpenMP implementation of the hardware-conscious multi-core Radix Hash Join, sequential oracle, baseline schedulers (`radix_static`, `paper_fine_grained`), empirical cycle cost model, bounded task allocation, lock-free private deques, and threshold-gated work stealing (`novelty_cost_gated_steal`).
- [`hashjoin.exe`](./hashjoin.exe): Precompiled optimized 64-bit binary built with `-O3 -std=c++17 -Wall -Wextra -Wpedantic -Werror -fopenmp`.
- [`Makefile`](./Makefile): Build script for strict compilation and self-test execution.

## Documentation & Academic Reports
- [`README.md`](./README.md): Primary repository entry point with project motivation, 8-thread quantitative results, build instructions, reproduction steps, and architectural overview.
- [`FINAL_REPORT.md`](./FINAL_REPORT.md): In-depth academic report covering the research question, baseline implementation, novelty design, empirical calibration, statistical methodology, and claim boundaries.
- [`PAPER_REPRODUCTION_AND_NOVELTY.md`](./PAPER_REPRODUCTION_AND_NOVELTY.md): Direct mapping to Balkesen et al. (ICDE 2013) algorithms and discussion of the work-stealing novelty boundary.
- [`Main-memory_hash_joins_on_multi-core_CPUs_Tuning_to_the_underlying_hardware.pdf`](./Main-memory_hash_joins_on_multi-core_CPUs_Tuning_to_the_underlying_hardware.pdf): Reference research paper from ICDE 2013.

## Benchmark Harness & Analysis Scripts
- [`scripts/run_8thread_grid.py`](./scripts/run_8thread_grid.py): Multi-threaded benchmark runner across 8 threads and the full 7-point Zipfian skew spectrum ($z \in [0.0, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75]$) with 3 independent seeds.
- [`scripts/run_full_skew_benchmark.py`](./scripts/run_full_skew_benchmark.py): 4-Thread benchmark harness across the complete 7-point Zipfian skew spectrum.
- [`scripts/generate_academic_plots.py`](./scripts/generate_academic_plots.py): Generates IEEE/ACM publication-grade academic plots with serif fonts, standard error bars, cross-hatching, and speedup breakdowns.
- [`scripts/create_three_scheduler_comparison.py`](./scripts/create_three_scheduler_comparison.py): Statistical consolidation and paired comparison generator.
- [`scripts/analyze_experiments.py`](./scripts/analyze_experiments.py): Statistical analysis module calculating bootstrap confidence intervals, ANOVA, load imbalance ($\lambda$), and speedup.
- [`scripts/run_validation.ps1`](./scripts/run_validation.ps1), [`scripts/run_validation.sh`](./scripts/run_validation.sh): Fast correctness validation scripts.
- [`tests/smoke.ps1`](./tests/smoke.ps1): Multi-platform smoke test.

## Benchmark Datasets & Publication Plots
- [`results/academic_plots/`](./results/academic_plots/): 12 publication-grade academic figures (IEEE/ACM style) in high-resolution PNG format.
- [`results/grid_8threads/`](./results/grid_8threads/): 8-Thread benchmark dataset covering all 7 skew factors ($z \in [0.0, 1.75]$) with per-run raw CSVs, statistical summaries, and comparison tables.
- [`results/full_skew_grid/`](./results/full_skew_grid/): 4-Thread benchmark dataset across the complete 7-skew spectrum.
- [`results/adaptive_linear_cost_final_grid/`](./results/adaptive_linear_cost_final_grid/): Exploratory 4-thread grid across 3 table sizes and 4 skew factors (864 raw runs).
- [`results/adaptive_linear_cost_final_z175/`](./results/adaptive_linear_cost_final_z175/): Large workload confirmatory 8-seed benchmark dataset at $z = 1.75$ (448 raw runs).
- [`results/adaptive_linear_cost_final_small_z175/`](./results/adaptive_linear_cost_final_small_z175/): Small workload confirmatory 8-seed benchmark dataset at $z = 1.75$ (448 raw runs).
- [`results/consolidated_results_and_plots/`](./results/consolidated_results_and_plots/): Consolidated multi-experiment archive and paired comparisons.
