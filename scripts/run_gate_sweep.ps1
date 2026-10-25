param([string]$OutputDir = 'results\gate_sweep_v1')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    if ((Test-Path $OutputDir) -and
        (Get-ChildItem $OutputDir -Filter '*_raw.csv' -Recurse -ErrorAction SilentlyContinue)) {
        throw "Refusing to overwrite gate sweep data in $OutputDir. Choose a new output directory."
    }
    New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
    $exe = Join-Path $env:TEMP 'adaptive_hashjoin_gate_sweep.exe'
    g++ -O3 -std=c++17 -Wall -Wextra -Wpedantic -Werror -fopenmp src\main.cpp -o $exe
    if ($LASTEXITCODE -ne 0) { throw 'Compilation failed.' }
    & $exe --self-test
    if ($LASTEXITCODE -ne 0) { throw 'Scheduler correctness tests failed.' }

    foreach ($multiplier in @(1, 2, 4, 8, 16, 32)) {
        foreach ($seed in 1301..1303) {
            $seedR = 620000001 + (1009 * $seed)
            $seedS = 720000001 + (9176 * $seed)
            $label = "tune_gate$($multiplier)_seed${seed}"
            Write-Host "`n=== $label ==="
            & $exe --r-size 250000 --s-size 4000000 --key-range 250000 --partitions 1024 `
                --threads 4 --chunk-size 512 --tasks-per-thread 8 --split-factor 4.0 `
                --queue-batch-size 1 --cost-samples 16 `
                --steal-threshold-multiplier $multiplier --repeats 5 --skews '1.4,1.75' `
                --seed-r $seedR --seed-s $seedS `
                --csv (Join-Path $OutputDir "${label}_summary.csv") `
                --raw-csv (Join-Path $OutputDir "${label}_raw.csv")
            if ($LASTEXITCODE -ne 0) { throw "Gate tuning run failed: $label" }
        }
    }
    python scripts\summarize_gate_sweep.py $OutputDir
    if ($LASTEXITCODE -ne 0) { throw 'Gate parameter selection failed.' }
} finally {
    Pop-Location
}
