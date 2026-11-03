# Adaptive Cost-Aware Work-Stealing Hash Join

A C++17/OpenMP implementation of the multi-core Radix Hash Join based on **Balkesen et al. (ICDE 2013)**, augmented with an **Adaptive Cost-Aware Work-Stealing Scheduler** for skewed database workloads.

---

## 1. Problem & Architecture

In main-memory hash joins under Zipfian data skew, existing partition schedulers face severe hardware bottlenecks:

1. **Static Coarse Partitioning (`radix_static`)**:
   - Round-robin static assignment of partitions to worker threads.
   - **Problem**: At high skew ($z \ge 1.0$), tuples concentrate in a few hot partitions. One core processes the bulk of the workload while others finish in milliseconds and wait idle at barriers (worker imbalance $\lambda$ reaches up to **7.71** on 8 threads, **3.96** on 4 threads).

2. **Fine-Grained Dynamic Scheduling (`paper_fine_grained` - Balkesen et al., ICDE 2013)**:
   - Partitions exceeding average size are split into fixed 256-row chunks and pushed into a shared task queue.
   - **Problem**: At high skew ($z \ge 1.4$), this triggers a task count explosion up to **15,498–15,578 tasks**. Atomic lock contention on the central queue degrades cache locality and balloons probe duration (> 4,000 µs queue lock wait).

### Cost-Aware Bounded Work-Stealing (`novelty_cost_gated_steal`)
* **Analytical Cost Model**: Estimates execution cost per partition:
  $$C_i = \alpha \cdot |R_i| + \beta \cdot |S_i| + H(k)$$
* **Cost-Benefit Gated Task Bounding**: Slices only partitions where $C_i > C_{\text{avg}} + \theta$, bounding total tasks to **~1,036–1,259** (~12x to 15x reduction vs. Balkesen dynamic queue).
* **Private Deques & Threshold-Gated Stealing**: Workers pop locally from private deques (LIFO tail). Idle threads steal from victim heads (FIFO) only when the estimated task payoff exceeds migration overhead:
  $$\tau_{\text{steal}} = t_{\text{CAS}} + t_{\text{migration}} + (k \cdot t_{\text{probe}})$$
* **Negligible Scheduling Overhead**: Total cost model and dispatch overhead is **< 250 µs** (< 1.0% of total runtime).

---

## 2. Experimental Results Summary

Evaluation on $|R| = 250\text{k}, |S| = 4\text{M}$ across Zipfian skews $z \in [0.0, 1.75]$.

### Performance Highlights (from Confirmatory Benchmarks)

| Metric | Proposed Cost-Aware Novelty | Static Coarse Baseline | Fine-Grained Dynamic (Balkesen et al.) | Performance Difference |
|:---|:---:|:---:|:---:|:---|
| **Throughput ($z = 1.40$)** | **173.03 M/s** | 142.22 M/s | 138.22 M/s | **+21.7% to +25.2%** higher |
| **Throughput ($z = 1.75$)** | **176.06 M/s** | 138.64 M/s | 146.94 M/s | **+19.8% to +27.0%** higher |
| **Confirmatory E2E ($z = 1.75$, 8 seeds)** | **32.18 ± 1.72 ms** | 40.27 ± 2.84 ms | 38.75 ± 1.98 ms | **+20.1% vs Static, +16.4% vs Dynamic** (100% win rate across 8 seeds) |
| **Probe Duration ($z = 1.75$)** | **3.66 ms** | 10.52 ms | 8.25 ms | **2.3× to 2.9× faster** probe phase |
| **Worker Imbalance $\lambda$ ($z = 1.75$)** | **1.25** | 3.96 | 1.06 | Prevents stragglers without queue thrashing |
| **Dispatched Task Count ($z = 1.75$)** | **1,036 tasks** | 1,024 tasks | 15,498 tasks | **15× fewer tasks**, eliminates lock contention |
| **Parallel Efficiency ($z = 1.40$)** | **59.0%** | 46.1% | 46.2% | **+12.9 percentage points** higher |
| **Scheduling Overhead** | **245 µs** | 0 µs | > 4,000 µs (lock wait) | **< 1.0%** total runtime |

### 8-Thread Multi-Core Skew Spectrum ($|R|=250\text{k}, |S|=4\text{M}$)

| Skew ($z$) | Scheduler | E2E Latency (ms) | Throughput (M/s) | Probe Time (ms) | Tasks | Imbalance $\lambda$ | Gain vs Static | Gain vs Dynamic |
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **0.00** | Static Coarse | 30.48 | 139.43 | 9.92 | 1,024 | 1.00 | — | — |
| | Fine-Grained Dyn | 32.07 | 132.53 | 11.08 | 1,024 | 1.07 | -5.2% | — |
| | **Proposed Novelty** | **25.29** | **168.07** | **8.09** | **1,024** | **1.00** | **+17.0%** | **+21.1%** |
| **0.50** | Static Coarse | 33.12 | 128.33 | 9.57 | 1,024 | 1.05 | — | — |
| | Fine-Grained Dyn | 30.82 | 137.91 | 9.53 | 1,024 | 1.08 | +6.9% | — |
| | **Proposed Novelty** | 36.78 | 115.54 | 10.59 | 1,024 | 1.06 | -11.1% | -19.3% |
| **0.75** | Static Coarse | 33.12 | 128.31 | 10.15 | 1,024 | 1.40 | — | — |
| | Fine-Grained Dyn | 30.00 | 141.67 | 8.84 | 1,041 | 1.07 | +9.4% | — |
| | **Proposed Novelty** | **30.54** | **139.14** | **9.11** | **1,032** | **1.11** | **+7.8%** | **-1.8%** |
| **1.00** *(Dominance Onset)* | Static Coarse | 27.05 | 157.10 | 8.42 | 1,024 | 2.05 | — | — |
| | Fine-Grained Dyn | 25.57 | 166.21 | 8.52 | 1,437 | 1.08 | +5.5% | — |
| | **Proposed Novelty** | **23.44** | **181.33** | **6.40** | **1,072** | **1.16** | **+13.3%** | **+8.3%** |
| **1.25** | Static Coarse | 44.03 | 96.53 | 11.23 | 1,024 | 4.39 | — | — |
| | Fine-Grained Dyn | 25.45 | 167.01 | 8.28 | 5,595 | 1.07 | +42.2% | — |
| | **Proposed Novelty** | **22.25** | **191.02** | **5.45** | **1,197** | **1.33** | **+49.5%** | **+12.6%** |
| **1.50** | Static Coarse | 31.65 | 134.28 | 9.98 | 1,024 | 6.81 | — | — |
| | Fine-Grained Dyn | 29.99 | 141.72 | 10.37 | 12,835 | 1.07 | +5.2% | — |
| | **Proposed Novelty** | **24.83** | **171.18** | **5.27** | **1,259** | **1.48** | **+21.6%** | **+17.2%** |
| **1.75** | Static Coarse | 27.60 | 154.00 | 10.51 | 1,024 | 7.71 | — | — |
| | Fine-Grained Dyn | 28.46 | 149.33 | 10.86 | 15,578 | 1.07 | -3.1% | — |
| | **Proposed Novelty** | **21.82** | **194.75** | **4.74** | **1,259** | **1.54** | **+20.9%** | **+23.3%** |

---

## 3. Calibrated Model Parameters

| Parameter | Meaning | Measured Value | Calibration Source |
|:---|:---|:---:|:---|
| **$\alpha$ (Build Row Cost)** | CPU time per build tuple insert | **$\approx 9.25\text{ ns/row}$** | Direct measurement ($T_{\text{build}} / \|R\|$) |
| **$\beta$ (Probe Row Cost)** | CPU time per probe lookup | **$\approx 6.27\text{ ns/row}$** | Partition probe latency sampling |
| **$H(k)$ (Task Cost)** | Fixed queue metadata & enqueue cost | **$\approx 180\text{ ns}$** | 4,096 push/pop microbenchmark |
| **$t_{\text{CAS}}$ (Lock Cost)** | Uncontended atomic spinlock acquisition | **$7.9 - 34.9\text{ ns}$** | 4,096 `SpinLockGuard` operations |
| **$t_{\text{migration}}$ (Transfer Cost)** | Cross-core cache transfer delta | **$26.9 - 35.2\text{ ns}$** | Two-worker contention benchmark |
| **$\tau_{\text{steal}}$ (Steal Gate)** | Minimum threshold to justify steal | **$39.0 - 70.9\text{ ns}$** | $\tau_{\text{steal}} = t_{\text{CAS}} + t_{\text{migration}} + (k \cdot t_{\text{probe}})$ |

---

## 4. Build & Quickstart

### Requirements
* C++17 compiler (`g++` 9+ or `clang++` 10+) with OpenMP
* Python 3.8+ (`pandas`, `numpy`, `matplotlib` for plot scripts)

### Compile
```powershell
g++ -O3 -std=c++17 -Wall -Wextra -Wpedantic -fopenmp src\main.cpp -o hashjoin.exe
```

### Self-Test
Runs edge-case verification (empty tables, skew, duplicate keys, concurrency, oracle validation):
```powershell
.\hashjoin.exe --self-test
```

---

## 5. Scripts

All scripts are non-interactive and ready to run:

* **End-to-End Demo Across Skews**:
  ```powershell
  python scripts\run_complete_demo.py
  ```
* **8-Thread Benchmark (7 Skews)**:
  ```powershell
  python scripts\run_8threads_all_skews.py
  ```
* **Technical Summary & Breakdown**:
  ```powershell
  python scripts\generate_complete_summary.py
  ```
* **Offline OLS Cost Model Regression**:
  ```powershell
  python scripts\offline_linear_regression_cost_model.py
  ```

---

## 6. Generated Academic Figures

Plots are stored in [`results/academic_plots/`](./results/academic_plots/):
* **Figure 1**: Multi-threaded throughput, cycles/tuple, latency, and relative gains across $z \in [0.0, 1.75]$.
* **Figure 2**: Speedup vs. sequential baseline and worker load imbalance ($\lambda$).
* **Figure 3**: Dispatched task explosion (15,498 vs 1,036 tasks) and probe phase duration.
* **Figure 4**: 4-thread vs. 8-thread scaling comparison.
* **Figure 5**: Confirmatory error bar chart at $z = 1.75$ across multi-seed runs.
* **Figure 6**: Per-worker tuple distribution (Static straggler core vs. Adaptive balance).

---

## 7. Repository Structure

```text
├── src/
│   └── main.cpp                  # C++17 Radix Hash Join, cost model & schedulers
├── scripts/
│   ├── run_complete_demo.py      # Non-interactive validation & demo
│   ├── run_8threads_all_skews.py # 8-thread benchmark across 7 skews
│   ├── generate_complete_summary.py # Prints technical metrics & breakdown
│   ├── offline_linear_regression_cost_model.py # OLS regression for alpha, beta
│   └── generate_academic_plots.py# Plot generation script
├── results/
│   ├── academic_plots/           # Output publication figures (Fig 1–6)
│   ├── grid_8threads/            # 8-thread benchmark CSVs
│   └── consolidated/             # Multi-seed confirmatory datasets
├── FINAL_REPORT.md               # Technical report & thesis document
├── PAPER_REPRODUCTION_AND_NOVELTY.md # Balkesen ICDE 2013 comparison boundary
├── presentation_results_summary.md # Viva presentation reference
└── README.md
```

---

## 8. Reference

* **C. Balkesen, J. Teubner, G. Alonso, and M. Tamer Özsu**, *“Main-Memory Hash Joins on Multi-Core CPUs: Tuning to the Underlying Hardware,”* IEEE International Conference on Data Engineering (**ICDE 2013**), [DOI: 10.1109/ICDE.2013.6544839](https://doi.org/10.1109/ICDE.2013.6544839).
