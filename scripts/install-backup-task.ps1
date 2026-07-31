param(
    [string]$TaskName = "Canvas Dashboard Encrypted Backup",
    [string]$DailyAt = "04:00"
)

$ErrorActionPreference = "Stop"
$Script = (Resolve-Path (Join-Path $PSScriptRoot "pull-production-backup.ps1")).Path
$PowerShell = (Get-Command powershell.exe).Source
$Action = New-ScheduledTaskAction `
    -Execute $PowerShell `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Script`" -CreateBackup"
$Trigger = New-ScheduledTaskTrigger -Daily -At $DailyAt
$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Creates, downloads, and verifies an encrypted Canvas Dashboard production data backup." `
    -Force | Out-Null
Write-Output "Scheduled task installed: $TaskName"
