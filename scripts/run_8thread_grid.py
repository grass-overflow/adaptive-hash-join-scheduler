#!/usr/bin/env python3
"""Run 8-thread benchmark across all 7 skews (0, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75)
with 3 independent seeds and Balkesen et al. standard chunk size (256).
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / "hashjoin.exe"
OUT_DIR = ROOT / "results" / "grid_8threads"
OUT_DIR.mkdir(parents=True, exist_ok=True)

SKEWS = "0,0.5,0.75,1.0,1.25,1.5,1.75"
SEEDS = [401, 402, 403]

def run():
    print(f"=== Running 8-Thread Grid ({SKEWS}) with 3 seeds ===")
    for seed in SEEDS:
        seed_r = 310000001 + (1009 * seed)
        seed_s = 910000001 + (9176 * seed)
        base = f"grid8t_r250000_seed{seed}"
        csv_path = OUT_DIR / f"{base}_summary.csv"
        raw_path = OUT_DIR / f"{base}_raw.csv"
        cmd = [
            str(EXE),
            "--r-size", "250000",
            "--s-size", "4000000",
            "--key-range", "250000",
            "--partitions", "1024",
            "--threads", "8",
            "--chunk-size", "256",
            "--tasks-per-thread", "32",
            "--split-factor", "2.5",
            "--repeats", "3",
            "--skews", SKEWS,
            "--seed-r", str(seed_r),
            "--seed-s", str(seed_s),
            "--csv", str(csv_path),
            "--raw-csv", str(raw_path),
        ]
        print(f"Running Seed {seed} on 8 threads...")
        res = subprocess.run(cmd, cwd=ROOT)
        if res.returncode != 0:
            raise RuntimeError(f"Run failed for {base}")

    print("\n=== Analyzing 8-Thread Grid ===")
    analysis_dir = OUT_DIR / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "analyze_experiments.py"),
        str(OUT_DIR / "grid8t_*_raw.csv"),
        "--out-dir", str(analysis_dir),
    ]
    subprocess.run(cmd, cwd=ROOT, check=True)
    print("8-Thread grid completed successfully!")

if __name__ == "__main__":
    run()
