param(
    [string]$BackupDirectory = "$HOME\CanvasDashboardBackups",
    [string]$KeyDirectory = "$HOME\.canvas-dashboard-backup",
    [switch]$CreateBackup,
    [switch]$RecoveryDrill
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$BackupTool = Join-Path $PSScriptRoot "backup_data.py"
$BackupRunner = Join-Path $RepoRoot "deploy\run-backup.sh"
$KnownHosts = (Resolve-Path (Join-Path $RepoRoot "deploy\known_hosts")).Path.Replace("\", "/")
$PrivateKey = Join-Path $KeyDirectory "private.pem"
$PublicKey = Join-Path $KeyDirectory "public.pem"
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
$Remote = "ubuntu@124.222.188.101"

function Invoke-RemoteBackupCommand {
    param([string]$Command, [string]$Description)

    for ($attempt = 1; $attempt -le 3; $attempt++) {
        & ssh @SshOptions $Remote $Command
        if ($LASTEXITCODE -eq 0) {
            return
        }
        if ($attempt -lt 3) {
            Start-Sleep -Seconds (5 * $attempt)
        }
    }
    throw "$Description failed after three verified SSH attempts."
}

function Send-RemoteBackupFile {
    param([string]$LocalPath, [string]$RemotePath)

    for ($attempt = 1; $attempt -le 3; $attempt++) {
        & scp @SshOptions $LocalPath "${Remote}:$RemotePath"
        if ($LASTEXITCODE -eq 0) {
            return
        }
        if ($attempt -lt 3) {
            Start-Sleep -Seconds (5 * $attempt)
        }
    }
    throw "Upload of $LocalPath failed after three verified transfer attempts."
}

function Receive-RemoteBackup {
    param(
        [string]$RemotePath,
        [string]$LocalPath
    )

    for ($attempt = 1; $attempt -le 3; $attempt++) {
        & scp @SshOptions "${Remote}:$RemotePath" $LocalPath
        if ($LASTEXITCODE -eq 0) {
            return
        }
        if ($attempt -lt 3) {
            Start-Sleep -Seconds (5 * $attempt)
        }
    }
    throw "Failed to download the encrypted backup after three verified transfer attempts."
}

New-Item -ItemType Directory -Force -Path $KeyDirectory, $BackupDirectory | Out-Null
if (-not (Test-Path $PrivateKey) -or -not (Test-Path $PublicKey)) {
    if ((Test-Path $PrivateKey) -or (Test-Path $PublicKey)) {
        throw "Backup key pair is incomplete; refusing to replace either key."
    }
    & $Python $BackupTool keygen --private-key $PrivateKey --public-key $PublicKey
    if ($LASTEXITCODE -ne 0) { throw "Failed to generate backup recovery key pair." }
}

if ($CreateBackup) {
    Invoke-RemoteBackupCommand -Command "mkdir -p /home/ubuntu/canvas-dashboard/incoming /home/ubuntu/canvas-dashboard/backups" -Description "Remote backup directory preparation"
    Send-RemoteBackupFile -LocalPath $PublicKey -RemotePath "/home/ubuntu/canvas-dashboard/incoming/backup-public.pem"
    Send-RemoteBackupFile -LocalPath $BackupTool -RemotePath "/home/ubuntu/canvas-dashboard/incoming/backup_data.py"
    Send-RemoteBackupFile -LocalPath $BackupRunner -RemotePath "/home/ubuntu/canvas-dashboard/incoming/run-backup.sh"
    Invoke-RemoteBackupCommand -Command "sudo install -d -m 0755 /etc/canvas-dashboard && sudo install -m 0644 /home/ubuntu/canvas-dashboard/incoming/backup-public.pem /etc/canvas-dashboard/backup-public.pem && sudo bash /home/ubuntu/canvas-dashboard/incoming/run-backup.sh" -Description "Production backup creation"
}

$LatestRemote = (& ssh @SshOptions $Remote "ls -1t /home/ubuntu/canvas-dashboard/backups/*.cdbak 2>/dev/null | head -1").Trim()
if ($LASTEXITCODE -ne 0 -or -not $LatestRemote) {
    throw "No production encrypted backup is available."
}
$LocalBackup = Join-Path $BackupDirectory ([IO.Path]::GetFileName($LatestRemote))
if (-not (Test-Path $LocalBackup)) {
    Receive-RemoteBackup -RemotePath $LatestRemote -LocalPath $LocalBackup
}

$VerifyOutput = & $Python $BackupTool verify --input $LocalBackup --private-key $PrivateKey
if ($LASTEXITCODE -ne 0) { throw "Downloaded backup failed authenticated verification." }
$VerifySummary = $VerifyOutput | ConvertFrom-Json
if (-not $VerifySummary.ok) { throw "Downloaded backup verification did not report success." }

if ($RecoveryDrill) {
    $DrillRoot = Join-Path ([IO.Path]::GetTempPath()) ("canvas-dashboard-restore-" + [guid]::NewGuid().ToString("N"))
    try {
        $RestoreOutput = & $Python $BackupTool restore --input $LocalBackup --private-key $PrivateKey --output-dir $DrillRoot
        if ($LASTEXITCODE -ne 0) { throw "Isolated recovery drill failed." }
        $RestoreSummary = $RestoreOutput | ConvertFrom-Json
        if (-not $RestoreSummary.ok -or $RestoreSummary.file_count -ne $VerifySummary.file_count) {
            throw "Recovered file manifest does not match the verified backup."
        }
    }
    finally {
        if (Test-Path $DrillRoot) {
            Remove-Item -LiteralPath $DrillRoot -Recurse -Force
        }
    }
}

Get-ChildItem -LiteralPath $BackupDirectory -Filter "*.cdbak" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip 30 |
    Remove-Item -Force

Write-Output "Backup verified: $LocalBackup ($($VerifySummary.file_count) protected files)"
if ($RecoveryDrill) {
    Write-Output "Recovery drill passed in an isolated temporary directory."
}
