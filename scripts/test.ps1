[CmdletBinding()]
param(
    [ValidateSet("all", "quick", "acceptance", "ui")]
    [string]$Suite = "all",
    [switch]$List,
    [switch]$ChangedOnly,
    [int]$Workers = 0,
    [int]$KeepSuccessRuns = 10,
    [int]$KeepFailedRuns = 30,
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
$SystemTempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
$TestTempRoot = Join-Path $SystemTempRoot ("canvas-dashboard-pytest-" + [Guid]::NewGuid().ToString("N"))
$RunName = (Get-Date -Format "yyyyMMdd-HHmmss") + "-" + [Guid]::NewGuid().ToString("N").Substring(0, 8)
$ArtifactRoot = Join-Path $RepoRoot "test-results\$RunName"
$PreviousTemp = $env:TEMP
$PreviousTmp = $env:TMP
$PreviousArtifacts = $env:CANVAS_TEST_ARTIFACTS
$TestExitCode = 1
$EffectiveWorkers = 1

function Remove-SafeArtifactDirectory {
    # Only ever delete a directory that is a direct child of the ignored test-results folder.
    param([string]$Path, [string]$ResultsRoot)
    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) { return $false }
    $resolvedRoot = [System.IO.Path]::GetFullPath($ResultsRoot).TrimEnd('\')
    $resolvedPath = [System.IO.Path]::GetFullPath($Path).TrimEnd('\')
    if ([System.IO.Path]::GetDirectoryName($resolvedPath) -ne $resolvedRoot) { return $false }
    for ($attempt = 1; $attempt -le 2; $attempt++) {
        try {
            Remove-Item -LiteralPath $resolvedPath -Recurse -Force -ErrorAction Stop
            return $true
        } catch {
            if ($attempt -eq 2) { return $false }
            Start-Sleep -Milliseconds 250
        }
    }
}

function Get-RecordedRuns {
    param([string]$ResultsRoot)
    if (-not (Test-Path -LiteralPath $ResultsRoot)) { return @() }
    $runs = @()
    foreach ($directory in Get-ChildItem -LiteralPath $ResultsRoot -Directory -ErrorAction SilentlyContinue) {
        $metadataPath = Join-Path $directory.FullName "run.json"
        $exitCode = $null
        if (Test-Path -LiteralPath $metadataPath) {
            try { $exitCode = (Get-Content -LiteralPath $metadataPath -Raw | ConvertFrom-Json).exit_code } catch { $exitCode = $null }
        }
        $runs += [pscustomobject]@{
            Name = $directory.Name
            Path = $directory.FullName
            LastWrite = $directory.LastWriteTimeUtc
            Failed = ($null -ne $exitCode -and [int]$exitCode -ne 0)
            Unknown = ($null -eq $exitCode)
        }
    }
    return @($runs | Sort-Object LastWrite -Descending)
}

function Invoke-ArtifactRetention {
    # Keep failures and the newest run; rotate old passing runs so the workspace stays searchable.
    param([string]$ResultsRoot, [string]$CurrentRun, [int]$KeepSuccess, [int]$KeepFailed)
    $runs = @(Get-RecordedRuns -ResultsRoot $ResultsRoot)
    $keptSuccess = 0
    $keptFailed = 0
    $removed = 0
    $freed = 0L
    foreach ($run in $runs) {
        if ($run.Name -eq $CurrentRun) { continue }
        $budgeted = $true
        if ($run.Failed) {
            $keptFailed++
            $budgeted = $keptFailed -le $KeepFailed
        } elseif ($run.Unknown) {
            $budgeted = $true
        } else {
            $keptSuccess++
            $budgeted = $keptSuccess -le $KeepSuccess
        }
        if ($budgeted) { continue }
        $size = 0L
        foreach ($file in Get-ChildItem -LiteralPath $run.Path -Recurse -File -ErrorAction SilentlyContinue) { $size += $file.Length }
        if (Remove-SafeArtifactDirectory -Path $run.Path -ResultsRoot $ResultsRoot) {
            $removed++
            $freed += $size
        }
    }
    if ($removed -gt 0) {
        Write-Host ("Artifact retention removed {0} old passing run(s), freed {1:N0} MB (kept {2} passing / {3} failing)." -f $removed, ($freed / 1MB), $KeepSuccess, $KeepFailed)
    }
}

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Missing .venv Python. Create it with: py -m venv .venv"
}
New-Item -ItemType Directory -Path $TestTempRoot -Force | Out-Null
New-Item -ItemType Directory -Path $ArtifactRoot -Force | Out-Null
$env:TEMP = $TestTempRoot
$env:TMP = $TestTempRoot
$env:CANVAS_TEST_ARTIFACTS = $ArtifactRoot
Push-Location $RepoRoot
try {
    & $Python -c "import flask, pytest"
    if ($LASTEXITCODE -ne 0) { throw "Missing test dependencies. Install requirements.txt and pytest." }
    if ($null -eq $PytestArgs -or $PytestArgs.Count -eq 0) {
        if ($ChangedOnly) {
            # The impact map lives in scripts/recommend_tests.py so the script, the docs and CI share one source.
            $Selection = & $Python scripts/recommend_tests.py --files-from-diff --pytest-args
            if ($LASTEXITCODE -ne 0) { throw "Impact-based selection failed; pass an explicit test path instead." }
            $PytestArgs = @($Selection | Where-Object { $_ -and $_.Trim() -ne "" })
            if ($PytestArgs.Count -eq 0) { throw "No tests matched the current diff; pass an explicit test path." }
            Write-Host "Changed-only selection: $($PytestArgs -join ' ')"
        } else {
            $PytestArgs = @("tests", "-q")
        }
    }

    $ParallelSupported = $false
    & $Python -c "import xdist" 2>$null
    if ($LASTEXITCODE -eq 0) { $ParallelSupported = $true }

    $RequestedWorkers = if ($PSBoundParameters.ContainsKey("Workers")) {
        $Workers
    } elseif ($env:CANVAS_TEST_WORKERS) {
        [int]$env:CANVAS_TEST_WORKERS
    } else {
        4
    }
    if ($RequestedWorkers -lt 1) { $RequestedWorkers = 1 }
    if (-not $ParallelSupported -and $RequestedWorkers -gt 1) {
        Write-Warning "pytest-xdist is missing; running serially. Install it with: .\.venv\Scripts\python.exe -m pip install pytest-xdist"
        $RequestedWorkers = 1
    }
    if ($List) { $RequestedWorkers = 1 }
    $EffectiveWorkers = $RequestedWorkers

    # no:cacheprovider keeps .pytest_cache out of the evidence directory: those folders are not
    # removable by the same account (/cache under test-results) and break repo-wide search tools.
    $RunArgs = @($PytestArgs) + @("--suite", $Suite, "--durations=10", "-p", "no:cacheprovider", "--junitxml=$ArtifactRoot\results.xml", "--log-file=$ArtifactRoot\pytest.log")
    if ($EffectiveWorkers -gt 1) {
        $RunArgs += @("-n", "$EffectiveWorkers", "--dist", "loadfile")
    }
    if ($Suite -eq "quick" -and -not ($PytestArgs -match '^--maxfail(?:=|$)')) { $RunArgs += "-x" }
    if ($List) { $RunArgs += "--collect-only" }
    $Revision = (& git rev-parse HEAD)
    $Dirty = [bool](& git status --porcelain --untracked-files=normal)
    $Started = [DateTime]::UtcNow.ToString("o")
    Write-Host "Suite: $Suite | Commit: $Revision | Dirty: $Dirty | Workers: $EffectiveWorkers | ChangedOnly: $([bool]$ChangedOnly)"
    & $Python -m pytest @RunArgs
    $TestExitCode = $LASTEXITCODE
    @{
        commit = $Revision; dirty = $Dirty; suite = $Suite; args = $RunArgs
        workers = $EffectiveWorkers; changed_only = [bool]$ChangedOnly; list_only = [bool]$List
        started_at = $Started; finished_at = [DateTime]::UtcNow.ToString("o")
        exit_code = $TestExitCode; collection_only = [bool]$List
    } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $ArtifactRoot "run.json") -Encoding UTF8
}
finally {
    Pop-Location
    $env:TEMP = $PreviousTemp
    $env:TMP = $PreviousTmp
    $env:CANVAS_TEST_ARTIFACTS = $PreviousArtifacts
    # Verify the final absolute target before recursive cleanup.
    $ResolvedTemp = [System.IO.Path]::GetFullPath($TestTempRoot)
    if ([System.IO.Path]::GetDirectoryName($ResolvedTemp).TrimEnd('\') -eq $SystemTempRoot.TrimEnd('\') -and
        [System.IO.Path]::GetFileName($ResolvedTemp).StartsWith("canvas-dashboard-pytest-")) {
        Remove-Item -LiteralPath $TestTempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
    try {
        Invoke-ArtifactRetention -ResultsRoot (Join-Path $RepoRoot "test-results") -CurrentRun $RunName -KeepSuccess $KeepSuccessRuns -KeepFailed $KeepFailedRuns
    } catch {
        Write-Warning "Artifact retention skipped: $($_.Exception.Message)"
    }
    Write-Host "Test evidence: $ArtifactRoot"
}
exit $TestExitCode
