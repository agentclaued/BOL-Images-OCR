@echo off
rem Removes the Windows auto-start shortcut. Does not stop the app running now (use "11 2 OFF").
for /f "usebackq delims=" %%N in (`powershell -NoProfile -Command "((Get-Content -Raw '%~dp0settings.json') -replace '(?m)^\s*//.*$','' | ConvertFrom-Json).shortcut"`) do set "SHORTCUT=%%N"
set "LNK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\%SHORTCUT%"
if exist "%LNK%" (
    del "%LNK%"
    echo Auto-start removed.
) else (
    echo Auto-start was not installed.
)
timeout /t 3 >nul
