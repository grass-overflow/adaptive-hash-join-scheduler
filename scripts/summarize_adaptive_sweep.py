#!/usr/bin/env python3
"""Rank scheduler task parameters by gains over every peer at high skew."""
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
SKEWS = (0.75, 1.4, 1.75)
TARGET_SKEWS = (1.4, 1.75)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    paths = sorted(glob.glob(str(args.directory / "tune_*_raw.csv")))
    if not paths:
        raise ValueError(f"No task-parameter tuning CSVs in {args.directory}")
    grouped = defaultdict(list)
    for path in paths:
        with open(path, newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        for row in rows:
            if row["correct"] != "1" or row["result"] != row["expected_result"]:
                raise ValueError(f"Correctness failure in {path}; refusing tuning analysis.")
            if row["algorithm"] == "sequential_reference":
                continue
            config = (
                int(row["chunk_size"]),
                int(row["tasks_per_thread"]),
                float(row["split_factor"]),
            )
            seed = (row["seed_r"], row["seed_s"])
            grouped[config, float(row["skew"]), seed, row["algorithm"]].append(float(row["e2e_s"]))
    medians = {key: statistics.median(values) for key, values in grouped.items()}
    configs = sorted({key[0] for key in medians})
    ranked = []
    for chunk, budget, split in configs:
        gain_by_skew_peer = {}
        for skew in SKEWS:
            seeds = sorted({key[2] for key in medians if key[0] == (chunk, budget, split) and key[1] == skew})
            for peer in PEERS:
                gains = []
                for seed in seeds:
                    candidate = medians.get(((chunk, budget, split), skew, seed, FULL))
                    baseline = medians.get(((chunk, budget, split), skew, seed, peer))
                    if candidate is None or baseline is None:
                        raise ValueError(f"Incomplete data for config={(chunk,budget,split)}, z={skew}, peer={peer}")
                    gains.append(100.0 * (baseline - candidate) / baseline)
                gain_by_skew_peer[skew, peer] = statistics.mean(gains)
        target_gains = [
            gain_by_skew_peer[skew, peer]
            for skew in TARGET_SKEWS
            for peer in PEERS
        ]
        ranked.append(
            {
                "chunk_size": chunk,
                "tasks_per_thread": budget,
                "split_factor": split,
                "queue_batch_size": 1,
                "cost_samples": 16,
                "steal_threshold_multiplier": 4.0,
                "min_mean_gain_vs_peer_z14_z175_pct": min(target_gains),
                "mean_gain_vs_all_peers_z14_z175_pct": statistics.mean(target_gains),
                "gain_z075_vs_budgeted_pct": gain_by_skew_peer[0.75, "novelty_budgeted"],
                "gain_z14_vs_budgeted_pct": gain_by_skew_peer[1.4, "novelty_budgeted"],
                "gain_z175_vs_budgeted_pct": gain_by_skew_peer[1.75, "novelty_budgeted"],
                "min_gain_vs_peer_z175_pct": min(gain_by_skew_peer[1.75, peer] for peer in PEERS),
                "seeds_per_skew": min(
                    len({key[2] for key in medians if key[0] == (chunk, budget, split) and key[1] == skew})
                    for skew in SKEWS
                ),
            }
        )
    ranked.sort(
        key=lambda row: (
            row["min_mean_gain_vs_peer_z14_z175_pct"],
            row["mean_gain_vs_all_peers_z14_z175_pct"],
        ),
        reverse=True,
    )
    with open(args.directory / "adaptive_ranking.csv", "w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(ranked[0]))
        writer.writeheader()
        writer.writerows(ranked)
    with open(args.directory / "selected_adaptive_config.json", "w", encoding="utf-8") as stream:
        json.dump(ranked[0], stream, indent=2)
        stream.write("\n")
    print("Selection objective: maximize the worst mean gain over each parallel peer")
    print("at z=1.4 and 1.75, with three paired tuning seeds; z=0.75 is a diagnostic.")
    for row in ranked[:10]:
        print(
            "chunk={chunk_size} budget={tasks_per_thread} split={split_factor:g}: "
            "worst-pair={min_mean_gain_vs_peer_z14_z175_pct:+.2f}% "
            "mean-all={mean_gain_vs_all_peers_z14_z175_pct:+.2f}% "
            "z.75 vs budget={gain_z075_vs_budgeted_pct:+.2f}% "
            "z1.4={gain_z14_vs_budgeted_pct:+.2f}% z1.75={gain_z175_vs_budgeted_pct:+.2f}%".format(**row)
        )


if __name__ == "__main__":
    main()
