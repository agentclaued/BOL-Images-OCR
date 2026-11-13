@echo off
rem Opens a console that shows the server status and the live server log. Closing this window does NOT stop the server.
title BOL Images - live log
for %%D in ("%~dp0.." "%~dp0..\..") do if not defined ROOT if exist "%%~fD\app\main.py" set "ROOT=%%~fD"
if not exist "%ROOT%\logs" mkdir "%ROOT%\logs"
if not exist "%ROOT%\logs\server.log" type nul > "%ROOT%\logs\server.log"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=((Get-Content '%~dp0settings.json' -Raw) -replace '(?m)^\s*//.*$','' | ConvertFrom-Json); $c=Get-NetTCPConnection -LocalPort $s.port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; if($c){Write-Host ('BOL Images is RUNNING at '+$s.public_url+'  (PID '+$c.OwningProcess+', port '+$s.port+')') -ForegroundColor Green}else{Write-Host ('BOL Images is NOT running on port '+$s.port+'. Run 66 4 RUN to start it.') -ForegroundColor Red}; Write-Host 'Closing this window does not stop the server.'; Write-Host '----- live log -----'; Get-Content '%ROOT%\logs\server.log' -Tail 30 -Wait"
