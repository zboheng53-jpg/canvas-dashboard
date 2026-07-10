@echo off
title Canvas Dashboard - Setup Auto-Start
cd /d "%~dp0"

echo.
echo   ============================================
echo     Canvas Dashboard - Register Auto-Start
echo   ============================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo   [ERROR] Virtual environment not found.
    echo   Please run 启动.bat first to set up the environment.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\pythonw.exe" (
    echo   [ERROR] pythonw.exe not found in .venv\Scripts\
    echo   This can happen with Python from the Microsoft Store.
    echo   Install Python from https://www.python.org/downloads/
    echo   then delete .venv and re-run 启动.bat.
    pause
    exit /b 1
)

echo   [1/2] Installing waitress (if needed)...
.venv\Scripts\python.exe -c "import waitress" 2>nul
if %errorlevel% neq 0 (
    .venv\Scripts\pip.exe install waitress -q
    if %errorlevel% neq 0 (
        echo   [ERROR] Failed to install waitress.
        pause
        exit /b 1
    )
    echo         waitress installed.
) else (
    echo         waitress already installed.
)

echo   [2/2] Creating Startup shortcut...
set "PS1=%TEMP%\canvas_dashboard_startup.ps1"
(
    echo $ws = New-Object -ComObject WScript.Shell
    echo $sc = $ws.CreateShortcut("$([Environment]::GetFolderPath('Startup'))\Canvas Dashboard.lnk"^)
    echo $sc.TargetPath = "wscript.exe"
    echo $sc.Arguments = "`"%~dp0canvas-server.vbs`""
    echo $sc.WorkingDirectory = "%~dp0"
    echo $sc.WindowStyle = 7
    echo $sc.Save(^)
) > "%PS1%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%"
set RESULT=%errorlevel%
del /f /q "%PS1%" >nul 2>&1

if %RESULT% equ 0 (
    echo.
    echo   ============================================
    echo     [OK] Auto-start registered!
    echo.
    echo     Canvas Dashboard will start silently in the
    echo     background when you log into Windows.
    echo.
    echo     To check if the server is running:
    echo       Open http://127.0.0.1:5000
    echo.
    echo     To uninstall auto-start:
    echo       Double-click 卸载服务.bat
    echo   ============================================
) else (
    echo.
    echo   [ERROR] Failed to create Startup shortcut.
    echo   You can manually place a shortcut to
    echo   canvas-server.vbs in the Startup folder.
)

pause
