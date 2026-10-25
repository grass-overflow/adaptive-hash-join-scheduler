#!/usr/bin/env python3
"""Select probe-sampling and queue-batch settings from paired tuning seeds."""
import argparse
import csv
import glob
import json
import statistics
from collections import defaultdict
from pathlib import Path


FULL = "novelty_cost_gated_steal"
PEERS = (
    "radix_static",
    "radix_dynamic_coarse",
    "paper_fine_grained",
    "novelty_budgeted",
    "cost_aware_no_steal",
    "cost_aware_ungated_steal",
)
TUNING_SKEWS = (0.75, 1.4, 1.75)
TARGET_SKEWS = (1.4, 1.75)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    paths = sorted(glob.glob(str(args.directory / "tune_*_raw.csv")))
    if not paths:
        raise ValueError(f"No tuning raw CSV files in {args.directory}")

    repetitions = defaultdict(list)
    for path in paths:
        with open(path, newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        if not rows:
            raise ValueError(f"No data rows in {path}")
        for row in rows:
            if row["correct"] != "1" or row["result"] != row["expected_result"]:
                raise ValueError(f"Correctness failure in {path}; refusing parameter analysis.")
            if row["algorithm"] == "sequential_reference":
                continue
            config = (int(row["cost_samples"]), int(row["queue_batch_size"]))
            seed = (row["seed_r"], row["seed_s"])
            key = (config, float(row["skew"]), seed, row["algorithm"])
            repetitions[key].append(float(row["e2e_s"]))

    seed_medians = {
        key: statistics.median(values) for key, values in repetitions.items()
    }
    by_config = defaultdict(lambda: defaultdict(dict))
    for (config, skew, seed, algorithm), value in seed_medians.items():
        by_config[config][skew][seed, algorithm] = value

    ranked = []
    for (samples, batch), by_skew in by_config.items():
        gain_by_skew = {}
        seed_count_by_skew = {}
        for skew in TUNING_SKEWS:
            values = by_skew.get(skew, {})
            seeds = sorted({seed for seed, algorithm in values})
            paired = []
            for seed in seeds:
                candidate = values.get((seed, FULL))
                competitors = [values.get((seed, name)) for name in PEERS]
                if candidate is None or any(value is None for value in competitors):
                    continue
                paired.append(
                    100.0 * (min(competitors) - candidate) / min(competitors)
                )
            if not paired:
                raise ValueError(f"Incomplete paired tuning data: samples={samples}, batch={batch}, z={skew}")
            gain_by_skew[skew] = statistics.mean(paired)
            seed_count_by_skew[skew] = len(paired)
        ranked.append(
            {
                "cost_samples": samples,
                "queue_batch_size": batch,
                "min_target_skew_gain_pct": min(gain_by_skew[z] for z in TARGET_SKEWS),
                "mean_target_skew_gain_pct": statistics.mean(gain_by_skew[z] for z in TARGET_SKEWS),
                "gain_z075_pct": gain_by_skew[0.75],
                "gain_z14_pct": gain_by_skew[1.4],
                "gain_z175_pct": gain_by_skew[1.75],
                "seeds_per_skew": min(seed_count_by_skew.values()),
            }
        )
    ranked.sort(
        key=lambda row: (
            row["min_target_skew_gain_pct"],
            row["mean_target_skew_gain_pct"],
        ),
        reverse=True,
    )
    with open(args.directory / "estimator_ranking.csv", "w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(ranked[0]))
        writer.writeheader()
        writer.writerows(ranked)
    with open(args.directory / "selected_estimator_config.json", "w", encoding="utf-8") as stream:
        json.dump(ranked[0], stream, indent=2)
        stream.write("\n")
    print("Objective: maximize the minimum mean gain over the fastest competing parallel scheduler")
    print("at z=1.4 and z=1.75, averaged over paired tuning seeds; z=0.75 is reported separately.")
    print(f"Configurations: {len(ranked)}; tuning seeds per skew: {ranked[0]['seeds_per_skew']}")
    for row in ranked:
        print(
            f"samples={row['cost_samples']} batch={row['queue_batch_size']} "
            f"min-high-skew={row['min_target_skew_gain_pct']:+.2f}% "
            f"mean-high-skew={row['mean_target_skew_gain_pct']:+.2f}% "
            f"z=[{row['gain_z075_pct']:+.2f},{row['gain_z14_pct']:+.2f},{row['gain_z175_pct']:+.2f}]"
        )


if __name__ == "__main__":
    main()
