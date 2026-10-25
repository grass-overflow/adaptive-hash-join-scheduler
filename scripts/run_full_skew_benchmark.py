#!/usr/bin/env python3
"""Run full skew spectrum (z in 0, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75)
across sizes (20k, 80k, 250k) and thread scaling (1, 2, 4) using hashjoin.exe.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / "hashjoin.exe"
OUT_DIR = ROOT / "results" / "full_skew_grid"
OUT_DIR.mkdir(parents=True, exist_ok=True)

SKEWS = "0,0.5,0.75,1.0,1.25,1.5,1.75"
SIZES = [20000, 80000, 250000]
SEEDS = [401, 402, 403]

def run_grid():
    print(f"=== Running Full Skew Grid ({SKEWS}) ===")
    for r_size in SIZES:
        s_size = 16 * r_size
        for seed in SEEDS:
            seed_r = 310000001 + (1009 * seed)
            seed_s = 910000001 + (9176 * seed)
            base = f"grid_r{r_size}_seed{seed}"
            csv_path = OUT_DIR / f"{base}_summary.csv"
            raw_path = OUT_DIR / f"{base}_raw.csv"
            cmd = [
                str(EXE),
                "--r-size", str(r_size),
                "--s-size", str(s_size),
                "--key-range", str(r_size),
                "--partitions", "1024",
                "--threads", "4",
                "--chunk-size", "1024",
                "--tasks-per-thread", "32",
                "--split-factor", "2.5",
                "--repeats", "3",
                "--skews", SKEWS,
                "--seed-r", str(seed_r),
                "--seed-s", str(seed_s),
                "--csv", str(csv_path),
                "--raw-csv", str(raw_path),
            ]
            print(f"Running R={r_size}, seed={seed}...")
            res = subprocess.run(cmd, cwd=ROOT)
            if res.returncode != 0:
                raise RuntimeError(f"Run failed for {base}")

    print("\n=== Running Thread Scalability Sweep (T=1, 2, 4) ===")
    thread_out = OUT_DIR / "threads"
    thread_out.mkdir(parents=True, exist_ok=True)
    for t in [1, 2, 4]:
        for seed in [401, 402, 403]:
            seed_r = 310000001 + (1009 * seed)
            seed_s = 910000001 + (9176 * seed)
            base = f"threads_t{t}_seed{seed}"
            csv_path = thread_out / f"{base}_summary.csv"
            raw_path = thread_out / f"{base}_raw.csv"
            cmd = [
                str(EXE),
                "--r-size", "250000",
                "--s-size", "4000000",
                "--key-range", "250000",
                "--partitions", "1024",
                "--threads", str(t),
                "--chunk-size", "1024",
                "--tasks-per-thread", "32",
                "--split-factor", "2.5",
                "--repeats", "3",
                "--skews", SKEWS,
                "--seed-r", str(seed_r),
                "--seed-s", str(seed_s),
                "--csv", str(csv_path),
                "--raw-csv", str(raw_path),
            ]
            print(f"Running Threads={t}, seed={seed}...")
            res = subprocess.run(cmd, cwd=ROOT)
            if res.returncode != 0:
                raise RuntimeError(f"Run failed for {base}")

    print("\n=== Analyzing Experiments ===")
    analysis_dir = OUT_DIR / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "analyze_experiments.py"),
        str(OUT_DIR / "grid_*_raw.csv"),
        "--out-dir", str(analysis_dir),
    ]
    subprocess.run(cmd, cwd=ROOT, check=True)
    
    # Also analyze threads
    cmd_t = [
        sys.executable,
        str(ROOT / "scripts" / "analyze_experiments.py"),
        str(thread_out / "threads_*_raw.csv"),
        "--out-dir", str(thread_out / "analysis"),
    ]
    subprocess.run(cmd_t, cwd=ROOT, check=True)
    print("Full skew benchmark and analysis complete!")

if __name__ == "__main__":
    run_grid()
