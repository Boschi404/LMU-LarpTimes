@echo off
pushd "%~dp0"
if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe run_overlay.py
    exit /b %ERRORLEVEL%
)
echo Virtual environment not found.
echo Please create/activate the project venv first.
echo Example:
echo    python -m venv .venv
echo    .\.venv\Scripts\Activate.ps1
echo    python -m pip install -r requirements.txt
echo    python run_overlay.py
exit /b 1
