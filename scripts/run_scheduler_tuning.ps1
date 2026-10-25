param([string]$OutputDir = 'results\adaptive_tuning_batch_v1')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    if ((Test-Path $OutputDir) -and
        (Get-ChildItem $OutputDir -Filter '*_raw.csv' -Recurse -ErrorAction SilentlyContinue)) {
        throw "Refusing to overwrite tuning measurements in $OutputDir. Choose a new output directory."
    }
    New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
    $exe = Join-Path $env:TEMP 'adaptive_hashjoin_tuning.exe'
    g++ -O3 -std=c++17 -Wall -Wextra -Wpedantic -Werror -fopenmp src\main.cpp -o $exe
    if ($LASTEXITCODE -ne 0) { throw 'Compilation failed.' }
    & $exe --self-test
    if ($LASTEXITCODE -ne 0) { throw 'Scheduler correctness tests failed.' }

    $chunks = @(512, 1024, 2048)
    $budgets = @(8, 32, 64)
    $splitFactors = @(1.5, 2.5, 4.0)
    $batchSizes = @(1, 16)
    foreach ($chunk in $chunks) {
        foreach ($budget in $budgets) {
            foreach ($split in $splitFactors) {
                foreach ($batch in $batchSizes) {
                    $label = "tune_c${chunk}_b${budget}_s$($split.ToString('0.0').Replace('.', 'p'))_q${batch}"
                    Write-Host "`n=== $label ==="
                    & $exe --r-size 250000 --s-size 4000000 --key-range 250000 --partitions 1024 `
                        --threads 4 --chunk-size $chunk --tasks-per-thread $budget `
                        --split-factor $split --queue-batch-size $batch --repeats 3 `
                        --cost-samples 16 `
                        --skews '0.75,1.4,1.75' --seed-r 19002001 --seed-s 19003001 `
                        --csv (Join-Path $OutputDir "${label}_summary.csv") `
                        --raw-csv (Join-Path $OutputDir "${label}_raw.csv")
                    if ($LASTEXITCODE -ne 0) { throw "Tuning run failed: $label" }
                }
            }
        }
    }

    python scripts\summarize_scheduler_tuning.py $OutputDir
    if ($LASTEXITCODE -ne 0) { throw 'Parameter ranking failed.' }
    $selected = Get-Content (Join-Path $OutputDir 'selected_config.json') -Raw | ConvertFrom-Json
    $confirmationDir = Join-Path $OutputDir 'confirmation'
    New-Item -ItemType Directory -Force -Path $confirmationDir | Out-Null
    foreach ($seed in 701..708) {
        $seedR = 710000001 + (1009 * $seed)
        $seedS = 810000001 + (9176 * $seed)
        $label = "confirm_seed${seed}"
        Write-Host "`n=== Frozen config confirmation: $label ==="
        & $exe --r-size 250000 --s-size 4000000 --key-range 250000 --partitions 1024 `
            --threads 4 --chunk-size $selected.chunk_size `
            --tasks-per-thread $selected.tasks_per_thread --split-factor $selected.split_factor `
            --queue-batch-size $selected.queue_batch_size --cost-samples $selected.cost_samples --repeats 7 `
            --skews '0.75,1.4,1.75' --seed-r $seedR --seed-s $seedS `
            --csv (Join-Path $confirmationDir "${label}_summary.csv") `
            --raw-csv (Join-Path $confirmationDir "${label}_raw.csv")
        if ($LASTEXITCODE -ne 0) { throw "Confirmation run failed: $label" }
    }
    python scripts\analyze_experiments.py (Join-Path $confirmationDir '*_raw.csv') `
        --out-dir (Join-Path $confirmationDir 'analysis')
    if ($LASTEXITCODE -ne 0) { throw 'Frozen-configuration confirmation analysis failed.' }
} finally {
    Pop-Location
}
