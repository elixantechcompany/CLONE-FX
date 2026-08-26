@echo off
title Test Demo Order Placement (MT5)
echo ===================================================================
echo   Sending a 0.01 Lot Test Demo Order on Gold (XAUUSDm) to MT5...
echo ===================================================================
echo.

set PY312="C:\Users\PwezaCore\AppData\Local\Programs\Python\Python312\python.exe"

if exist %PY312% (
    %PY312% test_order.py
) else (
    python test_order.py
)

pause
