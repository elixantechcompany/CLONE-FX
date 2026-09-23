@echo off
:: =============================================================================
:: run_vps_agent.bat
:: Starts vps_agent.py with an auto-restart loop.
:: Place this file in the same folder as vps_agent.py and .env
:: To auto-launch on VPS boot, copy the shortcut to:
::   C:\Users\Administrator\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup
:: =============================================================================

title GOLD CLONE — VPS Agent
cd /d "%~dp0"

:: Verify .env exists before starting
if not exist ".env" (
    echo.
    echo  ERROR: .env file not found in %~dp0
    echo  Copy .env.template to .env and fill in your credentials first.
    echo.
    pause
    exit /b 1
)

:: Verify Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  ERROR: Python not found on PATH.
    echo  Install Python 3.11+ and make sure "Add Python to PATH" was checked.
    echo.
    pause
    exit /b 1
)

echo.
echo  ============================================================
echo   GOLD CLONE — VPS Trading Agent
echo   Symbol  : %MT5_SYMBOL%
echo   Started : %DATE% %TIME%
echo  ============================================================
echo.

:LOOP
echo [%DATE% %TIME%] Starting vps_agent.py...
python vps_agent.py

set EXIT_CODE=%errorlevel%

if %EXIT_CODE% == 0 (
    echo [%DATE% %TIME%] Agent exited cleanly (code 0). Not restarting.
    goto :END
)

echo.
echo [%DATE% %TIME%] Agent stopped with exit code %EXIT_CODE%.
echo  Restarting in 30 seconds... (close this window to cancel)
echo.
timeout /t 30 /nobreak >nul
goto :LOOP

:END
echo.
echo  Agent has stopped. Press any key to close.
pause >nul
