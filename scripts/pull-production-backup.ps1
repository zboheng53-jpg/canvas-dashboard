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
$GuardDirectory = Join-Path $BackupDirectory "recovery-guards"
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

# Single source of truth for the transport helpers. It is dot-sourced here and injected into the
# background stages below, which run in their own PowerShell processes.
$RemoteCommandSource = @'
function Invoke-RemoteBackupCommand {
    param([string[]]$SshOptions, [string]$Remote, [string]$Command, [string]$Description)

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
    param([string[]]$SshOptions, [string]$Remote, [string]$LocalPath, [string]$RemotePath)

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
    param([string[]]$SshOptions, [string]$Remote, [string]$RemotePath, [string]$LocalPath)

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

function Get-LatestRemoteBackupPath {
    param([string[]]$SshOptions, [string]$Remote, [string]$RemotePattern, [string]$MissingMessage)

    $Latest = & ssh -n @SshOptions $Remote "ls -1t $RemotePattern 2>/dev/null | head -1"
    if ($LASTEXITCODE -ne 0 -or -not $Latest) {
        throw $MissingMessage
    }
    return "$Latest".Trim()
}
'@
. ([scriptblock]::Create($RemoteCommandSource))

# Snapshot transfer/verification and recovery-guard transfer/verification/restore are independent,
# so each one runs as a background stage that reports its own exit code to the aggregating parent.
$ParallelStageSource = @'
param(
    [string]$Stage,
    [string]$SshOptionsText,
    [string]$Remote,
    [string]$PythonPath,
    [string]$BackupToolPath,
    [string]$PrivateKeyPath,
    [string]$BackupDirectory,
    [string]$GuardDirectory,
    [bool]$RunDrill,
    [string]$DrillRoot,
    [string]$TransportOverrides,
    [string]$HelperSource
)

$ErrorActionPreference = "Continue"
# A background stage runs in a fresh process, so the caller's ssh/scp overrides (used by the
# offline workflow test) and the shared transport helpers must be restored before any work starts.
if ($TransportOverrides) { . ([scriptblock]::Create($TransportOverrides)) }
. ([scriptblock]::Create($HelperSource))

# Native tools may print warnings to stderr (ssh/scp do); inside a job any stderr write would
# otherwise surface as a terminating error and fail a healthy stage. Failures are therefore decided
# by exit codes and by the payloads below, never by the presence of diagnostic output.
foreach ($Required in @($PythonPath, $BackupToolPath, $PrivateKeyPath)) {
    if (-not (Test-Path -LiteralPath $Required)) {
        throw "Required backup file is missing: $Required"
    }
}

$SshOptions = @($SshOptionsText -split "\r?\n" | Where-Object { $_ -ne "" })
$Result = [pscustomobject]@{
    Ok = $false; Stage = $Stage; ExitCode = 1; Message = "stage did not report a result"
    LocalBackup = ""; LocalGuard = ""; Ledger = ""; Summary = $null
}

try {
    if ($Stage -eq "snapshot") {
        $LatestRemote = Get-LatestRemoteBackupPath -SshOptions $SshOptions -Remote $Remote `
            -RemotePattern "/home/ubuntu/canvas-dashboard/backups/*.cdbak" `
            -MissingMessage "No production encrypted backup is available."
        $LocalBackup = Join-Path $BackupDirectory ([IO.Path]::GetFileName($LatestRemote))
        if (-not (Test-Path $LocalBackup)) {
            Receive-RemoteBackup -SshOptions $SshOptions -Remote $Remote -RemotePath $LatestRemote -LocalPath $LocalBackup
        }
        if (-not (Test-Path -LiteralPath $LocalBackup)) {
            throw "The snapshot download did not produce $LocalBackup."
        }
        $VerifyOutput = & $PythonPath $BackupToolPath verify --input $LocalBackup --private-key $PrivateKeyPath
        if ($LASTEXITCODE -ne 0) { throw "Downloaded backup failed authenticated verification." }
        $VerifySummary = $VerifyOutput | ConvertFrom-Json
        if (-not $VerifySummary.ok) { throw "Downloaded backup verification did not report success." }
        $Result.LocalBackup = $LocalBackup
        $Result.Summary = $VerifySummary
    }
    elseif ($Stage -eq "guard") {
        # Historical data and the latest deletion ledger have different restore
        # semantics. Always fetch the guard independently, even when data is cached.
        $LatestRemote = Get-LatestRemoteBackupPath -SshOptions $SshOptions -Remote $Remote `
            -RemotePattern "/home/ubuntu/canvas-dashboard/backups/recovery-guards/*.cdbak" `
            -MissingMessage "No recovery guard is available. Run with -CreateBackup using the updated backup runner."
        $LocalGuard = Join-Path $GuardDirectory ([IO.Path]::GetFileName($LatestRemote))
        if (-not (Test-Path $LocalGuard)) {
            Receive-RemoteBackup -SshOptions $SshOptions -Remote $Remote -RemotePath $LatestRemote -LocalPath $LocalGuard
        }
        if (-not (Test-Path -LiteralPath $LocalGuard)) {
            throw "The recovery guard download did not produce $LocalGuard."
        }
        $GuardVerifyOutput = & $PythonPath $BackupToolPath verify --input $LocalGuard --private-key $PrivateKeyPath
        if ($LASTEXITCODE -ne 0) { throw "Downloaded recovery guard failed authenticated verification." }
        $GuardVerifySummary = $GuardVerifyOutput | ConvertFrom-Json
        if (-not $GuardVerifySummary.ok) { throw "Recovery guard verification did not report success." }
        $Result.LocalGuard = $LocalGuard
        if ($RunDrill) {
            $GuardRestoreDirectory = Join-Path $DrillRoot "guard"
            & $PythonPath $BackupToolPath restore --input $LocalGuard --private-key $PrivateKeyPath --output-dir $GuardRestoreDirectory | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "Recovery guard restore failed." }
            $Result.Ledger = Join-Path $GuardRestoreDirectory "data\deletion-ledger.json"
        }
    }
    else {
        throw "Unknown parallel backup stage '$Stage'."
    }
    $Result.Ok = $true
    $Result.ExitCode = 0
    $Result.Message = "completed"
}
catch {
    $Result.Ok = $false
    $Result.ExitCode = 1
    $Result.Message = $_.Exception.Message
}

$Result
'@

New-Item -ItemType Directory -Force -Path $KeyDirectory, $BackupDirectory, $GuardDirectory | Out-Null
if (-not (Test-Path $PrivateKey) -or -not (Test-Path $PublicKey)) {
    if ((Test-Path $PrivateKey) -or (Test-Path $PublicKey)) {
        throw "Backup key pair is incomplete; refusing to replace either key."
    }
    & $Python $BackupTool keygen --private-key $PrivateKey --public-key $PublicKey
    if ($LASTEXITCODE -ne 0) { throw "Failed to generate backup recovery key pair." }
}

if ($CreateBackup) {
    Invoke-RemoteBackupCommand -SshOptions $SshOptions -Remote $Remote -Command "mkdir -p /home/ubuntu/canvas-dashboard/incoming /home/ubuntu/canvas-dashboard/backups" -Description "Remote backup directory preparation"
    Send-RemoteBackupFile -SshOptions $SshOptions -Remote $Remote -LocalPath $PublicKey -RemotePath "/home/ubuntu/canvas-dashboard/incoming/backup-public.pem"
    Send-RemoteBackupFile -SshOptions $SshOptions -Remote $Remote -LocalPath $BackupTool -RemotePath "/home/ubuntu/canvas-dashboard/incoming/backup_data.py"
    Send-RemoteBackupFile -SshOptions $SshOptions -Remote $Remote -LocalPath $BackupRunner -RemotePath "/home/ubuntu/canvas-dashboard/incoming/run-backup.sh"
    Invoke-RemoteBackupCommand -SshOptions $SshOptions -Remote $Remote -Command "sudo install -d -m 0755 /etc/canvas-dashboard && sudo install -m 0644 /home/ubuntu/canvas-dashboard/incoming/backup-public.pem /etc/canvas-dashboard/backup-public.pem && sudo bash /home/ubuntu/canvas-dashboard/incoming/run-backup.sh" -Description "Production backup creation"
}

# Background stages cannot see the caller's ssh/scp functions, so pass them down when present.
$TransportOverrides = ""
foreach ($TransportCommand in @("ssh", "scp")) {
    $Override = Get-Command $TransportCommand -CommandType Function -ErrorAction SilentlyContinue
    if ($Override) { $TransportOverrides += "function $TransportCommand {$($Override.Definition)}" + [Environment]::NewLine }
}

$DrillRoot = $null
$Jobs = @()
try {
    if ($RecoveryDrill) {
        $DrillRoot = Join-Path ([IO.Path]::GetTempPath()) ("canvas-dashboard-restore-" + [guid]::NewGuid().ToString("N"))
        New-Item -ItemType Directory -Path $DrillRoot | Out-Null
    }

    $CommonArguments = @(
        ($SshOptions -join [Environment]::NewLine), $Remote, $Python, $BackupTool, $PrivateKey,
        $BackupDirectory, $GuardDirectory, [bool]$RecoveryDrill, "$DrillRoot",
        $TransportOverrides, $RemoteCommandSource
    )
    $StageScript = [scriptblock]::Create($ParallelStageSource)
    $Jobs = @(
        Start-Job -ScriptBlock $StageScript -ArgumentList (@("snapshot") + $CommonArguments)
        Start-Job -ScriptBlock $StageScript -ArgumentList (@("guard") + $CommonArguments)
    )

    $StageResults = @()
    foreach ($Job in $Jobs) {
        $StageOutput = @(Receive-Job -Job $Job -Wait -ErrorAction SilentlyContinue -ErrorVariable StageErrors)
        $StageResult = $StageOutput | Where-Object { $_ -and $_.PSObject.Properties["Ok"] } | Select-Object -Last 1
        if (-not $StageResult) {
            $Reason = if ($StageErrors) {
                ($StageErrors | ForEach-Object { $_.Exception.Message }) -join "; "
            } else {
                "job $($Job.Id) ended as $($Job.State) without reporting a result"
            }
            $StageResult = [pscustomobject]@{
                Ok = $false; Stage = "unknown"; ExitCode = 1; Message = $Reason
                LocalBackup = ""; LocalGuard = ""; Ledger = ""; Summary = $null
            }
        }
        $StageResults += $StageResult
    }

    $FailedStages = @($StageResults | Where-Object { -not $_.Ok })
    if ($FailedStages.Count -gt 0) {
        $Details = ($FailedStages | ForEach-Object { "[$($_.Stage)] exit code $($_.ExitCode): $($_.Message)" }) -join " | "
        Write-Host "Parallel backup and recovery stages failed: $Details" -ForegroundColor Red
        throw "Backup and recovery stages failed: $Details"
    }

    $SnapshotResult = $StageResults | Where-Object { $_.Stage -eq "snapshot" } | Select-Object -First 1
    $GuardResult = $StageResults | Where-Object { $_.Stage -eq "guard" } | Select-Object -First 1
    if (-not $SnapshotResult -or -not $GuardResult) {
        throw "Backup and recovery stages did not both report their results."
    }
    $LocalBackup = $SnapshotResult.LocalBackup
    $LocalGuard = $GuardResult.LocalGuard
    $VerifySummary = $SnapshotResult.Summary

    if ($RecoveryDrill) {
        $DataRestoreDirectory = Join-Path $DrillRoot "snapshot"
        $RestoreOutput = & $Python $BackupTool restore --input $LocalBackup --private-key $PrivateKey --output-dir $DataRestoreDirectory --deletion-ledger $GuardResult.Ledger
        if ($LASTEXITCODE -ne 0) { throw "Isolated recovery drill failed." }
        $RestoreSummary = $RestoreOutput | ConvertFrom-Json
        if (-not $RestoreSummary.ok -or $RestoreSummary.file_count -ne $VerifySummary.file_count) {
            throw "Recovered file manifest does not match the verified backup."
        }
    }
}
finally {
    foreach ($Job in $Jobs) {
        Remove-Job -Job $Job -Force -ErrorAction SilentlyContinue
    }
    if ($DrillRoot -and (Test-Path -LiteralPath $DrillRoot)) {
        $ResolvedDrillRoot = (Resolve-Path -LiteralPath $DrillRoot).Path
        $ExpectedDrillParent = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\', '/')
        if ([IO.Path]::GetDirectoryName($ResolvedDrillRoot) -ne $ExpectedDrillParent -or
            -not [IO.Path]::GetFileName($ResolvedDrillRoot).StartsWith('canvas-dashboard-restore-')) {
            throw "Refusing cleanup outside the isolated recovery drill directory: $ResolvedDrillRoot"
        }
        Remove-Item -LiteralPath $ResolvedDrillRoot -Recurse -Force
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
# Every stage above either threw or succeeded, so report success explicitly instead of leaving the
# caller with whatever $LASTEXITCODE an earlier command happened to set.
exit 0
