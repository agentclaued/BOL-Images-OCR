@echo off
rem Runs the server visibly in a terminal WITHOUT --reload (stops the background app first).
call "%~dp0stop_background.bat"
pushd "%~dp0..\.."
for /f "delims=" %%C in ('python "%~dp0cc_settings.py" start_command') do set "CMD=%%C"
%CMD%
popd
echo Stopped. Run start_background.bat to bring the background app back.
pause
