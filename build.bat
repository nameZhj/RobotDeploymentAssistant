@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ========================================================
echo   VSISLAB Robot Deployment Assistant - Packaging
echo ========================================================
echo.
python build_package.py
if errorlevel 1 (
    echo.
    echo [ERROR] Packaging failed.
    echo.
    pause
    exit /b 1
)
echo.
echo [SUCCESS] Build process completed successfully.
echo.
pause
