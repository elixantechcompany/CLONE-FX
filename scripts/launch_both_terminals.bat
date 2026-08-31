@echo off
title Launch Both MetaTrader 5 Terminals
echo ===================================================================
echo   LAUNCHING DUAL METATRADER 5 INSTANCES
echo ===================================================================
echo.
echo [1/2] Starting Terminal A (BrightFunded $1,000)...
start "" "C:\Program Files\MetaTrader 5\terminal64.exe"
timeout /t 2 /nobreak > nul

echo [2/2] Starting Terminal C ($20 HFMarkets)...
start "" "C:\MetaTrader5_AccountC\terminal64.exe"

echo.
echo Both MetaTrader 5 terminals are running side-by-side!
timeout /t 3
exit
