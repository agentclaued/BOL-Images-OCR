@echo off
rem Development: stops the background app, runs the server with --reload in this window,
rem and starts the background app again when you close it.
call "%~dp0stop_background.bat"
pushd "%~dp0..\.."
for /f "delims=" %%C in ('python "%~dp0cc_settings.py" dev_command') do set "CMD=%%C"
%CMD%
popd
call "%~dp0start_background.bat"
