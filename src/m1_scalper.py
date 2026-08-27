"""
1-Minute & 5-Minute (M1/M5) Gold Micro-Scalper Engine
High-Frequency Momentum & Micro-Pullback Scanner.
"""

import logging
from typing import Optional, Tuple
import MetaTrader5 as mt5
import numpy as np
import pandas as pd

logger = logging.getLogger("GoldBot.M1Scalper")


class M1Scalper:
    def __init__(self, config: dict):
        self.config = config
        self.scalp_cfg = config.get("m1_scalper", {})
        self.enabled = self.scalp_cfg.get("enabled", True)
        self.magic_number = self.scalp_cfg.get("magic_number", 1001)
        self.fast_ema = self.scalp_cfg.get("fast_ema", 7)
        self.slow_ema = self.scalp_cfg.get("slow_ema", 16)
        self.sweep_lookback = self.scalp_cfg.get("sweep_lookback_bars", 8)
        
        # Fix 21: ATR-Scaled Dynamic Stop Loss
        self.atr_period = self.scalp_cfg.get("atr_period", 14)
        self.atr_sl_multiplier = self.scalp_cfg.get("atr_sl_multiplier", 1.5)
        self.risk_reward_ratio = self.scalp_cfg.get("risk_reward_ratio", 2.0)
        self.min_sl_dollars = self.scalp_cfg.get("min_sl_dollars", 1.20)
        self.max_sl_dollars = self.scalp_cfg.get("max_loss_dollars", 6.00)

        # Fix 16: Lightweight M15 Trend Filter Context
        self.trend_filter_enabled = self.scalp_cfg.get("trend_filter_enabled", True)
        self.trend_tf_str = self.scalp_cfg.get("trend_timeframe", "M15")
        self.trend_tf_const = mt5.TIMEFRAME_M15 if self.trend_tf_str == "M15" else mt5.TIMEFRAME_H1
        self.trend_ema_period = self.scalp_cfg.get("trend_ema_period", 20)
        self.trend_slope_bars = self.scalp_cfg.get("trend_slope_bars", 3)

        tf_list = self.scalp_cfg.get("timeframes", ["M1"])
        self.timeframes = []
        if "M1" in tf_list:
            self.timeframes.append(("M1", mt5.TIMEFRAME_M1))
        if "M5" in tf_list:
            self.timeframes.append(("M5", mt5.TIMEFRAME_M5))
        if not self.timeframes:
            self.timeframes = [("M1", mt5.TIMEFRAME_M1)]

    def fetch_rates(self, symbol: str, timeframe: int, count: int = 50) -> Optional[pd.DataFrame]:
        """Fetches latest OHLCV candles from MT5."""
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
        if rates is None or len(rates) < 25:
            return None

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        return df

    def calc_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        """Calculates ATR for dynamic micro-volatility sizing."""
        if len(df) < period + 2:
            return 1.5
        high = df["high"]
        low = df["low"]
        close_prev = df["close"].shift(1)
        tr = pd.concat([high - low, (high - close_prev).abs(), (low - close_prev).abs()], axis=1).max(axis=1)
        atr_val = tr.rolling(window=period).mean().iloc[-2]
        return float(atr_val) if pd.notna(atr_val) and atr_val > 0 else 1.5

    def evaluate_tf(
        self, symbol: str, tf_name: str, tf_const: int, digits: int, tick
    ) -> Tuple[Optional[str], float, float, float, Optional[str], str]:
        """
        Evaluates high-probability pullback rejections and momentum breakouts.
        Fix 21: Dynamically scales stop-loss based on 14-period ATR (1.5x ATR).
        """
        df = self.fetch_rates(symbol, tf_const, count=40)
        if df is None or len(df) < 20:
            return None, 0.0, 0.0, 0.0, None, ""

        df["ema_fast"] = df["close"].ewm(span=self.fast_ema, adjust=False).mean()
        df["ema_slow"] = df["close"].ewm(span=self.slow_ema, adjust=False).mean()

        prev_bar = df.iloc[-2]
        c_time_str = str(prev_bar["time"])

        window = df.iloc[-(self.sweep_lookback + 2):-2]
        recent_high = window["high"].max()
        recent_low = window["low"].min()

        # Fix 21: Calculate ATR(14) and scale SL by 1.5x ATR
        atr = self.calc_atr(df, period=self.atr_period)
        raw_sl = atr * self.atr_sl_multiplier
        sl_dist = round(max(min(raw_sl, self.max_sl_dollars), self.min_sl_dollars), digits)
        tp_dist = round(sl_dist * self.risk_reward_ratio, digits)

        # Micro SELL: Fast EMA < Slow EMA + Pullback rejection into Fast/Slow EMA + breakdown trigger
        if prev_bar["ema_fast"] <= prev_bar["ema_slow"]:
            pullback_tested_high = prev_bar["high"] >= prev_bar["ema_fast"] or prev_bar["high"] >= prev_bar["ema_slow"] or prev_bar["high"] >= recent_high
            is_bearish = prev_bar["close"] <= prev_bar["open"]
            
            # Entry confirmed on tick breakdown of previous low
            if pullback_tested_high and is_bearish and tick.bid <= prev_bar["low"]:
                entry = tick.bid
                stop_loss = round(entry + sl_dist, digits)
                take_profit = round(entry - tp_dist, digits)
                candle_id = f"SCALP_SELL_{tf_name}_{c_time_str}"
                reason = (
                    f"[ATR-SCALED SL FIX 21] [SCALP SELL {tf_name}] Pullback Breakdown @ {entry:.2f} | "
                    f"M1 ATR({self.atr_period}): ${atr:.2f} | Multiplier: {self.atr_sl_multiplier}x -> "
                    f"Dynamic SL: {stop_loss:.2f} (-${sl_dist:.2f}) | Dynamic TP: {take_profit:.2f} (+${tp_dist:.2f}) [1:{self.risk_reward_ratio:.1f} R:R]"
                )
                return "SELL", entry, stop_loss, take_profit, candle_id, reason

        # Micro BUY: Fast EMA > Slow EMA + Pullback rejection into Fast/Slow EMA + breakout trigger
        if prev_bar["ema_fast"] >= prev_bar["ema_slow"]:
            pullback_tested_low = prev_bar["low"] <= prev_bar["ema_fast"] or prev_bar["low"] <= prev_bar["ema_slow"] or prev_bar["low"] <= recent_low
            is_bullish = prev_bar["close"] >= prev_bar["open"]
            
            # Entry confirmed on tick breakout of previous high
            if pullback_tested_low and is_bullish and tick.ask >= prev_bar["high"]:
                entry = tick.ask
                stop_loss = round(entry - sl_dist, digits)
                take_profit = round(entry + tp_dist, digits)
                candle_id = f"SCALP_BUY_{tf_name}_{c_time_str}"
                reason = (
                    f"[ATR-SCALED SL FIX 21] [SCALP BUY {tf_name}] Pullback Breakout @ {entry:.2f} | "
                    f"M1 ATR({self.atr_period}): ${atr:.2f} | Multiplier: {self.atr_sl_multiplier}x -> "
                    f"Dynamic SL: {stop_loss:.2f} (-${sl_dist:.2f}) | Dynamic TP: {take_profit:.2f} (+${tp_dist:.2f}) [1:{self.risk_reward_ratio:.1f} R:R]"
                )
                return "BUY", entry, stop_loss, take_profit, candle_id, reason

        return None, 0.0, 0.0, 0.0, None, f"No setup on {tf_name} ({c_time_str})"

    def check_momentum_reversal(self, symbol: str, position_type: str) -> Tuple[bool, str]:
        """
        Checks if market momentum has reversed against an active position on M1.
        Allows closing trades early to secure profits or prevent full stop-out when market turns.
        """
        df = self.fetch_rates(symbol, mt5.TIMEFRAME_M1, count=15)
        if df is None or len(df) < 10:
            return False, "Insufficient data"

        df["ema_fast"] = df["close"].ewm(span=self.fast_ema, adjust=False).mean()
        df["ema_slow"] = df["close"].ewm(span=self.slow_ema, adjust=False).mean()
        last_bar = df.iloc[-2]

        if position_type == "BUY":
            # Bearish reversal: Closed below Fast & Slow EMA with strong red body
            is_bearish = last_bar["close"] < last_bar["open"]
            crossed_under = last_bar["close"] < last_bar["ema_fast"] and last_bar["ema_fast"] < last_bar["ema_slow"]
            if is_bearish and crossed_under:
                return True, f"M1 Bearish Momentum Reversal (Closed {last_bar['close']:.2f} < EMA_Fast {last_bar['ema_fast']:.2f})"

        elif position_type == "SELL":
            # Bullish reversal: Closed above Fast & Slow EMA with strong green body
            is_bullish = last_bar["close"] > last_bar["open"]
            crossed_over = last_bar["close"] > last_bar["ema_fast"] and last_bar["ema_fast"] > last_bar["ema_slow"]
            if is_bullish and crossed_over:
                return True, f"M1 Bullish Momentum Reversal (Closed {last_bar['close']:.2f} > EMA_Fast {last_bar['ema_fast']:.2f})"

        return False, "Trend aligned"

    def get_trend_context(self, symbol: str) -> Tuple[str, str]:
        """
        Fix 16: Evaluates lightweight short-to-medium term trend context (M15 EMA20 + slope).
        Prevents fading strong sustained intraday trend runs.
        """
        if not self.trend_filter_enabled:
            return "NEUTRAL", "Trend Filter Disabled"

        df_m15 = self.fetch_rates(symbol, self.trend_tf_const, count=40)
        if df_m15 is None or len(df_m15) < self.trend_ema_period + self.trend_slope_bars + 2:
            return "NEUTRAL", f"Insufficient {self.trend_tf_str} bars for trend evaluation"

        df_m15["ema"] = df_m15["close"].ewm(span=self.trend_ema_period, adjust=False).mean()
        prev_bar = df_m15.iloc[-2]
        prev_ema = prev_bar["ema"]
        past_ema = df_m15["ema"].iloc[-2 - self.trend_slope_bars]
        slope = prev_ema - past_ema
        close_price = prev_bar["close"]

        # Strong Downtrend: Price < EMA20 and downward slope
        if close_price < prev_ema and slope < -0.05:
            return "DOWNTREND", f"{self.trend_tf_str} DOWNTREND (Price {close_price:.2f} < EMA{self.trend_ema_period} {prev_ema:.2f}, Slope: {slope:.2f})"

        # Strong Uptrend: Price > EMA20 and upward slope
        if close_price > prev_ema and slope > 0.05:
            return "UPTREND", f"{self.trend_tf_str} UPTREND (Price {close_price:.2f} > EMA{self.trend_ema_period} {prev_ema:.2f}, Slope: +{slope:.2f})"

        return "NEUTRAL", f"{self.trend_tf_str} NEUTRAL/RANGING (Price {close_price:.2f}, EMA{self.trend_ema_period} {prev_ema:.2f}, Slope: {slope:+.2f})"

    def generate_scalp_signal(
        self, symbol: str
    ) -> Tuple[Optional[str], float, float, float, Optional[str], str, str, Optional[str], str]:
        """
        Fix 19 & 20: Scans M1 and M5 for rapid micro-scalp setups with M15 trend awareness
        and returns explicit candle-by-candle evaluation metadata.
        """
        if not self.enabled:
            return None, 0.0, 0.0, 0.0, None, "M1 Scalper Disabled", "DISABLED", None, "Module Disabled"

        info = mt5.symbol_info(symbol)
        if info is None:
            return None, 0.0, 0.0, 0.0, None, "No symbol info", "NO_INFO", None, "No symbol info"

        digits = info.digits
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return None, 0.0, 0.0, 0.0, None, "No tick info", "NO_TICK", None, "No tick info"

        trend_ctx, trend_reason = self.get_trend_context(symbol)
        latest_bar_time = None
        no_trade_reason = "Scanning micro timeframes..."

        for tf_name, tf_const in self.timeframes:
            df = self.fetch_rates(symbol, tf_const, count=30)
            if df is not None and len(df) >= 2:
                latest_bar_time = str(df.iloc[-2]["time"])

            sig, entry, sl, tp, cid, reason = self.evaluate_tf(symbol, tf_name, tf_const, digits, tick)
            if sig:
                # Fix 16 & Fix 19: Block counter-trend scalp fading
                if self.trend_filter_enabled:
                    if sig == "BUY" and trend_ctx == "DOWNTREND":
                        no_trade_reason = f"M15 Trend Filter Blocked BUY against {trend_reason}"
                        continue
                    elif sig == "SELL" and trend_ctx == "UPTREND":
                        no_trade_reason = f"M15 Trend Filter Blocked SELL against {trend_reason}"
                        continue

                annotated_reason = f"{reason} | [M15 Trend: {trend_reason}]"
                return sig, entry, sl, tp, cid, annotated_reason, trend_reason, latest_bar_time, "Setup Valid"
            else:
                no_trade_reason = reason or "No valid EMA pullback setup on bar"

        return None, 0.0, 0.0, 0.0, None, no_trade_reason, trend_reason, latest_bar_time, no_trade_reason
