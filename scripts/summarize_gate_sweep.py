#!/usr/bin/env python3
"""Rank steal-gate scales by paired gain over every peer at high skew."""
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    paths = sorted(glob.glob(str(args.directory / "tune_*_raw.csv")))
    if not paths:
        raise ValueError(f"No gate-tuning raw CSV files in {args.directory}")
    grouped = defaultdict(list)
    for path in paths:
        with open(path, newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        for row in rows:
            if row["correct"] != "1" or row["result"] != row["expected_result"]:
                raise ValueError(f"Correctness failure in {path}; refusing gate analysis.")
            if row["algorithm"] == "sequential_reference":
                continue
            config = float(row["steal_threshold_multiplier"])
            seed = (row["seed_r"], row["seed_s"])
            grouped[config, float(row["skew"]), seed, row["algorithm"]].append(float(row["e2e_s"]))

    medians = {key: statistics.median(values) for key, values in grouped.items()}
    configs = sorted({key[0] for key in medians})
    result = []
    for multiplier in configs:
        per_skew = {}
        for skew in (1.4, 1.75):
            seeds = sorted({key[2] for key in medians if key[0] == multiplier and key[1] == skew})
            gains_by_peer = defaultdict(list)
            for seed in seeds:
                candidate = medians.get((multiplier, skew, seed, FULL))
                if candidate is None:
                    raise ValueError(f"Missing full policy, multiplier={multiplier}, z={skew}, seed={seed}")
                for peer in PEERS:
                    baseline = medians.get((multiplier, skew, seed, peer))
                    if baseline is None:
                        raise ValueError(f"Missing {peer}, multiplier={multiplier}, z={skew}, seed={seed}")
                    gains_by_peer[peer].append(100.0 * (baseline - candidate) / baseline)
            per_skew[skew] = {
                peer: statistics.mean(values) for peer, values in gains_by_peer.items()
            }
        all_target_gains = [
            gain for skew in (1.4, 1.75) for gain in per_skew[skew].values()
        ]
        row = {
            "steal_threshold_multiplier": multiplier,
            "min_gain_over_all_peers_z14_z175_pct": min(all_target_gains),
            "mean_gain_over_all_peers_z14_z175_pct": statistics.mean(all_target_gains),
            "z14_gain_vs_budgeted_pct": per_skew[1.4]["novelty_budgeted"],
            "z175_gain_vs_budgeted_pct": per_skew[1.75]["novelty_budgeted"],
            "z14_gain_vs_ungated_pct": per_skew[1.4]["cost_aware_ungated_steal"],
            "z175_gain_vs_ungated_pct": per_skew[1.75]["cost_aware_ungated_steal"],
            "seeds_per_skew": min(
                len({key[2] for key in medians if key[0] == multiplier and key[1] == skew})
                for skew in (1.4, 1.75)
            ),
        }
        result.append(row)
    result.sort(
        key=lambda row: (
            row["min_gain_over_all_peers_z14_z175_pct"],
            row["mean_gain_over_all_peers_z14_z175_pct"],
        ),
        reverse=True,
    )
    with open(args.directory / "gate_ranking.csv", "w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(result[0]))
        writer.writeheader()
        writer.writerows(result)
    with open(args.directory / "selected_gate_config.json", "w", encoding="utf-8") as stream:
        json.dump(result[0], stream, indent=2)
        stream.write("\n")
    print("Objective: maximize the minimum paired mean gain against every parallel peer")
    print("over z=1.4 and z=1.75; tuning uses paired per-seed repetition medians.")
    for row in result:
        print(
            "multiplier={steal_threshold_multiplier:g} min-all={min_gain_over_all_peers_z14_z175_pct:+.2f}% "
            "mean-all={mean_gain_over_all_peers_z14_z175_pct:+.2f}% "
            "budgeted[z1.4,z1.75]=[{z14_gain_vs_budgeted_pct:+.2f},{z175_gain_vs_budgeted_pct:+.2f}] "
            "ungated=[{z14_gain_vs_ungated_pct:+.2f},{z175_gain_vs_ungated_pct:+.2f}]".format(**row)
        )


if __name__ == "__main__":
    main()
