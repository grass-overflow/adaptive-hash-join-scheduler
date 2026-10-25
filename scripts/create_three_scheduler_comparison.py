#!/usr/bin/env python3
"""Create an auditable three-scheduler comparison from retained analyzer outputs."""
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
OUTPUT = RESULTS / "consolidated_results_and_plots" / "three_scheduler_comparison"
FULL = "novelty_cost_gated_steal"
SCHEDULERS = {
    "radix_static": "Static",
    "paper_fine_grained": "Fixed-chunk dynamic",
    FULL: "Proposed combined policy",
}
DATASETS = (
    ("Exploratory grid", RESULTS / "adaptive_linear_cost_final_grid" / "analysis"),
    ("Large confirmation", RESULTS / "adaptive_linear_cost_final_z175" / "analysis"),
    ("Small confirmation", RESULTS / "adaptive_linear_cost_final_small_z175" / "analysis"),
)


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def write_csv(path, rows):
    if not rows:
        raise ValueError(f"Refusing to write empty CSV: {path}")
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def dataset_label(name, row):
    return (
        f"{name}: R={int(row['r_size']) // 1000}k, "
        f"S={int(row['s_size']) // 1000}k, z={float(row['skew']):g}"
    )


def median_rows(name, directory):
    rows = read_csv(directory / "metrics_summary.csv")
    selected = []
    for row in rows:
        if row["algorithm"] in SCHEDULERS:
            item = dict(row)
            item["dataset"] = name
            item["condition"] = dataset_label(name, row)
            selected.append(item)
    return selected


def pairwise_rows(name, directory):
    rows = read_csv(directory / "comparison_summary.csv")
    return [
        dict(row, dataset=name)
        for row in rows
        if row["comparison"] in ("full_vs_static", "full_vs_fine_chunks")
    ]


def plot_condition(rows, title, filename):
    rows = sorted(rows, key=lambda row: (float(row["skew"]), row["algorithm"]))
    by_algo = {row["algorithm"]: row for row in rows}
    if set(by_algo) != set(SCHEDULERS):
        raise ValueError(f"Incomplete scheduler set for {title}")
    labels = list(SCHEDULERS.values())
    times = [float(by_algo[algorithm]["e2e_s_median_across_seeds"]) * 1000 for algorithm in SCHEDULERS]
    fig, ax = plt.subplots(figsize=(9, 5.2))
    colors = ["#6c757d", "#4c78a8", "#e45756"]
    bars = ax.bar(labels, times, color=colors, width=0.66)
    ax.bar_label(bars, fmt="%.3f ms", padding=4, fontsize=9)
    ax.set_ylabel("End-to-end runtime (ms; lower is better)")
    ax.set_title(title)
    ax.grid(axis="y", alpha=0.25)
    ax.set_ylim(0, max(times) * 1.2)
    fig.tight_layout()
    fig.savefig(OUTPUT / filename, dpi=180)
    plt.close(fig)


def plot_grid_by_size(rows, r_size):
    selected = [row for row in rows if int(row["r_size"]) == r_size and row["dataset"] == "Exploratory grid"]
    skews = sorted({float(row["skew"]) for row in selected})
    algorithms = list(SCHEDULERS)
    x = np.arange(len(skews))
    width = 0.24
    fig, ax = plt.subplots(figsize=(10, 5.5))
    colors = ["#6c757d", "#4c78a8", "#e45756"]
    for index, algorithm in enumerate(algorithms):
        times = []
        for skew in skews:
            match = [row for row in selected if float(row["skew"]) == skew and row["algorithm"] == algorithm]
            if len(match) != 1:
                raise ValueError(f"Missing or duplicate grid metric for R={r_size}, z={skew}, {algorithm}")
            times.append(float(match[0]["e2e_s_median_across_seeds"]) * 1000)
        ax.bar(x + (index - 1) * width, times, width, label=SCHEDULERS[algorithm], color=colors[index])
    ax.set_xticks(x, [f"z={skew:g}" for skew in skews])
    ax.set_ylabel("Median end-to-end runtime (ms; lower is better)")
    ax.set_title(f"All exploratory-grid conditions: R={r_size:,}, S={16*r_size:,}, 4 threads")
    ax.legend(frameon=False, ncols=1)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(OUTPUT / f"grid_all_schedulers_R{r_size}.png", dpi=180)
    plt.close(fig)


def plot_gain(rows, comparison, filename, title):
    selected = [row for row in rows if row["comparison"] == comparison]
    selected.sort(key=lambda row: (row["dataset"], int(row["r_size"]), float(row["skew"])))
    labels = [
        f"{row['dataset']}: R={int(row['r_size'])//1000}k, z={float(row['skew']):g}"
        for row in selected
    ]
    gain = np.array([float(row["mean_paired_gain_pct"]) for row in selected])
    low = np.array([float(row["ci95_low_pct"]) for row in selected])
    high = np.array([float(row["ci95_high_pct"]) for row in selected])
    yerr = np.vstack((gain - low, high - gain))
    fig_height = max(5.2, 0.34 * len(selected) + 1.4)
    fig, ax = plt.subplots(figsize=(10, fig_height))
    y = np.arange(len(selected))
    ax.errorbar(gain, y, xerr=yerr, fmt="o", color="#e45756", ecolor="#555555", capsize=3)
    ax.axvline(0, color="black", linewidth=1)
    ax.set_yticks(y, labels)
    ax.invert_yaxis()
    ax.set_xlabel("Paired E2E gain of proposed policy (%) — positive means faster")
    ax.set_title(title)
    ax.grid(axis="x", alpha=0.25)
    fig.tight_layout()
    fig.savefig(OUTPUT / filename, dpi=180)
    plt.close(fig)


def plot_winner_conditions(metrics, winners):
    selected = []
    for winner in winners:
        for row in metrics:
            if (
                row["dataset"] == winner["dataset"]
                and int(row["r_size"]) == int(winner["r_size"])
                and int(row["s_size"]) == int(winner["s_size"])
                and float(row["skew"]) == float(winner["skew"])
            ):
                selected.append((winner, row))
    if not selected:
        return
    conditions = []
    for winner, _ in selected:
        label = f"{winner['dataset'][:4]} R{int(winner['r_size'])//1000}k z{float(winner['skew']):g}"
        if label not in conditions:
            conditions.append(label)
    algorithms = list(SCHEDULERS)
    x = np.arange(len(conditions))
    width = 0.24
    fig, ax = plt.subplots(figsize=(max(11, 1.35 * len(conditions)), 6))
    colors = ["#6c757d", "#4c78a8", "#e45756"]
    for index, algorithm in enumerate(algorithms):
        values = []
        for condition in conditions:
            match = [
                row for winner, row in selected
                if f"{winner['dataset'][:4]} R{int(winner['r_size'])//1000}k z{float(winner['skew']):g}" == condition
                and row["algorithm"] == algorithm
            ]
            if len(match) != 1:
                raise ValueError(f"Missing or duplicate winner metric for {condition}, {algorithm}")
            values.append(float(match[0]["e2e_s_median_across_seeds"]) * 1000)
        ax.bar(x + (index - 1) * width, values, width, label=SCHEDULERS[algorithm], color=colors[index])
    ax.set_xticks(x, conditions, rotation=25, ha="right")
    ax.set_ylabel("Median end-to-end runtime (ms; lower is better)")
    ax.set_title("Observed conditions where proposed policy beats both baselines (paired 95% CIs > 0)")
    ax.legend(frameon=False)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(OUTPUT / "wins_vs_both_baselines.png", dpi=180)
    plt.close(fig)


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    all_metrics = []
    all_comparisons = []
    for name, directory in DATASETS:
        if not (directory / "metrics_summary.csv").is_file():
            raise FileNotFoundError(directory / "metrics_summary.csv")
        all_metrics.extend(median_rows(name, directory))
        all_comparisons.extend(pairwise_rows(name, directory))

    write_csv(OUTPUT / "three_scheduler_metrics.csv", all_metrics)
    write_csv(OUTPUT / "paired_gain_vs_baselines.csv", all_comparisons)

    for r_size in (20000, 80000, 250000):
        plot_grid_by_size(all_metrics, r_size)

    large = [
        row for row in all_metrics
        if row["dataset"] == "Large confirmation" and float(row["skew"]) == 1.75
    ]
    small = [
        row for row in all_metrics
        if row["dataset"] == "Small confirmation" and float(row["skew"]) == 1.75
    ]
    plot_condition(large, "Large high-skew confirmation: all three schedulers (8 seeds)", "confirmation_large_z175.png")
    plot_condition(small, "Small high-skew confirmation: all three schedulers (8 seeds)", "confirmation_small_z175.png")
    plot_gain(
        all_comparisons,
        "full_vs_static",
        "paired_gain_vs_static_all_conditions.png",
        "Proposed policy vs static: all measured size/skew conditions (95% paired bootstrap intervals)",
    )
    plot_gain(
        all_comparisons,
        "full_vs_fine_chunks",
        "paired_gain_vs_fixed_dynamic_all_conditions.png",
        "Proposed policy vs fixed-chunk dynamic: all measured size/skew conditions (95% paired bootstrap intervals)",
    )

    qualifying = {}
    for row in all_comparisons:
        key = (row["dataset"], int(row["r_size"]), int(row["s_size"]), float(row["skew"]))
        qualifying.setdefault(key, {})[row["comparison"]] = row
    winners = []
    for key, contrasts in qualifying.items():
        static = contrasts.get("full_vs_static")
        fixed = contrasts.get("full_vs_fine_chunks")
        if static and fixed and float(static["ci95_low_pct"]) > 0 and float(fixed["ci95_low_pct"]) > 0:
            winners.append({
                "dataset": key[0],
                "r_size": key[1],
                "s_size": key[2],
                "skew": key[3],
                "seeds": static["independent_seeds"],
                "gain_vs_static_pct": static["mean_paired_gain_pct"],
                "ci95_vs_static_low_pct": static["ci95_low_pct"],
                "ci95_vs_static_high_pct": static["ci95_high_pct"],
                "gain_vs_fixed_dynamic_pct": fixed["mean_paired_gain_pct"],
                "ci95_vs_fixed_dynamic_low_pct": fixed["ci95_low_pct"],
                "ci95_vs_fixed_dynamic_high_pct": fixed["ci95_high_pct"],
                "selection_note": (
                    "Both paired 95% intervals are above zero; exploratory grid cell with only three seeds and post-hoc condition selection."
                    if key[0] == "Exploratory grid"
                    else "Both paired 95% intervals are above zero in this eight-seed confirmation; workload was selected after exploratory analysis."
                ),
            })
    if winners:
        write_csv(OUTPUT / "conditions_faster_than_both_baselines.csv", winners)
        plot_winner_conditions(all_metrics, winners)

    report = """# Three-scheduler comparison and empirical parameter method

## What this comparison is (and is not)

This report compares the repository's `novelty_cost_gated_steal` implementation with two repository baselines: `radix_static` and `paper_fine_grained` (fixed-size chunks dynamically dispatched). It is not a reproduction-vs-paper head-to-head: `paper_fine_grained` is a code baseline inspired by the reference paper, run on this project’s implementation, compiler, and PC. These measurements do not justify saying that this project beats the original paper.

The proposed scheduler is the combined implementation: sampled cost estimation, bounded cost-weighted task allocation with a heuristic split-benefit check, and owner-local queues with threshold-gated stealing. Its results must be reported as the combined policy. They do not show that each component is independently novel, and the comparisons here do not replace the budgeted/no-steal/ungated ablations in the full evidence report.

## Plot inventory

- `grid_all_schedulers_R*.png`: all three schedulers at all four skew values for each exploratory input size. Nothing is filtered out.
- `confirmation_large_z175.png` and `confirmation_small_z175.png`: all three schedulers in both eight-seed high-skew confirmations.
- `paired_gain_vs_static_all_conditions.png` and `paired_gain_vs_fixed_dynamic_all_conditions.png`: every current-grid and confirmation comparison, with paired 95% bootstrap intervals. Positive gain means the proposed policy is faster; intervals crossing zero are inconclusive.
- `wins_vs_both_baselines.png`: winning conditions only, with all three bars in each condition. The full, unfiltered condition plots above and paired-gain plots should be read alongside it.
- `conditions_faster_than_both_baselines.csv`: only conditions whose two paired intervals are both above zero. These are selected views, not a full-results replacement; exploratory-grid cells have only three seeds and were inspected across several conditions.

`three_scheduler_metrics.csv` and `paired_gain_vs_baselines.csv` retain the plotted median E2E values and paired comparison statistics.

## Selected confirmation outcomes (not universal claims)

At `R=250k`, `S=4M`, `z=1.75`, four threads, the proposed policy's median E2E was 32.176 ms versus 40.271 ms static and 38.746 ms fixed-chunk dynamic. Paired mean gains were +20.08% vs static (95% interval +19.45% to +20.74%) and +16.35% vs fixed chunks (+15.15% to +17.48%), across eight fresh seeds. It was not faster than `novelty_budgeted` beyond uncertainty (−0.16%, interval −0.88% to +0.57%); see the full report.

At `R=20k`, `S=320k`, `z=1.75`, proposed median E2E was 4.283 ms versus 4.701 ms static and 4.629 ms fixed-chunk dynamic. Paired mean gains were +7.53% and +7.91%, respectively. It was slower by point estimate than coarse dynamic and the budgeted policy, and those comparisons were inconclusive. This is not proof that it wins a whole skew range.

## How coefficients and parameters were obtained

There are two different things sometimes called “weights”; they must not be conflated:

1. **Per-run cost coefficients in the implementation.** The build coefficient is measured as `alpha = measured build-phase seconds / number of build tuples`. The probe coefficient is measured from repeated timing of sampled probe rows; individual candidate partitions adjust this using sampled linear-probing slot counts relative to the sampled average. Thus candidate ranking approximates `alpha * |R_i| + beta_i * |S_i|`. These are measured anew per run, not coefficients learned by a statistical regression over a training corpus. Build has already completed before probe tasks are formed, so the build term ranks candidates but does not split or parallelize the build phase.
2. **Scheduler settings.** The evaluation held `chunk-size=256`, `tasks-per-thread=4`, `split-factor=3`, `cost-samples=16`, `queue-batch-size=1`, and `steal-threshold-multiplier=4` fixed. These were selected by empirical screening/sweeps performed during development. They were not obtained by formal statistical fitting or online optimization. Fresh seed ranges were then used for the confirmations, but the high-skew operating point was selected after exploratory results; this is not an untouched preregistered evaluation set.

The split-benefit calculation estimates the reduction in probe work from parallel chunks and subtracts an estimated queue-operation cost. It is a heuristic, not a fitted makespan model. The stealing threshold includes the measured atomic-flag lock acquisition time, a two-worker contention delta, and a configured multiple of measured probe-row time. The so-called cache-migration value is only a contention proxy; no hardware cache-to-cache counter was measured.

In the large confirmation, median measured coefficients were approximately `alpha=9.25 ns/build tuple` and `beta=6.27 ns/probe tuple`; in the small confirmation, approximately `alpha=23.77 ns/build tuple` and `beta=6.63 ns/probe tuple`. They vary with workload and runtime measurement; they are not universal constants or learned “optimal weights.”

## Evidence boundary

All plots and CSVs were generated from the retained analyzer summaries under `results/adaptive_linear_cost_final_*`. The full current-source evidence and limitations are in `../../FINAL_REPORT.md`. Static/fixed-dynamic wins are conditional measured results. The broad research novelty of the combination remains unestablished, and no result here demonstrates beating the original paper.
"""
    (OUTPUT / "WEIGHTS_AND_THREE_SCHEDULER_REPORT.md").write_text(report, encoding="utf-8")
    print(f"Created {OUTPUT}")
    print(f"Metrics rows: {len(all_metrics)}")
    print(f"Paired comparison rows: {len(all_comparisons)}")
    print(f"Conditions with both paired intervals above zero: {len(winners)}")


if __name__ == "__main__":
    main()
