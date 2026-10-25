param(
    [string]$OutputDir = 'results\r20k_skew_confirmation',
    [double]$Skew = 1.75,
    [int]$SeedStart = 2301
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    if ((Test-Path $OutputDir) -and
        (Get-ChildItem $OutputDir -Filter '*_raw.csv' -Recurse -ErrorAction SilentlyContinue)) {
        throw "Refusing to overwrite confirmation in $OutputDir. Choose a new output directory."
    }
    if ($Skew -lt 0 -or $Skew -gt 3) { throw 'Skew must be in [0, 3].' }
    New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
    $exe = Join-Path $env:TEMP 'adaptive_hashjoin_small_skew.exe'
    g++ -O3 -std=c++17 -Wall -Wextra -Wpedantic -Werror -fopenmp src\main.cpp -o $exe
    if ($LASTEXITCODE -ne 0) { throw 'Compilation failed.' }
    & $exe --self-test
    if ($LASTEXITCODE -ne 0) { throw 'Scheduler correctness tests failed.' }

    foreach ($seed in $SeedStart..($SeedStart + 7)) {
        $seedR = 1620000001 + (1009 * $seed)
        $seedS = 1720000001 + (9176 * $seed)
        $skewLabel = $Skew.ToString('0.00').Replace('.', '')
        $label = "r20k_z${skewLabel}_seed${seed}"
        & $exe --r-size 20000 --s-size 320000 --key-range 20000 --partitions 1024 `
            --threads 4 --chunk-size 256 --tasks-per-thread 4 --split-factor 3.0 `
            --queue-batch-size 1 --cost-samples 16 --steal-threshold-multiplier 4 `
            --repeats 7 --skews $Skew --seed-r $seedR --seed-s $seedS `
            --csv (Join-Path $OutputDir "${label}_summary.csv") `
            --raw-csv (Join-Path $OutputDir "${label}_raw.csv")
        if ($LASTEXITCODE -ne 0) { throw "Small high-skew confirmation failed: $label" }
    }
    python scripts\analyze_experiments.py (Join-Path $OutputDir '*_raw.csv') `
        --out-dir (Join-Path $OutputDir 'analysis')
    if ($LASTEXITCODE -ne 0) { throw 'Small high-skew confirmation analysis failed.' }
} finally {
    Pop-Location
}
