@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ========================================================
echo   ChoreoNexus - Robot Deployment Assistant Packaging
echo ========================================================
echo.
python -m PyInstaller --noconfirm --clean --windowed ^
    --name ChoreoNexus ^
    --icon app_icon.ico ^
    --add-data "configs;configs" ^
    --add-data "web;web" ^
    --add-data "preview;preview" ^
    --add-data "assets;assets" ^
    --add-data "backend/models;backend/models" ^
    main.py
if errorlevel 1 (
    echo.
    echo [ERROR] Packaging failed. Ensure pyinstaller is installed: pip install pyinstaller
    echo.
    pause
    exit /b 1
)
echo.
echo [SUCCESS] Build output generated under dist\ChoreoNexus.
echo.
pause
