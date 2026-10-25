param(
    [string]$OutputDir = 'results\current_source_grid',
    [int]$SeedStart = 2201
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    if ((Test-Path $OutputDir) -and
        (Get-ChildItem $OutputDir -Filter '*_raw.csv' -Recurse -ErrorAction SilentlyContinue)) {
        throw "Refusing to overwrite current-source measurements in $OutputDir. Choose a new output directory."
    }
    New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
    $exe = Join-Path $env:TEMP 'adaptive_hashjoin_current_grid.exe'
    g++ -O3 -std=c++17 -Wall -Wextra -Wpedantic -Werror -fopenmp src\main.cpp -o $exe
    if ($LASTEXITCODE -ne 0) { throw 'Compilation failed.' }
    & $exe --self-test
    if ($LASTEXITCODE -ne 0) { throw 'Scheduler correctness tests failed.' }

    foreach ($rSize in @(20000, 80000, 250000)) {
        foreach ($seed in $SeedStart..($SeedStart + 2)) {
            $sSize = 16 * $rSize
            $seedR = 1420000001 + (1009 * $seed)
            $seedS = 1520000001 + (9176 * $seed)
            $label = "grid_r${rSize}_seed${seed}"
            & $exe --r-size $rSize --s-size $sSize --key-range $rSize --partitions 1024 `
                --threads 4 --chunk-size 256 --tasks-per-thread 4 --split-factor 3.0 `
                --queue-batch-size 1 --cost-samples 16 --steal-threshold-multiplier 4 `
                --repeats 3 --skews '0,0.75,1.4,1.75' --seed-r $seedR --seed-s $seedS `
                --csv (Join-Path $OutputDir "${label}_summary.csv") `
                --raw-csv (Join-Path $OutputDir "${label}_raw.csv")
            if ($LASTEXITCODE -ne 0) { throw "Current-source grid run failed: $label" }
        }
    }

    python scripts\analyze_experiments.py (Join-Path $OutputDir '*_raw.csv') `
        --out-dir (Join-Path $OutputDir 'analysis')
    if ($LASTEXITCODE -ne 0) { throw 'Current-source grid analysis failed.' }
} finally {
    Pop-Location
}
