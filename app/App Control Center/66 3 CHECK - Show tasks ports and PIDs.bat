@echo off
rem Changes nothing. Lists BOL scheduled tasks, startup shortcuts, running servers (PID + port) and what uses this app's port.
rem Run as Administrator to see tasks created by other users.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0window_autostart.ps1" -Mode Check
pause
