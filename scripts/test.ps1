[CmdletBinding()]
param(
    [ValidateSet("all", "quick", "acceptance")]
    [string]$Suite = "all",
    [switch]$List,
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
        $PytestArgs = @("tests", "-q")
    }
    $RunArgs = @($PytestArgs) + @("--suite", $Suite, "--durations=10", "-o", "cache_dir=$ArtifactRoot\cache", "--junitxml=$ArtifactRoot\results.xml", "--log-file=$ArtifactRoot\pytest.log")
    if ($Suite -eq "quick") { $RunArgs += "-x" }
    if ($List) { $RunArgs += "--collect-only" }
    $Revision = (& git rev-parse HEAD)
    $Dirty = [bool](& git status --porcelain --untracked-files=normal)
    $Started = [DateTime]::UtcNow.ToString("o")
    Write-Host "Suite: $Suite | Commit: $Revision | Dirty: $Dirty"
    & $Python -m pytest @RunArgs
    $TestExitCode = $LASTEXITCODE
    @{
        commit = $Revision; dirty = $Dirty; suite = $Suite; args = $RunArgs
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
    Write-Host "Test evidence: $ArtifactRoot"
}
exit $TestExitCode
