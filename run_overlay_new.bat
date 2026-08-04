@echo off
pushd "%~dp0"
echo [Overlay] Nota: run_overlay_new.bat e' un duplicato legacy di run_overlay.bat.
if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe run_overlay_live.py --modular
    exit /b %ERRORLEVEL%
)
echo [Overlay] .venv non trovato - uso python di sistema...
python run_overlay_live.py --modular
exit /b %ERRORLEVEL%
