@echo off
pushd "%~dp0"
if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe run_overlay_live.py --modular
    exit /b %ERRORLEVEL%
)
echo [Overlay] .venv non trovato - uso python di sistema...
python run_overlay_live.py --modular
exit /b %ERRORLEVEL%
