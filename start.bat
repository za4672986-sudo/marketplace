@echo off
title TradeLink Wholesale - Dev Server
cd /d "%~dp0"
echo.
echo  ============================================
echo   TradeLink Wholesale - Starting Dev Server
echo  ============================================
echo.
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo  ERROR: Python is not installed or not in PATH.
    echo  Install Python 3.10+ from https://www.python.org/downloads/
    echo  then run this script again.
    pause
    exit /b 1
)
echo   Starting server... browser will open automatically.
echo   Press Ctrl+C to stop.
echo.
python dev_server.py
pause
