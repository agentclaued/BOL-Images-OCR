@echo off
rem Stops the dev-mode (--reload) server. Run "11 1 ON" to bring the background app back.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_background.ps1"
echo Dev server stopped.
timeout /t 2 >nul
