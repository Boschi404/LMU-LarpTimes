# Build PyInstaller standalone executables for Windows
@echo off
setlocal

echo === LMU Pit Strategist Build ===

if not exist build_env (
    echo Creating virtual environment...
    python -m venv build_env
)

echo Installing dependencies...
call build_env\Scripts\activate.bat
pip install -r requirements.txt
pip install pyinstaller

echo Building with PyInstaller...
pyinstaller build_exe.spec --clean --noconfirm

echo.
echo Build complete.
echo Output: dist\LMU Pit Strategist\
echo.

endlocal
pause
