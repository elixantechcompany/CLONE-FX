@echo off
title Launch All MT5 Terminals
echo ===================================================================
echo   LAUNCHING ALL 3 METATRADER 5 TERMINALS VISIBLY ON DESKTOP
echo   1. Account A: Exness (C:\Program Files\MetaTrader 5)
echo   2. Account C: HFMarkets (C:\Users\PwezaCore\Desktop\MT5_Account_C)
echo   3. Account D: FBS Demo (C:\Users\PwezaCore\Desktop\MT5 NEW ACC\FBS DEMO)
echo ===================================================================
echo.

echo [1/4] Closing any background terminal processes...
taskkill /F /IM terminal64.exe >nul 2>&1
timeout /t 2 /nobreak >nul

echo [2/4] Launching Account A (Exness MT5)...
start "" /D "C:\Program Files\MetaTrader 5" "C:\Program Files\MetaTrader 5\terminal64.exe"
timeout /t 5 /nobreak >nul

echo [3/4] Launching Account C (HFMarkets MT5)...
start "" /D "C:\Users\PwezaCore\Desktop\MT5_Account_C" "C:\Users\PwezaCore\Desktop\MT5_Account_C\terminal64.exe"
timeout /t 5 /nobreak >nul

echo [4/4] Launching Account D (FBS Demo MT5)...
start "" /D "C:\Users\PwezaCore\Desktop\MT5 NEW ACC\FBS DEMO" "C:\Users\PwezaCore\Desktop\MT5 NEW ACC\FBS DEMO\terminal64.exe"

echo.
echo ===================================================================
echo   All 3 terminals launched!
echo   Please wait 15-30 seconds for charts and connections to load.
echo ===================================================================
timeout /t 5 >nul
