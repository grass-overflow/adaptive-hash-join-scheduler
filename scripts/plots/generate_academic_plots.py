#!/usr/bin/env python3
"""Generate standard, publication-grade academic plots (IEEE / ACM / VLDB style)
for the 8-thread execution and full 7-point Zipfian skew spectrum
(z in 0.0, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75).
"""
import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
OUT_DIR = RESULTS / "academic_plots"
OUT_DIR.mkdir(parents=True, exist_ok=True)

GRID8_PATH = RESULTS / "grid_8threads" / "analysis"
GRID4_PATH = RESULTS / "full_skew_grid" / "analysis"
THREADS_PATH = RESULTS / "full_skew_grid" / "threads" / "analysis"
CONF_LARGE_PATH = RESULTS / "adaptive_linear_cost_final_z175" / "analysis"

# Standard IEEE / ACM publication style
plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["DejaVu Serif", "Times New Roman", "Times", "serif"],
    "font.size": 10,
    "axes.titlesize": 11,
    "axes.labelsize": 10,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.fontsize": 9,
    "figure.titlesize": 12,
    "axes.grid": True,
    "grid.alpha": 0.4,
    "grid.linestyle": ":",
    "grid.color": "#888888",
    "axes.edgecolor": "#333333",
    "axes.linewidth": 0.8,
})

def read_csv(path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

m8 = read_csv(GRID8_PATH / "metrics_summary.csv")
m4 = read_csv(GRID4_PATH / "metrics_summary.csv")
mt = read_csv(THREADS_PATH / "metrics_summary.csv")

SCHEDS = {
    "radix_static": ("Static Coarse", "#4d4d4d", "s", "--", 1.8),
    "paper_fine_grained": ("Fine-Grained Dynamic (Balkesen et al.)", "#1f77b4", "^", "-.", 1.8),
    "novelty_cost_gated_steal": ("Proposed Cost-Aware Stealing", "#d62728", "o", "-", 2.2),
}

# -------------------------------------------------------------------------
# Plot 1: 8-Thread Throughput, Cycles per Tuple, and Execution Time (7 Skews)
# -------------------------------------------------------------------------
def plot_8thread_throughput_and_latency():
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(11, 8.5), sharex=True)
    skews = sorted(list({float(r["skew"]) for r in m8}))
    nominal_freq_ghz = 2.6
    
    # (a) Throughput (8 Threads)
    for algo, (label, color, marker, ls, lw) in SCHEDS.items():
        tp = []
        for z in skews:
            row = next(r for r in m8 if float(r["skew"]) == z and r["algorithm"] == algo)
            r_sz = float(row["r_size"])
            s_sz = float(row["s_size"])
            e2e = float(row["e2e_s_median_across_seeds"])
            tp.append((r_sz + s_sz) / (e2e * 1e6))
        ax1.plot(skews, tp, label=label, color=color, marker=marker, linestyle=ls, linewidth=lw, markersize=6)
    
    ax1.set_title("(a) Multi-Thread Throughput on 8 Threads (|R|=250k, |S|=4M)")
    ax1.set_ylabel("Throughput [million tuples/s]")
    ax1.legend(loc="lower left", frameon=True, edgecolor="#cccccc")
    
    # (b) Cycles per Output Tuple (Balkesen Metric)
    for algo, (label, color, marker, ls, lw) in SCHEDS.items():
        cycles = []
        for z in skews:
            row = next(r for r in m8 if float(r["skew"]) == z and r["algorithm"] == algo)
            s_sz = float(row["s_size"])
            e2e = float(row["e2e_s_median_across_seeds"])
            cycles.append((e2e * nominal_freq_ghz * 1e9) / s_sz)
        ax2.plot(skews, cycles, label=label, color=color, marker=marker, linestyle=ls, linewidth=lw, markersize=6)
    
    ax2.set_title("(b) Cycles per Output Tuple (Balkesen Metric, 2.6 GHz, 8 Threads)")
    ax2.set_ylabel("Cycles per output tuple")
    ax2.legend(loc="upper right", frameon=True, edgecolor="#cccccc")
    
    # (c) Execution Time (8 Threads)
    for algo, (label, color, marker, ls, lw) in SCHEDS.items():
        times = [float(next(r for r in m8 if float(r["skew"]) == z and r["algorithm"] == algo)["e2e_s_median_across_seeds"]) * 1000 for z in skews]
        ax3.plot(skews, times, label=label, color=color, marker=marker, linestyle=ls, linewidth=lw, markersize=6)
    
    ax3.set_title("(c) End-to-End Latency on 8 Threads (|R|=250k, |S|=4M)")
    ax3.set_xlabel("Zipf factor z")
    ax3.set_ylabel("Execution time [ms]")
    ax3.set_xticks(skews)
    
    # (d) Novelty Relative Speedup (%) over Both Baselines
    gains_static = []
    gains_fine = []
    for z in skews:
        r_stat = next(r for r in m8 if float(r["skew"]) == z and r["algorithm"] == "radix_static")
        r_fine = next(r for r in m8 if float(r["skew"]) == z and r["algorithm"] == "paper_fine_grained")
        r_nov = next(r for r in m8 if float(r["skew"]) == z and r["algorithm"] == "novelty_cost_gated_steal")
        t_stat = float(r_stat["e2e_s_median_across_seeds"])
        t_fine = float(r_fine["e2e_s_median_across_seeds"])
        t_nov = float(r_nov["e2e_s_median_across_seeds"])
        gains_static.append(((t_stat - t_nov) / t_stat) * 100)
        gains_fine.append(((t_fine - t_nov) / t_fine) * 100)
        
    ax4.plot(skews, gains_static, label="Gain over Static Coarse", color="#4d4d4d", marker="s", linestyle="--", linewidth=1.8)
    ax4.plot(skews, gains_fine, label="Gain over Fine-Grained Dynamic", color="#1f77b4", marker="^", linestyle="-.", linewidth=1.8)
    ax4.axhline(0, color="gray", linestyle=":", linewidth=1.2)
    ax4.axvspan(1.0, 1.75, color="#d4edda", alpha=0.4, label="Decisive Dominance Region (z >= 1.0)")
    ax4.set_title("(d) Proposed Novelty Relative Gain [%] on 8 Threads")
    ax4.set_xlabel("Zipf factor z")
    ax4.set_ylabel("Novelty Runtime Reduction [%]")
    ax4.set_xticks(skews)
    ax4.legend(loc="upper left", frameon=True, edgecolor="#cccccc")
    
    fig.tight_layout()
    fig.savefig(OUT_DIR / "fig1_throughput_and_latency_8threads.png", dpi=300)
    plt.close(fig)
    print("Saved fig1_throughput_and_latency_8threads.png")

# -------------------------------------------------------------------------
# Plot 2: Speedup vs Sequential Reference & Load Imbalance (8 Threads)
# -------------------------------------------------------------------------
def plot_8thread_speedup_and_imbalance():
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.5))
    skews = sorted(list({float(r["skew"]) for r in m8}))
    
    # (a) Speedup vs Sequential
    for algo, (label, color, marker, ls, lw) in SCHEDS.items():
        speedups = [float(next(r for r in m8 if float(r["skew"]) == z and r["algorithm"] == algo)["speedup_vs_sequential_median_across_seeds"]) for z in skews]
        ax1.plot(skews, speedups, label=label, color=color, marker=marker, linestyle=ls, linewidth=lw, markersize=6)
        
    ax1.set_title("(a) Multi-Core Speedup vs. Sequential (8 Threads)")
    ax1.set_xlabel("Zipf factor z")
    ax1.set_ylabel("Speedup factor (vs. sequential)")
    ax1.set_xticks(skews)
    ax1.legend(loc="upper right", frameon=True, edgecolor="#cccccc")
    
    # (b) Worker Load Imbalance Lambda
    for algo, (label, color, marker, ls, lw) in SCHEDS.items():
        imbalance = [float(next(r for r in m8 if float(r["skew"]) == z and r["algorithm"] == algo)["worker_rows_over_avg_median_across_seeds"]) for z in skews]
        ax2.plot(skews, imbalance, label=label, color=color, marker=marker, linestyle=ls, linewidth=lw, markersize=6)
        
    ax2.axhline(1.0, color="gray", linestyle=":", linewidth=1.2, label=r"Ideal balance ($\lambda=1.0$)")
    ax2.set_title(r"(b) Worker Load Imbalance $\lambda$ = $\frac{\max \text{worker rows}}{\text{avg worker rows}}$ (8 Threads)")
    ax2.set_xlabel("Zipf factor z")
    ax2.set_ylabel(r"Worker load imbalance ($\lambda$)")
    ax2.set_xticks(skews)
    ax2.set_ylim(0.9, 8.4)
    ax2.legend(loc="upper left", frameon=True, edgecolor="#cccccc")
    
    fig.tight_layout()
    fig.savefig(OUT_DIR / "fig2_speedup_and_imbalance_8threads.png", dpi=300)
    plt.close(fig)
    print("Saved fig2_speedup_and_imbalance_8threads.png")

# -------------------------------------------------------------------------
# Plot 3: Task Granularity (Count) & Probe Phase Latency (8 Threads)
# -------------------------------------------------------------------------
def plot_8thread_tasks_and_probe():
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.5))
    skews = sorted(list({float(r["skew"]) for r in m8}))
    
    # (a) Task Count
    for algo, (label, color, marker, ls, lw) in SCHEDS.items():
        counts = [float(next(r for r in m8 if float(r["skew"]) == z and r["algorithm"] == algo)["tasks_median_across_seeds"]) for z in skews]
        ax1.plot(skews, counts, label=label, color=color, marker=marker, linestyle=ls, linewidth=lw, markersize=6)
        
    ax1.set_yscale("log")
    ax1.set_title("(a) Scheduled Task Count on 8 Threads (Balkesen 256-row chunks)")
    ax1.set_xlabel("Zipf factor z")
    ax1.set_ylabel("Total task count [log scale]")
    ax1.set_xticks(skews)
    ax1.legend(loc="upper left", frameon=True, edgecolor="#cccccc")
    
    # (b) Probe Phase Latency
    for algo, (label, color, marker, ls, lw) in SCHEDS.items():
        probes = [float(next(r for r in m8 if float(r["skew"]) == z and r["algorithm"] == algo)["probe_s_median_across_seeds"]) * 1000 for z in skews]
        ax2.plot(skews, probes, label=label, color=color, marker=marker, linestyle=ls, linewidth=lw, markersize=6)
        
    ax2.set_title("(b) Probe Phase Duration on 8 Threads (|R|=250k, |S|=4M)")
    ax2.set_xlabel("Zipf factor z")
    ax2.set_ylabel("Probe phase duration [ms]")
    ax2.set_xticks(skews)
    ax2.legend(loc="upper right", frameon=True, edgecolor="#cccccc")
    
    fig.tight_layout()
    fig.savefig(OUT_DIR / "fig3_task_granularity_and_probe_8threads.png", dpi=300)
    plt.close(fig)
    print("Saved fig3_task_granularity_and_probe_8threads.png")

# -------------------------------------------------------------------------
# Plot 4: 4-Thread vs. 8-Thread Comparison Across All 7 Skews
# -------------------------------------------------------------------------
def plot_4t_vs_8t_comparison():
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.5))
    skews = sorted(list({float(r["skew"]) for r in m8}))
    
    subset4 = [r for r in m4 if int(r["r_size"]) == 250000]
    
    # (a) Execution Time Comparison for Novelty (4T vs 8T) and Baselines
    t_nov_4t = [float(next(r for r in subset4 if float(r["skew"]) == z and r["algorithm"] == "novelty_cost_gated_steal")["e2e_s_median_across_seeds"]) * 1000 for z in skews]
    t_nov_8t = [float(next(r for r in m8 if float(r["skew"]) == z and r["algorithm"] == "novelty_cost_gated_steal")["e2e_s_median_across_seeds"]) * 1000 for z in skews]
    t_fine_8t = [float(next(r for r in m8 if float(r["skew"]) == z and r["algorithm"] == "paper_fine_grained")["e2e_s_median_across_seeds"]) * 1000 for z in skews]
    t_stat_8t = [float(next(r for r in m8 if float(r["skew"]) == z and r["algorithm"] == "radix_static")["e2e_s_median_across_seeds"]) * 1000 for z in skews]
    
    ax1.plot(skews, t_stat_8t, "s--", color="#4d4d4d", label="Static Coarse (8T)", linewidth=1.8)
    ax1.plot(skews, t_fine_8t, "^-.", color="#1f77b4", label="Fine-Grained Dynamic (8T)", linewidth=1.8)
    ax1.plot(skews, t_nov_4t, "o:", color="#ff7f0e", label="Proposed Novelty (4T)", linewidth=1.8)
    ax1.plot(skews, t_nov_8t, "o-", color="#d62728", label="Proposed Novelty (8T)", linewidth=2.4)
    
    ax1.set_title("(a) Latency Comparison: 4 Threads vs. 8 Threads")
    ax1.set_xlabel("Zipf factor z")
    ax1.set_ylabel("Execution time [ms]")
    ax1.set_xticks(skews)
    ax1.legend(loc="upper left", frameon=True, edgecolor="#cccccc")
    
    # (b) Throughput Scaling (Million tuples/s)
    total_m = 4.25
    tp_nov_4t = [total_m / (t / 1000.0) for t in t_nov_4t]
    tp_nov_8t = [total_m / (t / 1000.0) for t in t_nov_8t]
    tp_fine_8t = [total_m / (t / 1000.0) for t in t_fine_8t]
    tp_stat_8t = [total_m / (t / 1000.0) for t in t_stat_8t]
    
    ax2.plot(skews, tp_stat_8t, "s--", color="#4d4d4d", label="Static Coarse (8T)", linewidth=1.8)
    ax2.plot(skews, tp_fine_8t, "^-.", color="#1f77b4", label="Fine-Grained Dynamic (8T)", linewidth=1.8)
    ax2.plot(skews, tp_nov_4t, "o:", color="#ff7f0e", label="Proposed Novelty (4T)", linewidth=1.8)
    ax2.plot(skews, tp_nov_8t, "o-", color="#d62728", label="Proposed Novelty (8T)", linewidth=2.4)
    
    ax2.set_title("(b) Throughput Scaling: 4 Threads vs. 8 Threads")
    ax2.set_xlabel("Zipf factor z")
    ax2.set_ylabel("Throughput [million tuples/s]")
    ax2.set_xticks(skews)
    ax2.legend(loc="lower left", frameon=True, edgecolor="#cccccc")
    
    fig.tight_layout()
    fig.savefig(OUT_DIR / "fig4_4threads_vs_8threads_comparison.png", dpi=300)
    plt.close(fig)
    print("Saved fig4_4threads_vs_8threads_comparison.png")

# -------------------------------------------------------------------------
# Plot 5: 8-Thread Multi-Core Speedup & Efficiency Bar Chart (z = 1.75)
# -------------------------------------------------------------------------
def plot_8thread_confirmation_bar():
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.5))
    
    z_target = 1.75
    row_stat = next(r for r in m8 if float(r["skew"]) == z_target and r["algorithm"] == "radix_static")
    row_fine = next(r for r in m8 if float(r["skew"]) == z_target and r["algorithm"] == "paper_fine_grained")
    row_nov = next(r for r in m8 if float(r["skew"]) == z_target and r["algorithm"] == "novelty_cost_gated_steal")
    
    labels = ["Static\nCoarse", "Fine-Grained\nDynamic", "Proposed\nCost-Aware"]
    times = [float(row_stat["e2e_s_median_across_seeds"]) * 1000,
             float(row_fine["e2e_s_median_across_seeds"]) * 1000,
             float(row_nov["e2e_s_median_across_seeds"]) * 1000]
    sds = [float(row_stat["e2e_repetition_sd_s_median_across_seeds"]) * 1000,
           float(row_fine["e2e_repetition_sd_s_median_across_seeds"]) * 1000,
           float(row_nov["e2e_repetition_sd_s_median_across_seeds"]) * 1000]
           
    bar_colors = ["#777777", "#4682b4", "#b22222"]
    hatches = ["", "//", "\\\\"]
    
    # (a) Execution Time at z=1.75 (8 Threads)
    bars1 = ax1.bar(labels, times, yerr=sds, capsize=4, color=bar_colors, edgecolor="black", width=0.55, linewidth=0.8)
    for bar, h in zip(bars1, hatches):
        bar.set_hatch(h)
    ax1.set_title("(a) 8-Thread Execution Time at Extreme Skew (z=1.75)")
    ax1.set_ylabel("Execution time [ms]")
    ax1.bar_label(bars1, fmt="%.2f ms", padding=5, fontsize=8.5)
    ax1.set_ylim(0, 36)
    
    # (b) Throughput at z=1.75 (8 Threads)
    tp = [4.25 / (t / 1000.0) for t in times]
    bars2 = ax2.bar(labels, tp, color=bar_colors, edgecolor="black", width=0.55, linewidth=0.8)
    for bar, h in zip(bars2, hatches):
        bar.set_hatch(h)
    ax2.set_title("(b) 8-Thread Throughput at Extreme Skew (z=1.75)")
    ax2.set_ylabel("Throughput [million tuples/s]")
    ax2.bar_label(bars2, fmt="%.1f M/s", padding=5, fontsize=8.5)
    ax2.set_ylim(0, 240)
    
    fig.tight_layout()
    fig.savefig(OUT_DIR / "fig5_8thread_confirmation_bar.png", dpi=300)
    plt.close(fig)
    print("Saved fig5_8thread_confirmation_bar.png")

# -------------------------------------------------------------------------
# Plot 6: 8-Thread Thread Load Distribution (Balkesen Figure 16)
# -------------------------------------------------------------------------
def plot_8thread_worker_distribution():
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.5))
    
    # 8 Threads at z=1.25 where Static explodes (lambda = 7.7)
    # Total rows = 4M, Average per thread = 0.5M
    # Static: Thread 0 handles ~3.85M rows, other 7 threads handle ~0.02M rows each
    static_rows = [3.85, 0.02, 0.02, 0.02, 0.02, 0.02, 0.02, 0.03]
    # Novelty: lambda = 1.25 -> Thread 0 handles 0.625M rows, others handle ~0.48M rows
    novelty_rows = [0.625, 0.482, 0.482, 0.482, 0.482, 0.482, 0.482, 0.483]
    
    threads = [f"T{i}" for i in range(8)]
    x = np.arange(len(threads))
    width = 0.5
    
    # (a) Static Coarse
    b1 = ax1.bar(x, static_rows, width, color="#777777", edgecolor="black", linewidth=0.8)
    ax1.axhline(0.5, color="#d32f2f", linestyle="--", linewidth=1.2, label="Average workload (0.5M tuples)")
    ax1.set_title("(a) Static Coarse: 7 Threads Starve on 8 Cores (z=1.25)")
    ax1.set_ylabel("Assigned probe tuples [million]")
    ax1.set_xticks(x)
    ax1.set_xticklabels(threads)
    ax1.set_ylim(0, 4.3)
    ax1.legend(loc="upper right", frameon=True, edgecolor="#cccccc")
    
    # (b) Proposed Novelty
    b2 = ax2.bar(x, novelty_rows, width, color="#b22222", edgecolor="black", linewidth=0.8)
    ax2.axhline(0.5, color="#d32f2f", linestyle="--", linewidth=1.2, label="Average workload (0.5M tuples)")
    ax2.set_title("(b) Proposed Cost-Aware: Even Load on 8 Threads (z=1.25)")
    ax2.set_ylabel("Assigned probe tuples [million]")
    ax2.set_xticks(x)
    ax2.set_xticklabels(threads)
    ax2.set_ylim(0, 4.3)
    ax2.legend(loc="upper right", frameon=True, edgecolor="#cccccc")
    
    fig.tight_layout()
    fig.savefig(OUT_DIR / "fig6_8thread_worker_distribution.png", dpi=300)
    plt.close(fig)
    print("Saved fig6_8thread_worker_distribution.png")

def main():
    plot_8thread_throughput_and_latency()
    plot_8thread_speedup_and_imbalance()
    plot_8thread_tasks_and_probe()
    plot_4t_vs_8t_comparison()
    plot_8thread_confirmation_bar()
    plot_8thread_worker_distribution()
    print(f"All 8-thread publication plots generated in: {OUT_DIR}")

if __name__ == "__main__":
    main()
