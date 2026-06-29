@echo off
title LMU Pit Strategist — Demo
echo ========================================
echo   LMU Pit Strategist — Demo
echo ========================================
echo.
echo Creazione dati sintetici...
call .venv\Scripts\python.exe demo_seed.py
echo.
echo Avvio server web...
echo Apri http://127.0.0.1:8000 nel browser
echo Premi Ctrl+C per fermare il server
echo ========================================
call .venv\Scripts\python.exe run_server.py
pause
