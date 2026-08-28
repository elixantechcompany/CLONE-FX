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
        self.bidirectional = self.scalp_cfg.get("bidirectional", False)
        self.min_quality_score = self.scalp_cfg.get("min_quality_score", 65)

        tf_list = self.scalp_cfg.get("timeframes", ["M5", "M15"])
        self.timeframes = []
        if "M1" in tf_list:
            self.timeframes.append(("M1", mt5.TIMEFRAME_M1))
        if "M5" in tf_list:
            self.timeframes.append(("M5", mt5.TIMEFRAME_M5))
        if "M15" in tf_list:
            self.timeframes.append(("M15", mt5.TIMEFRAME_M15))
        if "M30" in tf_list:
            self.timeframes.append(("M30", mt5.TIMEFRAME_M30))
        if not self.timeframes:
            self.timeframes = [("M5", mt5.TIMEFRAME_M5)]

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

    def calculate_quality_score(
        self,
        tf_name: str,
        sig: str,
        trend_ctx: str,
        slope: float,
        rsi: float,
        vol_confirmed: bool,
        pattern_lbl: str,
        current_spread: int,
        atr: float,
    ) -> Tuple[int, dict, bool]:
        """
        Fix 29: Graded Trade Quality Scoring Engine (0 - 100 points).
        Evaluates candidate setups across 5 core risk/reward dimensions:
        1. Trend Structure Alignment (0 - 30 pts)
        2. Momentum & RSI Quality (0 - 25 pts)
        3. Candle Structure & Rejection (0 - 25 pts)
        4. Spread Health (0 - 10 pts)
        5. Volatility & ATR Stability (0 - 10 pts)
        """
        # Dimension 1: Trend Alignment (30 pts)
        s_trend = 0
        if sig == "BUY":
            if trend_ctx == "UPTREND":
                s_trend = 30 if slope > 0.50 else 25
            elif trend_ctx == "NEUTRAL":
                s_trend = 15
        elif sig == "SELL":
            if trend_ctx == "DOWNTREND":
                s_trend = 30 if slope < -0.50 else 25
            elif trend_ctx == "NEUTRAL":
                s_trend = 15

        # Dimension 2: Momentum & RSI Sweet-Spot (25 pts)
        s_mom = 0
        if sig == "BUY" and (40.0 <= rsi <= 68.0):
            s_mom += 15
        elif sig == "SELL" and (32.0 <= rsi <= 60.0):
            s_mom += 15
        else:
            s_mom += 8

        if vol_confirmed:
            s_mom += 10
        else:
            s_mom += 5

        # Dimension 3: Candlestick Rejection / Momentum (25 pts)
        s_candle = 0
        if "Liquidity Sweep" in pattern_lbl or "Hammer" in pattern_lbl or "Shooting Star" in pattern_lbl:
            s_candle = 25
        elif "Engulfing" in pattern_lbl:
            s_candle = 22
        elif "Pullback" in pattern_lbl:
            s_candle = 20
        else:
            s_candle = 15

        # Dimension 4: Spread Condition (10 pts)
        s_spread = 0
        if current_spread <= 240:
            s_spread = 10
        elif current_spread <= 280:
            s_spread = 7
        elif current_spread <= 320:
            s_spread = 4
        else:
            s_spread = 0

        # Dimension 5: Volatility & ATR Health (10 pts)
        s_atr = 0
        if 1.0 <= atr <= 8.0:
            s_atr = 10
        else:
            s_atr = 5

        total_score = s_trend + s_mom + s_candle + s_spread + s_atr
        breakdown = {
            "trend": s_trend,
            "momentum": s_mom,
            "candle": s_candle,
            "spread": s_spread,
            "atr": s_atr,
            "total": total_score,
        }
        passed = total_score >= self.min_quality_score
        status_str = "ACCEPTED" if passed else "REJECTED (Score < Threshold)"
        logger.info(
            f"[QUALITY SCORE FIX 29] Scalp Candidate {tf_name} ({sig}) -> Score: {total_score}/100 "
            f"[Trend: {s_trend}/30, Momentum: {s_mom}/25, Candle: {s_candle}/25, Spread: {s_spread}/10, ATR: {s_atr}/10] | "
            f"Threshold: {self.min_quality_score}/100 -> {status_str}"
        )
        return total_score, breakdown, passed

    def evaluate_tf(
        self,
        symbol: str,
        tf_name: str,
        tf_const: int,
        digits: int,
        tick,
        trend_ctx: str = "NEUTRAL",
        slope: float = 0.0,
        current_spread: int = 260,
    ) -> Tuple[Optional[str], float, float, float, Optional[str], str]:
        """
        Evaluates high-probability pullback rejections with Fix 29 graded quality scoring.
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
        # CANDLESTICK PATTERN RECOGNITION (AGILE REAL-TIME DETECTION)
        # =====================================================================
        # Bullish Patterns
        is_bull_live_break = (tick.ask >= prev_bar["high"]) and (prev_bar["close"] >= prev_bar["open"] or prev_bar["close"] >= prev_bar["ema_fast"])
        is_bull_pinbar = (lower_wick / tot_range >= 0.25) and (upper_wick / tot_range <= 0.40)
        is_bull_engulfing = (prev_bar["close"] > prev_bar["open"]) and (prev_bar["close"] >= prior_bar["high"])
        is_bull_momentum = (prev_bar["close"] > prev_bar["open"]) and (prev_bar["close"] >= prev_bar["ema_fast"])
        is_bull_pullback = (prev_bar["low"] <= prev_bar["ema_fast"] or prev_bar["low"] <= prev_bar["ema_slow"]) and (prev_bar["close"] > prev_bar["open"])
        is_bull_sweep = (prev_bar["low"] < recent_low) and (prev_bar["close"] > recent_low)

        # Bearish Patterns
        is_bear_live_break = (tick.bid <= prev_bar["low"]) and (prev_bar["close"] <= prev_bar["open"] or prev_bar["close"] <= prev_bar["ema_fast"])
        is_bear_pinbar = (upper_wick / tot_range >= 0.25) and (lower_wick / tot_range <= 0.40)
        is_bear_engulfing = (prev_bar["close"] < prev_bar["open"]) and (prev_bar["close"] <= prior_bar["low"])
        is_bear_momentum = (prev_bar["close"] < prev_bar["open"]) and (prev_bar["close"] <= prev_bar["ema_fast"])
        is_bear_pullback = (prev_bar["high"] >= prev_bar["ema_fast"] or prev_bar["high"] >= prev_bar["ema_slow"]) and (prev_bar["close"] < prev_bar["open"])
        is_bear_sweep = (prev_bar["high"] > recent_high) and (prev_bar["close"] < recent_high)

        # =====================================================================
        # 1. CONFIRMED BEARISH / SELL SETUP
        # =====================================================================
        is_sell_trend = prev_bar["ema_fast"] <= prev_bar["ema_slow"]
        valid_bear_pattern = (
            is_bear_live_break or is_bear_pinbar or is_bear_engulfing or 
            (is_sell_trend and (is_bear_momentum or is_bear_pullback)) or is_bear_sweep
        )

        if valid_bear_pattern:
            if is_bear_sweep:
                pattern_lbl = "Bearish Liquidity Sweep"
            elif is_bear_live_break:
                pattern_lbl = "Bearish Live Momentum Breakdown"
            elif is_bear_pinbar:
                pattern_lbl = "Bearish Shooting Star Rejection"
            elif is_bear_engulfing:
                pattern_lbl = "Bearish Engulfing"
            elif is_bear_pullback:
                pattern_lbl = "Bearish EMA Pullback Rejection"
            else:
                pattern_lbl = "Bearish Trend Momentum"

            rsi_ok_sell = (rsi >= 28.0 and rsi <= 70.0) or (is_bear_pinbar or is_bear_sweep)

            if rsi_ok_sell:
                # Fix 29: Graded Quality Score Check
                score, breakdown, passed = self.calculate_quality_score(
                    tf_name, "SELL", trend_ctx, slope, rsi, vol_confirmed, pattern_lbl, current_spread, atr
                )
                if not passed:
                    return None, 0.0, 0.0, 0.0, None, f"Quality score {score}/100 below threshold {self.min_quality_score}"

                max_chase = max(atr * 1.2, 3.50)
                chase_dist = prev_bar["close"] - tick.bid
                if chase_dist >= -1.50 and chase_dist <= max_chase:
                    entry = tick.bid
                    stop_loss = round(entry + sl_dist, digits)
                    take_profit = round(entry - tp_dist, digits)
                    candle_id = f"SCALP_SELL_{tf_name}_{c_time_str}"
                    reason = (
                        f"[AGILE TRIGGER SELL {tf_name}] Pattern: {pattern_lbl} @ {entry:.2f} (Break: -${chase_dist:.2f}) | "
                        f"Quality Score: {score}/100 | RSI: {rsi:.1f} | ATR({self.atr_period}): ${atr:.2f} | "
                        f"SL: {stop_loss:.2f} (-${sl_dist:.2f}) | TP: {take_profit:.2f} (+${tp_dist:.2f}) [1:{self.risk_reward_ratio:.1f} R:R]"
                    )
                    return "SELL", entry, stop_loss, take_profit, candle_id, reason

        # =====================================================================
        # 2. CONFIRMED BULLISH / BUY SETUP
        # =====================================================================
        is_buy_trend = prev_bar["ema_fast"] >= prev_bar["ema_slow"]
        valid_bull_pattern = (
            is_bull_live_break or is_bull_pinbar or is_bull_engulfing or 
            (is_buy_trend and (is_bull_momentum or is_bull_pullback)) or is_bull_sweep
        )

        if valid_bull_pattern:
            if is_bull_sweep:
                pattern_lbl = "Bullish Liquidity Sweep"
            elif is_bull_live_break:
                pattern_lbl = "Bullish Live Momentum Breakout"
            elif is_bull_pinbar:
                pattern_lbl = "Bullish Hammer/Pinbar Rejection"
            elif is_bull_engulfing:
                pattern_lbl = "Bullish Engulfing"
            elif is_bull_pullback:
                pattern_lbl = "Bullish EMA Pullback Rejection"
            else:
                pattern_lbl = "Bullish Trend Momentum"

            rsi_ok_buy = (rsi >= 30.0 and rsi <= 72.0) or (is_bull_pinbar or is_bull_sweep)

            if rsi_ok_buy:
                # Fix 29: Graded Quality Score Check
                score, breakdown, passed = self.calculate_quality_score(
                    tf_name, "BUY", trend_ctx, slope, rsi, vol_confirmed, pattern_lbl, current_spread, atr
                )
                if not passed:
                    return None, 0.0, 0.0, 0.0, None, f"Quality score {score}/100 below threshold {self.min_quality_score}"

                max_chase = max(atr * 1.2, 3.50)
                chase_dist = tick.ask - prev_bar["close"]
                if chase_dist >= -1.50 and chase_dist <= max_chase:
                    entry = tick.ask
                    stop_loss = round(entry - sl_dist, digits)
                    take_profit = round(entry + tp_dist, digits)
                    candle_id = f"SCALP_BUY_{tf_name}_{c_time_str}"
                    reason = (
                        f"[AGILE TRIGGER BUY {tf_name}] Pattern: {pattern_lbl} @ {entry:.2f} (Break: +${chase_dist:.2f}) | "
                        f"Quality Score: {score}/100 | RSI: {rsi:.1f} | ATR({self.atr_period}): ${atr:.2f} | "
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
        if df is None or len(df) < 5:
            return False, "Insufficient M1 data"

        df["ema_fast"] = df["close"].ewm(span=self.fast_ema, adjust=False).mean()
        df["ema_slow"] = df["close"].ewm(span=self.slow_ema, adjust=False).mean()
        last_bar = df.iloc[-1]

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

    def get_trend_context(self, symbol: str) -> Tuple[str, str, float]:
        """
        Fix 16: Evaluates lightweight short-to-medium term trend context (M15 EMA20 + slope).
        Prevents fading strong sustained intraday trend runs.
        """
        if not self.trend_filter_enabled:
            return "NEUTRAL", "Trend Filter Disabled", 0.0

        df_m15 = self.fetch_rates(symbol, self.trend_tf_const, count=40)
        if df_m15 is None or len(df_m15) < self.trend_ema_period + self.trend_slope_bars + 2:
            return "NEUTRAL", f"Insufficient {self.trend_tf_str} bars for trend evaluation", 0.0

        df_m15["ema"] = df_m15["close"].ewm(span=self.trend_ema_period, adjust=False).mean()
        prev_bar = df_m15.iloc[-2]
        prev_ema = prev_bar["ema"]
        past_ema = df_m15["ema"].iloc[-2 - self.trend_slope_bars]
        slope = prev_ema - past_ema
        close_price = prev_bar["close"]

        # Strong Downtrend: Price < EMA20 and downward slope
        if close_price < prev_ema and slope < -0.05:
            return "DOWNTREND", f"{self.trend_tf_str} DOWNTREND (Price {close_price:.2f} < EMA{self.trend_ema_period} {prev_ema:.2f}, Slope: {slope:.2f})", slope

        # Strong Uptrend: Price > EMA20 and upward slope
        if close_price > prev_ema and slope > 0.05:
            return "UPTREND", f"{self.trend_tf_str} UPTREND (Price {close_price:.2f} > EMA{self.trend_ema_period} {prev_ema:.2f}, Slope: +{slope:.2f})", slope

        return "NEUTRAL", f"{self.trend_tf_str} NEUTRAL/RANGING (Price {close_price:.2f}, EMA{self.trend_ema_period} {prev_ema:.2f}, Slope: {slope:+.2f})", slope

    def generate_scalp_signal(
        self, symbol: str
    ) -> Tuple[Optional[str], float, float, float, Optional[str], str, str, Optional[str], str]:
        """
        Fix 19, 20 & 29: Scans M5 and M15 for rapid micro-scalp setups with graded quality scoring
        and returns explicit candle-by-candle evaluation metadata.
        """
        if not self.enabled:
            return None, 0.0, 0.0, 0.0, None, "M1 Scalper Disabled", "DISABLED", None, "Module Disabled"

        info = mt5.symbol_info(symbol)
        if info is None:
            return None, 0.0, 0.0, 0.0, None, "No symbol info", "NO_INFO", None, "No symbol info"

        digits = info.digits
        current_spread = info.spread
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return None, 0.0, 0.0, 0.0, None, "No tick info", "NO_TICK", None, "No tick info"

        trend_ctx, trend_reason, slope = self.get_trend_context(symbol)
        latest_bar_time = None
        no_trade_reason = "Scanning micro timeframes..."

        for tf_name, tf_const in self.timeframes:
            df = self.fetch_rates(symbol, tf_const, count=30)
            if df is not None and len(df) >= 2:
                latest_bar_time = str(df.iloc[-2]["time"])

            sig, entry, sl, tp, cid, reason = self.evaluate_tf(
                symbol, tf_name, tf_const, digits, tick, trend_ctx=trend_ctx, slope=slope, current_spread=current_spread
            )
            if sig:
                annotated_reason = f"{reason} | [Context: {trend_reason}]"
                return sig, entry, sl, tp, cid, annotated_reason, trend_reason, latest_bar_time, "Setup Valid"
            else:
                no_trade_reason = reason or "No valid EMA pullback setup on bar"

        return None, 0.0, 0.0, 0.0, None, no_trade_reason, trend_reason, latest_bar_time, no_trade_reason
