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
    "-o", "StrictHostKeyChecking=yes",
    "-o", "HostKeyAlgorithms=ssh-ed25519",
    "-o", "UserKnownHostsFile=$KnownHosts"
)
$ReleaseName = "release-" + [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
$TarFile = Join-Path $RepoRoot "$ReleaseName.tar.gz"

Write-Host "Starting verified release deployment..." -ForegroundColor Cyan

Write-Host "Running local regression and compilation gates..." -ForegroundColor Yellow
& .\scripts\test.ps1
if ($LASTEXITCODE -ne 0) { throw "Local tests failed. Deployment aborted." }
& .\.venv\Scripts\python.exe -m compileall -q .
if ($LASTEXITCODE -ne 0) { throw "Python compilation failed. Deployment aborted." }

if (-not $SkipPreDeployBackup) {
    Write-Host "Creating an encrypted off-server backup and running a recovery drill..." -ForegroundColor Yellow
    & .\scripts\pull-production-backup.ps1 -CreateBackup -RecoveryDrill
    if ($LASTEXITCODE -ne 0) { throw "Pre-deployment backup or recovery drill failed." }
}

Write-Host "Packaging immutable release $ReleaseName..." -ForegroundColor Yellow
try {
    tar `
        --exclude='.venv' `
        --exclude='data' `
        --exclude='__pycache__' `
        --exclude='.superpowers' `
        --exclude='.claude' `
        --exclude='.git' `
        --exclude='.pytest_cache' `
        --exclude='.agents' `
        --exclude='*.tar.gz' `
        -czf $TarFile *
    if ($LASTEXITCODE -ne 0) { throw "Failed to create release archive." }

    & ssh @SshOptions $Remote "mkdir -p $RemoteRoot/incoming $RemoteRoot/releases"
    if ($LASTEXITCODE -ne 0) { throw "Failed to prepare the remote release directory." }
    & scp @SshOptions $TarFile "${Remote}:$RemoteRoot/incoming/$ReleaseName.tar.gz"
    if ($LASTEXITCODE -ne 0) { throw "Failed to upload release archive." }

    $RemoteInstall = "$RemoteRoot/releases/$ReleaseName/deploy/install-release.sh"
    $RemoteCommand = "mkdir -p '$RemoteRoot/releases/$ReleaseName' && tar -xzf '$RemoteRoot/incoming/$ReleaseName.tar.gz' -C '$RemoteRoot/releases/$ReleaseName' && bash '$RemoteInstall' '$RemoteRoot/incoming/$ReleaseName.tar.gz' '$ReleaseName'"
    & ssh @SshOptions $Remote $RemoteCommand
    if ($LASTEXITCODE -ne 0) { throw "Remote release activation failed or was rolled back." }

    & ssh @SshOptions $Remote "systemctl is-active canvas-dashboard.service zhihuishu-worker.service zhihuishu-login-cleanup.timer canvas-dashboard-backup.timer nginx && curl -fsS --max-time 10 http://127.0.0.1:5000/healthz && if sudo test -f /etc/letsencrypt/live/canvas-dashboard.xyz/fullchain.pem; then curl -fsS --max-time 10 --resolve canvas-dashboard.xyz:443:127.0.0.1 https://canvas-dashboard.xyz/healthz; fi"
    if ($LASTEXITCODE -ne 0) { throw "Post-deployment service verification failed." }
}
finally {
    Remove-Item -LiteralPath $TarFile -ErrorAction SilentlyContinue
}

Write-Host "Deployment completed: $ReleaseName" -ForegroundColor Green
