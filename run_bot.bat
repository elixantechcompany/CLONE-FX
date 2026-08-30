@echo off
title Multi-Account Bot Engine (4 Accounts | Dual Engines XAUUSD & BTCUSD)
echo ===================================================================
echo   MULTI-ACCOUNT INSTITUTIONAL TRADING ENGINE
echo   - Account A: $1,000 BrightFunded (Independent, Target +$100, Stop -$25)
echo   - Account B: $1,000 BrightFunded (Independent, Target +$100, Stop -$25)
echo   - Account C: $20.00 Personal Account (Copy Master, Stop -$3)
echo   - Account D: $20.00 Personal Account (Copy Follower, 8-Step Safety)
echo   - Shared Strategies: Musumali Sweeps (2001) & Agile Micro-Scalper (1001)
echo   - Dual Symbols: Gold (XAUUSD) & Bitcoin (BTCUSD)
echo ===================================================================
echo.

set PY312="C:\Users\PwezaCore\AppData\Local\Programs\Python\Python312\python.exe"

if exist %PY312% (
    %PY312% run.py
) else (
    python run.py
)

pause
