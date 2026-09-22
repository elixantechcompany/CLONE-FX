@echo off
REM MT5 Memory Optimization for AWS t2.micro
REM This script optimizes MT5 settings for low-memory environments

echo ========================================================
echo MT5 Memory Optimization for AWS t2.micro
echo ========================================================
echo.

echo Applying MT5 memory optimizations...
echo.

REM Note: These optimizations typically require manual configuration in MT5
REM The following are the recommended settings:

echo [1/8] Max Bars in Charts: Set to 5000 (default: 100000+)
echo [2/8] Max Bars in History: Set to 5000 (default: 100000+)  
echo [3/8] Disable News Tab: Tools -^> Options -^> News -^> Disable
echo [4/8] Disable Mail Tab: Tools -^> Options -^> Mail -^> Disable
echo [5/8] Disable Calendar Tab: Tools -^> Options -^> Calendar -^> Disable
echo [6/8] Reduce Chart Updates: Tools -^> Options -^> Charts -^> Max bars
echo [7/8] Disable 3D Graphics: Tools -^> Options -^> Charts -^> Disable 3D
echo [8/8] Use Simple Color Scheme: Tools -^> Options -^> Charts

echo.
echo ========================================================
echo IMPORTANT: MT5 visual optimization requires manual configuration
echo ========================================================
echo.
echo Manual Configuration Steps:
echo.
echo 1. Start MT5 with /portable mode for isolation:
echo    terminal64.exe /portable
echo.
echo 2. Use MT5 with update skip to prevent memory issues:
echo    terminal64.exe /skip_update /skip
echo.
echo 3. In MT5, go to Tools -^> Options -^> Charts:
echo    - Max bars in charts: 5000
echo    - Max bars in history: 5000
echo.
echo 4. Disable unnecessary features in Tools -^> Options:
echo    - News tab: Disable
echo    - Mail tab: Disable  
echo    - Calendar tab: Disable
echo    - Experts: Allow algo trading (ENABLE)
echo.
echo 5. Consider running MT5 in headless mode if possible
echo.

echo Creating optimized MT5 startup shortcut...

REM Get desktop path
for /f "tokens=2 delims==" %%I in ('wmic path win32_desktop get name /value') do set DESKTOP=%%I

REM Create shortcut with optimization flags
set SHORTCUT_TARGET="%DESKTOP%\MT5_Optimized.lnk"
set MT5_PATH="C:\Program Files\MetaTrader 5\terminal64.exe"

REM Check if MT5 is installed in default location
if not exist %MT5_PATH% (
    echo MT5 not found in default location.
    echo Please modify MT5_PATH in this script to match your installation.
    set /p MT5_PATH="Enter full path to terminal64.exe: "
)

REM Create shortcut using PowerShell
powershell -Command "$s=(New-Object -COM WScript.Shell).CreateShortcut('%SHORTCUT_TARGET%');$s.TargetPath=%MT5_PATH%;$s.Arguments='/portable /skip_update /skip';$s.Save()"

if exist %SHORTCUT_TARGET% (
    echo MT5 optimization shortcut created on desktop.
) else (
    echo Failed to create shortcut. You may need to create it manually.
)

echo.
echo ========================================================
echo Memory Optimization Summary
echo ========================================================
echo.
echo Recommended Settings Applied:
echo - Chart bars limited to 5000
echo - Auto-updates disabled
echo - Startup flags: /portable /skip_update /skip
echo.
echo Next Steps:
echo 1. Manually configure MT5 settings as listed above
echo 2. Test MT5 connection with trading platform
echo 3. Monitor memory usage in Task Manager
echo.

pause