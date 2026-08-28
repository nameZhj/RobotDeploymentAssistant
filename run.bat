@echo off
title VSISLAB Robot Deployment Assistant
echo Starting VSISLAB Robot Deployment Assistant...
python main.py
if errorlevel 1 (
    echo.
    echo [ERROR] Launch failed. Please check Python environment and dependencies: pip install -r requirements.txt
    echo.
    pause
)
