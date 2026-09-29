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
        & ssh -n @SshOptions $Remote $Command
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
        # The production host intermittently closes the modern SFTP-backed
        # scp stream while transferring encrypted backups.  Use the legacy
        # SCP protocol here; SSH host-key verification and encryption remain
        # enforced by $SshOptions.
        & scp "-O" @SshOptions "${Remote}:$RemotePath" $LocalPath
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

$LatestRemote = & ssh -n @SshOptions $Remote "ls -1t /home/ubuntu/canvas-dashboard/backups/*.cdbak 2>/dev/null | head -1"
if ($LASTEXITCODE -ne 0 -or -not $LatestRemote) {
    throw "No production encrypted backup is available."
}
$LatestRemote = $LatestRemote.Trim()
$LocalBackup = Join-Path $BackupDirectory ([IO.Path]::GetFileName($LatestRemote))
if (-not (Test-Path $LocalBackup)) {
    Receive-RemoteBackup -RemotePath $LatestRemote -LocalPath $LocalBackup
}

$VerifyOutput = & $Python $BackupTool verify --input $LocalBackup --private-key $PrivateKey
if ($LASTEXITCODE -ne 0) { throw "Downloaded backup failed authenticated verification." }
$VerifySummary = $VerifyOutput | ConvertFrom-Json
if (-not $VerifySummary.ok) { throw "Downloaded backup verification did not report success." }

# Historical data and the latest deletion ledger have different restore
# semantics. Always fetch the guard independently, even when data is cached.
$GuardDirectory = Join-Path $BackupDirectory "recovery-guards"
New-Item -ItemType Directory -Force -Path $GuardDirectory | Out-Null
$LatestRemoteGuard = & ssh -n @SshOptions $Remote "ls -1t /home/ubuntu/canvas-dashboard/backups/recovery-guards/*.cdbak 2>/dev/null | head -1"
if ($LASTEXITCODE -ne 0 -or -not $LatestRemoteGuard) {
    throw "No recovery guard is available. Run with -CreateBackup using the updated backup runner."
}
$LatestRemoteGuard = $LatestRemoteGuard.Trim()
$LocalGuard = Join-Path $GuardDirectory ([IO.Path]::GetFileName($LatestRemoteGuard))
if (-not (Test-Path $LocalGuard)) {
    Receive-RemoteBackup -RemotePath $LatestRemoteGuard -LocalPath $LocalGuard
}
$GuardVerifyOutput = & $Python $BackupTool verify --input $LocalGuard --private-key $PrivateKey
if ($LASTEXITCODE -ne 0) { throw "Downloaded recovery guard failed authenticated verification." }
$GuardVerifySummary = $GuardVerifyOutput | ConvertFrom-Json
if (-not $GuardVerifySummary.ok) { throw "Recovery guard verification did not report success." }

if ($RecoveryDrill) {
    $DrillRoot = Join-Path ([IO.Path]::GetTempPath()) ("canvas-dashboard-restore-" + [guid]::NewGuid().ToString("N"))
    try {
        New-Item -ItemType Directory -Path $DrillRoot | Out-Null
        $GuardRestoreDirectory = Join-Path $DrillRoot "guard"
        & $Python $BackupTool restore --input $LocalGuard --private-key $PrivateKey --output-dir $GuardRestoreDirectory | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Recovery guard restore failed." }
        $GuardLedger = Join-Path $GuardRestoreDirectory "data\deletion-ledger.json"
        $DataRestoreDirectory = Join-Path $DrillRoot "snapshot"
        $RestoreOutput = & $Python $BackupTool restore --input $LocalBackup --private-key $PrivateKey --output-dir $DataRestoreDirectory --deletion-ledger $GuardLedger
        if ($LASTEXITCODE -ne 0) { throw "Isolated recovery drill failed." }
        $RestoreSummary = $RestoreOutput | ConvertFrom-Json
        if (-not $RestoreSummary.ok -or $RestoreSummary.file_count -ne $VerifySummary.file_count) {
            throw "Recovered file manifest does not match the verified backup."
        }
    }
    finally {
        if (Test-Path $DrillRoot) {
            $ResolvedDrillRoot = (Resolve-Path -LiteralPath $DrillRoot).Path
            $ExpectedDrillParent = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\', '/')
            if ([IO.Path]::GetDirectoryName($ResolvedDrillRoot) -ne $ExpectedDrillParent -or
                -not [IO.Path]::GetFileName($ResolvedDrillRoot).StartsWith('canvas-dashboard-restore-')) {
                throw "Refusing cleanup outside the isolated recovery drill directory: $ResolvedDrillRoot"
            }
            Remove-Item -LiteralPath $ResolvedDrillRoot -Recurse -Force
        }
    }
}

Get-ChildItem -LiteralPath $BackupDirectory -Filter "*.cdbak" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip 30 |
    Remove-Item -Force
Get-ChildItem -LiteralPath $GuardDirectory -Filter "*.cdbak" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip 30 |
    Remove-Item -Force

Write-Output "Backup verified: $LocalBackup ($($VerifySummary.file_count) protected files)"
Write-Output "Latest recovery guard verified: $LocalGuard (copy time is the ledger recovery boundary)"
if ($RecoveryDrill) {
    Write-Output "Recovery drill passed in an isolated temporary directory."
}
