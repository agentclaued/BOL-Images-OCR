@echo off
rem Stops the server running on this app's port (terminal mode).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_background.ps1"
echo Server stopped.
timeout /t 2 >nul
