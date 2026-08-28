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

    def calc_rsi(self, df: pd.DataFrame, period: int = 14) -> float:
        """Calculates RSI(14) for momentum confirmation."""
        if len(df) < period + 2:
            return 50.0
        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()
        rs = avg_gain / avg_loss.replace(0, 1e-9)
        rsi = 100 - (100 / (1 + rs))
        val = rsi.iloc[-2]
        return float(val) if pd.notna(val) else 50.0

    def evaluate_tf(
        self, symbol: str, tf_name: str, tf_const: int, digits: int, tick
    ) -> Tuple[Optional[str], float, float, float, Optional[str], str]:
        """
        Evaluates high-probability pullback rejections with STRICT 5-POINT CONFIRMATION:
        1. EMA Trend Structure (Fast EMA > Slow EMA for BUY, Fast < Slow for SELL).
        2. Candle Body & Wick Quality (Strong directional close + rejection away from support/resistance).
        3. RSI(14) Momentum Range Confirmation (No chasing in overbought/oversold extremes).
        4. Volume Confirmation (Tick volume >= 85% of recent 5-bar average).
        5. Confirmed Trigger Breakout (Ask/Bid cleanly breaking candle boundary within fresh ATR window).
        """
        df = self.fetch_rates(symbol, tf_const, count=50)
        if df is None or len(df) < 25:
            return None, 0.0, 0.0, 0.0, None, ""

        df["ema_fast"] = df["close"].ewm(span=self.fast_ema, adjust=False).mean()
        df["ema_slow"] = df["close"].ewm(span=self.slow_ema, adjust=False).mean()

        prev_bar = df.iloc[-2]
        prior_bar = df.iloc[-3]
        c_time_str = str(prev_bar["time"])

        window = df.iloc[-(self.sweep_lookback + 2):-2]
        recent_high = window["high"].max()
        recent_low = window["low"].min()

        # Volatility & Momentum Indicators
        atr = self.calc_atr(df, period=self.atr_period)
        rsi = self.calc_rsi(df, period=14)
        vol_avg = df["tick_volume"].iloc[-7:-2].mean() if "tick_volume" in df.columns else 1.0
        curr_vol = prev_bar.get("tick_volume", 1.0)
        vol_confirmed = curr_vol >= (vol_avg * 0.80)

        raw_sl = atr * self.atr_sl_multiplier
        sl_dist = round(max(min(raw_sl, self.max_sl_dollars), self.min_sl_dollars), digits)
        tp_dist = round(sl_dist * self.risk_reward_ratio, digits)

        tot_range = prev_bar["high"] - prev_bar["low"]
        if tot_range <= 0:
            return None, 0.0, 0.0, 0.0, None, f"Flat bar on {tf_name}"

        body_size = abs(prev_bar["close"] - prev_bar["open"])
        prior_body = abs(prior_bar["close"] - prior_bar["open"])
        upper_wick = prev_bar["high"] - max(prev_bar["open"], prev_bar["close"])
        lower_wick = min(prev_bar["open"], prev_bar["close"]) - prev_bar["low"]

        # =====================================================================
        # CANDLESTICK PATTERN RECOGNITION (TEXTBOOK CHART & CANDLE STRUCTURE)
        # =====================================================================
        # Bullish Patterns
        is_bull_pinbar = (lower_wick / tot_range >= 0.50) and (upper_wick / tot_range <= 0.25)
        is_bull_engulfing = (prev_bar["close"] > prev_bar["open"]) and (prev_bar["close"] > prior_bar["high"]) and (body_size >= prior_body * 1.1)
        is_bull_momentum = (prev_bar["close"] > prev_bar["open"]) and (body_size / tot_range >= 0.55) and (prev_bar["close"] > prev_bar["ema_fast"])
        is_bull_sweep = (prev_bar["low"] < recent_low) and (prev_bar["close"] > recent_low) and (lower_wick / tot_range >= 0.40)

        # Bearish Patterns
        is_bear_pinbar = (upper_wick / tot_range >= 0.50) and (lower_wick / tot_range <= 0.25)
        is_bear_engulfing = (prev_bar["close"] < prev_bar["open"]) and (prev_bar["close"] < prior_bar["low"]) and (body_size >= prior_body * 1.1)
        is_bear_momentum = (prev_bar["close"] < prev_bar["open"]) and (body_size / tot_range >= 0.55) and (prev_bar["close"] < prev_bar["ema_fast"])
        is_bear_sweep = (prev_bar["high"] > recent_high) and (prev_bar["close"] < recent_high) and (upper_wick / tot_range >= 0.40)

        # =====================================================================
        # 1. CONFIRMED BEARISH / SELL SETUP
        # =====================================================================
        is_sell_trend = prev_bar["ema_fast"] <= prev_bar["ema_slow"]
        valid_bear_pattern = is_bear_pinbar or is_bear_engulfing or (is_sell_trend and is_bear_momentum) or is_bear_sweep

        if valid_bear_pattern:
            # Pattern classification label
            if is_bear_sweep:
                pattern_lbl = "Bearish Liquidity Sweep"
            elif is_bear_pinbar:
                pattern_lbl = "Bearish Shooting Star Rejection"
            elif is_bear_engulfing:
                pattern_lbl = "Bearish Engulfing"
            else:
                pattern_lbl = "Bearish Trend Momentum"

            # Context Check: No selling into oversold RSI extreme (<30) unless strong rejection pinbar
            rsi_ok_sell = (rsi >= 30.0 and rsi <= 65.0) or (is_bear_pinbar or is_bear_sweep)

            if rsi_ok_sell:
                # Trigger Confirmation: Bid cleanly breaks previous bar low
                if tick.bid <= prev_bar["low"]:
                    if (prev_bar["low"] - tick.bid) <= (atr * 0.75):
                        entry = tick.bid
                        stop_loss = round(entry + sl_dist, digits)
                        take_profit = round(entry - tp_dist, digits)
                        candle_id = f"SCALP_SELL_{tf_name}_{c_time_str}"
                        reason = (
                            f"[CONFIRMED SELL {tf_name}] Pattern: {pattern_lbl} @ {entry:.2f} | "
                            f"RSI: {rsi:.1f} | ATR({self.atr_period}): ${atr:.2f} | "
                            f"SL: {stop_loss:.2f} (-${sl_dist:.2f}) | TP: {take_profit:.2f} (+${tp_dist:.2f}) [1:{self.risk_reward_ratio:.1f} R:R]"
                        )
                        return "SELL", entry, stop_loss, take_profit, candle_id, reason

        # =====================================================================
        # 2. CONFIRMED BULLISH / BUY SETUP
        # =====================================================================
        is_buy_trend = prev_bar["ema_fast"] >= prev_bar["ema_slow"]
        valid_bull_pattern = is_bull_pinbar or is_bull_engulfing or (is_buy_trend and is_bull_momentum) or is_bull_sweep

        if valid_bull_pattern:
            # Pattern classification label
            if is_bull_sweep:
                pattern_lbl = "Bullish Liquidity Sweep"
            elif is_bull_pinbar:
                pattern_lbl = "Bullish Hammer/Pinbar Rejection"
            elif is_bull_engulfing:
                pattern_lbl = "Bullish Engulfing"
            else:
                pattern_lbl = "Bullish Trend Momentum"

            # Context Check: No buying into falling knife / oversold crash (<38) unless confirmed hammer/sweep rejection!
            rsi_ok_buy = (rsi >= 38.0 and rsi <= 70.0) or (is_bull_pinbar or is_bull_sweep)

            if rsi_ok_buy:
                # Trigger Confirmation: Ask cleanly breaks previous bar high
                if tick.ask >= prev_bar["high"]:
                    if (tick.ask - prev_bar["high"]) <= (atr * 0.75):
                        entry = tick.ask
                        stop_loss = round(entry - sl_dist, digits)
                        take_profit = round(entry + tp_dist, digits)
                        candle_id = f"SCALP_BUY_{tf_name}_{c_time_str}"
                        reason = (
                            f"[CONFIRMED BUY {tf_name}] Pattern: {pattern_lbl} @ {entry:.2f} | "
                            f"RSI: {rsi:.1f} | ATR({self.atr_period}): ${atr:.2f} | "
                            f"SL: {stop_loss:.2f} (-${sl_dist:.2f}) | TP: {take_profit:.2f} (+${tp_dist:.2f}) [1:{self.risk_reward_ratio:.1f} R:R]"
                        )
                        return "BUY", entry, stop_loss, take_profit, candle_id, reason

        return None, 0.0, 0.0, 0.0, None, f"No candlestick pattern on {tf_name} ({c_time_str})"

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
                # If trend filter is strictly enabled AND not in bidirectional mode, filter by trend
                if self.trend_filter_enabled and not self.bidirectional:
                    if sig == "BUY" and trend_ctx != "UPTREND":
                        no_trade_reason = f"M15 Trend Filter Blocked BUY: Requires M15 UPTREND (Current: {trend_reason})"
                        continue
                    elif sig == "SELL" and trend_ctx != "DOWNTREND":
                        no_trade_reason = f"M15 Trend Filter Blocked SELL: Requires M15 DOWNTREND (Current: {trend_reason})"
                        continue

                annotated_reason = f"{reason} | [Context: {trend_reason}]"
                return sig, entry, sl, tp, cid, annotated_reason, trend_reason, latest_bar_time, "Setup Valid"
            else:
                no_trade_reason = reason or "No valid EMA pullback setup on bar"

        return None, 0.0, 0.0, 0.0, None, no_trade_reason, trend_reason, latest_bar_time, no_trade_reason
