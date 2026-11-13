@echo off
rem Removes the boot task (run as Administrator). Does not stop a running server.
net session >nul 2>&1
if errorlevel 1 (
    echo Please right-click this file and choose "Run as administrator".
    pause
    exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0boot_autostart.ps1" -Action Remove
pause
