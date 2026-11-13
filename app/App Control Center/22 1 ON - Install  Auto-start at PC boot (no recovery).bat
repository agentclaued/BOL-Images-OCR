@echo off
rem Run once as Administrator. Server starts ~45s after the PC turns on, before login, hidden, once.
net session >nul 2>&1
if errorlevel 1 (
    echo Please right-click this file and choose "Run as administrator".
    pause
    exit /b 1
)
call "%~dp0_venv.bat" || (pause & exit /b 1)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0boot_autostart.ps1" -Action Install
pause
