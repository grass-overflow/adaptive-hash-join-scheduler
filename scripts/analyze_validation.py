#!/usr/bin/env python3
"""Paired cluster-bootstrap analysis of held-out hash-join validation runs."""
import argparse
import csv
import glob
import math
import random
import statistics
import sys
from pathlib import Path

BASELINE = "paper_fine_grained"
CANDIDATE = "novelty_budgeted"
BOOTSTRAPS = 20000


def pct_gain(base: float, candidate: float) -> float:
    return 100.0 * (base - candidate) / base if base > 0 else math.nan


def bootstrap_mean_ci(values, n_boot=BOOTSTRAPS, seed=20261009):
    rng = random.Random(seed)
    n = len(values)
    if n == 0:
        return math.nan, math.nan
    means = []
    for _ in range(n_boot):
        means.append(statistics.mean(values[rng.randrange(n)] for _ in range(n)))
    means.sort()
    lo = means[int(0.025 * n_boot)]
    hi = means[min(n_boot - 1, int(0.975 * n_boot))]
    return lo, hi


def read_rows(pattern):
    paths = sorted(glob.glob(pattern))
    if not paths:
        raise ValueError(f"No CSV files matched: {pattern}")
    per_seed = {}
    for path in paths:
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        if not rows:
            raise ValueError(f"No data rows in {path}")
        if any(row.get("correct") != "1" for row in rows):
            raise ValueError(f"Correctness failure recorded in {path}; refusing timing analysis")
        seed_keys = {(r.get("seed_r"), r.get("seed_s")) for r in rows}
        if len(seed_keys) != 1:
            raise ValueError(f"Mixed seeds in {path}")
        seed = next(iter(seed_keys))
        if seed in per_seed:
            raise ValueError(f"Duplicate dataset seed {seed} across files")
        seen = {(r["skew"], r["algorithm"]) for r in rows}
        if len(seen) != len(rows):
            raise ValueError(f"Duplicate skew/algorithm rows in {path}")
        per_seed[seed] = rows
    return per_seed


def by_skew(rows):
    return {(str(float(r["skew"])), r["algorithm"]): r for r in rows}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pattern", help="glob for CSV files from independent dataset seeds")
    ap.add_argument("--out", default="validation_runs/validation_summary.csv")
    ap.add_argument("--primary-skew", default="1.4", help="declared primary Zipf exponent (default: 1.4)")
    args = ap.parse_args()
    primary_skew = str(float(args.primary_skew))
    data = read_rows(args.pattern)
    if len(data) < 8:
        print(f"WARNING: only {len(data)} independent seeds; predeclared minimum is 8.")
    seeds = sorted(data)
    maps = {seed: by_skew(rows) for seed, rows in data.items()}

    primary_gains = []
    for seed in seeds:
        d = maps[seed]
        fixed = d.get((primary_skew, BASELINE))
        novel = d.get((primary_skew, CANDIDATE))
        if fixed is None or novel is None:
            raise ValueError(f"Missing primary z={primary_skew} rows for seed {seed}")
        primary_gains.append(pct_gain(float(fixed["e2e_median_s"]), float(novel["e2e_median_s"])))
    primary_mean = statistics.mean(primary_gains)
    primary_lo, primary_hi = bootstrap_mean_ci(primary_gains)

    print("PAIRED HELD-OUT VALIDATION: bounded task budget vs fixed-chunk paper-inspired strategy")
    print(f"Independent dataset seeds: {len(seeds)}")
    print(f"Primary endpoint: end-to-end median improvement at Zipf z={primary_skew}")
    print(f"Mean paired improvement: {primary_mean:+.2f}%")
    print(f"95% cluster-bootstrap CI: [{primary_lo:+.2f}%, {primary_hi:+.2f}%]")
    passed = len(seeds) >= 8 and primary_mean > 0 and primary_lo > 0
    print(f"RESULT: PERFORMANCE EVIDENCE PASSES for the declared z={primary_skew} condition." if passed else
          "RESULT: PERFORMANCE CLAIM NOT VALIDATED; do not claim a statistically supported win.")

    skew_values = sorted({str(float(r["skew"])) for rs in data.values() for r in rs}, key=float)
    summary = []
    print("\nPer-skew paired comparisons (positive gain means the named algorithm was faster):")
    print(f"{'skew':>6} {'comparison':>31} {'mean gain':>12} {'positive seeds':>15} {'95% CI':>25}")
    for skew in skew_values:
        for base_name in ("radix_static", "radix_dynamic_coarse", BASELINE):
            gains = []
            for seed in seeds:
                d = maps[seed]
                b = d.get((skew, base_name)); n = d.get((skew, CANDIDATE))
                if b is None or n is None:
                    continue
                gains.append(pct_gain(float(b["e2e_median_s"]), float(n["e2e_median_s"])))
            if not gains:
                continue
            if skew == primary_skew and base_name == BASELINE:
                lo, hi = primary_lo, primary_hi
            else:
                lo, hi = bootstrap_mean_ci(gains, seed=20261009 + int(float(skew)*100) + len(base_name))
            mean = statistics.mean(gains)
            label = f"{CANDIDATE} vs {base_name}"
            print(f"{float(skew):6.2f} {label:>31} {mean:+11.2f}% {sum(g>0 for g in gains):>7}/{len(gains):<7} [{lo:+9.2f}%, {hi:+9.2f}%]")
            summary.append({"skew": float(skew), "comparison": label, "seeds": len(gains),
                            "mean_gain_pct": mean, "positive_seeds": sum(g>0 for g in gains),
                            "ci95_low_pct": lo, "ci95_high_pct": hi})

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["skew", "comparison", "seeds", "mean_gain_pct", "positive_seeds", "ci95_low_pct", "ci95_high_pct"])
        writer.writeheader(); writer.writerows(summary)
    print(f"Summary written to {out}")
    return 0 if passed else 2

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
