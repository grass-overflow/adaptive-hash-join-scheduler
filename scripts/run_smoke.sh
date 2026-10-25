#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p results
g++ -O3 -std=c++17 -Wall -Wextra -Wpedantic -Werror -fopenmp src/main.cpp -o hashjoin
./hashjoin --self-test
./hashjoin --r-size 10000 --s-size 160000 --key-range 10000 --partitions 1024 --threads 4 --chunk-size 1024 --tasks-per-thread 32 --split-factor 2.5 --repeats 2 --skews 0,0.9,1.4,1.75 --csv results/smoke_summary.csv --raw-csv results/smoke_raw.csv
python3 - <<'PY'
import csv
with open('results/smoke_summary.csv', newline='') as f:
    rows = list(csv.DictReader(f))
assert len(rows) == 32, f'expected 32 summary rows, found {len(rows)}'
assert all(row['correct'] == '1' for row in rows), 'join result differs from oracle'
assert {row['algorithm'] for row in rows} == {
    'radix_static', 'radix_dynamic_coarse', 'paper_fine_grained', 'novelty_budgeted',
    'cost_aware_no_steal', 'cost_aware_ungated_steal', 'novelty_cost_gated_steal',
    'sequential_reference'
}
with open('results/smoke_raw.csv', newline='') as f:
    raw = list(csv.DictReader(f))
assert len(raw) == 64, f'expected 64 raw trial rows, found {len(raw)}'
assert all(row['correct'] == '1' for row in raw), 'raw trial correctness failure'
print('PASS: all 32 summary and 64 raw smoke rows matched the sequential oracle.')
PY
