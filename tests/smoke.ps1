$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    $exe = Join-Path $env:TEMP 'hashjoin_smoke.exe'
    g++ -O3 -std=c++17 -Wall -Wextra -Wpedantic -Werror -fopenmp src/main.cpp -o $exe
    if ($LASTEXITCODE -ne 0) { throw 'Compilation failed.' }
    & $exe --self-test
    if ($LASTEXITCODE -ne 0) { throw 'Correctness edge tests failed.' }
    New-Item -ItemType Directory -Force results | Out-Null
    $out = 'results\smoke_summary.csv'
    $raw = 'results\smoke_raw.csv'
    & $exe --r-size 10000 --s-size 160000 --key-range 10000 --partitions 1024 --threads 4 --chunk-size 1024 --tasks-per-thread 32 --split-factor 2.5 --repeats 2 --skews 0,0.9,1.4,1.75 --csv $out --raw-csv $raw
    if ($LASTEXITCODE -ne 0) { throw 'Smoke benchmark failed.' }
    $rows = Import-Csv $out
    if ($rows.Count -ne 32) { throw "Expected 32 summary rows; got $($rows.Count)." }
    if (@($rows | Where-Object { $_.correct -ne '1' }).Count -gt 0) { throw 'At least one result failed correctness.' }
    $algorithms = @($rows | Select-Object -ExpandProperty algorithm -Unique)
    if ($algorithms.Count -ne 8) { throw 'Expected the seven parallel policies and sequential reference.' }
    $rawRows = Import-Csv $raw
    if ($rawRows.Count -ne 64) { throw "Expected 64 raw trial rows; got $($rawRows.Count)." }
    Write-Host "PASS: edge cases and all $($rows.Count) summary/$($rawRows.Count) raw rows matched the sequential oracle."
} finally {
    Pop-Location
}
