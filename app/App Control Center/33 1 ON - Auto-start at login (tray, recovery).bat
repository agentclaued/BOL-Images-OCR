@echo off
rem Starts the app in the background (tray icon) every time you log in to Windows.
rem Creates a Startup-folder shortcut (no admin needed) and starts the tray app now.
call "%~dp0_venv.bat" || (pause & exit /b 1)
pushd "%ROOT%"

if not exist "%PYW%" (
    echo pythonw.exe not found at %PYW%
    pause
    exit /b 1
)
for /f "delims=" %%N in ('""%PY%" "%~dp0cc_settings.py" shortcut"') do set "SHORTCUT=%%N"
for /f "delims=" %%N in ('""%PY%" "%~dp0cc_settings.py" name"') do set "APPNAME=%%N"

set "LNK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\%SHORTCUT%"
set "SCRIPT=%~dp0background_tray.pyw"

powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:LNK); $s.TargetPath=$env:PYW; $s.Arguments='\"'+$env:SCRIPT+'\"'; $s.WorkingDirectory=$env:ROOT; $s.WindowStyle=7; $s.Description=$env:APPNAME+' (background)'; $s.Save()"
if errorlevel 1 (
    echo Could not create the startup shortcut.
    pause
    exit /b 1
)

echo.
echo Done. %APPNAME% now starts automatically when you log in to Windows.
echo Look for the BI icon near the clock (it may be under the ^ arrow).
echo To remove auto-start, run "33 2 OFF".
echo.
start "" "%PYW%" "%SCRIPT%"
popd
timeout /t 3 >nul
