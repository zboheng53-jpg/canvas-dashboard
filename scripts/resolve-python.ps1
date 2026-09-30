[CmdletBinding()]
param([string]$RepoRoot = "")

$ErrorActionPreference = "Stop"
if (-not $RepoRoot) { $RepoRoot = Split-Path -Parent $PSScriptRoot }
$LocalPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (Test-Path -LiteralPath $LocalPython -PathType Leaf) {
    return $LocalPython
}

# Linked worktrees may reuse installed packages, never another checkout's source or data.
$CommonGitDir = & git -C $RepoRoot rev-parse --path-format=absolute --git-common-dir
if ($LASTEXITCODE -ne 0) { throw "Cannot locate the repository Python environment." }
$PrimaryRoot = Split-Path -Parent ($CommonGitDir | Out-String).Trim()
$SharedPython = Join-Path $PrimaryRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $SharedPython -PathType Leaf)) {
    throw "Missing .venv Python. Create a local environment: py -m venv .venv; then install requirements-dev.txt."
}

# Dependency edits need an isolated environment; never install into the borrowed one.
foreach ($Name in @("requirements.txt", "requirements-dev.txt")) {
    $LocalFile = Join-Path $RepoRoot $Name
    $SharedFile = Join-Path $PrimaryRoot $Name
    $LocalExists = Test-Path -LiteralPath $LocalFile -PathType Leaf
    $SharedExists = Test-Path -LiteralPath $SharedFile -PathType Leaf
    if ($LocalExists -ne $SharedExists -or
        ($LocalExists -and (Get-FileHash -LiteralPath $LocalFile).Hash -ne (Get-FileHash -LiteralPath $SharedFile).Hash)) {
        throw "Dependency files differ ($Name). Create this worktree's own .venv and install requirements-dev.txt."
    }
}
Write-Host "Using shared Python packages from $PrimaryRoot (do not install into this environment during parallel work)."
return $SharedPython
