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

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Missing .venv Python. Create it with: py -m venv .venv"
}

Push-Location $RepoRoot
try {
    & $Python -c "import flask, pytest"
    if ($LASTEXITCODE -ne 0) {
        throw "Missing test dependencies. Run: .\.venv\Scripts\python.exe -m pip install -r requirements.txt pytest"
    }

    if ($null -eq $PytestArgs -or $PytestArgs.Count -eq 0) {
        $PytestArgs = @("-q")
    }

    & $Python -m pytest @PytestArgs
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
