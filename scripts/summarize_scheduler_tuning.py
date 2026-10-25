#!/usr/bin/env python3
"""Rank scheduler configurations by worst-skew gain over the strongest peer."""
import argparse
import csv
import glob
import json
import statistics
from collections import defaultdict
from pathlib import Path


FULL = "novelty_cost_gated_steal"
PARALLEL = {
    "radix_static",
    "radix_dynamic_coarse",
    "paper_fine_grained",
    "novelty_budgeted",
    "cost_aware_no_steal",
    "cost_aware_ungated_steal",
}
TARGET_SKEWS = (0.75, 1.4, 1.75)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    paths = sorted(glob.glob(str(args.directory / "tune_*_raw.csv")))
    if not paths:
        raise ValueError(f"No tuning raw CSV files in {args.directory}")

    trials = defaultdict(list)
    for path in paths:
        with open(path, newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        if not rows:
            raise ValueError(f"No data rows in {path}")
        for row in rows:
            if row["correct"] != "1" or row["result"] != row["expected_result"]:
                raise ValueError(f"Correctness failure in {path}; refusing to rank parameters.")
            if row["algorithm"] == "sequential_reference":
                continue
            config = (
                int(row["chunk_size"]),
                int(row["tasks_per_thread"]),
                float(row["split_factor"]),
                int(row["queue_batch_size"]),
                int(row["cost_samples"]),
            )
            key = (config, float(row["skew"]), row["algorithm"])
            trials[key].append(float(row["e2e_s"]))

    by_config = defaultdict(dict)
    for (config, skew, algorithm), values in trials.items():
        by_config[config].setdefault(skew, {})[algorithm] = statistics.median(values)

    ranked = []
    for config, by_skew in by_config.items():
        gains = {}
        for skew in TARGET_SKEWS:
            measurements = by_skew.get(skew, {})
            if FULL not in measurements or not PARALLEL.issubset(measurements):
                raise ValueError(f"Incomplete algorithm/skew data for {config}, z={skew}")
            strongest = min(measurements[name] for name in PARALLEL)
            gains[skew] = 100.0 * (strongest - measurements[FULL]) / strongest
        ranked.append(
            {
                "chunk_size": config[0],
                "tasks_per_thread": config[1],
                "split_factor": config[2],
                "queue_batch_size": config[3],
                "cost_samples": config[4],
                "min_gain_vs_strongest_pct": min(gains.values()),
                "mean_gain_vs_strongest_pct": statistics.mean(gains.values()),
                "gain_z075_pct": gains[0.75],
                "gain_z14_pct": gains[1.4],
                "gain_z175_pct": gains[1.75],
            }
        )
    ranked.sort(
        key=lambda row: (
            row["min_gain_vs_strongest_pct"],
            row["mean_gain_vs_strongest_pct"],
        ),
        reverse=True,
    )
    output_csv = args.directory / "tuning_ranking.csv"
    with open(output_csv, "w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(ranked[0]))
        writer.writeheader()
        writer.writerows(ranked)
    selected = ranked[0]
    with open(args.directory / "selected_config.json", "w", encoding="utf-8") as stream:
        json.dump(selected, stream, indent=2)
        stream.write("\n")
    print("Selection objective: maximize the minimum gain over the fastest competing parallel scheduler")
    print("across z=0.75, 1.4, and 1.75 on the tuning seed; ties use mean gain.")
    print(f"Configurations evaluated: {len(ranked)}")
    print(f"Ranking: {output_csv}")
    for row in ranked[:10]:
        print(
            "chunk={chunk_size} budget={tasks_per_thread} split={split_factor:g} "
            "batch={queue_batch_size} samples={cost_samples}: min={min_gain_vs_strongest_pct:+.2f}% "
            "mean={mean_gain_vs_strongest_pct:+.2f}% "
            "z=[{gain_z075_pct:+.2f},{gain_z14_pct:+.2f},{gain_z175_pct:+.2f}]".format(**row)
        )


if __name__ == "__main__":
    main()
