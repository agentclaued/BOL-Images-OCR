@echo off
rem Starts the hidden background app (tray icon) now, without waiting for the next login.
call "%~dp0_venv.bat" || (pause & exit /b 1)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0_paused.ps1" -Action Clear
schtasks /End /TN Tools-BOL_Images >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_background.ps1"
pushd "%ROOT%"
start "" "%PYW%" "%~dp0background_tray.pyw"
popd
echo Background app started. Look for the icon near the clock.
timeout /t 3 >nul
