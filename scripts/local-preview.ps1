[CmdletBinding()]
param(
    [int]$Port = 5000,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$Endpoint = "http://127.0.0.1:$Port"

function Test-LocalHealth {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 "$Endpoint/healthz"
        return $response.StatusCode -eq 200
    }
    catch {
        return $false
    }
}

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Missing .venv Python. Create it with: py -m venv .venv"
}

if (-not (Test-LocalHealth)) {
    & $Python -c "import flask, requests, cryptography, playwright; import Crypto"
    if ($LASTEXITCODE -ne 0) {
        throw "Missing dependencies. Run: .\.venv\Scripts\python.exe -m pip install -r requirements.txt"
    }

    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $Python
    $startInfo.Arguments = "app.py"
    $startInfo.WorkingDirectory = $RepoRoot
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $previousHost = $env:CANVAS_DASHBOARD_HOST
    $previousPort = $env:CANVAS_DASHBOARD_PORT
    try {
        $env:CANVAS_DASHBOARD_HOST = "127.0.0.1"
        $env:CANVAS_DASHBOARD_PORT = [string]$Port
        $process = [System.Diagnostics.Process]::Start($startInfo)
    }
    finally {
        if ($null -eq $previousHost) {
            Remove-Item Env:CANVAS_DASHBOARD_HOST -ErrorAction SilentlyContinue
        }
        else {
            $env:CANVAS_DASHBOARD_HOST = $previousHost
        }
        if ($null -eq $previousPort) {
            Remove-Item Env:CANVAS_DASHBOARD_PORT -ErrorAction SilentlyContinue
        }
        else {
            $env:CANVAS_DASHBOARD_PORT = $previousPort
        }
    }

    $deadline = (Get-Date).AddSeconds(15)
    while ((Get-Date) -lt $deadline) {
        if (Test-LocalHealth) {
            break
        }
        Start-Sleep -Milliseconds 250
    }

    if (-not (Test-LocalHealth)) {
        $process.Refresh()
        if ($process.HasExited) {
            throw "Local server exited unexpectedly (exit code $($process.ExitCode)). Run .\scripts\dev.ps1 to inspect its output."
        }
        throw "Local server did not become healthy within 15 seconds. Run .\scripts\dev.ps1 to inspect its output."
    }
}

if (-not $NoBrowser) {
    & cmd.exe /c start "" "$Endpoint"
}

Write-Host "Local preview ready: $Endpoint"
