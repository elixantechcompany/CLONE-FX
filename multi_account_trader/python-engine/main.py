"""
Main Trading Engine for Multi-Account Trading Platform
Integrates trend analysis, signal generation, and multi-account execution
Designed for 24/7 operation on AWS t2.micro Windows instance
"""

import asyncio
import os
import sys
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import json

from dotenv import load_dotenv

# Import custom modules
from trend_analyzer import EMATrendAnalyzer
from signal_generator import SignalGenerator
from multi_account_executor import MultiAccountExecutor
from supabase import create_client, Client

# Configure logging
log_dir = Path(__file__).parent / "logs"
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s',
    handlers=[
        logging.FileHandler(log_dir / "trading_engine.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("TradingEngine")


class TradingEngine:
    """
    Main trading engine that orchestrates all components
    - Trend analysis using 50 EMA on H4/H1
    - Signal generation with 5-minute freshness
    - Multi-account execution with risk management
    - Funded account protection (3.5% daily loss limit)
    """
    
    def __init__(self):
        # Load environment variables
        load_dotenv()
        
        # Configuration
        self.supabase_url = os.getenv('SUPABASE_URL', '')
        self.supabase_key = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')
        self.symbol = os.getenv('MT5_SYMBOL', 'XAUUSD')
        self.daily_loss_limit_pct = float(os.getenv('DAILY_LOSS_LIMIT_PCT', '3.5'))
        self.risk_per_trade_pct = float(os.getenv('RISK_PER_TRADE_PCT', '1.0'))
        self.signal_lifetime_minutes = int(os.getenv('SIGNAL_LIFETIME_MINUTES', '5'))
        self.generation_interval = int(os.getenv('SIGNAL_GENERATION_INTERVAL_SECONDS', '60'))
        
        # Initialize components
        self.supabase: Optional[Client] = None
        self.trend_analyzer: Optional[EMATrendAnalyzer] = None
        self.signal_generator: Optional[SignalGenerator] = None
        self.executor: Optional[MultiAccountExecutor] = None
        
        # State
        self.is_running = False
        self.current_signal: Optional[Dict] = None
        self.last_generation_time: Optional[datetime] = None
        self.emergency_stop = False
        
        logger.info("Trading Engine initialized")
    
    def initialize_components(self) -> bool:
        """Initialize all trading components"""
        try:
            logger.info("Initializing trading components...")
            
            # Initialize Supabase client
            if not self.supabase_url or not self.supabase_key:
                logger.error("Supabase credentials not configured")
                return False
            
            self.supabase = create_client(self.supabase_url, self.supabase_key)
            logger.info("Supabase client initialized")
            
            # Initialize trend analyzer
            self.trend_analyzer = EMATrendAnalyzer(self.symbol)
            logger.info("Trend analyzer initialized")
            
            # Initialize signal generator
            self.signal_generator = SignalGenerator(self.supabase_url, self.supabase_key, self.symbol)
            logger.info("Signal generator initialized")
            
            # Initialize multi-account executor
            accounts = self.fetch_trading_accounts()
            if not accounts:
                logger.warning("No trading accounts found. Will wait for accounts to be added.")
            else:
                self.executor = MultiAccountExecutor(accounts, self.daily_loss_limit_pct)
                logger.info(f"Multi-account executor initialized with {len(accounts)} accounts")
            
            return True
            
        except Exception as e:
            logger.error(f"Error initializing components: {e}")
            return False
    
    def fetch_trading_accounts(self) -> List[Dict]:
        """Fetch active trading accounts from Supabase"""
        try:
            result = self.supabase.table('trading_accounts')\
                .select('*')\
                .eq('is_active', True)\
                .eq('connection_status', 'connected')\
                .execute()
            
            accounts = result.data if result.data else []
            logger.info(f"Fetched {len(accounts)} active trading accounts")
            return accounts
            
        except Exception as e:
            logger.error(f"Error fetching trading accounts: {e}")
            return []
    
    def check_emergency_commands(self) -> bool:
        """Check for emergency commands from Supabase"""
        try:
            result = self.supabase.table('emergency_commands')\
                .select('*')\
                .eq('status', 'pending')\
                .order('created_at', desc=True)\
                .limit(1)\
                .execute()
            
            if result.data and len(result.data) > 0:
                command = result.data[0]
                logger.warning(f"Emergency command received: {command['command_type']}")
                
                # Execute command
                if command['command_type'] == 'KILL_ALL' and self.executor:
                    self.executor.emergency_close_all()
                    self.emergency_stop = True
                
                # Update command status
                self.supabase.table('emergency_commands')\
                    .update({'status': 'executed', 'executed_at': datetime.now().isoformat()})\
                    .eq('id', command['id'])\
                    .execute()
                
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking emergency commands: {e}")
            return False
    
    def generate_and_execute_signals(self):
        """Generate signals and execute across all accounts"""
        try:
            if self.emergency_stop:
                logger.warning("Emergency stop active - skipping signal generation")
                return
            
            # Generate new signal
            signal = self.signal_generator.generate_signal()
            
            if not signal:
                logger.info("No signal generated - market conditions not suitable")
                return
            
            self.current_signal = signal
            self.last_generation_time = datetime.now()
            
            logger.info(f"New signal generated: {signal['direction']} @ {signal['entry']:.2f}")
            
            # Execute signal across all accounts if executor is available
            if self.executor:
                results = self.executor.execute_trade_all_accounts(
                    symbol=signal['symbol'],
                    direction=signal['direction'],
                    entry=signal['entry'],
                    stop_loss=signal['stop_loss'],
                    take_profit=signal['take_profit'],
                    risk_pct=self.risk_per_trade_pct
                )
                
                successful = sum(1 for ticket in results.values() if ticket is not None)
                logger.info(f"Signal executed on {successful}/{len(results)} accounts")
            else:
                logger.info("No executor available - signal saved for manual execution")
            
        except Exception as e:
            logger.error(f"Error in signal generation and execution: {e}")
    
    def update_account_status(self):
        """Update account status in Supabase"""
        try:
            if not self.executor:
                return
            
            for account in self.executor.accounts:
                # Update connection status and financial data
                update_data = {
                    'connection_status': 'connected' if account.is_connected else 'disconnected',
                    'balance': account.balance,
                    'equity': account.equity,
                    'daily_profit_loss': account.equity - account.daily_start_equity,
                    'last_sync': datetime.now().isoformat()
                }
                
                # Find account ID from original data
                account_data = next(
                    (acc for acc in self.fetch_trading_accounts() 
                     if acc['account_number'] == str(account.login)),
                    None
                )
                
                if account_data:
                    self.supabase.table('trading_accounts')\
                        .update(update_data)\
                        .eq('id', account_data['id'])\
                        .execute()
            
        except Exception as e:
            logger.error(f"Error updating account status: {e}")
    
    def run(self):
        """Main trading loop"""
        logger.info("Starting trading engine...")
        self.is_running = True
        
        try:
            # Initialize components
            if not self.initialize_components():
                logger.error("Failed to initialize components. Exiting.")
                return
            
            # Connect to accounts if executor exists
            if self.executor:
                connected = self.executor.connect_all_accounts()
                if connected == 0:
                    logger.warning("No accounts connected. Will retry in next cycle.")
            
            # Start equity monitoring in background
            if self.executor:
                import threading
                monitor_thread = threading.Thread(
                    target=self.executor.monitor_equity,
                    args=(60,),  # Check every 60 seconds
                    daemon=True
                )
                monitor_thread.start()
            
            # Main trading loop
            logger.info("Entering main trading loop...")
            
            while self.is_running and not self.emergency_stop:
                try:
                    # Check emergency commands
                    if self.check_emergency_commands():
                        logger.warning("Emergency command executed - pausing trading")
                        time.sleep(30)  # Wait before checking again
                        continue
                    
                    # Refresh account list periodically
                    if not self.executor or len(self.executor.accounts) == 0:
                        accounts = self.fetch_trading_accounts()
                        if accounts:
                            self.executor = MultiAccountExecutor(accounts, self.daily_loss_limit_pct)
                            self.executor.connect_all_accounts()
                    
                    # Generate and execute signals
                    self.generate_and_execute_signals()
                    
                    # Update account status
                    self.update_account_status()
                    
                    # Cleanup expired signals
                    self.signal_generator.cleanup_expired_signals()
                    
                    # Wait for next cycle
                    logger.info(f"Waiting {self.generation_interval}s for next cycle...")
                    time.sleep(self.generation_interval)
                    
                except KeyboardInterrupt:
                    logger.info("Keyboard interrupt received - shutting down...")
                    self.is_running = False
                    break
                except Exception as e:
                    logger.error(f"Error in main loop: {e}")
                    time.sleep(30)  # Wait before retrying
            
        except Exception as e:
            logger.error(f"Fatal error in trading engine: {e}")
        finally:
            self.shutdown()
    
    def shutdown(self):
        """Cleanup and shutdown"""
        logger.info("Shutting down trading engine...")
        self.is_running = False
        
        if self.executor:
            self.executor.disconnect_all_accounts()
        
        if self.trend_analyzer:
            self.trend_analyzer.shutdown_mt5()
        
        logger.info("Trading engine shutdown complete")


def main():
    """Main entry point"""
    logger.info("=" * 60)
    logger.info("Multi-Account Trading Engine Starting")
    logger.info("=" * 60)
    
    engine = TradingEngine()
    
    try:
        engine.run()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
    finally:
        engine.shutdown()


if __name__ == "__main__":
    main()