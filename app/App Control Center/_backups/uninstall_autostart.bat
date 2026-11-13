@echo off
rem Removes the Windows auto-start shortcut. Does not stop the app running now (use stop_background.bat).
for /f "delims=" %%N in ('python "%~dp0cc_settings.py" shortcut') do set "SHORTCUT=%%N"
set "LNK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\%SHORTCUT%"
if exist "%LNK%" (
    del "%LNK%"
    echo Auto-start removed.
) else (
    echo Auto-start was not installed.
)
timeout /t 3 >nul
