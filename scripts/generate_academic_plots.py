#!/usr/bin/env python3
"""Generate standard, publication-grade academic plots (IEEE / ACM / VLDB style).
Clean formatting without decorative callouts, artificial badges, or marketing annotations.
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

GRID_PATH = RESULTS / "adaptive_linear_cost_final_grid" / "analysis"
LARGE_PATH = RESULTS / "adaptive_linear_cost_final_z175" / "analysis"
SMALL_PATH = RESULTS / "adaptive_linear_cost_final_small_z175" / "analysis"

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

grid_metrics = read_csv(GRID_PATH / "metrics_summary.csv")
grid_comp = read_csv(GRID_PATH / "comparison_summary.csv")
large_metrics = read_csv(LARGE_PATH / "metrics_summary.csv")
large_comp = read_csv(LARGE_PATH / "comparison_summary.csv")
small_metrics = read_csv(SMALL_PATH / "metrics_summary.csv")
small_comp = read_csv(SMALL_PATH / "comparison_summary.csv")

# Standard academic styling: dark gray, steel blue, crimson
SCHEDS = {
    "radix_static": ("Static Coarse", "#4d4d4d", "s", "--", 1.8),
    "paper_fine_grained": ("Fine-Grained Dynamic (Balkesen et al.)", "#1f77b4", "^", "-.", 1.8),
    "novelty_cost_gated_steal": ("Proposed Cost-Aware Stealing", "#d62728", "o", "-", 2.2),
}

# -------------------------------------------------------------------------
# -------------------------------------------------------------------------
# Plot 1: Throughput, Cycles per Tuple (Balkesen metric), and Latency vs Skew
# -------------------------------------------------------------------------
def plot_throughput_and_latency():
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(11, 8.5), sharex=True)
    
    subset_large = [m for m in grid_metrics if int(m["r_size"]) == 250000]
    skews = sorted(list({float(m["skew"]) for m in subset_large}))
    nominal_freq_ghz = 2.6
    
    # Subplot (a): Throughput - Large
    for algo, (label, color, marker, ls, lw) in SCHEDS.items():
        tp = []
        for z in skews:
            row = next(m for m in subset_large if float(m["skew"]) == z and m["algorithm"] == algo)
            r_sz = float(row["r_size"])
            s_sz = float(row["s_size"])
            e2e = float(row["e2e_s_median_across_seeds"])
            tp.append((r_sz + s_sz) / (e2e * 1e6))
        ax1.plot(skews, tp, label=label, color=color, marker=marker, linestyle=ls, linewidth=lw, markersize=6)
    
    ax1.set_title("(a) Throughput: Large Workload (|R|=250k, |S|=4M)")
    ax1.set_ylabel("Throughput [million tuples/s]")
    ax1.legend(loc="upper left", frameon=True, edgecolor="#cccccc")
    
    # Subplot (b): Cycles per Output Tuple (Balkesen et al. ICDE 2013 Metric)
    for algo, (label, color, marker, ls, lw) in SCHEDS.items():
        cycles = []
        for z in skews:
            row = next(m for m in subset_large if float(m["skew"]) == z and m["algorithm"] == algo)
            s_sz = float(row["s_size"]) # output tuple count = |S| in primary/foreign join
            e2e = float(row["e2e_s_median_across_seeds"])
            c_per_t = (e2e * nominal_freq_ghz * 1e9) / s_sz
            cycles.append(c_per_t)
        ax2.plot(skews, cycles, label=label, color=color, marker=marker, linestyle=ls, linewidth=lw, markersize=6)
    
    ax2.set_title("(b) Cycles per Output Tuple (Balkesen Metric, 2.6 GHz)")
    ax2.set_ylabel("Cycles per output tuple")
    ax2.set_ylim(13, 23)
    
    # Subplot (c): Execution Time - Large
    for algo, (label, color, marker, ls, lw) in SCHEDS.items():
        t = [float(next(m for m in subset_large if float(m["skew"]) == z and m["algorithm"] == algo)["e2e_s_median_across_seeds"]) * 1000 for z in skews]
        ax3.plot(skews, t, label=label, color=color, marker=marker, linestyle=ls, linewidth=lw, markersize=6)
    
    ax3.set_title("(c) Execution Time: Large Workload (|R|=250k, |S|=4M)")
    ax3.set_xlabel("Zipf factor z")
    ax3.set_ylabel("Execution time [ms]")
    ax3.set_xticks(skews)
    
    # Subplot (d): Execution Time - Medium
    subset_med = [m for m in grid_metrics if int(m["r_size"]) == 80000]
    for algo, (label, color, marker, ls, lw) in SCHEDS.items():
        t = [float(next(m for m in subset_med if float(m["skew"]) == z and m["algorithm"] == algo)["e2e_s_median_across_seeds"]) * 1000 for z in skews]
        ax4.plot(skews, t, label=label, color=color, marker=marker, linestyle=ls, linewidth=lw, markersize=6)
    
    ax4.set_title("(d) Execution Time: Medium Workload (|R|=80k, |S|=1.28M)")
    ax4.set_xlabel("Zipf factor z")
    ax4.set_ylabel("Execution time [ms]")
    ax4.set_xticks(skews)
    
    fig.tight_layout()
    fig.savefig(OUT_DIR / "fig1_throughput_and_latency.png", dpi=300)
    plt.close(fig)
    print("Saved fig1_throughput_and_latency.png")

# -------------------------------------------------------------------------
# Plot 2: Speedup vs Sequential Reference & Load Imbalance / Barrier Wait
# -------------------------------------------------------------------------
def plot_speedup_and_imbalance():
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.5))
    
    subset = [m for m in grid_metrics if int(m["r_size"]) == 250000]
    skews = sorted(list({float(m["skew"]) for m in subset}))
    
    # Subplot (a): Speedup vs Sequential
    for algo, (label, color, marker, ls, lw) in SCHEDS.items():
        speedups = [float(next(m for m in subset if float(m["skew"]) == z and m["algorithm"] == algo)["speedup_vs_sequential_median_across_seeds"]) for z in skews]
        ax1.plot(skews, speedups, label=label, color=color, marker=marker, linestyle=ls, linewidth=lw, markersize=6)
    
    ax1.set_title("(a) Speedup vs. Sequential Reference (|R|=250k, |S|=4M)")
    ax1.set_xlabel("Zipf factor z")
    ax1.set_ylabel("Speedup factor (vs. sequential)")
    ax1.set_xticks(skews)
    ax1.legend(loc="upper right", frameon=True, edgecolor="#cccccc")
    
    # Subplot (b): Worker Imbalance Lambda
    for algo, (label, color, marker, ls, lw) in SCHEDS.items():
        imbalance = []
        for z in skews:
            row = next(m for m in subset if float(m["skew"]) == z and m["algorithm"] == algo)
            val = float(row["worker_rows_over_avg_median_across_seeds"])
            if val < 1.0:
                val = 1.0
            imbalance.append(val)
        ax2.plot(skews, imbalance, label=label, color=color, marker=marker, linestyle=ls, linewidth=lw, markersize=6)
    
    ax2.axhline(1.0, color="gray", linestyle=":", linewidth=1.2, label=r"Ideal balance ($\lambda=1.0$)")
    ax2.set_title(r"(b) Worker Load Imbalance $\lambda$ = $\frac{\max \text{worker rows}}{\text{avg worker rows}}$")
    ax2.set_xlabel("Zipf factor z")
    ax2.set_ylabel(r"Worker load imbalance ($\lambda$)")
    ax2.set_xticks(skews)
    ax2.set_ylim(0.9, 4.4)
    ax2.legend(loc="upper left", frameon=True, edgecolor="#cccccc")
    
    fig.tight_layout()
    fig.savefig(OUT_DIR / "fig2_speedup_and_imbalance.png", dpi=300)
    plt.close(fig)
    print("Saved fig2_speedup_and_imbalance.png")


# -------------------------------------------------------------------------
# Plot 3: Task Granularity (Count) & Probe Phase Latency
# -------------------------------------------------------------------------
def plot_task_granularity_and_probe():
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.5))
    
    subset = [m for m in grid_metrics if int(m["r_size"]) == 250000]
    skews = sorted(list({float(m["skew"]) for m in subset}))
    
    # Subplot (a): Task Count
    for algo, (label, color, marker, ls, lw) in SCHEDS.items():
        counts = [float(next(m for m in subset if float(m["skew"]) == z and m["algorithm"] == algo)["tasks_median_across_seeds"]) for z in skews]
        ax1.plot(skews, counts, label=label, color=color, marker=marker, linestyle=ls, linewidth=lw, markersize=6)
    
    ax1.set_yscale("log")
    ax1.set_title("(a) Scheduled Task Count (|R|=250k, |S|=4M)")
    ax1.set_xlabel("Zipf factor z")
    ax1.set_ylabel("Total task count [log scale]")
    ax1.set_xticks(skews)
    ax1.legend(loc="upper left", frameon=True, edgecolor="#cccccc")
    
    # Subplot (b): Probe Phase Time
    for algo, (label, color, marker, ls, lw) in SCHEDS.items():
        probes = [float(next(m for m in subset if float(m["skew"]) == z and m["algorithm"] == algo)["probe_s_median_across_seeds"]) * 1000 for z in skews]
        ax2.plot(skews, probes, label=label, color=color, marker=marker, linestyle=ls, linewidth=lw, markersize=6)
    
    ax2.set_title("(b) Probe Phase Latency (|R|=250k, |S|=4M)")
    ax2.set_xlabel("Zipf factor z")
    ax2.set_ylabel("Probe phase duration [ms]")
    ax2.set_xticks(skews)
    ax2.legend(loc="upper left", frameon=True, edgecolor="#cccccc")
    
    fig.tight_layout()
    fig.savefig(OUT_DIR / "fig3_task_granularity_and_probe.png", dpi=300)
    plt.close(fig)
    print("Saved fig3_task_granularity_and_probe.png")

# -------------------------------------------------------------------------
# Plot 4: Confirmatory 8-Seed High-Skew Bar Chart (Classic Academic Style)
# -------------------------------------------------------------------------
def plot_academic_confirmation():
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.5))
    
    # Large
    row_static_l = next(m for m in large_metrics if m["algorithm"] == "radix_static")
    row_fixed_l = next(m for m in large_metrics if m["algorithm"] == "paper_fine_grained")
    row_novelty_l = next(m for m in large_metrics if m["algorithm"] == "novelty_cost_gated_steal")
    
    labels = ["Static\nCoarse", "Fine-Grained\nDynamic", "Proposed\nCost-Aware"]
    times_l = [float(row_static_l["e2e_s_median_across_seeds"]) * 1000,
               float(row_fixed_l["e2e_s_median_across_seeds"]) * 1000,
               float(row_novelty_l["e2e_s_median_across_seeds"]) * 1000]
    sds_l = [float(row_static_l["e2e_repetition_sd_s_median_across_seeds"]) * 1000,
             float(row_fixed_l["e2e_repetition_sd_s_median_across_seeds"]) * 1000,
             float(row_novelty_l["e2e_repetition_sd_s_median_across_seeds"]) * 1000]
    
    bar_colors = ["#777777", "#4682b4", "#b22222"]
    hatches = ["", "//", "\\\\"]
    
    bars1 = ax1.bar(labels, times_l, yerr=sds_l, capsize=4, color=bar_colors, edgecolor="black", width=0.55, linewidth=0.8)
    for bar, h in zip(bars1, hatches):
        bar.set_hatch(h)
    ax1.set_title("(a) Large Workload (|R|=250k, |S|=4M, z=1.75)")
    ax1.set_ylabel("Execution time [ms]")
    ax1.bar_label(bars1, fmt="%.2f ms", padding=5, fontsize=8.5)
    ax1.set_ylim(0, 52)
    
    # Small
    row_static_s = next(m for m in small_metrics if m["algorithm"] == "radix_static")
    row_fixed_s = next(m for m in small_metrics if m["algorithm"] == "paper_fine_grained")
    row_novelty_s = next(m for m in small_metrics if m["algorithm"] == "novelty_cost_gated_steal")
    
    times_s = [float(row_static_s["e2e_s_median_across_seeds"]) * 1000,
               float(row_fixed_s["e2e_s_median_across_seeds"]) * 1000,
               float(row_novelty_s["e2e_s_median_across_seeds"]) * 1000]
    sds_s = [float(row_static_s["e2e_repetition_sd_s_median_across_seeds"]) * 1000,
             float(row_fixed_s["e2e_repetition_sd_s_median_across_seeds"]) * 1000,
             float(row_novelty_s["e2e_repetition_sd_s_median_across_seeds"]) * 1000]
    
    bars2 = ax2.bar(labels, times_s, yerr=sds_s, capsize=4, color=bar_colors, edgecolor="black", width=0.55, linewidth=0.8)
    for bar, h in zip(bars2, hatches):
        bar.set_hatch(h)
    ax2.set_title("(b) Small Workload (|R|=20k, |S|=320k, z=1.75)")
    ax2.set_ylabel("Execution time [ms]")
    ax2.bar_label(bars2, fmt="%.2f ms", padding=5, fontsize=8.5)
    ax2.set_ylim(0, 7.2)
    
    fig.tight_layout()
    fig.savefig(OUT_DIR / "fig4_confirmatory_high_skew.png", dpi=300)
    plt.close(fig)
    print("Saved fig4_confirmatory_high_skew.png")

# -------------------------------------------------------------------------
# Plot 5: Stealing Dynamics and Overhead Breakdown
# -------------------------------------------------------------------------
def plot_stealing_and_overhead():
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.5))
    
    subset = [m for m in grid_metrics if int(m["r_size"]) == 250000]
    skews = sorted(list({float(m["skew"]) for m in subset}))
    
    # Subplot (a): Steal statistics vs skew
    novelty_rows = [next(m for m in subset if float(m["skew"]) == z and m["algorithm"] == "novelty_cost_gated_steal") for z in skews]
    attempts = [float(r["steal_attempts_median_across_seeds"]) for r in novelty_rows]
    steals = [float(r["successful_steals_median_across_seeds"]) for r in novelty_rows]
    batches = [float(r["successful_steal_batches_median_across_seeds"]) for r in novelty_rows]
    
    ax1.plot(skews, attempts, label="Steal attempts", marker="o", color="#4d4d4d", linestyle="--", linewidth=1.8)
    ax1.plot(skews, steals, label="Successful task steals", marker="s", color="#1f77b4", linestyle="-.", linewidth=1.8)
    ax1.plot(skews, batches, label="Successful steal batches", marker="^", color="#d62728", linestyle="-", linewidth=2.0)
    
    ax1.set_title("(a) Work Stealing Activity vs. Skew (|R|=250k, |S|=4M)")
    ax1.set_xlabel("Zipf factor z")
    ax1.set_ylabel("Operation count")
    ax1.set_xticks(skews)
    ax1.legend(loc="upper left", frameon=True, edgecolor="#cccccc")
    
    # Subplot (b): Scheduling Overhead Components
    est_us = [float(r["cost_estimation_s_median_across_seeds"]) * 1e6 if r.get("cost_estimation_s_median_across_seeds") else 0.0 for r in novelty_rows]
    plan_us = [float(r["task_planning_s_median_across_seeds"]) * 1e6 if r.get("task_planning_s_median_across_seeds") else 0.0 for r in novelty_rows]
    admin_us = [float(r["queue_admin_s_median_across_seeds"]) * 1e6 if r.get("queue_admin_s_median_across_seeds") else 0.0 for r in novelty_rows]
    
    x = np.arange(len(skews))
    width = 0.5
    p1 = ax2.bar(x, est_us, width, label="Cost estimation", color="#98c1d9", edgecolor="black", linewidth=0.8)
    p2 = ax2.bar(x, plan_us, width, bottom=est_us, label="Task allocation / planning", color="#ee6c4d", edgecolor="black", linewidth=0.8)
    p3 = ax2.bar(x, admin_us, width, bottom=np.array(est_us)+np.array(plan_us), label="Queue admin / synchronization", color="#293241", edgecolor="black", linewidth=0.8)
    
    ax2.set_title(r"(b) Scheduling & Estimation Overhead ($\mu$s)")
    ax2.set_xlabel("Zipf factor z")
    ax2.set_ylabel(r"Overhead duration [$\mu$s]")
    ax2.set_xticks(x)
    ax2.set_xticklabels([f"z={z:g}" for z in skews])
    ax2.legend(loc="upper left", frameon=True, edgecolor="#cccccc")
    
    fig.tight_layout()
    fig.savefig(OUT_DIR / "fig5_stealing_dynamics_and_overhead.png", dpi=300)
    plt.close(fig)
    print("Saved fig5_stealing_dynamics_and_overhead.png")

# -------------------------------------------------------------------------
# Plot 6: Parallel Efficiency & Phase Breakdown Stacked Bar Chart
# -------------------------------------------------------------------------
def plot_efficiency_and_phase_breakdown():
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.5))
    
    subset = [m for m in grid_metrics if int(m["r_size"]) == 250000]
    skews = sorted(list({float(m["skew"]) for m in subset}))
    
    # Subplot (a): Parallel Efficiency (%)
    for algo, (label, color, marker, ls, lw) in SCHEDS.items():
        effs = [float(next(m for m in subset if float(m["skew"]) == z and m["algorithm"] == algo)["parallel_efficiency_pct_median_across_seeds"]) for z in skews]
        ax1.plot(skews, effs, label=label, color=color, marker=marker, linestyle=ls, linewidth=lw, markersize=6)
    
    ax1.set_title(r"(a) Parallel Efficiency $E = \frac{Speedup}{p} \times 100\%$ (|R|=250k, |S|=4M)")
    ax1.set_xlabel("Zipf factor z")
    ax1.set_ylabel("Parallel efficiency [%]")
    ax1.set_xticks(skews)
    ax1.legend(loc="upper right", frameon=True, edgecolor="#cccccc")
    
    # Subplot (b): Phase Breakdown Stacked Bar Chart at z=1.75
    z_target = 1.75
    algos = ["radix_static", "paper_fine_grained", "novelty_cost_gated_steal"]
    algo_labels = ["Static\nCoarse", "Fine-Grained\nDynamic", "Proposed\nCost-Aware"]
    
    part_times = []
    build_times = []
    probe_times = []
    sched_times = []
    
    for algo in algos:
        row = next(m for m in subset if float(m["skew"]) == z_target and m["algorithm"] == algo)
        part = float(row["partition_s_median_across_seeds"]) * 1000
        build = float(row["build_s_median_across_seeds"]) * 1000
        probe = float(row["probe_s_median_across_seeds"]) * 1000
        e2e = float(row["e2e_s_median_across_seeds"]) * 1000
        sched = max(0.0, e2e - (part + build + probe))
        
        part_times.append(part)
        build_times.append(build)
        probe_times.append(probe)
        sched_times.append(sched)
        
    x = np.arange(len(algos))
    width = 0.5
    
    # Classic academic grays / blues
    c_part = "#b0bec5"
    c_build = "#78909c"
    c_probe = "#37474f"
    c_sched = "#d32f2f"
    
    b1 = ax2.bar(x, part_times, width, label="Partition phase", color=c_part, edgecolor="black", linewidth=0.8)
    b2 = ax2.bar(x, build_times, width, bottom=part_times, label="Build phase", color=c_build, edgecolor="black", linewidth=0.8)
    b3 = ax2.bar(x, probe_times, width, bottom=np.array(part_times)+np.array(build_times), label="Probe phase (Join)", color=c_probe, edgecolor="black", linewidth=0.8)
    b4 = ax2.bar(x, sched_times, width, bottom=np.array(part_times)+np.array(build_times)+np.array(probe_times), label="Scheduling / Overhead", color=c_sched, edgecolor="black", linewidth=0.8)
    
    totals = np.array(part_times) + np.array(build_times) + np.array(probe_times) + np.array(sched_times)
    for i, tot in enumerate(totals):
        ax2.text(x[i], tot + 0.8, f"{tot:.2f} ms", ha="center", va="bottom", fontsize=9, fontweight="bold")
        
    ax2.set_title(f"(b) Execution Phase Breakdown at Extreme Skew (z={z_target})")
    ax2.set_ylabel("Execution time [ms]")
    ax2.set_xticks(x)
    ax2.set_xticklabels(algo_labels)
    ax2.set_ylim(0, 36)
    ax2.legend(loc="upper right", frameon=True, edgecolor="#cccccc")
    
    fig.tight_layout()
    fig.savefig(OUT_DIR / "fig6_parallel_efficiency_and_phase_breakdown.png", dpi=300)
    plt.close(fig)
    print("Saved fig6_parallel_efficiency_and_phase_breakdown.png")

def main():
    plot_throughput_and_latency()
    plot_speedup_and_imbalance()
    plot_task_granularity_and_probe()
    plot_academic_confirmation()
    plot_stealing_and_overhead()
    plot_efficiency_and_phase_breakdown()
    print(f"All standard academic plots generated in: {OUT_DIR}")

if __name__ == "__main__":
    main()

