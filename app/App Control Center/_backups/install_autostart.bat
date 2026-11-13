@echo off
rem Starts the app in the background (tray icon) every time you log in to Windows.
rem Creates a Startup-folder shortcut (no admin needed) and starts the tray app now.
pushd "%~dp0..\.."

where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found on PATH. Install Python 3.11+ from https://python.org and try again.
    pause
    exit /b 1
)

python -c "import pystray, PIL" 2>nul
if errorlevel 1 (
    echo Installing tray packages...
    python -m pip install pystray pillow
    if errorlevel 1 (
        echo Could not install packages. Check your internet connection and try again.
        pause
        exit /b 1
    )
)

for /f "delims=" %%P in ('python -c "import sys, os; print(os.path.join(os.path.dirname(sys.executable), 'pythonw.exe'))"') do set "PYW=%%P"
if not exist "%PYW%" (
    echo pythonw.exe not found at %PYW%
    pause
    exit /b 1
)
for /f "delims=" %%N in ('python "%~dp0cc_settings.py" shortcut') do set "SHORTCUT=%%N"
for /f "delims=" %%N in ('python "%~dp0cc_settings.py" name') do set "APPNAME=%%N"

set "LNK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\%SHORTCUT%"
set "SCRIPT=%~dp0background_tray.pyw"
set "ROOT=%CD%"

powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:LNK); $s.TargetPath=$env:PYW; $s.Arguments='\"'+$env:SCRIPT+'\"'; $s.WorkingDirectory=$env:ROOT; $s.WindowStyle=7; $s.Description=$env:APPNAME+' (background)'; $s.Save()"
if errorlevel 1 (
    echo Could not create the startup shortcut.
    pause
    exit /b 1
)

echo.
echo Done. %APPNAME% now starts automatically when you log in to Windows.
echo Look for the BI icon near the clock (it may be under the ^ arrow).
echo To remove auto-start, run uninstall_autostart.bat.
echo.
start "" "%PYW%" "%SCRIPT%"
popd
timeout /t 3 >nul
