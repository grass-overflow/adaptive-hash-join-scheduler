param([string]$OutputDir = 'final_confirmation_rerun')
$ErrorActionPreference = 'Stop'
& "$PSScriptRoot\run_confirmation.ps1" -OutputDir $OutputDir
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
