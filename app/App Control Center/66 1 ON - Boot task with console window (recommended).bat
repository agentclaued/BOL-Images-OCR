@echo off
rem Run once as Administrator. Works from any folder.
rem 1) Shows existing BOL tasks / shortcuts / servers with port and PID and asks before changing anything.
rem 2) Creates the app's .venv INSIDE this app folder (not on C:) and installs requirements once.
rem 3) Creates task Tools-BOL_Images: starts the server at PC boot, at every login, and on manual run (66 4).
rem    Only one copy ever runs. A live-log console window opens at login (66 5 opens it any time).
rem The window stays open so you can read the result.
if /i not "%~1"=="inner" (
    cmd /k ""%~f0" inner"
    exit /b
)
net session >nul 2>&1
if errorlevel 1 (
    echo.
    echo NOT ADMINISTRATOR. Close this window, right-click the .bat and choose "Run as administrator".
    goto :end
)
pushd "%~dp0" || (echo Cannot open folder %~dp0 - a mapped network drive is not visible as Administrator. Use the \\server\share path instead. & goto :end)
call "%~dp0_venv.bat" || (echo Environment setup failed - read the error above. & goto :end)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0window_autostart.ps1" -Mode Install
if errorlevel 1 goto :end
schtasks /Query /TN Tools-BOL_Images >nul 2>&1 && (
    echo RESULT: task Tools-BOL_Images EXISTS. Starting it now...
    schtasks /Run /TN Tools-BOL_Images
    start "" "%~dp0_show_log.bat"
) || echo RESULT: task was NOT created - read the messages above.
popd
:end
echo.
echo Press any key to close.
pause >nul
exit
