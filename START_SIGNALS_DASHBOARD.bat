@echo off
title Market Structure & Perfect Setups Signals Dashboard
echo ===================================================================
echo   INSTITUTIONAL MARKET STRUCTURE & PERFECT SETUPS UI
echo   Continuous Multi-Timeframe Trend Decomposition & Signal Radar
echo ===================================================================
echo.

set PY312="C:\Users\PwezaCore\AppData\Local\Programs\Python\Python312\python.exe"

if exist %PY312% (
    %PY312% run_ui.py
) else (
    python run_ui.py
)

pause
