@echo off
rem Project Spoonbill, Track 3: install dependencies (first run) and launch the dashboard.
rem Usage:  run.bat                      auto-resolve data folder (repo data\ if present, else fixtures)
rem         run.bat --demo               demo mode (scripted click path)
rem         run.bat --data-dir D:\path   explicit data folder
setlocal
cd /d "%~dp0"

set "PY="
for %%V in (3.13 3.12 3.11 3.14) do (
    if not defined PY (
        py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V"
    )
)
if not defined PY (
    python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1 && set "PY=python"
)
if not defined PY (
    echo ERROR: Python 3.11 or newer was not found. Install it from https://www.python.org/downloads/
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment with %PY% ...
    %PY% -m venv .venv || goto :fail
)

echo Installing dependencies (quick when already installed) ...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt || goto :fail

if not exist "assets\fonts\NotoSansTC-Regular.ttf" (
    echo WARNING: bundled CJK font missing; PDF export is disabled until you run:
    echo          .venv\Scripts\python.exe -m pip install fonttools ^&^& .venv\Scripts\python.exe scripts\fetch_fonts.py
)

".venv\Scripts\python.exe" -m streamlit run app.py -- %*
exit /b %errorlevel%

:fail
echo ERROR: setup failed, see the messages above.
exit /b 1
