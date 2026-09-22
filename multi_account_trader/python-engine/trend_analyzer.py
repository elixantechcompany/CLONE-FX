"""
MT5 Trend Analyzer - EMA-based trend detection for XAUUSD
Implements specific 50 EMA trend filter on H4 and H1 timeframes
"""

import pandas as pd
import MetaTrader5 as mt5
from datetime import datetime, timedelta
from typing import Dict, Tuple, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TrendAnalyzer")


class EMATrendAnalyzer:
    """
    Analyzes Gold (XAUUSD) trends using 50-period EMA on H4 and H1 timeframes
    Implements the specific trading rules from the specification
    """
    
    def __init__(self, symbol: str = "XAUUSD"):
        self.symbol = symbol
        self.ema_period = 50
        self.atr_period = 14
        self.atr_multiplier = 1.5
        self.min_rr_ratio = 2.0  # Minimum 1:2 risk-reward ratio
        
    def connect_mt5(self) -> bool:
        """Initialize MT5 connection"""
        if not mt5.initialize():
            logger.error(f"MT5 initialization failed: {mt5.last_error()}")
            return False
        logger.info("MT5 connected successfully")
        return True
    
    def shutdown_mt5(self):
        """Shutdown MT5 connection"""
        mt5.shutdown()
        logger.info("MT5 connection closed")
    
    def get_candles(self, timeframe: int, count: int = 200) -> Optional[pd.DataFrame]:
        """
        Fetch candlestick data from MT5
        Timeframe constants: mt5.TIMEFRAME_H1, mt5.TIMEFRAME_H4
        """
        try:
            rates = mt5.copy_rates_from_pos(self.symbol, timeframe, 0, count)
            if rates is None or len(rates) == 0:
                logger.error(f"No data received for {self.symbol} on timeframe {timeframe}")
                return None
            
            df = pd.DataFrame(rates)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            return df
        except Exception as e:
            logger.error(f"Error fetching candles: {e}")
            return None
    
    def calculate_ema(self, df: pd.DataFrame, period: int = 50) -> pd.Series:
        """Calculate Exponential Moving Average"""
        return df['close'].ewm(span=period, adjust=False).mean()
    
    def calculate_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        """Calculate Average True Range"""
        high = df['high']
        low = df['low']
        close_prev = df['close'].shift(1)
        
        tr1 = high - low
        tr2 = (high - close_prev).abs()
        tr3 = (low - close_prev).abs()
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        
        return float(atr.iloc[-1]) if pd.notna(atr.iloc[-1]) else 0.0
    
    def analyze_trend(self) -> Dict:
        """
        Main trend analysis function
        Returns complete trend analysis with EMA values and trading direction
        """
        try:
            # Get H4 data
            h4_df = self.get_candles(mt5.TIMEFRAME_H4, count=200)
            if h4_df is None or len(h4_df) < self.ema_period + 10:
                return {"error": "Insufficient H4 data"}
            
            # Get H1 data
            h1_df = self.get_candles(mt5.TIMEFRAME_H1, count=200)
            if h1_df is None or len(h1_df) < self.ema_period + 10:
                return {"error": "Insufficient H1 data"}
            
            # Calculate EMAs
            h4_ema = self.calculate_ema(h4_df, self.ema_period)
            h1_ema = self.calculate_ema(h1_df, self.ema_period)
            
            # Get current values
            current_h4_close = h4_df['close'].iloc[-1]
            current_h1_close = h1_df['close'].iloc[-1]
            current_h4_ema = h4_ema.iloc[-1]
            current_h1_ema = h1_ema.iloc[-1]
            
            # Calculate ATR on H1 for dynamic SL
            atr_value = self.calculate_atr(h1_df, self.atr_period)
            
            # Determine trend direction
            h4_above_ema = current_h4_close > current_h4_ema
            h1_above_ema = current_h1_close > current_h1_ema
            
            # Trading Logic from specification:
            # Only BUY if price above 50 EMA on BOTH H4 and H1
            # Only SELL if price below 50 EMA on BOTH H4 and H1
            if h4_above_ema and h1_above_ema:
                trend_direction = "BUY"
                trend_strength = "STRONG_BULLISH"
            elif not h4_above_ema and not h1_above_ema:
                trend_direction = "SELL"
                trend_strength = "STRONG_BEARISH"
            else:
                trend_direction = "NEUTRAL"
                trend_strength = "MIXED"
            
            # Calculate dynamic SL using 1.5x ATR
            dynamic_sl_distance = atr_value * self.atr_multiplier
            
            # Current price for signal generation
            current_price = current_h1_close
            
            # Calculate SL and TP based on direction
            if trend_direction == "BUY":
                stop_loss = current_price - dynamic_sl_distance
                take_profit = current_price + (dynamic_sl_distance * self.min_rr_ratio)
            elif trend_direction == "SELL":
                stop_loss = current_price + dynamic_sl_distance
                take_profit = current_price - (dynamic_sl_distance * self.min_rr_ratio)
            else:
                stop_loss = 0
                take_profit = 0
            
            # Calculate actual risk-reward ratio
            if stop_loss != 0 and take_profit != 0:
                risk = abs(current_price - stop_loss)
                reward = abs(take_profit - current_price)
                actual_rr = reward / risk if risk > 0 else 0
            else:
                actual_rr = 0
            
            return {
                "symbol": self.symbol,
                "trend_direction": trend_direction,
                "trend_strength": trend_strength,
                "current_price": current_price,
                "h4_ema50": current_h4_ema,
                "h1_ema50": current_h1_ema,
                "h4_price_above_ema": h4_above_ema,
                "h1_price_above_ema": h1_above_ema,
                "atr_value": atr_value,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "risk_reward_ratio": actual_rr,
                "sl_distance": dynamic_sl_distance,
                "is_tradeable": trend_direction in ["BUY", "SELL"],
                "timestamp": datetime.now().isoformat(),
                "h4_data_points": len(h4_df),
                "h1_data_points": len(h1_df)
            }
            
        except Exception as e:
            logger.error(f"Error in trend analysis: {e}")
            return {"error": str(e)}
    
    def generate_signal(self) -> Optional[Dict]:
        """
        Generate a complete trading signal if conditions are met
        Returns None if trend is not tradeable
        """
        analysis = self.analyze_trend()
        
        if "error" in analysis:
            logger.error(f"Cannot generate signal: {analysis['error']}")
            return None
        
        if not analysis.get("is_tradeable", False):
            logger.info("Market conditions not suitable for trading (mixed trend)")
            return None
        
        # Verify minimum risk-reward ratio
        if analysis["risk_reward_ratio"] < self.min_rr_ratio:
            logger.warning(f"Risk-reward ratio {analysis['risk_reward_ratio']:.2f} below minimum {self.min_rr_ratio}")
            return None
        
        signal = {
            "signal_id": f"{self.symbol}_{analysis['trend_direction']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "symbol": analysis["symbol"],
            "direction": analysis["trend_direction"],
            "entry": analysis["current_price"],
            "stop_loss": analysis["stop_loss"],
            "take_profit": analysis["take_profit"],
            "risk_reward_ratio": analysis["risk_reward_ratio"],
            "h4_ema50": analysis["h4_ema50"],
            "h1_ema50": analysis["h1_ema50"],
            "atr_value": analysis["atr_value"],
            "sl_distance": analysis["sl_distance"],
            "generated_at": analysis["timestamp"],
            "expires_at": (datetime.now() + timedelta(minutes=5)).isoformat(),
            "is_valid": True
        }
        
        logger.info(f"Generated {signal['direction']} signal for {self.symbol} @ {signal['entry']:.2f}")
        return signal


def main():
    """Test the trend analyzer"""
    analyzer = EMATrendAnalyzer("XAUUSD")
    
    if analyzer.connect_mt5():
        try:
            # Perform trend analysis
            analysis = analyzer.analyze_trend()
            print("\n=== TREND ANALYSIS RESULTS ===")
            for key, value in analysis.items():
                if isinstance(value, float):
                    print(f"{key}: {value:.4f}")
                else:
                    print(f"{key}: {value}")
            
            # Generate signal if conditions are met
            signal = analyzer.generate_signal()
            if signal:
                print("\n=== TRADING SIGNAL GENERATED ===")
                for key, value in signal.items():
                    if isinstance(value, float):
                        print(f"{key}: {value:.4f}")
                    else:
                        print(f"{key}: {value}")
            else:
                print("\nNo trading signal generated - market conditions not suitable")
                
        finally:
            analyzer.shutdown_mt5()


if __name__ == "__main__":
    main()