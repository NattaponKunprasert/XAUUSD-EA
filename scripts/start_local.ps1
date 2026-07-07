$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot

$python = ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Local environment not found. Run .\scripts\setup_local.ps1 first."
}

& $python --version *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Local environment is broken. Run .\scripts\setup_local.ps1 -Recreate"
}

& $python -m jupyter lab
