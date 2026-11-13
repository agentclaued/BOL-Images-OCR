@echo off
rem Helper (not for double-click). Run by scheduled task "Tools-BOL_Images" (66) at boot, at login and on manual run.
rem Uses the app's own .venv (inside the app folder). Never starts a second copy: if the port is busy it exits.
rem Server output goes to logs\server.log (watch it live with "66 5 LOG"). Restarts the server if it stops.
title BOL Images server
call "%~dp0_venv.bat" || exit /b 1
cd /d "%ROOT%"
if not exist logs mkdir logs
for /f "delims=" %%C in ('""%PY%" "%~dp0cc_settings.py" start_command"') do set "CMD=%%C"
for /f "delims=" %%P in ('""%PY%" "%~dp0cc_settings.py" port"') do set "PORT=%%P"
for /f "delims=" %%U in ('""%PY%" "%~dp0cc_settings.py" public_url"') do set "URL=%%U"
:loop
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0_paused.ps1" -Action Test
if errorlevel 1 (
    echo [%date% %time%] Paused - terminal run or manual stop - auto-start stands down. >> logs\server.log
    exit /b 0
)
netstat -ano | findstr /r /c:"LISTENING" | findstr /r /c:":%PORT% " >nul
if not errorlevel 1 (
    echo [%date% %time%] Port %PORT% already in use - BOL Images is already running, not starting a second copy. >> logs\server.log
    exit /b 0
)
echo [%date% %time%] Starting BOL Images at %URL% (user %USERNAME%) >> logs\server.log
%CMD% >> logs\server.log 2>&1
echo [%date% %time%] Server stopped, restarting in 10 seconds >> logs\server.log
timeout /t 10 /nobreak >nul
goto loop
