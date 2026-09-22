"""
AWS Instance Setup Script for Multi-Account Trading Platform
Optimized for AWS t2.micro Windows instance (1GB RAM)
"""

import subprocess
import os
import sys
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AWSSetup")


class AWSSetup:
    """Automated setup for AWS t2.micro Windows instance"""
    
    def __init__(self):
        self.python_version = "3.11"
        self.project_dir = Path.cwd()
        self.mt5_optimization_applied = False
        
    def check_system_requirements(self) -> bool:
        """Check if system meets minimum requirements"""
        try:
            # Check Windows OS
            if sys.platform != "win32":
                logger.error("This setup script is designed for Windows only")
                return False
            
            # Check available memory (should be ~1GB for t2.micro)
            try:
                import psutil
                mem = psutil.virtual_memory()
                logger.info(f"Total Memory: {mem.total / (1024**3):.2f} GB")
                logger.info(f"Available Memory: {mem.available / (1024**3):.2f} GB")
                
                if mem.total < 800 * 1024 * 1024:  # Less than 800MB
                    logger.warning("Low memory detected. Optimization will be critical.")
            except ImportError:
                logger.warning("psutil not installed. Skipping memory check.")
            
            return True
        except Exception as e:
            logger.error(f"Error checking system requirements: {e}")
            return False
    
    def install_python_dependencies(self) -> bool:
        """Install required Python packages"""
        try:
            logger.info("Installing Python dependencies...")
            
            requirements_file = self.project_dir / "python-engine" / "requirements.txt"
            if not requirements_file.exists():
                logger.error(f"Requirements file not found: {requirements_file}")
                return False
            
            # Install dependencies
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", str(requirements_file)],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                logger.error(f"Failed to install dependencies: {result.stderr}")
                return False
            
            logger.info("Python dependencies installed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error installing Python dependencies: {e}")
            return False
    
    def optimize_mt5_settings(self) -> bool:
        """
        Optimize MT5 settings for low-memory AWS instance
        - Hide visual UI
        - Limit max bars in charts
        - Disable unnecessary features
        """
        try:
            logger.info("Applying MT5 memory optimizations...")
            
            # This would typically involve modifying MT5 configuration files
            # Since MT5 configuration is complex, we'll create a batch script
            # that the user can run to apply optimizations
            
            batch_script = self.project_dir / "aws-deployment" / "mt5_memory_optimization.bat"
            
            batch_content = """@echo off
REM MT5 Memory Optimization for AWS t2.micro
REM This script optimizes MT5 settings for low-memory environments

echo Applying MT5 memory optimizations...

REM Note: These optimizations typically require manual configuration in MT5
REM The following are the recommended settings:

echo 1. Max Bars in Charts: 5000 (default: 100000+)
echo 2. Max Bars in History: 5000 (default: 100000+)  
echo 3. Disable News Tab: Tools -> Options -> News -> Disable
echo 4. Disable Mail Tab: Tools -> Options -> Mail -> Disable
echo 5. Disable Calendar Tab: Tools -> Options -> Calendar -> Disable
echo 6. Reduce Chart Updates: Tools -> Options -> Charts -> Max bars
echo 7. Disable 3D Graphics: Tools -> Options -> Charts -> Disable 3D
echo 8. Use Simple Color Scheme: Tools -> Options -> Charts

echo.
echo IMPORTANT: MT5 visual optimization requires manual configuration:
echo - Start MT5 with /portable mode for isolation
echo - Use terminal64.exe /skip_update to disable auto-updates
echo - Consider running MT5 in headless mode if possible

echo.
echo Creating optimized MT5 startup shortcut...

REM Create shortcut with optimization flags
set SHORTCUT_TARGET="%USERPROFILE%\Desktop\MT5_Optimized.lnk"
set MT5_PATH="C:\\Program Files\\MetaTrader 5\\terminal64.exe"

powershell -Command "$s=(New-Object -COM WScript.Shell).CreateShortcut('%SHORTCUT_TARGET%');$s.TargetPath='%MT5_PATH%';$s.Arguments='/portable /skip_update /skip';$s.Save()"

echo MT5 optimization shortcut created on desktop.
echo Please manually configure MT5 settings as listed above.
pause
"""
            
            batch_script.write_text(batch_content)
            logger.info(f"MT5 optimization script created: {batch_script}")
            
            self.mt5_optimization_applied = True
            return True
            
        except Exception as e:
            logger.error(f"Error creating MT5 optimization script: {e}")
            return False
    
    def create_system_service(self) -> bool:
        """Create Windows service for continuous operation"""
        try:
            logger.info("Creating Windows service configuration...")
            
            # Create a batch script to run the trading engine as a service
            service_script = self.project_dir / "aws-deployment" / "run_trading_service.bat"
            
            service_content = """@echo off
REM Multi-Account Trading Engine Service
REM Runs continuously on AWS instance

cd /d "%~dp0..\\python-engine"

echo Starting Multi-Account Trading Engine...
python main.py

if errorlevel 1 (
    echo Error occurred. Restarting in 30 seconds...
    timeout /t 30
    goto :start
)

:start
echo Trading engine stopped. Exiting.
"""
            
            service_script.write_text(service_content)
            logger.info(f"Service script created: {service_script}")
            
            # Instructions for setting up as Windows service
            logger.info("To set up as Windows service, use:")
            logger.info("sc create TradingEngine binPath= \"C:\\path\\to\\run_trading_service.bat\" start= auto")
            logger.info("sc start TradingEngine")
            
            return True
            
        except Exception as e:
            logger.error(f"Error creating system service: {e}")
            return False
    
    def configure_environment_variables(self) -> bool:
        """Configure required environment variables"""
        try:
            logger.info("Configuring environment variables...")
            
            # Create .env template
            env_template = self.project_dir / "python-engine" / ".env.template"
            
            env_content = """# Supabase Configuration
SUPABASE_URL=your-supabase-project-url.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key

# MT5 Configuration
MT5_SYMBOL=XAUUSD
MT5_H4_TIMEFRAME=H4
MT5_H1_TIMEFRAME=H1

# Risk Management
DAILY_LOSS_LIMIT_PCT=3.5
RISK_PER_TRADE_PCT=1.0
MIN_RR_RATIO=2.0

# Signal Configuration
SIGNAL_LIFETIME_MINUTES=5
SIGNAL_GENERATION_INTERVAL_SECONDS=60

# Logging
LOG_LEVEL=INFO
LOG_FILE=logs/trading_engine.log
"""
            
            env_template.write_text(env_content)
            logger.info(f"Environment template created: {env_template}")
            logger.info("Please configure .env file with your actual credentials")
            
            return True
            
        except Exception as e:
            logger.error(f"Error configuring environment variables: {e}")
            return False
    
    def create_startup_script(self) -> bool:
        """Create Windows startup script for auto-launch"""
        try:
            logger.info("Creating Windows startup script...")
            
            startup_script = self.project_dir / "aws-deployment" / "startup.bat"
            
            startup_content = """@echo off
REM Auto-startup script for Multi-Account Trading Engine
REM Place this in Windows Startup folder

cd /d "%~dp0python-engine"

echo Starting Multi-Account Trading Engine at %date% %time%
python main.py >> logs\\startup.log 2>&1

if errorlevel 1 (
    echo Trading engine crashed. Restarting in 60 seconds...
    timeout /t 60
    goto :start
)

:start
echo Trading engine stopped normally.
"""
            
            startup_script.write_text(startup_content)
            logger.info(f"Startup script created: {startup_script}")
            logger.info("To enable auto-startup, copy this file to:")
            logger.info("C:\\Users\\Administrator\\AppData\\Roaming\\Microsoft\\Windows\\Start Menu\\Programs\\Startup")
            
            return True
            
        except Exception as e:
            logger.error(f"Error creating startup script: {e}")
            return False
    
    def setup_monitoring(self) -> bool:
        """Setup basic monitoring and health checks"""
        try:
            logger.info("Setting up monitoring...")
            
            # Create logs directory
            logs_dir = self.project_dir / "python-engine" / "logs"
            logs_dir.mkdir(exist_ok=True)
            
            # Create health check script
            health_script = self.project_dir / "aws-deployment" / "health_check.bat"
            
            health_content = """@echo off
REM Health check script for Trading Engine
REM Run this periodically to check system status

echo Trading Engine Health Check
echo ============================
echo.

REM Check if Python process is running
tasklist /FI "IMAGENAME eq python.exe" /FO TABLE | find /I "python.exe"
if errorlevel 1 (
    echo WARNING: Python process not running
) else (
    echo OK: Python process is running
)

REM Check memory usage
wmic OS get FreePhysicalMemory /Value
echo.

REM Check disk space
wmic logicaldisk get size,freespace,caption
echo.

REM Check recent log files
if exist "python-engine\\logs\\trading_engine.log" (
    echo Last 5 lines of trading log:
    powershell "Get-Content python-engine\\logs\\trading_engine.log -Tail 5"
) else (
    echo No log file found
)

echo.
echo Health check completed.
pause
"""
            
            health_script.write_text(health_content)
            logger.info(f"Health check script created: {health_script}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error setting up monitoring: {e}")
            return False
    
    def run_setup(self) -> bool:
        """Run complete setup process"""
        logger.info("Starting AWS instance setup...")
        logger.info("=" * 50)
        
        steps = [
            ("Checking system requirements", self.check_system_requirements),
            ("Installing Python dependencies", self.install_python_dependencies),
            ("Optimizing MT5 settings", self.optimize_mt5_settings),
            ("Configuring environment variables", self.configure_environment_variables),
            ("Creating system service", self.create_system_service),
            ("Creating startup script", self.create_startup_script),
            ("Setting up monitoring", self.setup_monitoring),
        ]
        
        failed_steps = []
        
        for step_name, step_func in steps:
            logger.info(f"\n{step_name}...")
            try:
                if not step_func():
                    logger.error(f"Failed: {step_name}")
                    failed_steps.append(step_name)
            except Exception as e:
                logger.error(f"Error in {step_name}: {e}")
                failed_steps.append(step_name)
        
        logger.info("\n" + "=" * 50)
        if failed_steps:
            logger.error(f"Setup completed with {len(failed_steps)} failed steps:")
            for step in failed_steps:
                logger.error(f"  - {step}")
            return False
        else:
            logger.info("AWS instance setup completed successfully!")
            logger.info("\nNext steps:")
            logger.info("1. Configure .env file with your Supabase credentials")
            logger.info("2. Run MT5 optimization script")
            logger.info("3. Configure MT5 terminals manually")
            logger.info("4. Test the trading engine")
            logger.info("5. Set up Windows startup for auto-launch")
            return True


def main():
    """Main setup function"""
    setup = AWSSetup()
    
    try:
        success = setup.run_setup()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.info("Setup interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error during setup: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()