@echo off
title Multi-Account Bot Engine (TwisterPro M15 & Micro-Scalper)
echo ===================================================================
echo   MULTI-ACCOUNT PRECISION TRADING ENGINE
echo   - Account A: $100 Exness Account (Personal Independent)
echo   - Account C: $10 HFMarkets Account (Copy Master)
echo   - Account D: $1,000 FBS Account (Copy Follower C -> D)
echo   - Engine 1: TwisterPro M15 Scalper (Magic: 2001 - 5-Layer Validation)
echo   - Engine 2: Agile Micro-Scalper (Magic: 1001 - M1/M5)
echo   - Symbols: Gold (XAUUSDm) & Bitcoin (BTCUSDm - Weekday only)
echo ===================================================================
echo.

set PY312="C:\Users\PwezaCore\AppData\Local\Programs\Python\Python312\python.exe"

if exist %PY312% (
    %PY312% run.py
) else (
    python run.py
)

pause
