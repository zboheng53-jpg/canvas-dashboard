@echo off
title Canvas Dashboard

:: Force working directory to the batch file's location
cd /d "%~dp0"

echo.
echo   ================================
echo     Canvas Dashboard - Tongji
echo   ================================
echo.

:: Check that we're running from an extracted directory, not inside a ZIP
if not exist "requirements.txt" (
    echo   [ERROR] File incomplete!
    echo.
    echo   *** Please extract the entire ZIP file first! ***
    echo   *** Do NOT double-click bat inside the ZIP! ***
    echo.
    echo   Steps:
    echo   1. Right-click canvas-dashboard.zip - Extract All
    echo   2. Open the extracted folder
    echo   3. Double-click start.bat
    echo.
    pause
    exit /b 1
)

if not exist "app.py" (
    echo   [ERROR] File incomplete! Extract the ZIP first.
    pause
    exit /b 1
)

:: Check Python (try python, then python3, then py)
set PYTHON_CMD=
python --version >nul 2>&1
if %errorlevel% equ 0 (
    set PYTHON_CMD=python
) else (
    python3 --version >nul 2>&1
    if %errorlevel% equ 0 (
        set PYTHON_CMD=python3
    ) else (
        py --version >nul 2>&1
        if %errorlevel% equ 0 (
            set PYTHON_CMD=py
        )
    )
)

if "%PYTHON_CMD%"=="" (
    echo   [ERROR] Python not found. Install Python 3.10+
    echo   Download: https://www.python.org/downloads/
    echo   Check "Add Python to PATH" during installation
    pause
    exit /b 1
)

echo   [1/4] Python detected:
%PYTHON_CMD% --version
echo.

:: Check Python version (3.8+ required for Flask 3.x)
for /f "tokens=2 delims= " %%v in ('%PYTHON_CMD% --version 2^>^&1') do set PY_VER=%%v
for /f "tokens=1,2 delims=." %%a in ("%PY_VER%") do (
    set PY_MAJOR=%%a
    set PY_MINOR=%%b
)
if %PY_MAJOR% lss 3 goto py_ver_fail
if %PY_MINOR% lss 8 goto py_ver_fail
goto py_ver_ok
:py_ver_fail
echo   [ERROR] Python 3.8+ required. Current: %PY_VER%
echo   Download: https://www.python.org/downloads/
pause
exit /b 1
:py_ver_ok

:: Check venv module
%PYTHON_CMD% -m venv --help >nul 2>&1
if %errorlevel% neq 0 (
    echo   [ERROR] Python venv module not installed.
    echo   Reinstall Python and select all optional components.
    pause
    exit /b 1
)

:: Create venv if not exists
if not exist ".venv" (
    echo   [2/4] Creating virtual environment...
    %PYTHON_CMD% -m venv .venv
    if %errorlevel% neq 0 (
        echo   [ERROR] Virtual environment creation failed.
        pause
        exit /b 1
    )
) else (
    echo   [2/4] Virtual environment exists, skip.
    echo.
)

:: Activate and install dependencies
echo   [3/4] Installing dependencies...

call .venv\Scripts\activate.bat
if %errorlevel% neq 0 (
    echo   [ERROR] Virtual environment activation failed.
    pause
    exit /b 1
)

:: Upgrade pip (with mirror fallback)
python -m pip install --upgrade pip -q 2>nul
if %errorlevel% neq 0 (
    echo   [INFO] pip upgrade via default PyPI failed, trying mirror...
    python -m pip install --upgrade pip -q -i https://pypi.tuna.tsinghua.edu.cn/simple 2>nul
)
:: Install dependencies (mirror first, since we already know pypi.org is slow)
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
if %errorlevel% neq 0 (
    echo   [INFO] Mirror failed, trying default PyPI...
    pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo.
        echo   ========================================
        echo   [ERROR] Dependency installation failed!
        echo.
        echo   Possible reasons:
        echo   1. Network issue - check your internet
        echo   2. Firewall/proxy blocking pip
        echo.
        echo   Try manual install:
        echo   cd to this folder, then:
        echo   pip install -r requirements.txt
        echo   ========================================
        pause
        exit /b 1
    )
)

echo   [4/4] Dependencies installed.
echo.
echo   ================================
echo     [OK] Server starting, open:
echo     http://127.0.0.1:5000
echo   ================================
echo.

:: Open browser
start http://127.0.0.1:5000

:: Start server
python app.py
pause
