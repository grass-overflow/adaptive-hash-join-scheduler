param([string]$OutputDir = 'results\final_run')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    if ((Test-Path $OutputDir) -and
        (Get-ChildItem $OutputDir -Filter '*_raw.csv' -ErrorAction SilentlyContinue)) {
        throw "Refusing to overwrite raw measurements in $OutputDir. Choose a new output directory."
    }
    New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
    $exe = Join-Path $env:TEMP 'adaptive_hashjoin_experiments.exe'
    g++ -O3 -std=c++17 -Wall -Wextra -Wpedantic -Werror -fopenmp src\main.cpp -o $exe
    if ($LASTEXITCODE -ne 0) { throw 'Compilation failed.' }

    $sizes = @(20000, 80000, 250000)
    $gridSeeds = @(401, 402, 403)
    foreach ($rSize in $sizes) {
        foreach ($seed in $gridSeeds) {
            $sSize = 16 * $rSize
            $seedR = 310000001 + (1009 * $seed)
            $seedS = 910000001 + (9176 * $seed)
            $base = "grid_r${rSize}_seed${seed}"
            Write-Host "`n=== Grid R=$rSize S=$sSize, seed=$seed, T=4 ==="
            & $exe --r-size $rSize --s-size $sSize --key-range $rSize --partitions 1024 `
                --threads 4 --chunk-size 1024 --tasks-per-thread 32 --split-factor 2.5 `
                --repeats 3 --skews '0,0.75,1.4,1.75' --seed-r $seedR --seed-s $seedS `
                --csv (Join-Path $OutputDir "${base}_summary.csv") `
                --raw-csv (Join-Path $OutputDir "${base}_raw.csv")
            if ($LASTEXITCODE -ne 0) { throw "Grid run failed: $base" }
        }
    }

    foreach ($seed in 501..508) {
        $seedR = 510000001 + (1009 * $seed)
        $seedS = 610000001 + (9176 * $seed)
        $base = "confirm_z175_seed${seed}"
        Write-Host "`n=== Held-out high-skew confirmation seed=$seed, T=4 ==="
        & $exe --r-size 250000 --s-size 4000000 --key-range 250000 --partitions 1024 `
            --threads 4 --chunk-size 1024 --tasks-per-thread 32 --split-factor 2.5 `
            --repeats 7 --skews 1.75 --seed-r $seedR --seed-s $seedS `
            --csv (Join-Path $OutputDir "${base}_summary.csv") `
            --raw-csv (Join-Path $OutputDir "${base}_raw.csv")
        if ($LASTEXITCODE -ne 0) { throw "Confirmation run failed: $base" }
    }

    $singleSeedR = 710000001
    $singleSeedS = 810000001
    & $exe --r-size 250000 --s-size 4000000 --key-range 250000 --partitions 1024 `
        --threads 1 --chunk-size 1024 --tasks-per-thread 32 --split-factor 2.5 `
        --repeats 5 --skews '0,1.75' --seed-r $singleSeedR --seed-s $singleSeedS `
        --csv (Join-Path $OutputDir 'single_thread_summary.csv') `
        --raw-csv (Join-Path $OutputDir 'single_thread_raw.csv')
    if ($LASTEXITCODE -ne 0) { throw 'Single-thread comparison failed.' }

    $diagnosticsDir = Join-Path $OutputDir 'diagnostics'
    New-Item -ItemType Directory -Force -Path $diagnosticsDir | Out-Null
    & $exe --r-size 0 --s-size 3 --key-range 1 --partitions 16 --threads 4 `
        --chunk-size 1 --tasks-per-thread 2 --split-factor 2.5 --repeats 5 --skews 0 `
        --csv (Join-Path $diagnosticsDir 'tiny_gate_summary.csv') `
        --raw-csv (Join-Path $diagnosticsDir 'tiny_gate_raw.csv')
    if ($LASTEXITCODE -ne 0) { throw 'Tiny-work steal-gate diagnostic failed.' }

    $gridPattern = Join-Path $OutputDir '*_raw.csv'
    python scripts\analyze_experiments.py $gridPattern --out-dir (Join-Path $OutputDir 'analysis')
    if ($LASTEXITCODE -ne 0) { throw 'Raw-result analysis failed.' }
    $confirmationPattern = Join-Path $OutputDir 'confirm_z175_seed*_raw.csv'
    python scripts\analyze_experiments.py $confirmationPattern `
        --out-dir (Join-Path $OutputDir 'confirmation_analysis')
    if ($LASTEXITCODE -ne 0) { throw 'Held-out confirmation analysis failed.' }
} finally {
    Pop-Location
}
