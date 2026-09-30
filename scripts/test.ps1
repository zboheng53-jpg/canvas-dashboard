[CmdletBinding()]
param(
    [ValidateSet("all", "quick", "acceptance", "ui")]
    [string]$Suite = "all",
    [switch]$List,
    [switch]$ChangedOnly,
    [string]$BaseRef,
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
# Prefer this checkout's .venv; unchanged worktrees can borrow the primary packages.
$Python = & (Join-Path $PSScriptRoot "resolve-python.ps1") -RepoRoot $RepoRoot
$SystemTempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
$TestTempRoot = Join-Path $SystemTempRoot ("canvas-dashboard-pytest-" + [Guid]::NewGuid().ToString("N"))
$RunName = (Get-Date -Format "yyyyMMdd-HHmmss") + "-" + [Guid]::NewGuid().ToString("N").Substring(0, 8)
$ArtifactRoot = Join-Path $RepoRoot "test-results\$RunName"
$PreviousTemp = $env:TEMP
$PreviousTmp = $env:TMP
$PreviousArtifacts = $env:CANVAS_TEST_ARTIFACTS
$TestExitCode = 1
$EffectiveWorkers = 1

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Missing .venv Python. Create it with: py -m venv .venv"
}
if ($null -eq $PytestArgs -or $PytestArgs.Count -eq 0) {
    if ($ChangedOnly -or $BaseRef) {
        # The impact map lives in scripts/recommend_tests.py so the script, the docs and CI share one source.
        [string[]]$SelectorArgs = if ($BaseRef) { @("--base", $BaseRef) } else { @("--files-from-diff") }
        $Selection = & $Python (Join-Path $RepoRoot "scripts/recommend_tests.py") --repo $RepoRoot @SelectorArgs --pytest-args
        if ($LASTEXITCODE -ne 0) { throw "Impact-based selection failed; pass an explicit test path instead." }
        $PytestArgs = @($Selection | Where-Object { $_ -and $_.Trim() -ne "" })
        if ($PytestArgs.Count -eq 0) { Write-Host "No changed files; no tests run."; exit 0 }
        Write-Host "Changed-only selection: $($PytestArgs -join ' ')"
    } else {
        $PytestArgs = @("tests", "-q")
    }
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
    $FullSuite = ($Suite -eq "all" -and -not $List -and -not $ChangedOnly -and -not $BaseRef -and
        -not $PSBoundParameters.ContainsKey("PytestArgs") -and -not $env:PYTEST_ADDOPTS -and -not $env:PYTEST_PLUGINS)
    $Environment = (& $Python scripts/check_release.py --environment)
    if ($LASTEXITCODE -ne 0) { throw "Cannot record the test environment." }
    $Started = [DateTime]::UtcNow.ToString("o")
    $Manifest = @{
        schema_version = 2; commit = $Revision; dirty = $Dirty; suite = $Suite; args = $RunArgs
        full_suite = $FullSuite; environment = $Environment; end_commit = $null; end_dirty = $null
        workers = $EffectiveWorkers; changed_only = [bool]$ChangedOnly; base_ref = $BaseRef
        started_at = $Started; finished_at = $null; exit_code = $null; collection_only = [bool]$List
    }
    # Persist before pytest so interruption invalidates an older pass for the same commit.
    $Manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $ArtifactRoot "run.json") -Encoding UTF8
    Write-Host "Suite: $Suite | Commit: $Revision | Dirty: $Dirty | Workers: $EffectiveWorkers | ChangedOnly: $([bool]$ChangedOnly)"
    & $Python -m pytest @RunArgs
    $TestExitCode = $LASTEXITCODE
    $Manifest.end_commit = (& git rev-parse HEAD)
    $Manifest.end_dirty = [bool](& git status --porcelain --untracked-files=normal)
    $EndEnvironment = (& $Python scripts/check_release.py --environment)
    if ($LASTEXITCODE -ne 0 -or $EndEnvironment -ne $Environment) { $Manifest.environment = $null }
    $Manifest.finished_at = [DateTime]::UtcNow.ToString("o")
    $Manifest.exit_code = $TestExitCode
    $Manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $ArtifactRoot "run.json") -Encoding UTF8
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
        & $Python (Join-Path $RepoRoot "scripts/clean_test_artifacts.py") --apply --current-run $RunName --keep-success $KeepSuccessRuns --keep-failed $KeepFailedRuns
    } catch {
        Write-Warning "Artifact retention skipped: $($_.Exception.Message)"
    }
    Write-Host "Test evidence: $ArtifactRoot"
}
exit $TestExitCode
