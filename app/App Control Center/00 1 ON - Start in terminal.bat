@echo off
rem Runs the server visibly in a terminal WITHOUT --reload (stops the background app first). Tray icon shows status.
rem Terminal wins: auto-start / watchdog (66) stands down while this window is open, then resumes by itself.
title BOL Images (terminal)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0_paused.ps1" -Action Set
schtasks /End /TN Tools-BOL_Images >nul 2>&1
call "%~dp011 2 OFF - Stop in background.bat"
call "%~dp0_venv.bat" || (pause & exit /b 1)
pushd "%ROOT%"
start "" "%PYW%" "%~dp0background_tray.pyw" --attach
for /f "delims=" %%C in ('""%PY%" "%~dp0cc_settings.py" start_command"') do set "CMD=%%C"
%CMD%
popd
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_background.ps1"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0_paused.ps1" -Action Clear
echo Stopped. If task Tools-BOL_Images (66) is installed it restarts the app within 5 minutes.
pause
