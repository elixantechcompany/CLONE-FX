"""
Multi-Account Execution Engine
Concurrently executes trades across up to 5 MT5 accounts with dynamic lot sizing
Implements funded account protection (3.5% daily loss limit)
"""

import MetaTrader5 as mt5
import pandas as pd
import time
import threading
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import logging
from dataclasses import dataclass
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MultiAccountExecutor")


@dataclass
class MT5Account:
    """Represents a single MT5 trading account"""
    account_id: str
    login: int
    password: str
    server: str
    path: Optional[str] = None
    balance: float = 0.0
    equity: float = 0.0
    daily_start_equity: float = 0.0
    is_connected: bool = False
    mt5_initialized: bool = False


class MultiAccountExecutor:
    """
    Manages multiple MT5 accounts and executes trades concurrently
    Implements funded account protection with 3.5% daily loss limit
    """
    
    def __init__(self, accounts: List[Dict], daily_loss_limit_pct: float = 3.5):
        """
        Initialize multi-account executor
        
        Args:
            accounts: List of account dictionaries with login, password, server
            daily_loss_limit_pct: Daily loss limit percentage (default 3.5%)
        """
        self.accounts: List[MT5Account] = []
        self.daily_loss_limit_pct = daily_loss_limit_pct
        self.lock = threading.Lock()
        self.emergency_stop = False
        
        # Initialize MT5 accounts
        for acc_data in accounts:
            account = MT5Account(
                account_id=acc_data.get('id', ''),
                login=int(acc_data['account_number']),
                password=acc_data['encrypted_password'],
                server=acc_data['mt5_server'],
                path=acc_data.get('mt5_path')
            )
            self.accounts.append(account)
        
        logger.info(f"Initialized {len(self.accounts)} trading accounts")
    
    def connect_account(self, account: MT5Account) -> bool:
        """Connect to a single MT5 account"""
        try:
            # Initialize MT5 for this account
            if not mt5.initialize(
                path=account.path,
                login=account.login,
                password=account.password,
                server=account.server
            ):
                logger.error(f"Failed to initialize MT5 for account {account.account_id}: {mt5.last_error()}")
                return False
            
            account.mt5_initialized = True
            
            # Verify connection
            account_info = mt5.account_info()
            if account_info is None:
                logger.error(f"Failed to get account info for {account.account_id}")
                mt5.shutdown()
                account.mt5_initialized = False
                return False
            
            account.balance = account_info.balance
            account.equity = account_info.equity
            account.daily_start_equity = account.equity  # Set daily baseline
            account.is_connected = True
            
            logger.info(f"Successfully connected to account {account.account_id} (Balance: ${account.balance:.2f})")
            return True
            
        except Exception as e:
            logger.error(f"Error connecting to account {account.account_id}: {e}")
            if account.mt5_initialized:
                mt5.shutdown()
                account.mt5_initialized = False
            return False
    
    def connect_all_accounts(self) -> int:
        """Connect to all MT5 accounts concurrently"""
        logger.info("Connecting to all MT5 accounts...")
        
        connected_count = 0
        threads = []
        
        def connect_wrapper(account: MT5Account):
            nonlocal connected_count
            if self.connect_account(account):
                with self.lock:
                    connected_count += 1
        
        # Connect to each account in separate thread
        for account in self.accounts:
            thread = threading.Thread(target=connect_wrapper, args=(account,))
            threads.append(thread)
            thread.start()
        
        # Wait for all connections to complete
        for thread in threads:
            thread.join(timeout=30)
        
        logger.info(f"Connected to {connected_count}/{len(self.accounts)} accounts")
        return connected_count
    
    def disconnect_account(self, account: MT5Account):
        """Disconnect from a single MT5 account"""
        try:
            if account.mt5_initialized:
                mt5.shutdown()
                account.mt5_initialized = False
                account.is_connected = False
                logger.info(f"Disconnected from account {account.account_id}")
        except Exception as e:
            logger.error(f"Error disconnecting account {account.account_id}: {e}")
    
    def disconnect_all_accounts(self):
        """Disconnect from all MT5 accounts"""
        logger.info("Disconnecting from all accounts...")
        for account in self.accounts:
            self.disconnect_account(account)
        logger.info("All accounts disconnected")
    
    def calculate_lot_size(self, account: MT5Account, symbol: str, stop_loss: float, risk_pct: float = 1.0) -> float:
        """
        Calculate dynamic lot size based on account equity and risk percentage
        
        Args:
            account: MT5 account
            symbol: Trading symbol (e.g., 'XAUUSD')
            stop_loss: Stop loss price
            risk_pct: Risk percentage per trade (default 1.0%)
        """
        try:
            # Get current symbol info
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                logger.error(f"Cannot get symbol info for {symbol}")
                return 0.0
            
            # Get current price
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                logger.error(f"Cannot get tick for {symbol}")
                return 0.0
            
            current_price = tick.bid if tick else 0
            if current_price == 0:
                return 0.0
            
            # Calculate risk amount in account currency
            risk_amount = account.equity * (risk_pct / 100)
            
            # Calculate stop loss distance in points
            sl_distance = abs(current_price - stop_loss)
            
            if sl_distance == 0:
                return 0.0
            
            # Calculate lot size
            # Formula: Risk Amount / (SL Distance * Value per Point)
            # For XAUUSD, 1 point = 0.01, value per point depends on lot size
            # Simplified calculation for XAUUSD
            if 'XAU' in symbol.upper():
                # For Gold: 1 lot = 100 oz, 1 point = $0.01, so 1 point = $1 per lot
                value_per_point = 1.0
            else:
                # Default calculation
                value_per_point = symbol_info.trade_tick_value
            
            lot_size = risk_amount / (sl_distance * value_per_point)
            
            # Round to valid lot size
            min_lot = symbol_info.volume_min
            max_lot = symbol_info.volume_max
            lot_step = symbol_info.volume_step
            
            # Round to lot step
            lot_size = round(lot_size / lot_step) * lot_step
            
            # Ensure within limits
            lot_size = max(min_lot, min(max_lot, lot_size))
            
            logger.info(f"Account {account.account_id}: Calculated lot size {lot_size:.2f} for {risk_pct}% risk")
            return lot_size
            
        except Exception as e:
            logger.error(f"Error calculating lot size: {e}")
            return 0.0
    
    def check_daily_loss_limit(self, account: MT5Account) -> Tuple[bool, float]:
        """
        Check if account has exceeded daily loss limit
        
        Returns:
            (is_safe, current_loss_pct)
        """
        try:
            # Update account equity
            account_info = mt5.account_info()
            if account_info:
                account.equity = account_info.equity
            
            # Calculate daily loss percentage
            if account.daily_start_equity > 0:
                daily_pnl = account.equity - account.daily_start_equity
                daily_loss_pct = (daily_pnl / account.daily_start_equity) * 100
                
                # Check if loss exceeds limit
                is_safe = daily_loss_pct > -self.daily_loss_limit_pct
                
                if not is_safe:
                    logger.warning(f"Account {account.account_id} exceeded daily loss limit: {daily_loss_pct:.2f}%")
                
                return is_safe, daily_loss_pct
            
            return True, 0.0
            
        except Exception as e:
            logger.error(f"Error checking daily loss limit: {e}")
            return True, 0.0
    
    def execute_trade(self, account: MT5Account, symbol: str, direction: str, 
                     entry: float, stop_loss: float, take_profit: float, 
                     risk_pct: float = 1.0) -> Optional[int]:
        """
        Execute a trade on a single account
        
        Returns:
            Order ticket if successful, None otherwise
        """
        try:
            if not account.is_connected or self.emergency_stop:
                return None
            
            # Check daily loss limit before trade
            is_safe, loss_pct = self.check_daily_loss_limit(account)
            if not is_safe:
                logger.warning(f"Account {account.account_id} blocked due to daily loss limit: {loss_pct:.2f}%")
                return None
            
            # Calculate lot size
            lot_size = self.calculate_lot_size(account, symbol, stop_loss, risk_pct)
            if lot_size <= 0:
                logger.error(f"Invalid lot size calculated for account {account.account_id}")
                return None
            
            # Prepare order
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                logger.error(f"Symbol {symbol} not found")
                return None
            
            # Determine order type
            order_type = mt5.ORDER_TYPE_BUY if direction.upper() == 'BUY' else mt5.ORDER_TYPE_SELL
            
            # Prepare order request
            request = {
                'action': mt5.TRADE_ACTION_DEAL,
                'symbol': symbol,
                'volume': lot_size,
                'type': order_type,
                'price': mt5.symbol_info_tick(symbol).ask if direction.upper() == 'BUY' else mt5.symbol_info_tick(symbol).bid,
                'sl': stop_loss,
                'tp': take_profit,
                'deviation': 20,
                'magic': 123456,
                'comment': f'Multi-Account Trader {direction}',
                'type_time': mt5.ORDER_TIME_GTC,
                'type_filling': mt5.ORDER_FILLING_IOC,
            }
            
            # Send order
            result = mt5.order_send(request)
            
            if result is None:
                logger.error(f"Order send failed for account {account.account_id}: {mt5.last_error()}")
                return None
            
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                logger.error(f"Order rejected for account {account.account_id}: {result.comment}")
                return None
            
            logger.info(f"Order executed successfully for account {account.account_id}: Ticket #{result.order}")
            return result.order
            
        except Exception as e:
            logger.error(f"Error executing trade on account {account.account_id}: {e}")
            return None
    
    def execute_trade_all_accounts(self, symbol: str, direction: str, 
                                   entry: float, stop_loss: float, 
                                   take_profit: float, risk_pct: float = 1.0) -> Dict[str, Optional[int]]:
        """
        Execute trade concurrently across all connected accounts
        
        Returns:
            Dictionary mapping account_id to order ticket (or None if failed)
        """
        logger.info(f"Executing {direction} trade on {symbol} across all accounts...")
        
        results = {}
        threads = []
        
        def execute_wrapper(account: MT5Account):
            ticket = self.execute_trade(account, symbol, direction, entry, stop_loss, take_profit, risk_pct)
            with self.lock:
                results[account.account_id] = ticket
        
        # Execute on each account in separate thread
        for account in self.accounts:
            if account.is_connected and not self.emergency_stop:
                thread = threading.Thread(target=execute_wrapper, args=(account,))
                threads.append(thread)
                thread.start()
        
        # Wait for all executions to complete
        for thread in threads:
            thread.join(timeout=30)
        
        # Log results
        successful = sum(1 for ticket in results.values() if ticket is not None)
        logger.info(f"Trade execution completed: {successful}/{len(results)} accounts successful")
        
        return results
    
    def close_all_positions(self, account: MT5Account) -> int:
        """Close all positions for a specific account"""
        try:
            if not account.is_connected:
                return 0
            
            positions = mt5.positions_get()
            if positions is None or len(positions) == 0:
                return 0
            
            closed_count = 0
            for position in positions:
                # Prepare close request
                if position.type == mt5.POSITION_TYPE_BUY:
                    order_type = mt5.ORDER_TYPE_SELL
                    price = mt5.symbol_info_tick(position.symbol).bid
                else:
                    order_type = mt5.ORDER_TYPE_BUY
                    price = mt5.symbol_info_tick(position.symbol).ask
                
                request = {
                    'action': mt5.TRADE_ACTION_DEAL,
                    'symbol': position.symbol,
                    'volume': position.volume,
                    'type': order_type,
                    'position': position.ticket,
                    'price': price,
                    'deviation': 20,
                    'magic': 123456,
                    'comment': 'Emergency close',
                    'type_time': mt5.ORDER_TIME_GTC,
                    'type_filling': mt5.ORDER_FILLING_IOC,
                }
                
                result = mt5.order_send(request)
                if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                    closed_count += 1
                    logger.info(f"Closed position #{position.ticket} for account {account.account_id}")
            
            return closed_count
            
        except Exception as e:
            logger.error(f"Error closing positions for account {account.account_id}: {e}")
            return 0
    
    def emergency_close_all(self) -> Dict[str, int]:
        """
        Emergency close all positions across all accounts
        Sets emergency_stop flag to prevent new trades
        """
        logger.warning("EMERGENCY: Closing all positions across all accounts!")
        self.emergency_stop = True
        
        results = {}
        threads = []
        
        def close_wrapper(account: MT5Account):
            closed = self.close_all_positions(account)
            with self.lock:
                results[account.account_id] = closed
        
        for account in self.accounts:
            if account.is_connected:
                thread = threading.Thread(target=close_wrapper, args=(account,))
                threads.append(thread)
                thread.start()
        
        for thread in threads:
            thread.join(timeout=60)
        
        total_closed = sum(results.values())
        logger.warning(f"EMERGENCY: Closed {total_closed} positions across {len(results)} accounts")
        
        return results
    
    def monitor_equity(self, check_interval: int = 60):
        """
        Continuously monitor account equity and enforce daily loss limits
        Runs in background thread
        
        Args:
            check_interval: Check interval in seconds (default 60)
        """
        logger.info(f"Starting equity monitoring (checking every {check_interval}s)...")
        
        while not self.emergency_stop:
            try:
                for account in self.accounts:
                    if account.is_connected:
                        is_safe, loss_pct = self.check_daily_loss_limit(account)
                        if not is_safe:
                            logger.error(f"Account {account.account_id} exceeded daily loss limit! Triggering emergency close...")
                            self.emergency_close_all()
                            return
                
                time.sleep(check_interval)
                
            except Exception as e:
                logger.error(f"Error in equity monitoring: {e}")
                time.sleep(check_interval)
        
        logger.info("Equity monitoring stopped")


def main():
    """Test the multi-account executor"""
    # Example usage (replace with actual account data)
    test_accounts = [
        {
            'id': 'account_1',
            'account_number': '12345678',
            'encrypted_password': 'password1',
            'mt5_server': 'Exness-MT5Trial'
        }
    ]
    
    executor = MultiAccountExecutor(test_accounts, daily_loss_limit_pct=3.5)
    
    try:
        # Connect to accounts
        connected = executor.connect_all_accounts()
        if connected == 0:
            logger.error("No accounts connected. Exiting.")
            return
        
        # Example trade execution
        results = executor.execute_trade_all_accounts(
            symbol='XAUUSD',
            direction='BUY',
            entry=2650.0,
            stop_loss=2645.0,
            take_profit=2660.0,
            risk_pct=1.0
        )
        
        logger.info(f"Trade results: {results}")
        
        # Monitor for a short time
        time.sleep(10)
        
    finally:
        executor.disconnect_all_accounts()


if __name__ == "__main__":
    main()