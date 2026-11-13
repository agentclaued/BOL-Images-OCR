@echo off
rem Run as Administrator. Stops the server now. Auto-start stays installed but paused: it starts again at next PC reboot or with "66 4 RUN".
net session >nul 2>&1
if errorlevel 1 (
    echo Please right-click this file and choose "Run as administrator".
    pause
    exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0_paused.ps1" -Action Set -Manual
schtasks /End /TN Tools-BOL_Images >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_background.ps1"
echo Server stopped.
timeout /t 3 >nul
