# Adaptive Cost-Aware Work-Stealing Hash Join

A high-performance C++17/OpenMP implementation of the hardware-conscious multi-core Radix Hash Join based on the seminal work of **Balkesen et al. (ICDE 2013)**, augmented with an **Adaptive Cost-Aware Work-Stealing Scheduler** designed for skewed database workloads.

---

## 1. Project Overview

Modern main-memory hash joins achieve high throughput through hardware-conscious radix partitioning, cache-sized hash tables, and multi-core parallelism. However, under non-uniform key distributions (Zipfian data skew), traditional partition scheduling suffers from severe bottlenecks:
1. **Static Coarse Partitioning (`radix_static`)**: Partitions are statically mapped round-robin to threads. At high skew ($z \ge 1.0$), heavy partitions concentrate up to 90% of all tuples, creating severe stragglers ($\lambda = 7.71$ on 8 threads) where idle cores stall at the OpenMP barrier.
2. **Fine-Grained Dynamic Scheduling (`paper_fine_grained`)**: As proposed in Section VI-E of Balkesen et al. (ICDE 2013), oversized partitions are diced into fixed-size chunks (256 tuples) and queued into a central work pool. Under extreme skew, this explodes the task count to **15,578 tasks**, causing massive atomic lock contention that degrades the probe phase.

### Proposed Novelty: Cost-Aware Work-Stealing
This project introduces a **Cost-Aware Work-Stealing Scheduler (`novelty_cost_gated_steal`)**:
- **Analytical Cost Model**: Estimates partition execution cost $C_i = \alpha \cdot |R_i| + \beta \cdot |S_i|$ using empirical cycle-calibrated coefficients.
- **Cost-Benefit Gated Task Bounding**: Slices only partitions where $C_i > C_{\text{avg}} + \theta$, bounding the task count to **~1,200 tasks** (a 12× reduction in task metadata overhead).
- **Private Deques & Threshold-Gated Stealing**: Each worker executes locally from a lock-free private deque. Idle workers steal from the victim's tail only when the estimated task payoff exceeds migration overhead $\tau_{\text{steal}} = t_{\text{CAS}} + t_{\text{migration}} + k \cdot t_{\text{probe}}$.

---

## 2. Key Experimental Findings (8 Threads, Full Skew Spectrum)

Extensive benchmarking on an 8-thread SMT architecture across 7 Zipfian skew factors ($z \in [0.0, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75]$) with 3 independent seeds and 3 repeats per configuration confirms:

> **Decisive Dominance Region ($z \ge 1.00$):**  
> Past $z = 1.00$, the proposed novelty **decisively outperforms both the Static Coarse baseline and Balkesen's Fine-Grained Dynamic scheduler** across all skew points, achieving up to **+49.5% faster execution time (nearly 2× speedup)** over Static and **+23.3% faster execution time** over Fine-Grained Dynamic.

### 8-Thread Quantitative Summary ($|R|=250\text{k}, |S|=4\text{M}$)

| Skew ($z$) | Scheduler | E2E Latency (ms) | Throughput (M/s) | Probe Time (ms) | Tasks Created | Imbalance $\lambda$ | Gain vs Static | Gain vs Dynamic |
|:---|:---|---:|---:|---:|---:|---:|---:|---:|
| **0.00** | Static Coarse | 30.48 | 139.43 | 9.92 | 1,024 | 1.00 | — | — |
| | Fine-Grained Dynamic | 32.07 | 132.53 | 11.08 | 1,024 | 1.07 | -5.2% | — |
| | **Proposed Novelty** | **25.29** | **168.07** | **8.09** | **1,024** | **1.00** | **+17.0%** | **+21.1%** |
| **0.50** | Static Coarse | 33.12 | 128.33 | 9.57 | 1,024 | 1.05 | — | — |
| | Fine-Grained Dynamic | 30.82 | 137.91 | 9.53 | 1,024 | 1.08 | +6.9% | — |
| | **Proposed Novelty** | **36.78** | **115.54** | **10.59** | **1,024** | **1.06** | -11.1% | -19.3% |
| **0.75** | Static Coarse | 33.12 | 128.31 | 10.15 | 1,024 | 1.40 | — | — |
| | Fine-Grained Dynamic | 30.00 | 141.67 | 8.84 | 1,041 | 1.07 | +9.4% | — |
| | **Proposed Novelty** | **30.54** | **139.14** | **9.11** | **1,032** | **1.11** | **+7.8%** | -1.8% |
| **1.00** *(Dominance Onset)* | Static Coarse | 27.05 | 157.10 | 8.42 | 1,024 | 2.05 | — | — |
| | Fine-Grained Dynamic | 25.57 | 166.21 | 8.52 | 1,437 | 1.08 | +5.5% | — |
| | **Proposed Novelty** | **23.44** | **181.33** | **6.40** | **1,072** | **1.16** | **+13.3%** | **+8.3%** |
| **1.25** | Static Coarse | 44.03 | 96.53 | 11.23 | 1,024 | 4.39 | — | — |
| | Fine-Grained Dynamic | 25.45 | 167.01 | 8.28 | 5,595 | 1.07 | +42.2% | — |
| | **Proposed Novelty** | **22.25** | **191.02** | **5.45** | **1,197** | **1.33** | **+49.5%** | **+12.6%** |
| **1.50** | Static Coarse | 31.65 | 134.28 | 9.98 | 1,024 | 6.81 | — | — |
| | Fine-Grained Dynamic | 29.99 | 141.72 | 10.37 | 12,835 | 1.07 | +5.2% | — |
| | **Proposed Novelty** | **24.83** | **171.18** | **5.27** | **1,259** | **1.48** | **+21.6%** | **+17.2%** |
| **1.75** | Static Coarse | 27.60 | 154.00 | 10.51 | 1,024 | 7.71 | — | — |
| | Fine-Grained Dynamic | 28.46 | 149.33 | 10.86 | 15,578 | 1.07 | -3.1% | — |
| | **Proposed Novelty** | **21.82** | **194.75** | **4.74** | **1,259** | **1.54** | **+20.9%** | **+23.3%** |

---

## 3. Academic Publication Figures

Standard IEEE/ACM/VLDB academic figures are located in [`results/academic_plots/`](./results/academic_plots/):
- **Figure 1 (`fig1_throughput_and_latency_8threads.png`)**: 4-panel Throughput, Cycles/Tuple, Latency, and Relative Gain showing the shaded dominance region ($z \ge 1.00$).
- **Figure 2 (`fig2_speedup_and_imbalance_8threads.png`)**: Speedup vs. Sequential Baseline and Worker Load Imbalance ($\lambda$).
- **Figure 3 (`fig3_task_granularity_and_probe_8threads.png`)**: Task count explosion (15,578 vs. 1,259 tasks) and Probe Phase Latency.
- **Figure 4 (`fig4_4threads_vs_8threads_comparison.png`)**: Multi-core scaling comparison (4 threads vs. 8 threads).
- **Figure 5 (`fig5_8thread_confirmation_bar.png`)**: Hatched confirmatory bar chart with standard deviation error bars at $z=1.75$.
- **Figure 6 (`fig6_8thread_worker_distribution.png`)**: Worker tuple load distribution comparing Static stragglers against Novelty load balance.

---

## 4. Build and Testing Instructions

### Prerequisites
- Modern C++17 compiler (GCC 9+ or Clang 10+ with OpenMP support)
- Python 3.8+ with `matplotlib` and `numpy` (for benchmark harness and plotting)

### Compilation
Build the optimized executable using strict warnings and OpenMP:
```powershell
g++ -O3 -std=c++17 -Wall -Wextra -Wpedantic -Werror -fopenmp src\main.cpp -o hashjoin.exe
```

### Self-Test & Correctness Suite
Verify execution correctness across all corner cases (empty tables, duplicates, extreme skew, 1/2/4/8 threads, concurrent joins):
```powershell
.\hashjoin.exe --self-test
```

### Run a Single Benchmark
```powershell
.\hashjoin.exe --benchmark --r-size 250000 --s-size 4000000 --skew 1.75 --threads 8 --repeats 3
```

---

## 5. Experiment Reproduction

To rerun the full skew benchmarks and regenerate the publication plots:

```powershell
# 1. Run the 8-thread full skew benchmark (z in 0.0, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75)
python scripts\run_8thread_grid.py

# 2. Run the 4-thread full skew benchmark
python scripts\run_full_skew_benchmark.py

# 3. Generate all academic publication figures
python scripts\generate_academic_plots.py
```

---

## 6. Repository Structure

```text
├── src/
│   └── main.cpp                  # Complete C++17 Radix Hash Join engine & all schedulers
├── scripts/
│   ├── run_8thread_grid.py       # 8-Thread benchmark harness across 7-skew spectrum
│   ├── run_full_skew_benchmark.py# 4-Thread benchmark harness across 7-skew spectrum
│   ├── generate_academic_plots.py# Publication-grade academic plot generator
│   ├── create_three_scheduler_comparison.py # Statistical report generator
│   ├── analyze_experiments.py    # Experiment analysis, bootstrap CIs, ANOVA
│   └── run_validation.ps1        # Fast correctness validation runner
├── results/
│   ├── academic_plots/           # Generated IEEE/ACM publication figures
│   ├── grid_8threads/            # 8-Thread full skew benchmark raw CSVs and analysis
│   ├── full_skew_grid/           # 4-Thread full skew benchmark raw CSVs and analysis
│   ├── adaptive_linear_cost_final_grid/ # Multi-workload 4-thread grid dataset
│   ├── adaptive_linear_cost_final_z175/ # Confirmatory 8-seed large skew dataset
│   └── consolidated_results_and_plots/  # Consolidated datasets and historical archives
├── tests/
│   └── smoke.ps1                 # Smoke test suite
├── Makefile                      # Standard build automation
├── FINAL_REPORT.md               # Exhaustive academic report & technical thesis
├── ARTIFACT_MANIFEST.md          # Detailed manifest of all source artifacts
└── README.md                     # This file
```

---

## 7. Reference

- **C. Balkesen, J. Teubner, G. Alonso, and M. Tamer Özsu**, *“Main-Memory Hash Joins on Multi-Core CPUs: Tuning to the Underlying Hardware,”* IEEE International Conference on Data Engineering (**ICDE 2013**), [DOI: 10.1109/ICDE.2013.6544839](https://doi.org/10.1109/ICDE.2013.6544839).
