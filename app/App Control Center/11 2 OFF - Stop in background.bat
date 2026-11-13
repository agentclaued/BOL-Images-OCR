@echo off
rem Stops this app's tray and server (matched by this folder path and this app's port).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_background.ps1"
echo Background app stopped.
timeout /t 2 >nul
