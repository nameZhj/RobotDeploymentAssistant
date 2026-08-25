@echo off
python main.py
if errorlevel 1 (
    echo.
    echo [ERROR] Launch failed. Please install dependencies: pip install -r requirements.txt
    echo.
    pause
)
