#!/usr/bin/env python3
"""Summarize paired raw hash-join trials and generate comparison plots."""
import argparse
import csv
import glob
import math
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


FULL = "novelty_cost_gated_steal"
def bootstrap_ci(values, seed):
    if not values:
        return math.nan, math.nan
    rng = random.Random(seed)
    draws = sorted(
        statistics.mean(values[rng.randrange(len(values))] for _ in values)
        for _ in range(20000)
    )
    return draws[500], draws[19499]


def load_rows(patterns):
    paths = sorted({path for pattern in patterns for path in glob.glob(pattern)})
    if not paths:
        raise ValueError("No raw CSV files matched the supplied patterns.")
    rows = []
    for path in paths:
        with open(path, newline="", encoding="utf-8") as stream:
            file_rows = list(csv.DictReader(stream))
        if not file_rows:
            raise ValueError(f"No data rows in {path}")
        if any(row["correct"] != "1" or row["result"] != row["expected_result"] for row in file_rows):
            raise ValueError(f"Correctness failure in {path}; refusing timing analysis.")
        rows.extend(file_rows)
    return rows, paths


def median_by_seed(rows):
    values = defaultdict(list)
    for row in rows:
        condition = (
            int(row["r_size"]),
            int(row["s_size"]),
            int(row["threads"]),
            float(row["skew"]),
            row["seed_r"],
            row["seed_s"],
            row["algorithm"],
        )
        values[condition].append(row)
    medians = {}
    for key, repetitions in values.items():
        medians[key] = {
            field: statistics.median(float(row[field]) for row in repetitions if row[field] != "")
            for field in (
                "partition_s",
                "build_s",
                "cost_estimation_s",
                "task_planning_s",
                "probe_s",
                "e2e_s",
                "tasks",
                "heavy_partitions",
                "split_partitions",
                "max_partition_over_avg",
                "worker_rows_over_avg",
                "steal_attempts",
                "successful_steals",
                "successful_steal_batches",
                "failed_steals",
                "threshold_skips",
                "steal_cas_retries",
                "steal_threshold_ns",
                "queue_admin_s",
                "cost_model_holdout_wape_pct",
                "build_cost_ns_per_row",
                "probe_cost_ns_per_row",
                "cas_steal_cost_ns",
                "cache_migration_proxy_ns",
                "split_benefit_ns",
            )
            if any(row[field] != "" for row in repetitions)
        }
        times = [float(row["e2e_s"]) for row in repetitions]
        medians[key]["e2e_repetition_sd_s"] = statistics.stdev(times) if len(times) > 1 else 0.0
        medians[key]["e2e_repetition_cv_pct"] = (
            100.0 * medians[key]["e2e_repetition_sd_s"] / statistics.mean(times)
            if statistics.mean(times) > 0.0 else math.nan
        )
        medians[key]["repetitions"] = len(repetitions)
    return medians


def write_comparisons(medians, output_path):
    by_condition = defaultdict(dict)
    for key, measurements in medians.items():
        r_size, s_size, threads, skew, seed_r, seed_s, algorithm = key
        by_condition[(r_size, s_size, threads, skew)][(seed_r, seed_s, algorithm)] = measurements
    comparisons = [
        ("budget_only", "paper_fine_grained", "novelty_budgeted"),
        ("cost_estimation", "novelty_budgeted", "cost_aware_no_steal"),
        ("ungated_stealing", "cost_aware_no_steal", "cost_aware_ungated_steal"),
        ("threshold_gate", "cost_aware_ungated_steal", FULL),
        ("full_vs_fine_chunks", "paper_fine_grained", FULL),
        ("full_vs_budgeted", "novelty_budgeted", FULL),
        ("full_vs_cost_aware_no_steal", "cost_aware_no_steal", FULL),
        ("full_vs_ungated_steal", "cost_aware_ungated_steal", FULL),
        ("full_vs_coarse_dynamic", "radix_dynamic_coarse", FULL),
        ("full_vs_static", "radix_static", FULL),
        ("full_vs_sequential", "sequential_reference", FULL),
    ]
    result_rows = []
    for (r_size, s_size, threads, skew), seed_values in sorted(by_condition.items()):
        seeds = sorted({(seed_r, seed_s) for seed_r, seed_s, _ in seed_values})
        for label, baseline, candidate in comparisons:
            gains = []
            base_times = []
            candidate_times = []
            for seed in seeds:
                base = seed_values.get((*seed, baseline))
                proposed = seed_values.get((*seed, candidate))
                if base is None or proposed is None or base["e2e_s"] <= 0.0:
                    continue
                base_times.append(base["e2e_s"])
                candidate_times.append(proposed["e2e_s"])
                gains.append(100.0 * (base["e2e_s"] - proposed["e2e_s"]) / base["e2e_s"])
            if not gains:
                continue
            lo, hi = bootstrap_ci(gains, 881 + int(skew * 100) + len(label) + r_size)
            result_rows.append(
                {
                    "r_size": r_size,
                    "s_size": s_size,
                    "threads": threads,
                    "skew": skew,
                    "comparison": label,
                    "baseline": baseline,
                    "candidate": candidate,
                    "independent_seeds": len(gains),
                    "mean_paired_gain_pct": statistics.mean(gains),
                    "positive_seeds": sum(value > 0.0 for value in gains),
                    "ci95_low_pct": lo,
                    "ci95_high_pct": hi,
                    "baseline_median_s": statistics.median(base_times),
                    "candidate_median_s": statistics.median(candidate_times),
                    "candidate_wins_every_seed": int(all(value > 0.0 for value in gains)),
                }
            )
    if not result_rows:
        raise ValueError("No complete paired algorithm comparisons were found.")
    with open(output_path, "w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(result_rows[0]))
        writer.writeheader()
        writer.writerows(result_rows)
    return result_rows


def write_metrics(medians, output_path):
    fields = (
        "partition_s",
        "build_s",
        "cost_estimation_s",
        "task_planning_s",
        "probe_s",
        "e2e_s",
        "tasks",
        "heavy_partitions",
        "split_partitions",
        "max_partition_over_avg",
        "worker_rows_over_avg",
        "steal_attempts",
        "successful_steals",
        "successful_steal_batches",
        "failed_steals",
        "threshold_skips",
        "steal_cas_retries",
        "steal_threshold_ns",
        "queue_admin_s",
        "cost_model_holdout_wape_pct",
        "build_cost_ns_per_row",
        "probe_cost_ns_per_row",
        "cas_steal_cost_ns",
        "cache_migration_proxy_ns",
        "split_benefit_ns",
        "e2e_repetition_sd_s",
        "e2e_repetition_cv_pct",
    )
    groups = defaultdict(list)
    by_seed = defaultdict(dict)
    for key, measurements in medians.items():
        groups[(*key[:4], key[-1])].append(measurements)
        by_seed[key[:-1]][key[-1]] = measurements
    rows = []
    for (r_size, s_size, threads, skew, algorithm), seeds in sorted(groups.items()):
        row = {
            "r_size": r_size,
            "s_size": s_size,
            "threads": threads,
            "skew": skew,
            "algorithm": algorithm,
            "independent_seeds": len(seeds),
        }
        for field in fields:
            samples = [seed[field] for seed in seeds if field in seed]
            row[f"{field}_median_across_seeds"] = statistics.median(samples) if samples else ""
        speedups = []
        for seed_key in by_seed:
            if seed_key[:4] != (r_size, s_size, threads, skew):
                continue
            current = by_seed[seed_key].get(algorithm)
            sequential = by_seed[seed_key].get("sequential_reference")
            if current is not None and sequential is not None and current["e2e_s"] > 0.0:
                speedups.append(sequential["e2e_s"] / current["e2e_s"])
        row["speedup_vs_sequential_median_across_seeds"] = statistics.median(speedups) if speedups else ""
        row["parallel_efficiency_pct_median_across_seeds"] = (
            100.0 * statistics.median(speedups) / threads if speedups else ""
        )
        rows.append(row)
    with open(output_path, "w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def save_plots(comparisons, metrics, output_dir):
    sizes = sorted({int(row["r_size"]) for row in metrics})
    comparison_names = {
        "radix_dynamic_coarse": ("radix_dynamic_coarse", "Dynamic coarse"),
        "paper_fine_grained": ("paper_fine_grained", "Fixed chunks"),
        "novelty_budgeted": ("novelty_budgeted", "Budgeted"),
        "cost_aware_no_steal": ("cost_aware_no_steal", "Cost-aware, no steal"),
        "cost_aware_ungated_steal": ("cost_aware_ungated_steal", "Ungated steal"),
        FULL: (FULL, "Cost-gated steal"),
        "sequential_reference": ("sequential_reference", "Sequential"),
    }
    fig, axes = plt.subplots(1, len(sizes), figsize=(6 * len(sizes), 4), squeeze=False)
    for axis, r_size in zip(axes[0], sizes):
        subset = [row for row in metrics if int(row["r_size"]) == r_size]
        skews = sorted({float(row["skew"]) for row in subset})
        for algorithm, label in comparison_names.values():
            points = []
            for skew in skews:
                matches = [
                    float(row["e2e_s_median_across_seeds"])
                    for row in subset
                    if row["algorithm"] == algorithm and float(row["skew"]) == skew
                ]
                points.append(statistics.median(matches) if matches else math.nan)
            axis.plot(skews, points, marker="o", label=label)
        s_sizes = {int(row["s_size"]) for row in subset}
        s_label = f"S={next(iter(s_sizes)):,}" if len(s_sizes) == 1 else "multiple S sizes"
        axis.set_title(f"R={r_size:,}, {s_label}")
        axis.set_xlabel("Zipf exponent")
        axis.set_ylabel("Median end-to-end time (s)")
        axis.grid(True, alpha=0.3)
    axes[0][0].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(output_dir / "e2e_by_skew.png", dpi=160)
    plt.close(fig)

    ablations = [
        ("cost_estimation", "Cost model vs budget-only"),
        ("ungated_stealing", "Ungated steal vs no steal"),
        ("threshold_gate", "Cost gate vs ungated steal"),
    ]
    fig, axes = plt.subplots(1, len(sizes), figsize=(6 * len(sizes), 4), squeeze=False)
    for axis, r_size in zip(axes[0], sizes):
        for name, label in ablations:
            points = []
            skews = sorted(
                {float(row["skew"]) for row in comparisons if int(row["r_size"]) == r_size}
            )
            for skew in skews:
                matches = [
                    float(row["mean_paired_gain_pct"])
                    for row in comparisons
                    if int(row["r_size"]) == r_size
                    and float(row["skew"]) == skew
                    and row["comparison"] == name
                ]
                points.append(statistics.mean(matches) if matches else math.nan)
            axis.plot(skews, points, marker="o", label=label)
        axis.axhline(0.0, color="black", linewidth=0.8)
        axis.set_title(f"Ablations, R={r_size:,}")
        axis.set_xlabel("Zipf exponent")
        axis.set_ylabel("Paired end-to-end improvement (%)")
        axis.grid(True, alpha=0.3)
    axes[0][0].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(output_dir / "ablation_gains.png", dpi=160)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("raw_csv", nargs="+", help="raw CSV paths or glob patterns")
    parser.add_argument("--out-dir", default="results/analysis")
    args = parser.parse_args()
    rows, paths = load_rows(args.raw_csv)
    medians = median_by_seed(rows)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    comparisons = write_comparisons(medians, out_dir / "comparison_summary.csv")
    write_metrics(medians, out_dir / "metrics_summary.csv")
    with open(out_dir / "metrics_summary.csv", newline="", encoding="utf-8") as stream:
        metrics = list(csv.DictReader(stream))
    save_plots(comparisons, metrics, out_dir)
    print(f"Validated {len(rows)} raw rows from {len(paths)} files.")
    print(f"Comparison summary: {out_dir / 'comparison_summary.csv'}")
    print(f"Metric summary: {out_dir / 'metrics_summary.csv'}")
    print(f"Graphs: {out_dir / 'e2e_by_skew.png'}, {out_dir / 'ablation_gains.png'}")
    primary = [
        row for row in comparisons
        if row["comparison"] == "threshold_gate" and float(row["skew"]) == 1.75
    ]
    for row in primary:
        print(
            f"R={row['r_size']}, S={row['s_size']}, T={row['threads']}: "
            f"gated-vs-ungated {row['mean_paired_gain_pct']:+.2f}% "
            f"[{row['ci95_low_pct']:+.2f}%, {row['ci95_high_pct']:+.2f}%], "
            f"n={row['independent_seeds']}"
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
