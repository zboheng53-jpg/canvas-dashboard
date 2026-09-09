[CmdletBinding()]
param(
    [string]$Server = "http://127.0.0.1:5000",
    [string]$Token = "",
    [ValidateSet("agents", "claude")]
    [string]$Target = "agents",
    [string]$Dir = "",
    [switch]$MigrateLegacy
)

$ErrorActionPreference = "Stop"

$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom

$Server = $Server.TrimEnd("/")
if ([string]::IsNullOrWhiteSpace($Dir)) {
    $InstallDir = Join-Path $HOME ".agents\skills\canvas-dashboard"
} else {
    $InstallDir = $Dir
}

Write-Host "==> Downloading Canvas Dashboard Skill files from $Server ..." -ForegroundColor Cyan

$TmpDir = Join-Path ([System.IO.Path]::GetTempPath()) ("canvas-skill-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $TmpDir -Force | Out-Null

try {
    # Download SKILL.md
    $skillUrl = "$Server/skill/SKILL.md"
    $skillFile = Join-Path $TmpDir "SKILL.md"
    Invoke-WebRequest -Uri $skillUrl -OutFile $skillFile -UseBasicParsing

    # Download canvas_api.py
    $apiUrl = "$Server/skill/canvas_api.py"
    $apiFile = Join-Path $TmpDir "canvas_api.py"
    Invoke-WebRequest -Uri $apiUrl -OutFile $apiFile -UseBasicParsing

    # Check existing token if updating
    $existingConfig = Join-Path $InstallDir "config.json"
    $finalToken = $Token
    if ([string]::IsNullOrWhiteSpace($finalToken) -and (Test-Path -LiteralPath $existingConfig)) {
        try {
            $parsed = Get-Content -LiteralPath $existingConfig -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($parsed.token) {
                $finalToken = $parsed.token
            }
        } catch {
            # Ignore parse errors
        }
    }

    # Write config.json
    $configObj = @{
        server_url = $Server
        token = $finalToken
    }
    $configJson = $configObj | ConvertTo-Json -Compress
    $configFile = Join-Path $TmpDir "config.json"
    [System.IO.File]::WriteAllText($configFile, $configJson, $Utf8NoBom)

    # Write .gitignore
    $gitignoreContent = "config.json`r`n.env`r`n*.tmp`r`n__pycache__/`r`n"
    $gitignoreFile = Join-Path $TmpDir ".gitignore"
    [System.IO.File]::WriteAllText($gitignoreFile, $gitignoreContent, $Utf8NoBom)

    # Target folder
    if (-not (Test-Path -LiteralPath $InstallDir)) {
        New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
        Write-Host "==> Installing Canvas Dashboard Skill to $InstallDir ..." -ForegroundColor Green
    } else {
        Write-Host "==> Updating existing Skill at $InstallDir ..." -ForegroundColor Green
    }

    Copy-Item -Path (Join-Path $TmpDir "*") -Destination $InstallDir -Force -Recurse

    # Handle Claude target
    if ($Target -eq "claude") {
        $claudeSkillsDir = Join-Path $HOME ".claude\skills"
        $claudeTarget = Join-Path $claudeSkillsDir "canvas-dashboard"
        if (-not (Test-Path -LiteralPath $claudeSkillsDir)) {
            New-Item -ItemType Directory -Path $claudeSkillsDir -Force | Out-Null
        }
        if (Test-Path -LiteralPath $claudeTarget) {
            if ($MigrateLegacy) {
                Remove-Item -LiteralPath $claudeTarget -Force -Recurse
            }
        }
        if (-not (Test-Path -LiteralPath $claudeTarget)) {
            try {
                New-Item -ItemType SymbolicLink -Path $claudeTarget -Target $InstallDir -Force | Out-Null
                Write-Host "==> Created Claude Code symlink: $claudeTarget -> $InstallDir" -ForegroundColor Green
            } catch {
                try {
                    New-Item -ItemType Junction -Path $claudeTarget -Target $InstallDir -Force | Out-Null
                    Write-Host "==> Created Claude Code junction: $claudeTarget -> $InstallDir" -ForegroundColor Green
                } catch {
                    Copy-Item -Path $InstallDir -Destination $claudeTarget -Recurse -Force
                    Write-Host "==> Copied to Claude Code directory: $claudeTarget" -ForegroundColor Yellow
                }
            }
        }
    }

    Write-Host "==> Canvas Dashboard Skill installed successfully!" -ForegroundColor Green
    Write-Host "    Path: $InstallDir" -ForegroundColor Gray
    if ([string]::IsNullOrWhiteSpace($finalToken)) {
        Write-Host "    [NOTE] Token not configured. Please add your token into $InstallDir\config.json" -ForegroundColor Yellow
    }

    Write-Host "`nNext steps:" -ForegroundColor Cyan
    Write-Host "1. Restart your Agent or start a new session (most agents discover skills at startup)."
    Write-Host "2. Verify by asking: '我今天有什么课？分别在哪个教室？'"
} finally {
    if (Test-Path -LiteralPath $TmpDir) {
        Remove-Item -LiteralPath $TmpDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}
