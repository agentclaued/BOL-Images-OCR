@echo off
setlocal
cd /d "%~dp0"
set "BOL_PYTHON=C:\Users\Lenovo\AppData\Local\Programs\Python\Python314\python.exe"

if not exist "%BOL_PYTHON%" set "BOL_PYTHON=python"

echo Checking BOL Images requirements...
"%BOL_PYTHON%" -m pip install --disable-pip-version-check --no-input -r requirements.txt
if errorlevel 1 (
  echo.
  echo Required packages could not be installed. Check the internet connection and Python installation, then run this file again.
  pause
  exit /b 1
)

echo Starting BOL Images at http://127.0.0.1:8766
"%BOL_PYTHON%" -m uvicorn app.main:app --host 127.0.0.1 --port 8766

exit /b %errorlevel%
