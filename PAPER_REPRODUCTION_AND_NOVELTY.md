# Reference-Paper Reproduction and Novelty Boundary

## Reproduction scope

This project reproduces a focused portion of Balkesen et al., “Main-Memory Hash Joins on Multi-Core CPUs: Tuning to the Underlying Hardware,” ICDE 2013. The code implements radix partitioning, partition-wise hash-table build/probe, and skew-related scheduling variants. It is not a reproduction of the paper's complete algorithm suite, specialized SIMD hash-table layout, hardware platform, or absolute performance results.

The reference paper already addresses skew using fine-grained decomposition of oversized partitions so multiple workers can share the probe work. Therefore, the fixed-size `paper_fine_grained` baseline is prior work, not a new contribution of this repository.

## Current implementation mapping

| Method | Code | Assessment |
|---|---|---|
| Static/coarse partition scheduling | `radix_static`, `radix_dynamic_coarse` | Comparison baselines. |
| Fixed-size splitting of heavy probe partitions | `paper_fine_grained` | Established in the reference paper. |
| Bounded task allocation | `novelty_budgeted`, `make_cost_aware_tasks` | Implements adaptive granularity in this code; the general idea has prior art. |
| Empirical partition-work estimate | `estimate_partition_costs` | Measures build time per build row and sampled probe slot-work/probe timing. The resulting partition cost estimate is used to rank heavy candidates. |
| Benefit-gated task splitting | `make_cost_aware_tasks` | Estimates probe parallelism benefit less queue-operation cost. This is a heuristic, not a makespan optimizer. |
| Owner-local queues and stealing | `execute_private_queues` | Uses atomic-flag spinlocks around private queues; work stealing is established prior art. |
| Threshold-gated stealing | `execute_private_queues` and scheduler calibration | Threshold includes atomic-lock time, a contended-minus-uncontended proxy, and measured probe-row cost. The proxy is not direct cache-migration measurement. |

The cost estimate has a build term `alpha * |R_i|` and a per-partition probe term `beta_i * |S_i|` for ranking tasks. `alpha` is measured as the completed build-phase time divided by build rows. `beta_i` is based on sampled slot-probe work and measured probe-row time. It is not a statistical regression fit across datasets. The build phase is finished before probe decomposition, so this term helps rank candidate partitions but does not make build work parallel or dynamically schedulable.

The splitting rule estimates a potential probe-time reduction using useful chunks and subtracts estimated deque-operation cost. This calculation is not a predictive global schedule or empirical proof that a split will reduce total elapsed time. Likewise, the threshold's contended atomic-flag lock time is a proxy containing scheduler/coherence effects, not a measured cache-to-cache transfer cost.

## Prior-work boundary

- Balkesen et al., ICDE 2013, [DOI 10.1109/ICDE.2013.6544839](https://doi.org/10.1109/ICDE.2013.6544839): radix join and fine-grained handling of skewed partitions.
- Leis et al., “Morsel-Driven Parallelism,” SIGMOD 2014, [DOI 10.1145/2588555.2610507](https://doi.org/10.1145/2588555.2610507): dynamic task/morsel-based database execution.
- Blumofe and Leiserson, “Scheduling Multithreaded Computations by Work Stealing,” JACM 1999, [DOI 10.1145/324133.324234](https://doi.org/10.1145/324133.324234): foundational work-stealing scheduling.

These references establish that skew splitting, dynamic granularity, and stealing are not new by themselves. This focused comparison does not establish whether the exact combination or estimator appears elsewhere. A systematic literature review and independent prior-art verification are required before making a research-novelty claim.

## Current-source evidence

The current results are in [`results/adaptive_linear_cost_final_grid/`](./results/adaptive_linear_cost_final_grid/), [`results/adaptive_linear_cost_final_z175/`](./results/adaptive_linear_cost_final_z175/), and [`results/adaptive_linear_cost_final_small_z175/`](./results/adaptive_linear_cost_final_small_z175/). These include 1,760 raw rows in total, paired comparisons, phase/scheduler metrics, and plots.

At `R=250k`, `S=4M`, `z=1.75`, four threads, and eight fresh seeds, the full policy was 20.08% faster than static scheduling and 16.35% faster than fixed-size fine-grained scheduling. Against `novelty_budgeted`, its mean paired gain was −0.16% (95% interval −0.88% to +0.57%, four of eight seeds faster): no improvement was established. At `R=20k`, `S=320k`, `z=1.75`, it beat static and fixed chunks by 7.53% and 7.91%, but the comparisons against coarse dynamic, `novelty_budgeted`, and cost-aware ablations did not establish a general advantage.

The three-seed exploratory grid has mixed outcomes, including regressions. At `R=250k,z=0.75`, the full policy was 1.42% slower than fixed chunks and 6.22% slower than coarse dynamic, with bootstrap intervals below zero. Grid conditions are exploratory and are not independent confirmation of a skew threshold.

The large high-skew ablation showed the cost-aware no-steal variant 2.79% slower than `novelty_budgeted`; ungated stealing was 1.49% faster than the no-steal variant; the gated policy was 1.07% faster than ungated stealing by timing contrast. However, the threshold-skip median was zero, so these timings do not demonstrate that a gate skip caused the difference or that threshold gating is beneficial. In the small confirmation, these ablation contrasts were inconclusive or regressed.

All parameter settings were fixed across the current grid and confirmations (`chunk-size 256`, `tasks-per-thread 4`, `split-factor 3`, `cost-samples 16`, `queue-batch-size 1`, threshold multiplier `4`). They were empirically screened engineering settings, not statistically optimized coefficients. Per-run build/probe coefficients are measured from that run. The report separates this observed implementation from any claim of global novelty; see [`FINAL_REPORT.md`](./FINAL_REPORT.md) for the protocol, all primary comparisons, and limitations.
