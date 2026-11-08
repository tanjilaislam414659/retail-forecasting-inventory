# Run from PowerShell; no activation or execution-policy change is needed.
param([string]$PythonExecutable = 'py')

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $projectRoot
try {
    if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
        & $PythonExecutable -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Could not create .venv.' }
    }
    & .\.venv\Scripts\python.exe -m pip --version
    if ($LASTEXITCODE -ne 0) { throw 'pip is missing. Run .venv\Scripts\python.exe -m ensurepip --upgrade.' }
    & .\.venv\Scripts\python.exe -m pip install --disable-pip-version-check -r requirements-dev.txt
    if ($LASTEXITCODE -ne 0) { throw 'Could not install packaging tools.' }
    & .\.venv\Scripts\python.exe -m pip install --disable-pip-version-check --no-build-isolation --no-deps -e .
    if ($LASTEXITCODE -ne 0) { throw 'Could not install the project.' }
    & .\.venv\Scripts\python.exe scripts\verify.py
    if ($LASTEXITCODE -ne 0) { throw 'Verification failed.' }
} finally {
    Pop-Location
}
