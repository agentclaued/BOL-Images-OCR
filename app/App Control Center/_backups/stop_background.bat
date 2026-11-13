@echo off
rem Stops THIS app's tray and hidden server only (matched by this folder path and this app's port).
for /f "delims=" %%N in ('python "%~dp0cc_settings.py" port') do set "APPPORT=%%N"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$dir=(Resolve-Path '%~dp0').Path; Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -like ('*'+$dir+'background_tray.pyw*') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }; Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -ne $PID -and $_.Name -eq 'pythonw.exe' -and $_.CommandLine -like ('*--port '+$env:APPPORT+'*') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
echo Background app stopped.
timeout /t 2 >nul
