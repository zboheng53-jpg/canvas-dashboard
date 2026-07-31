[CmdletBinding()]
param(
    [string]$HostName = "",
    [int]$Port = 0
)

$ErrorActionPreference = "Stop"

$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$env:PYTHONUTF8 = "1"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Missing .venv Python. Create it with: py -m venv .venv"
}

Push-Location $RepoRoot
try {
    & $Python -c "import flask, requests, cryptography, playwright; import Crypto"
    if ($LASTEXITCODE -ne 0) {
        throw "Missing dependencies. Run: .\.venv\Scripts\python.exe -m pip install -r requirements.txt"
    }

    if ($HostName -ne "") {
        $env:CANVAS_DASHBOARD_HOST = $HostName
    }
    if ($Port -gt 0) {
        $env:CANVAS_DASHBOARD_PORT = [string]$Port
    }

    & $Python app.py
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
