param(
    [string]$OutputDir = 'results\z175_targeted_confirmation',
    [int]$SeedStart = 1901
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    if ((Test-Path $OutputDir) -and
        (Get-ChildItem $OutputDir -Filter '*_raw.csv' -Recurse -ErrorAction SilentlyContinue)) {
        throw "Refusing to overwrite targeted confirmation in $OutputDir. Choose a new output directory."
    }
    New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
    $exe = Join-Path $env:TEMP 'adaptive_hashjoin_z175_target.exe'
    g++ -O3 -std=c++17 -Wall -Wextra -Wpedantic -Werror -fopenmp src\main.cpp -o $exe
    if ($LASTEXITCODE -ne 0) { throw 'Compilation failed.' }
    & $exe --self-test
    if ($LASTEXITCODE -ne 0) { throw 'Scheduler correctness tests failed.' }

    foreach ($seed in $SeedStart..($SeedStart + 7)) {
        $seedR = 1220000001 + (1009 * $seed)
        $seedS = 1320000001 + (9176 * $seed)
        $label = "z175_seed${seed}"
        & $exe --r-size 250000 --s-size 4000000 --key-range 250000 --partitions 1024 `
            --threads 4 --chunk-size 256 --tasks-per-thread 4 --split-factor 3.0 `
            --queue-batch-size 1 --cost-samples 16 --steal-threshold-multiplier 4 `
            --repeats 7 --skews 1.75 --seed-r $seedR --seed-s $seedS `
            --csv (Join-Path $OutputDir "${label}_summary.csv") `
            --raw-csv (Join-Path $OutputDir "${label}_raw.csv")
        if ($LASTEXITCODE -ne 0) { throw "z=1.75 targeted confirmation failed: $label" }
    }
    python scripts\analyze_experiments.py (Join-Path $OutputDir '*_raw.csv') `
        --out-dir (Join-Path $OutputDir 'analysis')
    if ($LASTEXITCODE -ne 0) { throw 'Targeted confirmation analysis failed.' }
} finally {
    Pop-Location
}
