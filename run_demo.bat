@echo off
pushd "%~dp0"
title LMU Pit Strategist — Demo
echo ========================================
echo   LMU Pit Strategist — Demo
echo ========================================
echo.
echo Creazione dati sintetici...
if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe demo_seed.py
) else (
    python demo_seed.py
)
echo.
echo Avvio server web...
echo Apri http://127.0.0.1:8000 nel browser
echo Premi Ctrl+C per fermare il server
echo ========================================
if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe run_server.py
) else (
    python run_server.py
)
pause
