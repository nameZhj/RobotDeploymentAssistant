@echo off
chcp 65001 >nul
cd /d "%~dp0"
title ChoreoNexus Verification Suite
echo Running code hygiene audit...
python scripts\verify_hygiene.py
if errorlevel 1 (
    echo [ERROR] Code hygiene audit failed.
    pause
    exit /b 1
)
echo Running pytest suite...
python -m pytest -v
if errorlevel 1 (
    echo [ERROR] Some tests failed.
    pause
    exit /b 1
)
echo [PASS] All checks and tests passed.
