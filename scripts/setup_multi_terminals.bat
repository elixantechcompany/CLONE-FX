@echo off
title Multi-Terminal Instance Setup (Accounts A, B, C, D)
echo ===================================================================
echo   PRECISION MT5 MULTI-TERMINAL INSTANCE SETUP UTILITY
echo   Creates isolated terminal folders for 100%% independent accounts
echo ===================================================================
echo.

set BASE_DIR="C:\Program Files\MetaTrader 5"

if not exist %BASE_DIR% (
    echo [ERROR] Default MetaTrader 5 directory not found at: %BASE_DIR%
    echo Please ensure MetaTrader 5 is installed.
    pause
    exit /b 1
)

echo [1/4] Checking Terminal A folder (Default)...
echo  * Path: %BASE_DIR%

echo.
echo [2/4] Setting up Terminal B folder (Account B)...
set DIR_B="C:\Program Files\MetaTrader 5 - Account B"
if not exist %DIR_B% (
    echo  * Creating %DIR_B%...
    robocopy %BASE_DIR% %DIR_B% /E /NFL /NDL /NJH /NJS
    echo  [OK] Terminal B directory created.
) else (
    echo  * Terminal B directory already exists: %DIR_B%
)

echo.
echo [3/4] Setting up Terminal C folder ($20 Account C Master)...
set DIR_C="C:\Program Files\MetaTrader 5 - Account C"
if not exist %DIR_C% (
    echo  * Creating %DIR_C%...
    robocopy %BASE_DIR% %DIR_C% /E /NFL /NDL /NJH /NJS
    echo  [OK] Terminal C directory created.
) else (
    echo  * Terminal C directory already exists: %DIR_C%
)

echo.
echo [4/4] Setting up Terminal D folder ($20 Account D Follower)...
set DIR_D="C:\Program Files\MetaTrader 5 - Account D"
if not exist %DIR_D% (
    echo  * Creating %DIR_D%...
    robocopy %BASE_DIR% %DIR_D% /E /NFL /NDL /NJH /NJS
    echo  [OK] Terminal D directory created.
) else (
    echo  * Terminal D directory already exists: %DIR_D%
)

echo.
echo ===================================================================
echo   ALL MULTI-TERMINAL DIRECTORIES READY!
echo   You can now launch each terminal independently:
echo     - Terminal A: %BASE_DIR%\terminal64.exe (Account A)
echo     - Terminal B: %DIR_B%\terminal64.exe (Account B)
echo     - Terminal C: %DIR_C%\terminal64.exe ($20 Master)
echo     - Terminal D: %DIR_D%\terminal64.exe ($20 Follower)
echo ===================================================================
echo.
pause
