param([string]$OutputDir = 'results\estimator_sweep_batch_v2')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    if ((Test-Path $OutputDir) -and
        (Get-ChildItem $OutputDir -Filter '*_raw.csv' -Recurse -ErrorAction SilentlyContinue)) {
        throw "Refusing to overwrite estimator sweep data in $OutputDir. Choose a new output directory."
    }
    New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
    $exe = Join-Path $env:TEMP 'adaptive_hashjoin_estimator_sweep.exe'
    g++ -O3 -std=c++17 -Wall -Wextra -Wpedantic -Werror -fopenmp src\main.cpp -o $exe
    if ($LASTEXITCODE -ne 0) { throw 'Compilation failed.' }
    & $exe --self-test
    if ($LASTEXITCODE -ne 0) { throw 'Scheduler correctness tests failed.' }

    foreach ($samples in @(2, 4, 8, 16, 32)) {
        foreach ($batch in @(1, 16)) {
            foreach ($seed in 601..603) {
                $seedR = 120000001 + (1009 * $seed)
                $seedS = 220000001 + (9176 * $seed)
                $label = "tune_n${samples}_q${batch}_seed${seed}"
                Write-Host "`n=== $label ==="
                & $exe --r-size 250000 --s-size 4000000 --key-range 250000 --partitions 1024 `
                    --threads 4 --chunk-size 512 --tasks-per-thread 8 --split-factor 4.0 `
                    --queue-batch-size $batch --cost-samples $samples --repeats 3 `
                    --skews '0.75,1.4,1.75' --seed-r $seedR --seed-s $seedS `
                    --csv (Join-Path $OutputDir "${label}_summary.csv") `
                    --raw-csv (Join-Path $OutputDir "${label}_raw.csv")
                if ($LASTEXITCODE -ne 0) { throw "Estimator tuning run failed: $label" }
            }
        }
    }
    python scripts\summarize_estimator_sweep.py $OutputDir
    if ($LASTEXITCODE -ne 0) { throw 'Estimator parameter selection failed.' }
    $selected = Get-Content (Join-Path $OutputDir 'selected_estimator_config.json') -Raw | ConvertFrom-Json

    $confirmationDir = Join-Path $OutputDir 'confirmation'
    New-Item -ItemType Directory -Force -Path $confirmationDir | Out-Null
    foreach ($seed in 1101..1108) {
        $seedR = 320000001 + (1009 * $seed)
        $seedS = 420000001 + (9176 * $seed)
        $label = "holdout_seed${seed}"
        Write-Host "`n=== Frozen estimator config confirmation: $label ==="
        & $exe --r-size 250000 --s-size 4000000 --key-range 250000 --partitions 1024 `
            --threads 4 --chunk-size 512 --tasks-per-thread 8 --split-factor 4.0 `
            --queue-batch-size $selected.queue_batch_size --cost-samples $selected.cost_samples `
            --repeats 7 --skews '1.4,1.75' --seed-r $seedR --seed-s $seedS `
            --csv (Join-Path $confirmationDir "${label}_summary.csv") `
            --raw-csv (Join-Path $confirmationDir "${label}_raw.csv")
        if ($LASTEXITCODE -ne 0) { throw "Frozen estimator confirmation failed: $label" }
    }
    python scripts\analyze_experiments.py (Join-Path $confirmationDir '*_raw.csv') `
        --out-dir (Join-Path $confirmationDir 'analysis')
    if ($LASTEXITCODE -ne 0) { throw 'Estimator holdout analysis failed.' }
} finally {
    Pop-Location
}
