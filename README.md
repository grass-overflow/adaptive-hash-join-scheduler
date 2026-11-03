# Adaptive Cost-Aware Work-Stealing Hash Join

A C++17 and OpenMP implementation of a parallel radix hash join based on Balkesen et al. (ICDE 2013). The project implements and compares three scheduling strategies under different data distributions:

- Static coarse-grained partition scheduling
- Fine-grained dynamic scheduling
- Cost-aware work-stealing scheduling

The proposed scheduler estimates partition execution costs, selectively divides large partitions into smaller tasks, and uses per-thread deques to distribute work.

---

## 1. Problem Statement

Radix hash joins divide relations into smaller partitions before building and probing hash tables. This improves cache locality and allows multiple threads to process partitions in parallel.

However, non-uniform key distributions can produce partitions of significantly different sizes. This creates load imbalance and affects overall execution time.

This project studies two scheduling approaches and implements a cost-aware alternative.

### Static Coarse Partitioning (`radix_static`)

- Partitions are assigned to threads in a round-robin manner.
- Each thread processes its assigned partitions.
- Under skewed distributions, some partitions become significantly larger than others.
- Threads assigned smaller partitions finish early and wait at the OpenMP synchronization barrier.

At $z=1.75$, the measured worker imbalance ratio reaches 3.96 with 4 threads and 7.71 with 8 threads.

### Fine-Grained Dynamic Scheduling (`paper_fine_grained`)

- Large partitions are divided into fixed-size tasks of 256 rows.
- Tasks are placed in a shared queue and consumed by available threads.
- This improves load distribution but increases scheduling activity.

In the extreme-skew experiments, this strategy generates approximately 15,500 tasks. Contention around the shared queue also increases scheduling overhead, with measured queue wait time exceeding 4,000 µs.

### Proposed Approach: Cost-Aware Work-Stealing (`novelty_cost_gated_steal`)

The proposed scheduler uses estimated partition costs to determine where additional parallelism is needed.

**1. Partition cost estimation**

The estimated execution cost is:

$$
C_i = \alpha |R_i| + \beta |S_i| + H(k)
$$

where:

- $|R_i|$ is the build-side partition size.
- $|S_i|$ is the probe-side partition size.
- $\alpha$ and $\beta$ represent measured build and probe costs.
- $H(k)$ represents task creation and scheduling overhead.

**2. Selective task generation**

Partitions are subdivided only when their estimated cost exceeds the average cost by a configurable threshold:

$$
C_i > C_{\text{avg}} + \theta
$$

This avoids dividing every partition into small tasks.

In the extreme-skew experiments, the scheduler generates 1,036 tasks with 4 threads and 1,259 tasks with 8 threads, compared with approximately 15,500 tasks for fine-grained dynamic scheduling.

**3. Per-thread work queues**

Each thread maintains a private deque.

- Threads process their own tasks from the tail using LIFO ordering.
- Idle threads attempt to steal tasks from another thread's head using FIFO ordering.
- A steal is attempted only when the estimated task payoff is sufficient to justify its scheduling cost.

The stealing threshold is modelled as:

$$
\tau_{\text{steal}} =
t_{\text{CAS}} +
t_{\text{migration}} +
(k \cdot t_{\text{probe}})
$$

This accounts for synchronization cost, estimated cache-transfer cost, and the expected cost of processing the stolen work.

The implementation aims to balance task distribution while limiting scheduling overhead.

---

## 2. Benchmark Results

The experiments compare the proposed scheduler against static coarse partitioning and fine-grained dynamic scheduling.

The main benchmark uses:

- Build relation: $|R| = 250,000$
- Probe relation: $|S| = 4,000,000$
- Thread counts: 4 and 8
- Zipfian skew: $z \in [0.0, 1.75]$

### 2.1 Key Experimental Observations

| Metric | Proposed Cost-Aware | Static Coarse | Fine-Grained Dynamic |
|:---|---:|---:|---:|
| Throughput at $z=1.40$, 4T | **173.03 M/s** | 142.22 M/s | 138.22 M/s |
| Throughput at $z=1.75$, 4T | **176.06 M/s** | 138.64 M/s | 146.94 M/s |
| Throughput at $z=1.75$, 8T | **194.75 M/s** | 154.00 M/s | 149.33 M/s |
| E2E latency at $z=1.75$, 8T | **21.82 ms** | 27.60 ms | 28.46 ms |
| Probe duration at $z=1.75$, 4T | **3.66 ms** | 10.52 ms | 8.25 ms |
| Worker imbalance at $z=1.75$, 4T | **1.25** | 3.96 | 1.06 |
| Worker imbalance at $z=1.75$, 8T | **1.54** | 7.71 | 1.07 |
| Tasks at $z=1.75$, 4T | **1,036** | 1,024 | 15,498 |
| Tasks at $z=1.75$, 8T | **1,259** | 1,024 | 15,578 |
| Parallel efficiency at $z=1.40$ | **59.0%** | 46.1% | 46.2% |
| Scheduling overhead | **245 µs** | 0 µs | >4,000 µs queue wait |

The proposed scheduler performs better in the higher-skew configurations, particularly during the probe phase. At lower skew, its additional scheduling logic does not always provide a benefit.

### 2.2 Eight-Thread Benchmark

The following results were obtained using $|R|=250,000$ and $|S|=4,000,000$.

The benchmark covers seven skew values, with three independent seeds and three repetitions per configuration (63 join runs per scheduler).

| Skew $z$ | Scheduler | E2E Latency (ms) | Throughput (M/s) | Probe Time (ms) | Tasks | Imbalance $\lambda$ |
|:---:|:---|---:|---:|---:|---:|---:|
| **0.00** | Static Coarse | 30.48 | 139.43 | 9.92 | 1,024 | 1.00 |
| | Fine-Grained Dyn | 32.07 | 132.53 | 11.08 | 1,024 | 1.07 |
| | **Proposed** | **25.29** | **168.07** | **8.09** | **1,024** | **1.00** |
| **0.50** | Static Coarse | 33.12 | 128.33 | 9.57 | 1,024 | 1.05 |
| | Fine-Grained Dyn | 30.82 | 137.91 | 9.53 | 1,024 | 1.08 |
| | **Proposed** | **36.78** | **115.54** | **10.59** | **1,024** | **1.06** |
| **0.75** | Static Coarse | 33.12 | 128.31 | 10.15 | 1,024 | 1.40 |
| | Fine-Grained Dyn | 30.00 | 141.67 | 8.84 | 1,041 | 1.07 |
| | **Proposed** | **30.54** | **139.14** | **9.11** | **1,032** | **1.11** |
| **1.00** | Static Coarse | 27.05 | 157.10 | 8.42 | 1,024 | 2.05 |
| | Fine-Grained Dyn | 25.57 | 166.21 | 8.52 | 1,437 | 1.08 |
| | **Proposed** | **23.44** | **181.33** | **6.40** | **1,072** | **1.16** |
| **1.25** | Static Coarse | 44.03 | 96.53 | 11.23 | 1,024 | 4.39 |
| | Fine-Grained Dyn | 25.45 | 167.01 | 8.28 | 5,595 | 1.07 |
| | **Proposed** | **22.25** | **191.02** | **5.45** | **1,197** | **1.33** |
| **1.50** | Static Coarse | 31.65 | 134.28 | 9.98 | 1,024 | 6.81 |
| | Fine-Grained Dyn | 29.99 | 141.72 | 10.37 | 12,835 | 1.07 |
| | **Proposed** | **24.83** | **171.18** | **5.27** | **1,259** | **1.48** |
| **1.75** | Static Coarse | 27.60 | 154.00 | 10.51 | 1,024 | 7.71 |
| | Fine-Grained Dyn | 28.46 | 149.33 | 10.86 | 15,578 | 1.07 |
| | **Proposed** | **21.82** | **194.75** | **4.74** | **1,259** | **1.54** |

#### Throughput improvement over static scheduling

| Skew | Improvement |
|:---:|---:|
| 0.00 | +17.0% |
| 0.50 | -11.1% |
| 0.75 | +7.8% |
| 1.00 | +13.3% |
| 1.25 | +49.5% |
| 1.50 | +21.6% |
| 1.75 | +20.9% |

The results show that the cost-aware approach becomes more useful as partition sizes become increasingly uneven. At $z=0.5$, the additional scheduling work outweighs its benefits.

### 2.3 Four-Thread Benchmark

The following experiments use the same relation sizes and skew configurations.

| Skew $z$ | Scheduler | E2E Latency (ms) | Throughput (M/s) | Probe Time (ms) | Tasks | Imbalance $\lambda$ |
|:---:|:---|---:|---:|---:|---:|---:|
| **0.00** | Static Coarse | 33.30 | 127.63 | 10.13 | 1,024 | 1.00 |
| | Fine-Grained Dyn | 31.90 | 133.22 | 9.53 | 1,024 | 1.04 |
| | **Proposed** | **32.45** | **130.98** | **10.21** | **1,024** | **1.00** |
| **0.75** | Static Coarse | 30.24 | 140.55 | 10.25 | 1,024 | 1.39 |
| | Fine-Grained Dyn | 28.71 | 148.03 | 8.52 | 1,782 | 1.08 |
| | **Proposed** | **28.87** | **147.22** | **8.62** | **1,036** | **1.09** |
| **1.40** | Static Coarse | 29.88 | 142.22 | 9.55 | 1,024 | 3.72 |
| | Fine-Grained Dyn | 30.75 | 138.22 | 10.25 | 13,483 | 1.06 |
| | **Proposed** | **24.56** | **173.03** | **4.07** | **1,036** | **1.27** |
| **1.75** | Static Coarse | 30.66 | 138.64 | 10.52 | 1,024 | 3.96 |
| | Fine-Grained Dyn | 28.92 | 146.94 | 8.25 | 15,498 | 1.06 |
| | **Proposed** | **24.14** | **176.06** | **3.66** | **1,036** | **1.25** |

#### Throughput improvement over static scheduling

| Skew | Improvement |
|:---:|---:|
| 0.00 | +2.6% |
| 0.75 | +4.5% |
| 1.40 | +21.7% |
| 1.75 | +27.0% |

The four-thread results show a similar pattern. The largest improvements occur at higher skew values, where static partition assignment produces more uneven workloads.

### 2.4 Confirmatory Evaluation at Extreme Skew

An additional evaluation was conducted at $z=1.75$ using eight independent pseudorandom seeds. Each scheduler was evaluated over 56 runs. The reported values are mean latency and standard deviation.

**Large workload: $|R|=250,000$, $|S|=4,000,000$**

| Scheduler | E2E Latency |
|:---|---:|
| **Proposed Cost-Aware** | **32.18 ± 1.72 ms** |
| Fine-Grained Dynamic | 38.75 ± 1.98 ms |
| Static Coarse | 40.27 ± 2.84 ms |

The proposed scheduler had the lowest mean latency in all eight seed-level comparisons.

**Small workload: $|R|=20,000$, $|S|=320,000$**

| Scheduler | E2E Latency |
|:---|---:|
| **Proposed Cost-Aware** | **4.28 ± 0.80 ms** |
| Fine-Grained Dynamic | 4.63 ± 1.07 ms |
| Static Coarse | 4.70 ± 0.89 ms |

The difference is smaller for the small workload, where scheduling overhead represents a larger proportion of execution time.

### 2.5 Phase Breakdown at Extreme Skew

At $z=1.75$, the main benchmark records the following phase timings:

| Execution Phase | Duration |
|:---|---:|
| Two-pass radix partitioning | 18.30 ms |
| Hash table build | 1.68 ms |

These phases take approximately the same time across the three schedulers.

The main difference is observed in the probe phase:

| Scheduler | Probe Duration |
|:---|---:|
| **Proposed Cost-Aware (4T)** | **3.66 ms** |
| Fine-Grained Dynamic (4T) | 8.25 ms |
| Static Coarse (4T) | 10.52 ms |

This indicates that most of the measured improvement comes from distributing probe work more effectively.

---

## 3. Cost Model Calibration

The scheduler uses measured parameters to estimate partition processing and scheduling costs.

| Parameter | Description | Measured Value | Calibration Source |
|:---|:---|---:|:---|
| $\alpha$ | Build insertion latency | ≈ 9.25 ns/row | Build time divided by build relation size |
| $\beta$ | Probe lookup latency | ≈ 6.27 ns/row | Sampled probe lookup times |
| $H(k)$ | Task creation and enqueue overhead | ≈ 180 ns | Microbenchmark of 4,096 deque operations |
| $t_{\text{CAS}}$ | Uncontended atomic spinlock cost | ≈ 7.9–34.9 ns | Five repetitions of 4,096 lock acquisitions |
| $t_{\text{migration}}$ | Cross-core cache transfer estimate | ≈ 26.9–35.2 ns | Contended two-worker timing delta minus uncontended CAS cost |
| $\tau_{\text{steal}}$ | Stealing threshold | ≈ 39.0–70.9 ns | Calculated using the stealing cost model |
| Task budget cap | Maximum sliced task budget | 1,259 tasks | Thread count × tasks per thread × 4 |

The build and probe parameters are estimated from measured execution times. The synchronization and migration parameters are obtained from separate microbenchmarks.

The stealing threshold is calculated as:

$$
\tau_{\text{steal}} =
t_{\text{CAS}} +
t_{\text{migration}} +
(k \cdot t_{\text{probe}})
$$

These values are used by the scheduler to decide whether stealing is worthwhile.

---

## 4. Platform, Build, and Getting Started

### Target Platforms & Environment

- **Evaluated & Tested On**: Windows 11 (x86_64), using MinGW-w64 GCC (v13.x/v14.x) with OpenMP and Python 3.11.
- **Ubuntu / Linux Support**: **Yes, fully supported**. The C++ engine (`src/main.cpp`) uses standard ISO C++17 and standard OpenMP (`-fopenmp`) without any Windows-specific APIs or system headers. It compiles and runs out-of-the-box on Ubuntu (20.04, 22.04, 24.04).

### Prerequisites

- C++17 compiler (GCC 9+ or Clang 10+ with OpenMP support)
- Python 3.8+ with `pandas`, `numpy`, and `matplotlib` (for running benchmarks and plotting)

---

### Getting Started

#### On Ubuntu / Debian:

```bash
# 1. Install compiler and dependencies
sudo apt update
sudo apt install -y build-essential g++ libomp-dev python3 python3-pip
pip3 install pandas numpy matplotlib

# 2. Build executable
make
# Or compile directly:
g++ -O3 -std=c++17 -Wall -Wextra -Wpedantic -fopenmp src/main.cpp -o hashjoin

# 3. Run self-test
./hashjoin --self-test
```

#### On Windows (MinGW-w64 / MSYS2 / PowerShell):

```powershell
# 1. Compile executable
g++ -O3 -std=c++17 -Wall -Wextra -Wpedantic -fopenmp src\main.cpp -o hashjoin.exe

# 2. Run self-test
.\hashjoin.exe --self-test
```

---

### How to Test This Project

Testing is divided into three tiers:

1. **Automated Correctness & Concurrency Self-Test (`--self-test`)**:
   Runs the built-in test suite verifying:
   - Empty relations ($|R|=0, |S|=0$)
   - Single-element relations ($|R|=1, |S|=1$)
   - Duplicate key handling
   - Extreme Zipf skew handling
   - Multi-threaded OpenMP concurrency
   - Join verification against a sequential reference hash join oracle (ensures identical tuple match counts)

   ```bash
   ./hashjoin --self-test      # Linux
   .\hashjoin.exe --self-test  # Windows
   ```

2. **Automated Smoke Test Suite (`tests/smoke.ps1`)**:
   Compiles a fresh binary in a temporary directory, runs `--self-test`, executes a 4-thread grid across 4 skew values ($z \in [0.0, 0.9, 1.4, 1.75]$), and verifies that all parallel outputs match the sequential oracle across all runs.
   ```powershell
   pwsh -File tests/smoke.ps1
   ```

3. **End-to-End Live Benchmark**:
   Runs the full suite across 7 skew points ($z \in [0.0, 1.75]$) and prints comparative speedup tables:
   ```bash
   python3 scripts/run_complete_demo.py    # Linux
   python scripts\run_complete_demo.py     # Windows
   ```

---

### CLI Options

```text
Usage: hashjoin [options]

  --r-size R             Build relation rows (default: 100000)
  --s-size S             Probe relation rows (default: 1600000; 16x R)
  --key-range K          Zipf domain (default: R size)
  --partitions P         Partition count (power of 2 with even log2, e.g. 1024)
  --threads T            OpenMP thread count (default: 4)
  --chunk-size C         Fixed chunk size for paper baseline (default: 256)
  --tasks-per-thread K   Task budget multiplier for novelty (default: 32)
  --cost-samples N       Probe samples per partition (default: 16)
  --repeats R            Measured repetitions per configuration (default: 3)
  --skews z1,z2,...      Zipf skew exponents (default: 0,0.75,1.25)
  --csv PATH             Output CSV path (default: results.csv)
  --self-test            Run built-in validation tests
```

Manual execution example:

```bash
# Linux
./hashjoin --r-size 250000 --s-size 4000000 --threads 8 --skews 0,0.5,0.75,1.0,1.25,1.5,1.75 --repeats 3

# Windows
.\hashjoin.exe --r-size 250000 --s-size 4000000 --threads 8 --skews 0,0.5,0.75,1.0,1.25,1.5,1.75 --repeats 3
```

---

## 5. Benchmark and Analysis Scripts

The `scripts/` directory contains utilities for running benchmarks, analysing results, and generating figures.

### Main demonstration

```bash
python scripts/run_complete_demo.py
```

Runs the self-tests and the multi-core benchmark across the configured skew values. It also prints comparative performance tables.

### Eight-thread benchmark

```bash
python scripts/run_8threads_all_skews.py
```

Runs the eight-thread benchmark using $|R|=250,000$ and $|S|=4,000,000$ across seven skew values.

### Generate benchmark summary

```bash
python scripts/generate_complete_summary.py
```

Prints execution phase timings, worker imbalance, and scheduling statistics.

### Cost model estimation

```bash
python scripts/offline_linear_regression_cost_model.py
```

Uses Ordinary Least Squares (OLS) regression to estimate the build and probe cost parameters from partition measurements.

### Generate publication figures

```bash
python scripts/plots/generate_academic_plots.py
```

Generates the benchmark figures in `results/plots/`.

---

## 6. Generated Figures

The benchmark scripts generate the following figures in `results/plots/`:

| Figure | File | Description |
|:---|:---|:---|
| Figure 1 | `fig1_throughput_and_latency_8threads.png` | Throughput, cycles per tuple, latency, and relative performance |
| Figure 2 | `fig2_speedup_and_imbalance_8threads.png` | Speedup and worker load imbalance |
| Figure 3 | `fig3_task_granularity_and_probe_8threads.png` | Task counts and probe phase duration |
| Figure 4 | `fig4_4threads_vs_8threads_comparison.png` | Comparison between four-thread and eight-thread execution |
| Figure 5 | `fig5_8thread_confirmation_bar.png` | Confirmatory evaluation with standard deviation error bars |
| Figure 6 | `fig6_8thread_worker_distribution.png` | Per-thread work distribution for static and proposed scheduling |

---

## 7. Repository Structure

```text
├── src/
│   └── main.cpp                                # Core C++17 Radix Hash Join engine, cost model, & schedulers
│
├── scripts/
│   ├── Benchmark & Evaluation Runners:
│   │   ├── run_complete_demo.py                # Master end-to-end benchmark and validation suite
│   │   ├── run_8threads_all_skews.py           # Dedicated 8-thread benchmark across all 7 skews
│   │   ├── generate_complete_summary.py        # Extracts phase latency breakdowns & imbalance metrics
│   │   ├── explain_novelty_performance.py      # Quantitative comparison table generator
│   │   └── offline_linear_regression_cost_model.py # OLS regression script estimating alpha and beta
│   │
│   ├── Microbenchmarks & Hardware Calibration (C++):
│   │   ├── full_scheduler_benchmark.cpp        # Standalone multi-scheduler timing harness
│   │   ├── measure_hk.cpp                      # Microbenchmark measuring task enqueue cost H(k)
│   │   ├── steal_benchmark_windows.cpp         # Measures atomic CAS and cross-core migration latency
│   │   ├── steal_cost.cpp                      # Stealing threshold calibration microbenchmark
│   │   └── task_overhead.cpp                   # Deque task creation overhead microbenchmark
│   │
│   └── plots/                                  # Plotting and grid evaluation scripts
│       ├── generate_academic_plots.py          # Publication-ready figure generator (Figures 1 to 6)
│       ├── create_three_scheduler_comparison.py# Generates 3-way scheduler comparative plots
│       ├── analyze_experiments.py              # Analyzes raw benchmark CSVs into aggregated metrics
│       ├── analyze_validation.py               # Statistical multi-seed variance & confidence intervals
│       ├── run_8thread_grid.py                 # Multi-core 8-thread parameter sweep runner
│       ├── run_full_skew_benchmark.py          # Full skew spectrum automation script
│       ├── run_validation.ps1                  # PowerShell runner for validation suite
│       └── run_validation.sh                   # Bash runner for validation suite
│
├── results/
│   ├── plots/                                  # Generated publication figures (Figures 1 through 6)
│   ├── grid_8threads/                          # 8-thread raw and aggregated benchmark measurements
│   ├── consolidated/                           # Confirmatory 8-seed benchmark datasets (z=1.75)
│   ├── live_run_summary.csv                    # Latest benchmark run summary
│   └── run_8threads_all_skews.csv              # Full spectrum benchmark results
│
├── tests/
│   └── smoke.ps1                               # Automated end-to-end PowerShell smoke test
│
├── Makefile                                    # Compilation targets (all, smoke, confirm, clean)
└── README.md                                   # Project documentation
```

---

## 8. Reference

C. Balkesen, J. Teubner, G. Alonso, and M. Tamer Özsu, "Main-Memory Hash Joins on Multi-Core CPUs: Tuning to the Underlying Hardware," IEEE International Conference on Data Engineering (ICDE), 2013.

DOI: [10.1109/ICDE.2013.6544839](https://doi.org/10.1109/ICDE.2013.6544839)

---

## 9. Summary

This project implements and evaluates three scheduling strategies for parallel radix hash joins.

The proposed cost-aware scheduler uses partition cost estimates, selective task generation, and per-thread work-stealing queues.

The experiments show that:

- Static scheduling can suffer from load imbalance under highly skewed workloads.
- Fine-grained scheduling improves load distribution but can generate a large number of tasks.
- Cost-aware scheduling reduces task generation compared with fixed-size slicing.
- The proposed approach improves probe performance in the higher-skew configurations evaluated.
- At lower skew, the additional scheduling overhead can offset the benefits.

The implementation compares these approaches using execution time, throughput, task count, worker imbalance, and scheduling overhead.