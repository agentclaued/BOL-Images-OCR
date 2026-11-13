@echo off
setlocal
cd /d "%~dp0"

set "HEALTH_URL=http://127.0.0.1:8766/health"
set "WATCHDOG=%~dp0watch_bol_images.ps1"

echo [1/3] Checking BOL Images health endpoint...
powershell.exe -NoProfile -Command "try { $r=Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 -Uri '%HEALTH_URL%'; if ($r.StatusCode -eq 200 -and $r.Content -match '\"status\"\s*:\s*\"ok\"') { exit 0 }; exit 1 } catch { exit 1 }"
if not errorlevel 1 goto :healthy

echo [2/3] Server is unavailable. Starting the watchdog...
start "BOL Images Watchdog Test" /min powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%WATCHDOG%"
timeout /t 12 /nobreak >nul

echo [3/3] Checking health again...
powershell.exe -NoProfile -Command "try { $r=Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 -Uri '%HEALTH_URL%'; if ($r.StatusCode -eq 200 -and $r.Content -match '\"status\"\s*:\s*\"ok\"') { exit 0 }; exit 1 } catch { exit 1 }"
if errorlevel 1 goto :failed

:healthy
echo SUCCESS: BOL Images is responding at %HEALTH_URL%
echo Open http://127.0.0.1:8766/ in this PC's browser.
pause
exit /b 0

:failed
echo FAILED: BOL Images did not become healthy. Check the launcher and Python installation.
pause
exit /b 1
