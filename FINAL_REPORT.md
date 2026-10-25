# Adaptive Hash Join: Novelty and Experimental Evidence Audit

## Executive conclusion

The current source implements an empirical partition-work estimate, bounded adaptive probe-task creation, a benefit-versus-dispatch-cost split heuristic, and owner-local task queues with optional threshold-gated stealing. Correctness tests and the current-source benchmark runs pass.

The defensible claim is limited to an **experimental implementation and evaluation of these mechanisms in a radix hash join on one four-thread Windows system**. This work does not establish global algorithmic novelty: fine-grained skew handling and work stealing are established techniques, and this is not a systematic prior-art review. The policy also does not consistently beat the strongest simpler scheduler in the repository.

The most favorable confirmatory result is at `R=250,000`, `S=4,000,000`, Zipf `z=1.75`, four threads: the full policy is faster than static and fixed-size fine-grained scheduling, but its difference from the bounded `novelty_budgeted` scheduler is effectively zero. At `R=20,000`, `S=320,000`, `z=1.75`, it beats static and fixed chunks but is slower by point estimate than coarse dynamic scheduling, the budgeted scheduler, and both cost-aware ablations. Results do not support a claim that the full method beats every scheduler.

## 1. Precise claim and prior-work boundary

**Narrow claim supported by the artifact:** this repository implements and measures a bounded, per-partition probe-work-weighted task-allocation policy with an empirical build/probe tuple cost ranking, a heuristic split-cost gate, and an optional stealing threshold that includes a measured atomic-lock contention proxy. It reports correctness, phase timings, work distribution, scheduling counts, and ablations for one CPU/workload family.

That is an implementation/evaluation contribution, not evidence that the algorithm is new to the field. Specifically:

| Technique | Current implementation | Novelty assessment |
|---|---|---|
| Radix partitioning and build/probe join | Partitioning, hash build, and probe phases in `src/main.cpp` | Standard hash-join machinery. |
| Fine-grained splitting of skewed partitions | `paper_fine_grained` | Already addressed by the supplied Balkesen et al. paper; not novel here. |
| Bounded task generation and adaptive granularity | `novelty_budgeted`, `make_cost_aware_tasks` | Adaptive/bounded scheduling has prior art. Project-specific implementation is not proof of a new method. |
| Per-partition sampled probe work and build/probe cost ranking | `estimate_partition_costs`, `make_cost_aware_tasks` | Implemented here, but cost-based scheduling and sampling are established patterns. No comprehensive search establishes that this exact combination is absent elsewhere. |
| Owner-local queues and work stealing | `execute_private_queues`, `SpinMutex` | Work stealing is established prior art. The queues use an atomic-flag spinlock; they are not lock-free deques. |
| Threshold-gated stealing and estimated split benefit | Cost comparisons in task creation and queue execution | Engineering heuristics, not a new scheduling theory. Their practical benefit is not consistently established. |

The comparison can legitimately use three headline names—`radix_static`, `paper_fine_grained` (fixed chunks dispatched dynamically), and `novelty_cost_gated_steal`—but this is only a presentation choice. `novelty_budgeted`, `cost_aware_no_steal`, and `cost_aware_ungated_steal` remain essential baselines and ablations. Excluding them from a headline table cannot establish novelty or broad superiority.

### Reference and related work reviewed

- C. Balkesen, J. Teubner, G. Alonso, and M. T. Özsu, “Main-Memory Hash Joins on Multi-Core CPUs: Tuning to the Underlying Hardware,” ICDE 2013, [DOI 10.1109/ICDE.2013.6544839](https://doi.org/10.1109/ICDE.2013.6544839). Its Section VI-E addresses skew through fine-grained decomposition. Its reported performance is not directly comparable to this machine or implementation.
- V. Leis et al., “Morsel-Driven Parallelism,” SIGMOD 2014, [DOI 10.1145/2588555.2610507](https://doi.org/10.1145/2588555.2610507). Prior art for dynamic task/morsel scheduling in database execution.
- R. D. Blumofe and C. E. Leiserson, “Scheduling Multithreaded Computations by Work Stealing,” JACM 1999, [DOI 10.1145/324133.324234](https://doi.org/10.1145/324133.324234). Foundational work-stealing prior art.

This is a focused comparison, not a systematic literature review. It cannot support a claim that no prior work uses similar cost models, adaptive splitting, or cost-aware stealing.

## 2. Implementation audit: what the algorithm does

Implementation and relevant symbols are in [`src/main.cpp`](./src/main.cpp):

1. **Cost estimate.** `estimate_partition_costs` measures the completed build phase to obtain `alpha = build_seconds / |R|`. For candidate heavy probe partitions, it samples linear-probing slot counts, separately samples held-out probe rows, and times repeated probe operations to estimate a probe-row coefficient. A partition is ranked with an estimate of the form `alpha * |R_i| + beta_i * |S_i|`. The per-partition probe coefficient is adjusted using its sampled slot count relative to the sampled average.
2. **Important scope distinction.** The build term affects candidate ranking and task-budget allocation only. The build phase has already finished before probe splitting; the method does not subdivide or parallelize build work. This is therefore not a scheduler that jointly assigns end-to-end build and probe tasks.
3. **Bounded decomposition.** `make_cost_aware_tasks` chooses heavy candidates and apportions a budget of `threads * tasks_per_thread`; partitions not selected remain coarse. It estimates the benefit of splitting from probe work and useful parallel chunks, then subtracts estimated queue-operation cost. This is a heuristic, not an optimizer or a measured makespan simulation.
4. **Stealing.** `execute_private_queues` assigns tasks to private queues and permits remote stealing for the stealing variants. `SpinMutex` uses `atomic_flag::test_and_set`; it is a spinlock, not a lock-free queue.
5. **Threshold.** The threshold combines uncontended atomic-lock acquisition, the measured two-worker contention delta, and a configured multiple of measured probe-row time. The field named `cache_migration_proxy_ns` is only that contention delta. It is not a direct cache-to-cache or cache-migration measurement and also includes runtime/coherence effects.
6. **Fallback and correctness.** The implementation retains sequential, static, coarse dynamic, fixed-chunk, budgeted, no-steal, ungated-steal, and gated-steal algorithms. `--self-test` exercises duplicate keys, empty inputs, extreme skew, 1/2/4 threads, concurrent joins, and all schedulers.

### Parameters and how they were obtained

The new grid and confirmations use `--threads 4 --chunk-size 256 --tasks-per-thread 4 --split-factor 3 --queue-batch-size 1 --cost-samples 16 --steal-threshold-multiplier 4`. These are empirical engineering settings screened in earlier parameter sweeps, then held fixed for the results below; they were not fitted by regression, Bayesian optimization, or an online optimizer. The fresh confirmation seeds were distinct from the exploratory grid seeds.

`alpha` and `beta` are measured/recomputed from build and sampled probe work in each run; they are not fixed coefficients learned from a multi-dataset statistical regression. In the large `z=1.75` confirmation, median measured values were about `9.25 ns/build row` and `6.27 ns/probe row`; in the small confirmation they were about `23.77 ns/build row` and `6.63 ns/probe row`. The `35.18 ns` and `30.94 ns` median contention proxies in those conditions are not direct cache-migration costs.

## 3. Experimental protocol and provenance

- Platform: Windows, MinGW-w64 GCC/OpenMP; four OpenMP worker threads on the available four-physical-core PC. Results are machine- and runtime-specific; no CPU affinity, isolated host, Linux run, or hardware cache counter was used.
- Build: `g++ -O3 -std=c++17 -Wall -Wextra -Wpedantic -Werror -fopenmp`.
- Exploratory grid: `R=20k/80k/250k`, `S=16R`, `z=0/0.75/1.4/1.75`, three independent seeds per size, three repetitions. It contains 864 raw scheduler rows, all checked against the sequential oracle.
- Large confirmation: `R=250k`, `S=4M`, `z=1.75`, eight fresh seeds, seven repetitions per scheduler and seed (448 raw rows).
- Small confirmation: `R=20k`, `S=320k`, `z=1.75`, eight fresh seeds, seven repetitions per scheduler and seed (448 raw rows).
- Analyzer: raw per-repetition measurements and correctness flags are retained. Comparison summaries use paired seed-level measurements and bootstrap 95% intervals; positive gain means the candidate ran faster. Confirmations have eight independent dataset seeds; the exploratory cells have only three and are not confirmatory.
- Timing includes partition, build, estimation, task planning, and probe for the reported per-run E2E result. One-time scheduler calibration is initialized during warm-up and is excluded from per-run E2E; this amortization boundary is disclosed and is not a cold-start result.

The three current-source data sets and analyzer artifacts are retained under:

- [`results/adaptive_linear_cost_final_grid/`](./results/adaptive_linear_cost_final_grid/)
- [`results/adaptive_linear_cost_final_z175/`](./results/adaptive_linear_cost_final_z175/)
- [`results/adaptive_linear_cost_final_small_z175/`](./results/adaptive_linear_cost_final_small_z175/)

Together these contain **1,760 correct raw scheduler rows**, CSV summaries, paired comparisons, metric summaries, and plots. These results were regenerated from the current source; prior result directories are historical and must not be mixed with them.

## 4. Results

### Confirmatory full-policy comparisons

Median E2E values are across independent seeds. Gain and confidence intervals are paired analyses over those seeds.

| Workload | Baseline | Baseline median | Full policy median | Mean paired gain (95% interval) | Seeds faster |
|---|---|---:|---:|---:|---:|
| Large, `R=250k`, `S=4M`, `z=1.75` | `radix_static` | 40.271 ms | 32.176 ms | +20.08% [+19.45%, +20.74%] | 8/8 |
| Large, same | `radix_dynamic_coarse` | 34.559 ms | 32.176 ms | +7.05% [+6.11%, +7.98%] | 8/8 |
| Large, same | `paper_fine_grained` | 38.746 ms | 32.176 ms | +16.35% [+15.15%, +17.48%] | 8/8 |
| Large, same | `novelty_budgeted` | 32.019 ms | 32.176 ms | **−0.16% [−0.88%, +0.57%]** | 4/8 |
| Small, `R=20k`, `S=320k`, `z=1.75` | `radix_static` | 4.701 ms | 4.283 ms | +7.53% [+4.16%, +10.79%] | 8/8 |
| Small, same | `radix_dynamic_coarse` | 4.143 ms | 4.283 ms | **−2.66% [−7.67%, +1.69%]** | 4/8 |
| Small, same | `paper_fine_grained` | 4.629 ms | 4.283 ms | +7.91% [+3.04%, +12.21%] | 7/8 |
| Small, same | `novelty_budgeted` | 4.231 ms | 4.283 ms | **−0.99% [−5.73%, +3.29%]** | 4/8 |

Thus a qualified win against static and fixed-size fine-grained scheduling is measured in the large high-skew workload. The full policy does **not** establish an improvement over the strongest simpler budgeted policy there. In the smaller confirmation it does not establish an advantage over coarse dynamic scheduling, the budgeted policy, or the cost-aware ablations. There is no evidence for “wins at all `z >= 0.75`” or “wins over every scheduler.”

### Ablation results: large high-skew confirmation

| Comparison (candidate vs baseline) | Mean paired gain (95% interval) | Faster seeds | Interpretation |
|---|---:|---:|---|
| `novelty_budgeted` vs `paper_fine_grained` | +16.47% [+15.02%, +17.89%] | 8/8 | Bounded task count outperformed this fixed-chunk setup in this condition. |
| `cost_aware_no_steal` vs `novelty_budgeted` | −2.79% [−3.89%, −1.56%] | 1/8 | Adding the sampled estimator and custom non-stealing path was slower here. |
| `cost_aware_ungated_steal` vs `cost_aware_no_steal` | +1.49% [+0.37%, +2.62%] | 7/8 | Ungated stealing improved this cost-aware/no-steal ablation in this condition. |
| `novelty_cost_gated_steal` vs `cost_aware_ungated_steal` | +1.07% [+0.24%, +1.85%] | 7/8 | The timing contrast is positive, but the gate had zero threshold skips in the confirmation; it does not establish that threshold gating caused the gain. |
| Full vs `novelty_budgeted` | −0.16% [−0.88%, +0.57%] | 4/8 | No established full-policy advantage over the strongest simpler policy. |

For the small confirmation, adding the cost estimator to `novelty_budgeted` yielded +0.77% [−2.38%, +3.43%] (5/8 faster), ungated stealing vs no-steal yielded −0.43% [−2.59%, +1.74%] (5/8), and gated vs ungated yielded −1.30% [−2.97%, +0.19%] (3/8). These intervals do not establish a contribution from those mechanisms at this size.

The multi-size/multi-skew grid shows heterogeneous point estimates and some regressions; its three seeds per cell are exploratory. For example, at `R=250k,z=0.75`, full vs fixed chunks was −1.42% [−3.22%, −0.48%] and vs coarse dynamic was −6.22% [−7.75%, −4.39%]. The complete grid comparisons are in [`comparison_summary.csv`](./results/adaptive_linear_cost_final_grid/analysis/comparison_summary.csv); no selected cell should be used alone to imply a general skew threshold.

### Overhead and model evidence

In the large confirmation, median full-policy estimates included `55 µs` cost estimation, `148 µs` task planning, and `111 µs` queue administration; median probe time was `5.09 ms`. In the small confirmation, the corresponding medians were `53 µs`, `113 µs`, and `81 µs`, against a `0.525 ms` probe phase. These overheads are included in per-run E2E. Partition and build are also timed and reported separately in `metrics_summary.csv`.

The held-out WAPE validates sampled probe-step estimates only for the sampled heavy partitions, not predictions of complete partition runtime or end-to-end speedup. The split-benefit value is a scheduling heuristic, not demonstrated as a predictive model. The large confirmation's median threshold-skip count was zero, so the gate mechanism did not visibly suppress stealing in that workload. The contention proxy must not be described as a cache-migration measurement.

## 5. Answers to the requested questions

1. **Precise final novelty claim:** a repository-scale implementation and empirical evaluation of bounded cost-weighted probe-task decomposition with a sampled per-partition probe-work estimate, a heuristic split-cost check, and optional threshold-gated owner-local stealing. Research novelty is unestablished.
2. **Difference from the reference paper and related work:** it adds measured per-partition work ranking, a bounded budget, and implementation-level split/steal heuristics to this reproduction. The reference already decomposes skewed partitions; morsel scheduling and work stealing are also prior techniques. The build term ranks candidates but cannot parallelize the already-finished build phase.
3. **Genuinely new versus established:** no component is demonstrated as globally new. The code-specific combination and its measured engineering behavior are project-specific; radix joins, sampling, bounded/adaptive tasks, queue stealing, and skew decomposition are established or closely related techniques.
4. **Does code contain the mechanisms?** Yes, in the qualified forms above: empirical build/probe ranking, bounded task allocation, a heuristic split-benefit check, and an atomic-flag-spinlock queue with a calibrated threshold/proxy. It does not directly measure cache migration, jointly schedule build and probe, or optimize predicted makespan.
5. **Experiments demonstrating contribution:** current-source raw grid plus two eight-seed, seven-repeat confirmations and ablations. The large confirmation supports gains over static/fixed-chunk scheduling and a context-specific stealing contrast; it does not support a gain over budgeted scheduling. The small confirmation does not establish added value over all adaptive alternatives.
6. **Improvements and regressions:** large `z=1.75` gains of 20.08% over static and 16.35% over fixed chunks; −0.16% vs budgeted with an interval crossing zero. Small `z=1.75` gains 7.53% over static and 7.91% over fixed chunks, but −2.66% vs coarse dynamic and −0.99% vs budgeted, both inconclusive. The grid includes a regression at `R=250k,z=0.75`; all results are preserved.
7. **Correctness/reproducibility/overhead:** strict build and self-tests pass; benchmark rows are checked against the sequential reference; seeds, repeats, raw CSV, analyzer outputs, and run scripts are preserved. Major scheduling/estimation overheads and phase timings are reported. Evidence remains one Windows machine, without race sanitizers, direct hardware counters, memory measurements, Linux replication, or a cold-start calibration measurement.
8. **Missing for a research novelty claim:** systematic literature search; independent implementation/platform replication; more independent seeds and workload families; train/validation separation for any parameter selection; robust runtime prediction validation; direct cache-coherence measurement if claiming locality cost; tests for contention and concurrency under sanitizers; and evidence that each mechanism yields repeatable improvements over the strongest baseline.

## 6. Reproduction commands

From the repository root, these commands generate the current evidence into new, non-overwriting directories:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_current_source_grid.ps1 -OutputDir results\adaptive_linear_cost_final_grid_rerun -SeedStart 2901
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_z175_targeted_confirmation.ps1 -OutputDir results\adaptive_linear_cost_final_z175_rerun -SeedStart 3901
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_small_skew_confirmation.ps1 -OutputDir results\adaptive_linear_cost_final_small_z175_rerun -SeedStart 4301 -Skew 1.75
```

The scripts compile with strict warnings, run `--self-test`, preserve per-run raw CSV, verify the sequential oracle, and invoke the analyzer. For correctness-only validation:

```powershell
g++ -O3 -std=c++17 -Wall -Wextra -Wpedantic -Werror -fopenmp src\main.cpp -o hashjoin.exe
.\hashjoin.exe --self-test
```
