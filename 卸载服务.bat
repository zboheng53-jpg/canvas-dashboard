@echo off
title Canvas Dashboard - Remove Auto-Start
echo.
echo   ============================================
echo     Canvas Dashboard - Remove Auto-Start
echo   ============================================
echo.

:: Remove Startup shortcut
if exist "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Canvas Dashboard.lnk" (
    del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Canvas Dashboard.lnk"
    echo   [OK] Startup shortcut removed.
) else (
    echo   [INFO] No Startup shortcut found.
)

:: Also try schtasks removal (in case user ran with admin before)
schtasks /delete /tn "Canvas Dashboard" /f 2>nul

echo.
echo   To stop the server if it is currently running:
echo   Open Task Manager, find wscript.exe and pythonw.exe,
echo   select them and click End Task.
echo.
pause
