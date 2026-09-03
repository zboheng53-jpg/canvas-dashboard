param(
    [switch]$SkipPreDeployBackup
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..\..")).Path
Set-Location $RepoRoot

$Remote = "ubuntu@124.222.188.101"
$RemoteRoot = "/home/ubuntu/canvas-dashboard"
$KnownHosts = (Resolve-Path ".\deploy\known_hosts").Path.Replace("\", "/")
$SshOptions = @(
    "-o", "BatchMode=yes",
    "-o", "ConnectTimeout=15",
    "-o", "ConnectionAttempts=1",
    "-o", "ServerAliveInterval=20",
    "-o", "ServerAliveCountMax=6",
    "-o", "StrictHostKeyChecking=yes",
    "-o", "HostKeyAlgorithms=ssh-ed25519",
    "-o", "UserKnownHostsFile=$KnownHosts"
)
$ReleaseName = "release-" + [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
$TarFile = Join-Path $RepoRoot "$ReleaseName.tar.gz"

function Invoke-DeploySsh {
    param([string]$Command, [string]$Description)
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        & ssh @SshOptions $Remote $Command
        if ($LASTEXITCODE -eq 0) { return }
        if ($attempt -lt 3) { Start-Sleep -Seconds (5 * $attempt) }
    }
    throw "$Description failed after three verified SSH attempts."
}

function Send-DeployArchive {
    param([string]$LocalPath, [string]$RemotePath)
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        & scp @SshOptions $LocalPath "${Remote}:$RemotePath"
        if ($LASTEXITCODE -eq 0) { return }
        if ($attempt -lt 3) { Start-Sleep -Seconds (5 * $attempt) }
    }
    throw "Release archive upload failed after three verified transfer attempts."
}

Write-Host "Starting verified release deployment..." -ForegroundColor Cyan

Write-Host "Running local regression and compilation gates..." -ForegroundColor Yellow
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1
if ($LASTEXITCODE -ne 0) { throw "Local tests failed. Deployment aborted." }
$PythonFiles = @(& git ls-files -- "*.py")
if ($LASTEXITCODE -ne 0 -or $PythonFiles.Count -eq 0) { throw "Failed to enumerate tracked Python files." }
& .\.venv\Scripts\python.exe -m py_compile @PythonFiles
if ($LASTEXITCODE -ne 0) { throw "Python compilation failed. Deployment aborted." }

if (-not $SkipPreDeployBackup) {
    Write-Host "Creating an encrypted off-server backup and running a recovery drill..." -ForegroundColor Yellow
    & .\scripts\pull-production-backup.ps1 -CreateBackup -RecoveryDrill
    if ($LASTEXITCODE -ne 0) { throw "Pre-deployment backup or recovery drill failed." }
}

Write-Host "Packaging immutable release $ReleaseName..." -ForegroundColor Yellow
try {
    & git archive --format=tar.gz --output=$TarFile HEAD
    if ($LASTEXITCODE -ne 0) { throw "Failed to create release archive." }

    Invoke-DeploySsh -Command "mkdir -p $RemoteRoot/incoming $RemoteRoot/releases" -Description "Remote release directory preparation"
    Send-DeployArchive -LocalPath $TarFile -RemotePath "$RemoteRoot/incoming/$ReleaseName.tar.gz"

    $RemoteInstall = "$RemoteRoot/releases/$ReleaseName/deploy/install-release.sh"
    $RemoteCommand = "mkdir -p '$RemoteRoot/releases/$ReleaseName' && tar -xzf '$RemoteRoot/incoming/$ReleaseName.tar.gz' -C '$RemoteRoot/releases/$ReleaseName' && bash '$RemoteInstall' '$RemoteRoot/incoming/$ReleaseName.tar.gz' '$ReleaseName'"
    Invoke-DeploySsh -Command $RemoteCommand -Description "Remote release activation (the server restores the previous release on failure)"

    Invoke-DeploySsh -Command "systemctl is-active canvas-dashboard.service zhihuishu-worker.service zhihuishu-login-cleanup.timer canvas-dashboard-backup.timer nginx && curl -fsS --max-time 10 http://127.0.0.1:5000/healthz && if sudo test -f /etc/letsencrypt/live/canvas-dashboard.xyz/fullchain.pem; then curl -fsS --max-time 10 --resolve canvas-dashboard.xyz:443:127.0.0.1 https://canvas-dashboard.xyz/healthz; fi" -Description "Post-deployment service verification"
}
finally {
    Remove-Item -LiteralPath $TarFile -ErrorAction SilentlyContinue
}

Write-Host "Deployment completed: $ReleaseName" -ForegroundColor Green
