@echo off
title Musumali Gold Strategy Backtester (MT5)
echo ========================================================
echo   Running Musumali Strategy Historical Backtest...
echo ========================================================
echo.

set PYTHON_CMD="C:\Users\PwezaCore\AppData\Local\Programs\Python\Python312\python.exe"

if exist %PYTHON_CMD% (
    %PYTHON_CMD% backtest.py
) else (
    python backtest.py
)

pause
