@echo off
:: =============================================================================
:: install_vps.bat
:: One-shot dependency installer for the VPS Agent.
:: Run this ONCE after copying the project to your AWS Windows VPS.
:: Requires Python 3.11+ already installed with pip available.
:: =============================================================================

title GOLD CLONE — Install Dependencies
cd /d "%~dp0"

echo.
echo  ============================================================
echo   GOLD CLONE — VPS Dependency Installer
echo  ============================================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Python not found. Install Python 3.11+ first.
    echo  https://www.python.org/downloads/windows/
    pause
    exit /b 1
)

python --version
echo.

:: Upgrade pip silently
echo  [1/3] Upgrading pip...
python -m pip install --upgrade pip --quiet
if errorlevel 1 (
    echo  WARNING: pip upgrade failed — continuing anyway.
)

:: Install all requirements
echo  [2/3] Installing requirements from requirements.txt...
python -m pip install -r requirements.txt --upgrade
if errorlevel 1 (
    echo.
    echo  ERROR: Dependency installation failed.
    echo  Check your internet connection and try again.
    pause
    exit /b 1
)

:: Quick smoke-test of key imports
echo.
echo  [3/3] Verifying key imports...
python -c "import MetaTrader5; import pandas; import supabase; import dotenv; print('  All imports OK')"
if errorlevel 1 (
    echo.
    echo  WARNING: One or more imports failed.
    echo  MetaTrader5 requires a real Windows MT5 terminal to be installed.
    echo  All other packages should be present — check the output above.
)

echo.
echo  ============================================================
echo   Installation complete.
echo.
echo   Next steps:
echo     1. Copy .env.template  ->  .env
echo     2. Fill in .env with your Supabase + MT5 credentials
echo     3. Double-click run_vps_agent.bat to start the agent
echo  ============================================================
echo.
pause
