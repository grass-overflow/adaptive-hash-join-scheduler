#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
RESULT_DIR="${1:-final_confirmation_rerun}"
if [[ -d "$RESULT_DIR" ]] && compgen -G "$RESULT_DIR/confirm_seed_*.csv" >/dev/null; then
  echo "Refusing to overwrite existing result files in $RESULT_DIR. Pass a new output directory as the first argument." >&2
  exit 1
fi
g++ -O3 -std=c++17 -Wall -Wextra -Wpedantic -Werror -fopenmp src/main.cpp -o hashjoin
mkdir -p "$RESULT_DIR"
# Independent seeds 35--42. The task budget and primary Zipf condition are locked.
for i in $(seq 35 42); do
  seed_r=$((123456789 + 1009 * i))
  seed_s=$((987654321 + 9176 * i))
  out="$RESULT_DIR/confirm_seed_${i}.csv"
  echo "=== Independent confirmation seed $i (R=$seed_r, S=$seed_s) ==="
  OMP_PROC_BIND=close OMP_PLACES=cores ./hashjoin --r-size 250000 --s-size 4000000 --key-range 250000 --partitions 1024 --threads 4 --chunk-size 1024 --tasks-per-thread 32 --split-factor 2.5 --repeats 7 --skews 1.75 --seed-r "$seed_r" --seed-s "$seed_s" --csv "$out"
  python3 - "$out" <<'PY'
import csv,sys
with open(sys.argv[1], newline='') as f: rows=list(csv.DictReader(f))
assert len(rows)==4, f'expected four algorithm rows, got {len(rows)}'
assert all(r['correct']=='1' for r in rows), 'correctness failure'
PY
done
set +e
python3 scripts/analyze_validation.py "$RESULT_DIR/confirm_seed_*.csv" --primary-skew 1.75 --out "$RESULT_DIR/confirmation_summary.csv"
status=$?
set -e
if [[ $status -eq 2 ]]; then echo 'Correctness passed; the extreme-skew performance claim was NOT statistically validated.'; exit 0; fi
exit "$status"
