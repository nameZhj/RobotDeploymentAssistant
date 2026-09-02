@echo off
cd /d "%~dp0"
echo ========================================================
echo   VSISLAB Robot Deployment Assistant - Packaging EXE
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
echo [SUCCESS] Standalone EXE created successfully in dist folder.
echo.
pause
