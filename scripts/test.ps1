[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PytestArgs
)

$ErrorActionPreference = "Stop"

$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$env:PYTHONUTF8 = "1"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$TestTempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("canvas-dashboard-pytest-" + [Guid]::NewGuid().ToString("N"))

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Missing .venv Python. Create it with: py -m venv .venv"
}

New-Item -ItemType Directory -Path $TestTempRoot -Force | Out-Null
$env:TEMP = $TestTempRoot
$env:TMP = $TestTempRoot

Push-Location $RepoRoot
try {
    & $Python -c "import flask, pytest"
    if ($LASTEXITCODE -ne 0) {
        throw "Missing test dependencies. Run: .\.venv\Scripts\python.exe -m pip install -r requirements.txt pytest"
    }

    if ($null -eq $PytestArgs -or $PytestArgs.Count -eq 0) {
        $PytestArgs = @("tests", "-q")
    }

    & $Python -m pytest @PytestArgs
    exit $LASTEXITCODE
}
finally {
    Pop-Location
    Remove-Item -LiteralPath $TestTempRoot -Recurse -Force -ErrorAction SilentlyContinue
}
