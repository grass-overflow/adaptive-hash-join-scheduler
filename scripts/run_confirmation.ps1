param([string]$OutputDir = 'final_confirmation_rerun')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    if ((Test-Path $OutputDir) -and (Get-ChildItem $OutputDir -Filter 'confirm_seed_*.csv' -ErrorAction SilentlyContinue)) {
        throw "Refusing to overwrite existing result files in $OutputDir. Pass a new output directory."
    }
    g++ -O3 -std=c++17 -Wall -Wextra -Wpedantic -Werror -fopenmp src/main.cpp -o hashjoin.exe
    if ($LASTEXITCODE -ne 0) { throw 'Compilation failed.' }
    New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
    # Independent seeds 35--42. The task budget and primary Zipf condition are locked.
    for ($i = 35; $i -le 42; $i++) {
        $seedR = 123456789 + (1009 * $i)
        $seedS = 987654321 + (9176 * $i)
        $out = Join-Path $OutputDir "confirm_seed_$i.csv"
        Write-Host "`n=== Independent confirmation seed $i (R=$seedR, S=$seedS) ==="
        .\hashjoin.exe --r-size 250000 --s-size 4000000 --key-range 250000 --partitions 1024 --threads 4 --chunk-size 1024 --tasks-per-thread 32 --split-factor 2.5 --repeats 7 --skews 1.75 --seed-r $seedR --seed-s $seedS --csv $out
        if ($LASTEXITCODE -ne 0) { throw "Benchmark failed for seed $i." }
        $rows = Import-Csv $out
        if ($rows.Count -ne 4) { throw "Expected four algorithm rows in $out; got $($rows.Count)." }
        if (@($rows | Where-Object { $_.correct -ne '1' }).Count -gt 0) { throw "Correctness failed for seed $i; stopping." }
    }
    python .\scripts\analyze_validation.py "$OutputDir\confirm_seed_*.csv" --primary-skew 1.75 --out (Join-Path $OutputDir 'confirmation_summary.csv')
    if ($LASTEXITCODE -eq 2) { Write-Warning 'Correctness passed, but the extreme-skew performance claim was not statistically validated.' }
    elseif ($LASTEXITCODE -ne 0) { throw 'Validation analysis failed.' }
} finally { Pop-Location }
