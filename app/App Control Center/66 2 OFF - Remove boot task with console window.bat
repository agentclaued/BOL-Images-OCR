@echo off
rem Run as Administrator. Removes task Tools-BOL_Images and the live-log window at login, and stops the server.
net session >nul 2>&1
if errorlevel 1 (
    echo Please right-click this file and choose "Run as administrator".
    pause
    exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0window_autostart.ps1" -Mode Remove
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_background.ps1"
echo Server stopped and auto-start removed.
pause
