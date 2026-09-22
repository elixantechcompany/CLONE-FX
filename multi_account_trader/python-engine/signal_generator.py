"""
Signal Generator with Freshness Tracking
Generates trading signals with 5-minute expiration and freshness tracking
Integrates with Supabase for signal storage and retrieval
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import logging
from supabase import create_client, Client

from trend_analyzer import EMATrendAnalyzer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SignalGenerator")


class SignalGenerator:
    """
    Generates trading signals with automatic freshness tracking
    Signals expire after 5 minutes to prevent stale data trading
    """
    
    def __init__(self, supabase_url: str, supabase_key: str, symbol: str = "XAUUSD"):
        self.symbol = symbol
        self.signal_lifetime_minutes = 5
        self.trend_analyzer = EMATrendAnalyzer(symbol)
        
        # Initialize Supabase client
        self.supabase: Client = create_client(supabase_url, supabase_key)
        
        # Signal cache
        self.current_signal: Optional[Dict] = None
        self.last_generation_time: Optional[datetime] = None
        
        logger.info(f"Signal generator initialized for {symbol}")
    
    def generate_signal(self) -> Optional[Dict]:
        """
        Generate a new trading signal using the trend analyzer
        
        Returns:
            Signal dictionary or None if conditions not met
        """
        try:
            # Connect to MT5
            if not self.trend_analyzer.connect_mt5():
                logger.error("Failed to connect to MT5 for signal generation")
                return None
            
            # Generate signal
            signal = self.trend_analyzer.generate_signal()
            
            if signal:
                # Add metadata
                signal['generated_at'] = datetime.now().isoformat()
                signal['expires_at'] = (datetime.now() + timedelta(minutes=self.signal_lifetime_minutes)).isoformat()
                signal['is_valid'] = True
                
                # Update cache
                self.current_signal = signal
                self.last_generation_time = datetime.now()
                
                logger.info(f"Generated new signal: {signal['direction']} @ {signal['entry']:.2f}")
                return signal
            else:
                logger.info("No signal generated - market conditions not suitable")
                return None
                
        except Exception as e:
            logger.error(f"Error generating signal: {e}")
            return None
        finally:
            self.trend_analyzer.shutdown_mt5()
    
    def check_signal_freshness(self, signal: Dict) -> Dict:
        """
        Check if a signal is still fresh (not expired)
        
        Returns:
            Dictionary with freshness status and age information
        """
        if not signal:
            return {
                'is_fresh': False,
                'age_seconds': 0,
                'age_text': 'No signal',
                'opacity': 0.0
            }
        
        try:
            generated_time = datetime.fromisoformat(signal['generated_at'])
            expires_time = datetime.fromisoformat(signal['expires_at'])
            current_time = datetime.now()
            
            age_seconds = (current_time - generated_time).total_seconds()
            time_until_expiry = (expires_time - current_time).total_seconds()
            
            is_fresh = time_until_expiry > 0
            
            # Calculate opacity based on freshness (fades as it gets older)
            total_lifetime = self.signal_lifetime_minutes * 60
            remaining_ratio = max(0, time_until_expiry / total_lifetime)
            opacity = 0.3 + (0.7 * remaining_ratio)  # Minimum 0.3 opacity
            
            # Format age text
            if age_seconds < 60:
                age_text = f"{int(age_seconds)}s ago"
            elif age_seconds < 3600:
                age_text = f"{int(age_seconds / 60)}m ago"
            else:
                age_text = f"{int(age_seconds / 3600)}h ago"
            
            return {
                'is_fresh': is_fresh,
                'age_seconds': age_seconds,
                'age_text': age_text,
                'opacity': opacity,
                'expires_at': signal['expires_at'],
                'time_until_expiry': time_until_expiry
            }
            
        except Exception as e:
            logger.error(f"Error checking signal freshness: {e}")
            return {
                'is_fresh': False,
                'age_seconds': 0,
                'age_text': 'Error',
                'opacity': 0.0
            }
    
    def save_signal_to_supabase(self, signal: Dict) -> bool:
        """
        Save generated signal to Supabase database
        
        Returns:
            True if successful, False otherwise
        """
        try:
            signal_data = {
                'symbol': signal['symbol'],
                'direction': signal['direction'],
                'entry_price': signal['entry'],
                'stop_loss': signal['stop_loss'],
                'take_profit': signal['take_profit'],
                'risk_reward_ratio': signal['risk_reward_ratio'],
                'signal_time': signal['generated_at'],
                'expires_at': signal['expires_at'],
                'h4_ema50': signal.get('h4_ema50'),
                'h1_ema50': signal.get('h1_ema50'),
                'h4_price_above_ema': signal.get('h4_price_above_ema'),
                'h1_price_above_ema': signal.get('h1_price_above_ema'),
                'atr_value': signal.get('atr_value'),
                'is_valid': True
            }
            
            result = self.supabase.table('trading_signals').insert(signal_data).execute()
            
            if result.data:
                logger.info(f"Signal saved to Supabase with ID: {result.data[0]['id']}")
                return True
            else:
                logger.error("Failed to save signal to Supabase")
                return False
                
        except Exception as e:
            logger.error(f"Error saving signal to Supabase: {e}")
            return False
    
    def get_latest_signals(self, limit: int = 10) -> List[Dict]:
        """
        Retrieve latest signals from Supabase
        
        Returns:
            List of signal dictionaries
        """
        try:
            result = self.supabase.table('trading_signals')\
                .select('*')\
                .eq('is_valid', True)\
                .order('created_at', desc=True)\
                .limit(limit)\
                .execute()
            
            signals = result.data if result.data else []
            
            # Add freshness information to each signal
            for signal in signals:
                freshness = self.check_signal_freshness(signal)
                signal['freshness'] = freshness
            
            logger.info(f"Retrieved {len(signals)} signals from Supabase")
            return signals
            
        except Exception as e:
            logger.error(f"Error retrieving signals from Supabase: {e}")
            return []
    
    def cleanup_expired_signals(self) -> int:
        """
        Mark expired signals as invalid in Supabase
        
        Returns:
            Number of signals marked as expired
        """
        try:
            current_time = datetime.now().isoformat()
            
            result = self.supabase.table('trading_signals')\
                .update({'is_valid': False})\
                .lt('expires_at', current_time)\
                .eq('is_valid', True)\
                .execute()
            
            expired_count = len(result.data) if result.data else 0
            
            if expired_count > 0:
                logger.info(f"Marked {expired_count} signals as expired")
            
            return expired_count
            
        except Exception as e:
            logger.error(f"Error cleaning up expired signals: {e}")
            return 0
    
    def get_current_signal_with_freshness(self) -> Optional[Dict]:
        """
        Get the current signal with freshness information
        
        Returns:
            Signal dictionary with freshness info, or None if no valid signal
        """
        if not self.current_signal:
            return None
        
        # Check freshness
        freshness = self.check_signal_freshness(self.current_signal)
        
        # If signal is expired, clear it
        if not freshness['is_fresh']:
            logger.info("Current signal has expired")
            self.current_signal = None
            return None
        
        # Add freshness info to signal
        signal_with_freshness = self.current_signal.copy()
        signal_with_freshness['freshness'] = freshness
        
        return signal_with_freshness
    
    async def continuous_generation_loop(self, interval_seconds: int = 60):
        """
        Continuously generate signals at specified intervals
        
        Args:
            interval_seconds: Generation interval in seconds
        """
        logger.info(f"Starting continuous signal generation (every {interval_seconds}s)...")
        
        while True:
            try:
                # Cleanup expired signals first
                self.cleanup_expired_signals()
                
                # Generate new signal
                signal = self.generate_signal()
                
                if signal:
                    # Save to Supabase
                    self.save_signal_to_supabase(signal)
                
                # Wait for next interval
                await asyncio.sleep(interval_seconds)
                
            except Exception as e:
                logger.error(f"Error in continuous generation loop: {e}")
                await asyncio.sleep(interval_seconds)


def main():
    """Test the signal generator"""
    import os
    
    # Get Supabase credentials from environment
    supabase_url = os.getenv('SUPABASE_URL', '')
    supabase_key = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')
    
    if not supabase_url or not supabase_key:
        logger.error("Supabase credentials not set in environment variables")
        return
    
    generator = SignalGenerator(supabase_url, supabase_key, "XAUUSD")
    
    try:
        # Generate a signal
        signal = generator.generate_signal()
        
        if signal:
            print("\n=== GENERATED SIGNAL ===")
            print(f"Direction: {signal['direction']}")
            print(f"Entry: {signal['entry']:.2f}")
            print(f"Stop Loss: {signal['stop_loss']:.2f}")
            print(f"Take Profit: {signal['take_profit']:.2f}")
            print(f"Risk/Reward: {signal['risk_reward_ratio']:.2f}")
            print(f"Generated: {signal['generated_at']}")
            print(f"Expires: {signal['expires_at']}")
            
            # Check freshness
            freshness = generator.check_signal_freshness(signal)
            print(f"\n=== FRESHNESS STATUS ===")
            print(f"Is Fresh: {freshness['is_fresh']}")
            print(f"Age: {freshness['age_text']}")
            print(f"Opacity: {freshness['opacity']:.2f}")
            
            # Save to Supabase
            if generator.save_signal_to_supabase(signal):
                print("Signal saved to Supabase successfully")
            
            # Retrieve latest signals
            latest_signals = generator.get_latest_signals(5)
            print(f"\n=== LATEST {len(latest_signals)} SIGNALS ===")
            for sig in latest_signals:
                print(f"{sig['direction']} @ {sig['entry_price']:.2f} | Fresh: {sig['freshness']['is_fresh']}")
        else:
            print("No signal generated - market conditions not suitable")
            
    except Exception as e:
        logger.error(f"Error in signal generator test: {e}")


if __name__ == "__main__":
    main()