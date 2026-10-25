param([string]$OutputDir = 'results\adaptive_sweep_v3')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    if ((Test-Path $OutputDir) -and
        (Get-ChildItem $OutputDir -Filter '*_raw.csv' -Recurse -ErrorAction SilentlyContinue)) {
        throw "Refusing to overwrite adaptive sweep data in $OutputDir. Choose a new output directory."
    }
    New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
    $exe = Join-Path $env:TEMP 'adaptive_hashjoin_task_sweep.exe'
    g++ -O3 -std=c++17 -Wall -Wextra -Wpedantic -Werror -fopenmp src\main.cpp -o $exe
    if ($LASTEXITCODE -ne 0) { throw 'Compilation failed.' }
    & $exe --self-test
    if ($LASTEXITCODE -ne 0) { throw 'Scheduler correctness tests failed.' }

    foreach ($chunk in @(256, 512, 1024)) {
        foreach ($budget in @(4, 8, 16)) {
            foreach ($split in @(2.0, 3.0, 4.0)) {
                foreach ($seed in 1601..1603) {
                    $seedR = 820000001 + (1009 * $seed)
                    $seedS = 920000001 + (9176 * $seed)
                    $label = "tune_c${chunk}_b${budget}_s$($split.ToString('0.0').Replace('.', 'p'))_seed${seed}"
                    Write-Host "`n=== $label ==="
                    & $exe --r-size 250000 --s-size 4000000 --key-range 250000 --partitions 1024 `
                        --threads 4 --chunk-size $chunk --tasks-per-thread $budget `
                        --split-factor $split --queue-batch-size 1 --cost-samples 16 `
                        --steal-threshold-multiplier 4 --repeats 3 --skews '0.75,1.4,1.75' `
                        --seed-r $seedR --seed-s $seedS `
                        --csv (Join-Path $OutputDir "${label}_summary.csv") `
                        --raw-csv (Join-Path $OutputDir "${label}_raw.csv")
                    if ($LASTEXITCODE -ne 0) { throw "Adaptive task sweep failed: $label" }
                }
            }
        }
    }
    python scripts\summarize_adaptive_sweep.py $OutputDir
    if ($LASTEXITCODE -ne 0) { throw 'Adaptive parameter ranking failed.' }

    $selected = Get-Content (Join-Path $OutputDir 'selected_adaptive_config.json') -Raw | ConvertFrom-Json
    $confirmationDir = Join-Path $OutputDir 'confirmation'
    New-Item -ItemType Directory -Force -Path $confirmationDir | Out-Null
    foreach ($seed in 1701..1708) {
        $seedR = 920000001 + (1009 * $seed)
        $seedS = 1020000001 + (9176 * $seed)
        $label = "holdout_seed${seed}"
        & $exe --r-size 250000 --s-size 4000000 --key-range 250000 --partitions 1024 `
            --threads 4 --chunk-size $selected.chunk_size `
            --tasks-per-thread $selected.tasks_per_thread --split-factor $selected.split_factor `
            --queue-batch-size 1 --cost-samples 16 --steal-threshold-multiplier 4 `
            --repeats 7 --skews '1.4,1.75' --seed-r $seedR --seed-s $seedS `
            --csv (Join-Path $confirmationDir "${label}_summary.csv") `
            --raw-csv (Join-Path $confirmationDir "${label}_raw.csv")
        if ($LASTEXITCODE -ne 0) { throw "Adaptive holdout failed: $label" }
    }
    python scripts\analyze_experiments.py (Join-Path $confirmationDir '*_raw.csv') `
        --out-dir (Join-Path $confirmationDir 'analysis')
    if ($LASTEXITCODE -ne 0) { throw 'Adaptive holdout analysis failed.' }
} finally {
    Pop-Location
}
