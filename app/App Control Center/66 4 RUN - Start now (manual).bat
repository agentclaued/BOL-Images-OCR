@echo off
rem Run as Administrator. Starts task Tools-BOL_Images now (does nothing if the app is already running) and shows the live log.
net session >nul 2>&1
if errorlevel 1 (
    echo Please right-click this file and choose "Run as administrator".
    pause
    exit /b 1
)
schtasks /Query /TN Tools-BOL_Images >nul 2>&1 || (echo Task Tools-BOL_Images is not installed. Run "66 1 ON" first. & pause & exit /b 1)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0_paused.ps1" -Action Clear
schtasks /Run /TN Tools-BOL_Images
start "" "%~dp0_show_log.bat"
timeout /t 3 >nul
