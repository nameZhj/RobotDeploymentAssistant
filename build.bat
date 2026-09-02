@echo off
title VSISLAB Robot Deployment Assistant - Build EXE
echo ========================================================
echo   VSISLAB Robot Deployment Assistant - Packaging EXE
echo ========================================================
echo.
python build_package.py
if errorlevel 1 (
    echo.
    echo [ERROR] Packaging failed. Please check the logs above.
    echo.
    pause
) else (
    echo.
    echo [SUCCESS] Standalone EXE created successfully at: dist\VSISLAB机器人部署助手.exe
    echo.
    pause
)
