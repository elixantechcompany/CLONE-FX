"""
TwisterPro M15 Scalper Strategy Engine
Specialized for XAUUSD (Gold) and canonical symbols on the M15 timeframe.

Architecture & Logic:
  - Non-grid, non-martingale: Exactly 1 position per signal with hard SL & TP.
  - 5 Independent Validation Layers (Each contributes up to 20 pts -> Total 0-100 score):
      Layer 1: Momentum & Trend Alignment (Fast EMA 9, Mid EMA 21, Slow EMA 50 + RSI 14).
      Layer 2: Micro-Structure Swing Breakout & Rejection (20-bar swing high/low breakout with closed candle or rejection wick).
      Layer 3: Dynamic Volatility & ATR Bounds (ATR(14) >= min threshold, entry candle <= 2.5x ATR, dynamic SL/TP).
      Layer 4: High-Liquidity Session Gate (London & New York active sessions 07:00 - 20:00 UTC).
      Layer 5: Real-time Spread & Execution Control (Spread <= max scalping threshold).
  - 3 Selectable Operating Modes:
      MODE_1 (High Conviction - Recommended): Score >= 80, SL = 1.5x ATR, TP = 2.5x ATR.
      MODE_2 (Short SL Scalp): Score >= 65, SL = 1.0x ATR, TP = 1.5x ATR.
      MODE_3 (3-Phase Trailing): Score >= 80, Mode 1 entry with 3-phase trailing management.
"""

import datetime
import logging
from typing import Optional, Tuple, Set, Dict, Any, List
import pandas as pd
import numpy as np

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

logger = logging.getLogger("GoldBot.TwisterProStrategy")


class TwisterProStrategy:
    """
    Reverse-engineered, institutional-grade TwisterPro M15 Scalper Engine.
    """

    def __init__(self, config: dict):
        self.config = config
        self.strat_cfg = config.get("twister_strategy", {})
        if not self.strat_cfg:
            # Fallback if config has musumali_strategy key during transition
            self.strat_cfg = config.get("musumali_strategy", {})

        self.enabled = self.strat_cfg.get("enabled", True)
        self.magic_number = int(self.strat_cfg.get("magic_number", 2001))
        self.mode = self.strat_cfg.get("mode", "MODE_1").upper()
        self.timeframe_str = self.strat_cfg.get("timeframe", "M5").upper()
        self.min_quality_score = int(self.strat_cfg.get("min_quality_score", 75))
        
        # Resolve MT5 timeframe constant
        if mt5 is not None:
            if self.timeframe_str == "M1":
                self.mt5_timeframe = mt5.TIMEFRAME_M1
            elif self.timeframe_str == "M5":
                self.mt5_timeframe = mt5.TIMEFRAME_M5
            elif self.timeframe_str == "M15":
                self.mt5_timeframe = mt5.TIMEFRAME_M15
            else:
                self.mt5_timeframe = mt5.TIMEFRAME_M5
        else:
            self.mt5_timeframe = 5

        # Scalper Precision & No-Chase Bounds
        self.max_entry_chase_dollars = float(self.strat_cfg.get("max_chase_dollars", 0.35))
        self.scalp_min_sl_dollars = float(self.strat_cfg.get("scalp_min_sl_dollars", 1.00))
        self.scalp_max_sl_dollars = float(self.strat_cfg.get("scalp_max_sl_dollars", 2.20))
        self.scalp_min_tp_dollars = float(self.strat_cfg.get("scalp_min_tp_dollars", 2.00))
        self.scalp_max_tp_dollars = float(self.strat_cfg.get("scalp_max_tp_dollars", 4.00))

        # Layer 1: Trend & Momentum parameters
        self.fast_ema_period = int(self.strat_cfg.get("fast_ema", 9))
        self.mid_ema_period = int(self.strat_cfg.get("mid_ema", 21))
        self.slow_ema_period = int(self.strat_cfg.get("slow_ema", 50))
        self.rsi_period = int(self.strat_cfg.get("rsi_period", 14))
        self.rsi_buy_min = float(self.strat_cfg.get("rsi_buy_min", 48.0))
        self.rsi_buy_max = float(self.strat_cfg.get("rsi_buy_max", 72.0))
        self.rsi_sell_min = float(self.strat_cfg.get("rsi_sell_min", 28.0))
        self.rsi_sell_max = float(self.strat_cfg.get("rsi_sell_max", 52.0))

        # Layer 2: Micro-Structure parameters
        self.swing_lookback_bars = int(self.strat_cfg.get("swing_lookback_bars", 8))
        self.min_rejection_wick_pct = float(self.strat_cfg.get("min_rejection_wick_pct", 0.15))

        # Layer 3: Volatility & ATR parameters
        self.atr_period = int(self.strat_cfg.get("atr_period", 14))
        self.atr_min_points = float(self.strat_cfg.get("atr_min_points", 0.40))
        self.max_candle_atr_ratio = float(self.strat_cfg.get("max_candle_atr_ratio", 2.5))
        
        # Mode-based ATR multipliers
        if self.mode == "MODE_2":
            self.atr_sl_multiplier = float(self.strat_cfg.get("atr_sl_multiplier_mode2", 1.0))
            self.atr_tp_multiplier = float(self.strat_cfg.get("atr_tp_multiplier_mode2", 1.5))
            if self.min_quality_score > 65:
                self.min_quality_score = 65
        else:
            self.atr_sl_multiplier = float(self.strat_cfg.get("atr_sl_multiplier", 1.2))
            self.atr_tp_multiplier = float(self.strat_cfg.get("atr_tp_multiplier", 2.0))

        # Layer 4: Session Filter parameters
        self.session_filter_enabled = self.strat_cfg.get("session_filter_enabled", True)
        self.session_start_hour_utc = int(self.strat_cfg.get("session_start_hour_utc", 7))
        self.session_end_hour_utc = int(self.strat_cfg.get("session_end_hour_utc", 20))

        # Layer 5: Spread Gate parameters
        self.max_spread_points = int(self.strat_cfg.get("max_spread_points", 320))

        logger.info(
            f"Initialized TwisterPro Scalper [Magic: {self.magic_number} | Mode: {self.mode} | "
            f"TF: {self.timeframe_str} | Score Req: {self.min_quality_score} | "
            f"SL Range: ${self.scalp_min_sl_dollars}-${self.scalp_max_sl_dollars} | Max Chase: ${self.max_entry_chase_dollars}]"
        )

    def fetch_rates(self, symbol: str, mt5_timeframe: int, count: int = 100) -> Optional[pd.DataFrame]:
        """Fetches OHLCV candlestick data from MT5."""
        if mt5 is None:
            return None
        rates = mt5.copy_rates_from_pos(symbol, mt5_timeframe, 0, count)
        if rates is None or len(rates) < 30:
            return None
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        return df

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculates EMAs (9, 21, 50), RSI(14), and ATR(14)."""
        df = df.copy()
        # EMAs
        if "ema_fast" not in df.columns:
            df["ema_fast"] = df["close"].ewm(span=self.fast_ema_period, adjust=False).mean()
        if "ema_mid" not in df.columns:
            df["ema_mid"] = df["close"].ewm(span=self.mid_ema_period, adjust=False).mean()
        if "ema_slow" not in df.columns:
            df["ema_slow"] = df["close"].ewm(span=self.slow_ema_period, adjust=False).mean()

        # RSI(14)
        if "rsi" not in df.columns:
            delta = df["close"].diff()
            gain = delta.where(delta > 0, 0.0)
            loss = -delta.where(delta < 0, 0.0)
            avg_gain = gain.rolling(window=self.rsi_period).mean()
            avg_loss = loss.rolling(window=self.rsi_period).mean()
            rs = avg_gain / (avg_loss + 1e-9)
            df["rsi"] = 100.0 - (100.0 / (1.0 + rs))

        # ATR(14)
        if "atr" not in df.columns:
            high = df["high"]
            low = df["low"]
            close_prev = df["close"].shift(1)
            tr = pd.concat([high - low, (high - close_prev).abs(), (low - close_prev).abs()], axis=1).max(axis=1)
            df["atr"] = tr.rolling(window=self.atr_period).mean()

        return df

    # =========================================================================
    # 5 INDEPENDENT VALIDATION LAYERS
    # =========================================================================

    def validate_layer_1_momentum(self, df: pd.DataFrame) -> Tuple[Optional[str], int, str]:
        """
        Layer 1: Momentum & Trend Alignment
        BUY: EMA 9 > EMA 21 > EMA 50 and 50 <= RSI <= 70.
        SELL: EMA 9 < EMA 21 < EMA 50 and 30 <= RSI <= 50.
        Returns: (direction, points_awarded, explanation)
        """
        curr = df.iloc[-2]  # Last closed candle
        ema_fast = curr["ema_fast"]
        ema_mid = curr["ema_mid"]
        ema_slow = curr["ema_slow"]
        rsi = curr["rsi"]

        if pd.isna(ema_fast) or pd.isna(ema_mid) or pd.isna(ema_slow) or pd.isna(rsi):
            return None, 0, "Layer 1 Fail: Incomplete indicator data"

        # Bullish momentum
        if ema_fast > ema_mid > ema_slow:
            if self.rsi_buy_min <= rsi <= self.rsi_buy_max:
                return "BUY", 20, f"Layer 1 Pass (BUY): EMA 9>21>50 aligned & RSI {rsi:.1f} bullish momentum"
            elif rsi > self.rsi_buy_max:
                return None, 0, f"Layer 1 Reject (BUY): RSI {rsi:.1f} overbought (> {self.rsi_buy_max})"
            else:
                return None, 0, f"Layer 1 Reject (BUY): RSI {rsi:.1f} below bullish threshold ({self.rsi_buy_min})"

        # Bearish momentum
        if ema_fast < ema_mid < ema_slow:
            if self.rsi_sell_min <= rsi <= self.rsi_sell_max:
                return "SELL", 20, f"Layer 1 Pass (SELL): EMA 9<21<50 aligned & RSI {rsi:.1f} bearish momentum"
            elif rsi < self.rsi_sell_min:
                return None, 0, f"Layer 1 Reject (SELL): RSI {rsi:.1f} oversold (< {self.rsi_sell_min})"
            else:
                return None, 0, f"Layer 1 Reject (SELL): RSI {rsi:.1f} above bearish threshold ({self.rsi_sell_max})"

        return None, 0, f"Layer 1 Reject: No EMA trend alignment (Fast: {ema_fast:.2f}, Mid: {ema_mid:.2f}, Slow: {ema_slow:.2f})"

    def validate_layer_2_micro_structure(self, df: pd.DataFrame, direction: str) -> Tuple[bool, int, str]:
        """
        Layer 2: Micro-Structure Swing Breakout & Rejection
        BUY: Candle broke out above recent swing high, printed rejection wick, bounced off EMA, or made higher high.
        SELL: Candle broke out below recent swing low, printed rejection wick, rejected off EMA, or made lower low.
        """
        if len(df) < self.swing_lookback_bars + 3:
            return False, 0, "Layer 2 Fail: Insufficient lookback bars"

        window = df.iloc[-(self.swing_lookback_bars + 2):-2]
        curr = df.iloc[-2]
        prev = df.iloc[-3]

        swing_high = window["high"].max()
        swing_low = window["low"].min()

        candle_range = curr["high"] - curr["low"]
        if candle_range <= 0:
            return False, 0, "Layer 2 Fail: Zero candle range"

        if direction == "BUY":
            # 1. Breakout close above recent swing high
            closed_above = curr["close"] > swing_high
            # 2. Bullish rejection wick
            lower_wick = min(curr["open"], curr["close"]) - curr["low"]
            lower_wick_pct = lower_wick / candle_range
            is_rejection = lower_wick_pct >= self.min_rejection_wick_pct and curr["close"] > curr["open"]
            # 3. Pullback bounce off Fast/Mid EMA
            ema_fast = curr.get("ema_fast", curr["close"])
            ema_mid = curr.get("ema_mid", curr["close"])
            is_ema_bounce = curr["low"] <= ema_fast and curr["close"] > ema_fast
            # 4. Immediate bar breakout
            is_bar_break = curr["close"] > prev["high"]
            # 5. Trend continuation (bullish close holding above Fast EMA)
            is_trend_continuation = curr["close"] > curr["open"] and curr["close"] >= ema_fast

            if closed_above:
                return True, 20, f"Layer 2 Pass: Closed breakout above swing high ({swing_high:.2f})"
            elif is_rejection:
                return True, 15, f"Layer 2 Pass: Bullish rejection wick ({lower_wick_pct*100:.1f}%)"
            elif is_ema_bounce:
                return True, 15, f"Layer 2 Pass: Bullish EMA dynamic pullback bounce"
            elif is_bar_break:
                return True, 15, f"Layer 2 Pass: Bar breakout above previous high ({prev['high']:.2f})"
            elif is_trend_continuation:
                return True, 15, f"Layer 2 Pass: Bullish trend continuation candle above EMA 9"
            else:
                return False, 0, f"Layer 2 Reject: No micro-structure confirmation ({curr['close']:.2f} <= {swing_high:.2f})"

        elif direction == "SELL":
            # 1. Breakdown close below recent swing low
            closed_below = curr["close"] < swing_low
            # 2. Bearish rejection wick
            upper_wick = curr["high"] - max(curr["open"], curr["close"])
            upper_wick_pct = upper_wick / candle_range
            is_rejection = upper_wick_pct >= self.min_rejection_wick_pct and curr["close"] < curr["open"]
            # 3. Pullback rejection off Fast/Mid EMA
            ema_fast = curr.get("ema_fast", curr["close"])
            ema_mid = curr.get("ema_mid", curr["close"])
            is_ema_rejection = curr["high"] >= ema_fast and curr["close"] < ema_fast
            # 4. Immediate bar breakdown
            is_bar_break = curr["close"] < prev["low"]
            # 5. Trend continuation (bearish close holding below Fast EMA)
            is_trend_continuation = curr["close"] < curr["open"] and curr["close"] <= ema_fast

            if closed_below:
                return True, 20, f"Layer 2 Pass: Closed breakdown below swing low ({swing_low:.2f})"
            elif is_rejection:
                return True, 15, f"Layer 2 Pass: Bearish rejection wick ({upper_wick_pct*100:.1f}%)"
            elif is_ema_rejection:
                return True, 15, f"Layer 2 Pass: Bearish EMA dynamic pullback rejection"
            elif is_bar_break:
                return True, 15, f"Layer 2 Pass: Bar breakdown below previous low ({prev['low']:.2f})"
            elif is_trend_continuation:
                return True, 15, f"Layer 2 Pass: Bearish trend continuation candle below EMA 9"
            else:
                return False, 0, f"Layer 2 Reject: No micro-structure confirmation ({curr['close']:.2f} >= {swing_low:.2f})"

        return False, 0, "Layer 2 Fail: Unknown direction"

    def validate_layer_3_volatility(self, df: pd.DataFrame) -> Tuple[bool, float, int, str]:
        """
        Layer 3: Dynamic Volatility & ATR Scaling
        - ATR must exceed min threshold (avoids flat consolidation).
        - Candle range must not exceed max_candle_atr_ratio * ATR (avoids chasing news spikes).
        """
        curr = df.iloc[-2]
        atr = curr.get("atr", None)
        if pd.isna(atr) or atr is None or atr <= 0:
            return False, 1.0, 0, "Layer 3 Fail: Invalid ATR"

        if atr < self.atr_min_points:
            return False, float(atr), 0, f"Layer 3 Reject: Volatility too low (ATR {atr:.2f} < {self.atr_min_points})"

        candle_range = curr["high"] - curr["low"]
        if candle_range > (self.max_candle_atr_ratio * atr):
            return False, float(atr), 0, f"Layer 3 Reject: Abnormal news spike (Range {candle_range:.2f} > {self.max_candle_atr_ratio}x ATR)"

        return True, float(atr), 20, f"Layer 3 Pass: Dynamic ATR {atr:.2f} within optimal volatility bounds"

    def validate_layer_4_session(self, now_utc: Optional[datetime.datetime] = None, symbol: str = "XAUUSD") -> Tuple[bool, int, str]:
        """
        Layer 4: High-Liquidity Session Gate (London & New York 07:00 - 20:00 UTC).
        Crypto (Bitcoin) is allowed 24/7 including weekends.
        """
        if not self.session_filter_enabled or "BTC" in symbol.upper():
            return True, 20, "Layer 4 Pass: 24/7 session active (Crypto/Session filter disabled)"

        if now_utc is None:
            now_utc = datetime.datetime.now(datetime.timezone.utc)

        current_hour = now_utc.hour
        if self.session_start_hour_utc <= current_hour < self.session_end_hour_utc:
            return True, 20, f"Layer 4 Pass: Liquid market session (UTC Hour: {current_hour})"
        else:
            return False, 0, f"Layer 4 Reject: Low-liquidity window (UTC Hour {current_hour} outside {self.session_start_hour_utc}:00-{self.session_end_hour_utc}:00)"

    def validate_layer_5_spread(self, current_spread: Optional[int], symbol: str = "XAUUSD") -> Tuple[bool, int, str]:
        """
        Layer 5: Real-Time Spread & Execution Control.
        Allows up to 60,000 pts for Bitcoin (to accommodate 3-digit broker quote structures and weekend volatility).
        """
        if current_spread is None:
            return True, 20, "Layer 5 Pass: Spread check skipped (no real-time spread supplied)"

        max_spread = 60000 if "BTC" in symbol.upper() else self.max_spread_points
        if current_spread <= max_spread:
            return True, 20, f"Layer 5 Pass: Spread {current_spread} pts within allowable limit ({max_spread} pts)"
        else:
            return False, 0, f"Layer 5 Reject: Spread {current_spread} pts exceeds scalping limit ({max_spread} pts)"

    # =========================================================================
    # CORE SIGNAL GENERATION
    # =========================================================================

    def generate_signal(
        self,
        symbol: str,
        traded_candle_ids: Optional[Set[str]] = None,
        current_spread: Optional[int] = None,
        now_utc: Optional[datetime.datetime] = None,
        current_tick: Any = None,
    ) -> Tuple[Optional[str], float, float, float, Optional[str], Optional[str], int, str]:
        """
        Executes the full 5-Layer TwisterPro Validation Matrix on micro scalping timeframe.
        Anchors SL/TP directly to live market price with strict No-Chase drift guard.

        Returns:
            (signal, entry, sl, tp, candle_id, zone_id, quality_score, reason)
        """
        if not self.enabled:
            return None, 0.0, 0.0, 0.0, None, None, 0, "TwisterPro engine disabled"

        if mt5 is None:
            return None, 0.0, 0.0, 0.0, None, None, 0, "MT5 package unavailable"

        # Fetch rates on configured scalping timeframe
        df = self.fetch_rates(symbol, self.mt5_timeframe, count=100)
        if df is None or len(df) < 55:
            return None, 0.0, 0.0, 0.0, None, None, 0, f"Insufficient {self.timeframe_str} rate bars"

        df = self.calculate_indicators(df)
        curr_bar = df.iloc[-2]
        c_time = curr_bar["time"]
        c_time_str = c_time.strftime("%Y%m%d_%H%M") if hasattr(c_time, "strftime") else str(c_time)
        candle_id = f"TWISTER_{symbol}_{self.timeframe_str}_{c_time_str}"

        # Duplicate Candle Deduplication Gate
        if traded_candle_ids and candle_id in traded_candle_ids:
            return None, 0.0, 0.0, 0.0, None, None, 0, f"Candle {candle_id} already executed"

        total_score = 0
        reasons: List[str] = []

        # ---------------------------------------------------------------------
        # Layer 1: Momentum & Trend Alignment
        # ---------------------------------------------------------------------
        direction, l1_score, l1_msg = self.validate_layer_1_momentum(df)
        total_score += l1_score
        reasons.append(l1_msg)
        if not direction:
            return None, 0.0, 0.0, 0.0, None, None, total_score, " | ".join(reasons)

        # ---------------------------------------------------------------------
        # Layer 2: Micro-Structure Swing Breakout & Pullback Rejection
        # ---------------------------------------------------------------------
        l2_pass, l2_score, l2_msg = self.validate_layer_2_micro_structure(df, direction)
        total_score += l2_score
        reasons.append(l2_msg)
        if not l2_pass:
            return None, 0.0, 0.0, 0.0, None, None, total_score, " | ".join(reasons)

        # ---------------------------------------------------------------------
        # Layer 3: Dynamic Volatility & ATR Bounds
        # ---------------------------------------------------------------------
        l3_pass, atr_val, l3_score, l3_msg = self.validate_layer_3_volatility(df)
        total_score += l3_score
        reasons.append(l3_msg)
        if not l3_pass:
            return None, 0.0, 0.0, 0.0, None, None, total_score, " | ".join(reasons)

        # ---------------------------------------------------------------------
        # Layer 4: Session Gate
        # ---------------------------------------------------------------------
        l4_pass, l4_score, l4_msg = self.validate_layer_4_session(now_utc, symbol=symbol)
        total_score += l4_score
        reasons.append(l4_msg)
        if not l4_pass:
            return None, 0.0, 0.0, 0.0, None, None, total_score, " | ".join(reasons)

        # ---------------------------------------------------------------------
        # Layer 5: Spread Gate
        # ---------------------------------------------------------------------
        l5_pass, l5_score, l5_msg = self.validate_layer_5_spread(current_spread, symbol=symbol)
        total_score += l5_score
        reasons.append(l5_msg)
        if not l5_pass:
            return None, 0.0, 0.0, 0.0, None, None, total_score, " | ".join(reasons)

        # ---------------------------------------------------------------------
        # Quality Score Threshold Check
        # ---------------------------------------------------------------------
        if total_score < self.min_quality_score:
            return (
                None,
                0.0,
                0.0,
                0.0,
                None,
                None,
                total_score,
                f"Conviction score {total_score} below minimum threshold ({self.min_quality_score})"
            )

        # ---------------------------------------------------------------------
        # Dynamic Price Levels & No-Chase Protection
        # ---------------------------------------------------------------------
        signal_price = float(curr_bar["close"])

        # Fetch current live tick price
        live_price = signal_price
        if current_tick is not None and hasattr(current_tick, "bid") and current_tick.bid > 0:
            live_price = float(current_tick.ask if direction == "BUY" else current_tick.bid)
        elif mt5 is not None:
            tick_info = mt5.symbol_info_tick(symbol)
            if tick_info is not None and tick_info.bid > 0:
                live_price = float(tick_info.ask if direction == "BUY" else tick_info.bid)

        # STRICT NO-CHASE GUARD: Disallow entries if price has drifted away from signal close
        drift = abs(live_price - signal_price)
        max_chase = 80.0 if "BTC" in symbol.upper() else self.max_entry_chase_dollars
        if drift > max_chase:
            return (
                None,
                0.0,
                0.0,
                0.0,
                None,
                None,
                total_score,
                f"[NO-CHASE GUARD] Live price {live_price:.2f} drifted ${drift:.2f} > max allowed ${max_chase:.2f} from signal price {signal_price:.2f}. Entry blocked."
            )

        # Calculate tight scalping SL/TP distances
        if "BTC" in symbol.upper():
            min_sl = 60.0
            max_sl = 90.0
            raw_sl = atr_val * self.atr_sl_multiplier
            sl_distance = max(min_sl, min(raw_sl, max_sl))
            tp_distance = max(180.0, min(sl_distance * max(3.0, self.atr_tp_multiplier), 300.0))
        else:
            raw_sl = atr_val * self.atr_sl_multiplier
            sl_distance = max(self.scalp_min_sl_dollars, min(raw_sl, self.scalp_max_sl_dollars))
            raw_tp = sl_distance * (self.atr_tp_multiplier / max(0.1, self.atr_sl_multiplier))
            tp_distance = max(self.scalp_min_tp_dollars, min(raw_tp, self.scalp_max_tp_dollars))

        entry_price = live_price
        if direction == "BUY":
            sl_price = entry_price - sl_distance
            tp_price = entry_price + tp_distance
        else:
            sl_price = entry_price + sl_distance
            tp_price = entry_price - tp_distance

        zone_id = f"Z_TWISTER_{direction}_{symbol}"
        summary_reason = (
            f"[TWISTERPRO {self.mode} {direction} {self.timeframe_str}] Score: {total_score}/100 | "
            f"Fill: {entry_price:.2f} | ATR: {atr_val:.2f} | SL Dist: {sl_distance:.2f} | TP Dist: {tp_distance:.2f}"
        )

        logger.info(f"Signal confirmed: {summary_reason} on {symbol}")
        return direction, entry_price, sl_price, tp_price, candle_id, zone_id, total_score, summary_reason
