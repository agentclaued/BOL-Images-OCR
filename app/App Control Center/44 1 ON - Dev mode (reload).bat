@echo off
rem Development: stops the background app, runs the server with --reload in this window (tray icon shows status),
rem and starts the background app again when you close it.
call "%~dp011 2 OFF - Stop in background.bat"
call "%~dp0_venv.bat" || (pause & exit /b 1)
pushd "%ROOT%"
start "" "%PYW%" "%~dp0background_tray.pyw" --attach
for /f "delims=" %%C in ('""%PY%" "%~dp0cc_settings.py" dev_command"') do set "CMD=%%C"
%CMD%
popd
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_background.ps1"
call "%~dp011 1 ON - Start in background.bat"
