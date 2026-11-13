@echo off
rem Helper (not for double-click). Called by the ON files.
rem Creates a private Python environment (.venv in the app folder, or a local copy on this PC
rem when the app folder is on a network drive that refuses python.exe), installs requirements.txt
rem once, and reinstalls only when requirements.txt changes.
rem Sets: ROOT (app folder), PY (python.exe), PYW (pythonw.exe).

set "ROOT="
for %%D in ("%~dp0.." "%~dp0..\..") do if not defined ROOT if exist "%%~fD\app\main.py" set "ROOT=%%~fD"
if not defined ROOT (
    echo Could not find the app folder - app\main.py is missing.
    exit /b 1
)
rem Local fallback lives in ProgramData so the boot task (runs as SYSTEM) and the logged-in user share it.
set "LOCALVENV=%ProgramData%\BOL_Images\venv"
call :use "%ROOT%\.venv"
"%PY%" -c "import sys" >nul 2>nul
if not errorlevel 1 goto :venv_ok
call :use "%LOCALVENV%"
"%PY%" -c "import sys" >nul 2>nul
if not errorlevel 1 goto :venv_ok
rem Older fallback location (per-user), still reused if it already works.
call :use "%LOCALAPPDATA%\BOL_Images\venv"
"%PY%" -c "import sys" >nul 2>nul
if not errorlevel 1 goto :venv_ok

where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found on PATH. Install Python 3.11+ from https://python.org and try again.
    exit /b 1
)
call :use "%ROOT%\.venv"
if exist "%VENV%" rmdir /s /q "%VENV%" >nul 2>nul
echo Creating the app's Python environment in "%VENV%" - first run only...
python -m venv "%VENV%"
if not errorlevel 1 goto :venv_ok
rem Network drives often refuse python.exe creation (Access denied). Use a local copy on this PC.
echo Could not create it in the app folder - using a local environment on this PC: "%LOCALVENV%"
call :use "%LOCALVENV%"
if exist "%VENV%" rmdir /s /q "%VENV%" >nul 2>nul
python -m venv "%VENV%"
if errorlevel 1 (
    echo Could not create the Python environment.
    exit /b 1
)
:venv_ok

rem Install packages when requirements.txt changed OR a required module is missing (e.g. "No module named 'fitz'").
set "NEED_INSTALL=1"
if exist "%STAMP%" fc /b "%ROOT%\requirements.txt" "%STAMP%" >nul 2>nul && "%PY%" -c "import fastapi, uvicorn, pymupdf, rapidocr, onnxruntime, openpyxl" >nul 2>nul && set "NEED_INSTALL="
if not defined NEED_INSTALL exit /b 0
echo Installing required packages into the app's environment - one time, needs internet...
"%PY%" -m pip install --disable-pip-version-check --no-input -r "%ROOT%\requirements.txt" pystray pillow
if errorlevel 1 (
    echo Could not install packages. Check your internet connection and try again.
    exit /b 1
)
"%PY%" -c "import fastapi, uvicorn, pymupdf, rapidocr, onnxruntime, openpyxl"
if errorlevel 1 (
    echo Packages installed but a module still fails to import - see the error above.
    exit /b 1
)
copy /y "%ROOT%\requirements.txt" "%STAMP%" >nul
exit /b 0

:use
set "VENV=%~1"
set "PY=%VENV%\Scripts\python.exe"
set "PYW=%VENV%\Scripts\pythonw.exe"
set "STAMP=%VENV%\installed-requirements.txt"
exit /b 0
