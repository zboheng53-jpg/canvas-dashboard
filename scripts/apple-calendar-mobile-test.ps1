[CmdletBinding()]
param(
    [switch]$DryRun
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

if ($DryRun) {
    Write-Output "Dry run passed: no server, tunnel, or temporary data was created."
    exit 0
}

$Cloudflared = (Get-Command cloudflared -ErrorAction Stop).Source
$TestDir = Join-Path $env:TEMP ("canvas-dashboard-apple-test-" + [guid]::NewGuid().ToString("N"))
$PortListener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
$PortListener.Start()
$Port = $PortListener.LocalEndpoint.Port
$PortListener.Stop()
$Server = $null
$Tunnel = $null

try {
    New-Item -ItemType Directory -Path $TestDir | Out-Null
    $env:CANVAS_APPLE_MOBILE_TEST_DIR = $TestDir
    $env:CANVAS_APPLE_MOBILE_TEST_PORT = [string]$Port
    $Bootstrap = @'
import os
from datetime import datetime
from pathlib import Path

root = Path(os.environ["CANVAS_APPLE_MOBILE_TEST_DIR"])
port = int(os.environ["CANVAS_APPLE_MOBILE_TEST_PORT"])

import auth
import user_paths

auth.DATA_DIR = root
auth.USERS_FILE = root / "users.json"
auth.SECRET_KEY_FILE = root / ".flask_secret_key"
user_paths.DATA_DIR = root

import apple_calendar
apple_calendar.DATA_DIR = root

import zhihuishu_store
import zhihuishu_login_sessions
zhihuishu_store.DATA_DIR = root
zhihuishu_login_sessions.DATA_DIR = root

import app
from storage import write_json_file

app.DATA_DIR = root
username = "apple_mobile_test"
todo_dir = user_paths.user_dir(username)
now = datetime.now(app.CST)
write_json_file(todo_dir / "custom_todos.json", [{
    "id": 1,
    "text": "Apple Calendar mobile test",
    "done": False,
    "created_at": now.isoformat(),
    "updated_at": now.isoformat(),
    "due_date": now.date().isoformat(),
    "highlighted": False,
    "labels": [],
    "subtasks": [],
}])
token = apple_calendar.create_token(username)
(root / "subscription_path.txt").write_text(f"/calendar/{token}.ics", encoding="utf-8")
app.app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)
'@
    $EncodedBootstrap = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($Bootstrap))
    $Launcher = "exec(__import__('base64').b64decode('$EncodedBootstrap'))"
    $Server = Start-Process -FilePath $Python -ArgumentList @("-c", $Launcher) -WorkingDirectory $RepoRoot -RedirectStandardOutput (Join-Path $TestDir "server.out.log") -RedirectStandardError (Join-Path $TestDir "server.err.log") -WindowStyle Hidden -PassThru

    $Ready = $false
    $SubscriptionFile = Join-Path $TestDir "subscription_path.txt"
    $Deadline = (Get-Date).AddSeconds(20)
    while ((Get-Date) -lt $Deadline) {
        try {
            $Healthy = (Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$Port/healthz" -TimeoutSec 2).StatusCode -eq 200
            $Ready = $Healthy -and (Test-Path -LiteralPath $SubscriptionFile)
        } catch {
            $Ready = $false
        }
        if ($Ready) { break }
        Start-Sleep -Milliseconds 250
    }
    if (-not $Ready) {
        throw "Temporary test server did not start. See $TestDir"
    }

    $SubscriptionPath = (Get-Content -Raw $SubscriptionFile).Trim()
    $Tunnel = Start-Process -FilePath $Cloudflared -ArgumentList @("tunnel", "--url", "http://127.0.0.1:$Port") -WorkingDirectory $RepoRoot -RedirectStandardOutput (Join-Path $TestDir "tunnel.out.log") -RedirectStandardError (Join-Path $TestDir "tunnel.err.log") -WindowStyle Hidden -PassThru

    $PublicUrl = $null
    $Deadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $Deadline) {
        $Log = (Get-Content -Raw (Join-Path $TestDir "tunnel.out.log"), (Join-Path $TestDir "tunnel.err.log") -ErrorAction SilentlyContinue) -join "`n"
        $Match = [regex]::Match($Log, "https://[-a-z0-9]+\.trycloudflare\.com")
        if ($Match.Success) {
            $PublicUrl = $Match.Value
            break
        }
        Start-Sleep -Milliseconds 250
    }
    if (-not $PublicUrl) {
        throw "Temporary HTTPS tunnel did not start. See $TestDir"
    }

    Write-Output "Open this private test URL on the iPhone Calendar subscription screen:"
    Write-Output "$PublicUrl$SubscriptionPath"
    Write-Output "This address exposes only temporary fake data. Keep this window open while testing; press Ctrl+C to revoke the address and delete all temporary data."
    while ($true) {
        Start-Sleep -Seconds 1
    }
}
finally {
    if ($Tunnel -and -not $Tunnel.HasExited) {
        Stop-Process -Id $Tunnel.Id -Force -ErrorAction SilentlyContinue
    }
    if ($Server -and -not $Server.HasExited) {
        Stop-Process -Id $Server.Id -Force -ErrorAction SilentlyContinue
    }
    if ($TestDir -and (Test-Path -LiteralPath $TestDir)) {
        Remove-Item -LiteralPath $TestDir -Recurse -Force
    }
    Remove-Item Env:CANVAS_APPLE_MOBILE_TEST_DIR -ErrorAction SilentlyContinue
    Remove-Item Env:CANVAS_APPLE_MOBILE_TEST_PORT -ErrorAction SilentlyContinue
}
