@echo off
setlocal
set "BOL_PORT=8766"
set "BOL_FOUND="

for /f "tokens=5" %%P in ('netstat -aon ^| findstr /R /C:":%BOL_PORT% .*LISTENING"') do (
    set "BOL_FOUND=1"
    echo Stopping BOL Images server (process %%P)...
    taskkill /F /PID %%P
)

if not defined BOL_FOUND echo BOL Images is not running on port %BOL_PORT%.
exit /b 0
