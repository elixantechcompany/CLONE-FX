@echo off
:: =============================================================================
:: INSTALL_DEPS.bat — One-shot dependency installer
:: Run this ONCE on a new machine before running RUN_BOT.bat
:: =============================================================================

title GOLD CLONE — Install Dependencies
cd /d "%~dp0"

echo.
echo  ============================================================
echo   GOLD CLONE — Dependency Installer
echo  ============================================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Python not found. Please install Python 3.11+
    echo  https://www.python.org/downloads/windows/
    echo  IMPORTANT: Check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

python --version
echo.

echo  [1/2] Upgrading pip...
python -m pip install --upgrade pip --quiet

echo  [2/2] Installing all requirements...
python -m pip install -r requirements.txt

echo.
echo  Verifying key imports...
python -c "import MetaTrader5; import pandas; import yaml; import dotenv; print('  All imports OK')"

echo.
echo  ============================================================
echo   Done! Now:
echo     1. Make sure MetaTrader 5 is installed and logged in
echo     2. Double-click RUN_BOT.bat to start trading
echo  ============================================================
echo.
pause
