@echo off
title Musumali Gold 24/7 Trading Bot (Exness MT5)
echo ===================================================================
echo   Starting Musumali Gold Automated 24/7 Trading Bot
echo   - 24/7 Continuous Market Analysis
echo   - Take Profit: Strategy TP or +$2.00 Dollar Target Closer
echo ===================================================================
echo.

set PY312="C:\Users\PwezaCore\AppData\Local\Programs\Python\Python312\python.exe"

if exist %PY312% (
    %PY312% run.py
) else (
    python run.py
)

pause
