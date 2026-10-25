param([string]$OutputDir = 'results\tuned_gate_confirmation')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    if ((Test-Path $OutputDir) -and
        (Get-ChildItem $OutputDir -Filter '*_raw.csv' -Recurse -ErrorAction SilentlyContinue)) {
        throw "Refusing to overwrite tuned-gate data in $OutputDir. Choose a new output directory."
    }
    New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
    $exe = Join-Path $env:TEMP 'adaptive_hashjoin_tuned_gate.exe'
    g++ -O3 -std=c++17 -Wall -Wextra -Wpedantic -Werror -fopenmp src\main.cpp -o $exe
    if ($LASTEXITCODE -ne 0) { throw 'Compilation failed.' }
    & $exe --self-test
    if ($LASTEXITCODE -ne 0) { throw 'Scheduler correctness tests failed.' }

    foreach ($seed in 1401..1408) {
        $seedR = 720000001 + (1009 * $seed)
        $seedS = 820000001 + (9176 * $seed)
        $label = "gate4_seed${seed}"
        & $exe --r-size 250000 --s-size 4000000 --key-range 250000 --partitions 1024 `
            --threads 4 --chunk-size 512 --tasks-per-thread 8 --split-factor 4.0 `
            --queue-batch-size 1 --cost-samples 16 --steal-threshold-multiplier 4 `
            --repeats 7 --skews '1.4,1.75' --seed-r $seedR --seed-s $seedS `
            --csv (Join-Path $OutputDir "${label}_summary.csv") `
            --raw-csv (Join-Path $OutputDir "${label}_raw.csv")
        if ($LASTEXITCODE -ne 0) { throw "Tuned gate confirmation failed: $label" }
    }
    python scripts\analyze_experiments.py (Join-Path $OutputDir '*_raw.csv') `
        --out-dir (Join-Path $OutputDir 'analysis')
    if ($LASTEXITCODE -ne 0) { throw 'Tuned gate analysis failed.' }
} finally {
    Pop-Location
}
