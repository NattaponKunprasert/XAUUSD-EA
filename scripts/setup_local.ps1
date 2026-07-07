param(
    [string]$PythonCommand = "python",
    [switch]$Recreate
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot

function Test-VenvPython {
    $venvPython = ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $venvPython)) {
        return $false
    }
    & $venvPython --version *> $null
    return $LASTEXITCODE -eq 0
}

$venvExists = Test-Path -LiteralPath ".venv"
$venvWorks = Test-VenvPython

if ($venvExists -and -not $venvWorks) {
    if (-not $Recreate) {
        throw "Existing .venv is broken. Rerun with: .\scripts\setup_local.ps1 -Recreate"
    }
    $resolvedRoot = (Resolve-Path -LiteralPath $projectRoot).Path
    $resolvedVenv = (Resolve-Path -LiteralPath ".venv").Path
    if (-not $resolvedVenv.StartsWith($resolvedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove .venv outside the project root: $resolvedVenv"
    }
    Remove-Item -LiteralPath $resolvedVenv -Recurse -Force
    $venvExists = $false
}

if (-not $venvExists) {
    # Some managed local workspaces allow PowerShell to create directories
    # while Python's os.makedirs receives WinError 2. Pre-create the standard
    # venv directory layout so Python can populate it normally.
    @(
        ".venv",
        ".venv\Include",
        ".venv\Lib",
        ".venv\Lib\site-packages",
        ".venv\Scripts"
    ) | ForEach-Object {
        New-Item -ItemType Directory -Force -Path $_ | Out-Null
    }

    & $PythonCommand -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create .venv with: $PythonCommand"
    }
}

if (-not (Test-VenvPython)) {
    throw "Python could not create .venv. Install a standard Python 3.12 distribution with venv support, then rerun this script."
}

& ".venv\Scripts\python.exe" -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    throw "Failed to upgrade pip in .venv"
}
& ".venv\Scripts\python.exe" -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    throw "Failed to install requirements.txt in .venv"
}

& ".venv\Scripts\python.exe" -m pytest -q
if ($LASTEXITCODE -ne 0) {
    throw "Environment was created, but the test suite failed"
}

Write-Host "Local environment is ready. Start with: .\scripts\start_local.ps1"
