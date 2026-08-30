"""
Agile Micro-Scalper Engine (Multi-Symbol: XAUUSD & BTCUSD)
Engine 2 [Magic: 1001]
High-Frequency Momentum & Micro-Pullback Scanner (M1, M5 with M15 context).
Enforces:
  1. Timeframe Isolation: M1/M5 microstructure entries with M15 trend context.
  2. Graded Quality Scoring Engine (0 - 100).
  3. Dynamic ATR-Scaled Stop Loss with symbol-specific bounds.
  4. Agile Bidirectional Scalping.
"""

import logging
from typing import Optional, Tuple, Any
import MetaTrader5 as mt5
import pandas as pd

logger = logging.getLogger("GoldBot.M1Scalper")


class M1Scalper:
    def __init__(self, config: dict):
        self.config = config
        self.scalp_cfg = config.get("m1_scalper", {})
        self.symbols_cfg = config.get("symbols", {})
        self.enabled = self.scalp_cfg.get("enabled", True)
        self.magic_number = self.scalp_cfg.get("magic_number", 1001)
        self.fast_ema = self.scalp_cfg.get("fast_ema", 7)
        self.slow_ema = self.scalp_cfg.get("slow_ema", 16)
        self.sweep_lookback = self.scalp_cfg.get("sweep_lookback_bars", 8)

        # Dynamic ATR parameters
        self.atr_period = self.scalp_cfg.get("atr_period", 14)
        self.atr_sl_multiplier = self.scalp_cfg.get("atr_sl_multiplier", 1.5)
        self.risk_reward_ratio = self.scalp_cfg.get("risk_reward_ratio", 2.0)

        # M15 Trend Filter Context
        self.trend_filter_enabled = self.scalp_cfg.get("trend_filter_enabled", True)
        self.trend_tf_str = self.scalp_cfg.get("trend_timeframe", "M15")
        self.trend_tf_const = mt5.TIMEFRAME_M15 if self.trend_tf_str == "M15" else mt5.TIMEFRAME_H1
        self.trend_ema_period = self.scalp_cfg.get("trend_ema_period", 20)
        self.trend_slope_bars = self.scalp_cfg.get("trend_slope_bars", 3)
        self.bidirectional = self.scalp_cfg.get("bidirectional", True)
        self.min_quality_score = self.scalp_cfg.get("min_quality_score", 50)

        tf_list = self.scalp_cfg.get("timeframes", ["M1", "M5", "M15"])
        self.timeframes = []
        if "M1" in tf_list:
            self.timeframes.append(("M1", mt5.TIMEFRAME_M1))
        if "M5" in tf_list:
            self.timeframes.append(("M5", mt5.TIMEFRAME_M5))
        if "M15" in tf_list:
            self.timeframes.append(("M15", mt5.TIMEFRAME_M15))
        if not self.timeframes:
            self.timeframes = [("M1", mt5.TIMEFRAME_M1), ("M5", mt5.TIMEFRAME_M5)]

    def fetch_rates(self, symbol: str, timeframe: int, count: int = 50) -> Optional[pd.DataFrame]:
        """Fetches latest OHLCV candles from MT5."""
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
        if rates is None or len(rates) < 25:
            return None
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        return df

    def get_symbol_settings(self, symbol: str) -> dict:
        """Returns symbol-specific parameters for XAUUSD vs BTCUSD."""
        clean_sym = symbol.replace("m", "").replace("_i", "").replace("z", "").upper()
        canonical = "BTCUSD" if "BTC" in clean_sym else "XAUUSD"
        return self.symbols_cfg.get("symbol_settings", {}).get(canonical, {})

    def calc_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        """Calculates ATR for dynamic volatility sizing."""
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
        symbol: str,
        tf_name: str,
        sig: str,
        trend_ctx: str,
        slope: float,
        rsi: float,
        vol_confirmed: bool,
        pattern_lbl: str,
        current_spread: int,
        atr: float,
        quality_threshold: Optional[int] = None,
    ) -> Tuple[int, dict, bool]:
        """
        Graded Trade Quality Scoring Engine (0 - 100 points).
        Evaluates setups across 5 core dimensions:
          1. Trend Alignment (0 - 30 pts)
          2. Momentum & RSI Quality (0 - 25 pts)
          3. Candlestick Structure & Rejection (0 - 25 pts)
          4. Spread Health (0 - 10 pts)
          5. Volatility & ATR Stability (0 - 10 pts)
        """
        s_trend = 0
        if sig == "BUY":
            if trend_ctx == "UPTREND":
                s_trend = 30 if slope > 0.10 else 25
            elif trend_ctx == "NEUTRAL":
                s_trend = 15
        elif sig == "SELL":
            if trend_ctx == "DOWNTREND":
                s_trend = 30 if slope < -0.10 else 25
            elif trend_ctx == "NEUTRAL":
                s_trend = 15

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

        s_candle = 0
        if "Liquidity Sweep" in pattern_lbl or "Hammer" in pattern_lbl or "Shooting Star" in pattern_lbl:
            s_candle = 25
        elif "Engulfing" in pattern_lbl:
            s_candle = 22
        elif "Pullback" in pattern_lbl:
            s_candle = 20
        else:
            s_candle = 15

        s_spread = 0
        is_btc = "BTC" in symbol.upper()
        spread_max = 2200 if is_btc else 280
        if current_spread <= spread_max:
            s_spread = 10
        else:
            s_spread = 5

        s_atr = 10 if atr > 0 else 5

        total_score = s_trend + s_mom + s_candle + s_spread + s_atr
        breakdown = {
            "trend": s_trend,
            "momentum": s_mom,
            "candle": s_candle,
            "spread": s_spread,
            "atr": s_atr,
            "total": total_score,
        }
        threshold = quality_threshold if quality_threshold is not None else self.min_quality_score
        passed = total_score >= threshold
        return total_score, breakdown, passed

    def get_trend_context(self, symbol: str) -> Tuple[str, str, float]:
        """Evaluates lightweight M15 trend context (EMA20 + slope)."""
        if not self.trend_filter_enabled:
            return "NEUTRAL", "Trend Filter Disabled", 0.0

        df_m15 = self.fetch_rates(symbol, self.trend_tf_const, count=40)
        if df_m15 is None or len(df_m15) < self.trend_ema_period + self.trend_slope_bars + 2:
            return "NEUTRAL", f"Insufficient {self.trend_tf_str} bars", 0.0

        df_m15["ema"] = df_m15["close"].ewm(span=self.trend_ema_period, adjust=False).mean()
        prev_bar = df_m15.iloc[-2]
        prev_ema = prev_bar["ema"]
        past_ema = df_m15["ema"].iloc[-2 - self.trend_slope_bars]
        slope = prev_ema - past_ema
        close_price = prev_bar["close"]

        if close_price < prev_ema and slope < -0.05:
            return "DOWNTREND", f"{self.trend_tf_str} DOWNTREND", slope
        elif close_price > prev_ema and slope > 0.05:
            return "UPTREND", f"{self.trend_tf_str} UPTREND", slope

        return "NEUTRAL", f"{self.trend_tf_str} NEUTRAL", slope

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
        quality_threshold: Optional[int] = None,
    ) -> Tuple[Optional[str], float, float, float, Optional[str], int, str]:
        """Evaluates high-probability pullback / momentum setups on micro timeframes."""
        df = self.fetch_rates(symbol, tf_const, count=50)
        if df is None or len(df) < 25:
            return None, 0.0, 0.0, 0.0, None, 0, ""

        sym_settings = self.get_symbol_settings(symbol)
        min_sl = sym_settings.get("scalp_min_sl_dollars", 1.50 if "XAU" in symbol else 120.0)
        max_sl = sym_settings.get("scalp_max_sl_dollars", 4.50 if "XAU" in symbol else 500.0)

        df["ema_fast"] = df["close"].ewm(span=self.fast_ema, adjust=False).mean()
        df["ema_slow"] = df["close"].ewm(span=self.slow_ema, adjust=False).mean()

        prev_bar = df.iloc[-2]
        prior_bar = df.iloc[-3]
        c_time_str = str(prev_bar["time"])

        window = df.iloc[-(self.sweep_lookback + 2):-2]
        recent_high = window["high"].max()
        recent_low = window["low"].min()

        atr = self.calc_atr(df, period=self.atr_period)
        rsi = self.calc_rsi(df, period=14)
        vol_avg = df["tick_volume"].iloc[-7:-2].mean() if "tick_volume" in df.columns else 1.0
        curr_vol = prev_bar.get("tick_volume", 1.0)
        vol_confirmed = curr_vol >= (vol_avg * 0.80)

        raw_sl = atr * self.atr_sl_multiplier
        sl_dist = round(max(min(raw_sl, max_sl), min_sl), digits)
        tp_dist = round(sl_dist * self.risk_reward_ratio, digits)

        tot_range = prev_bar["high"] - prev_bar["low"]
        if tot_range <= 0:
            return None, 0.0, 0.0, 0.0, None, 0, f"Flat bar on {tf_name}"

        upper_wick = prev_bar["high"] - max(prev_bar["open"], prev_bar["close"])
        lower_wick = min(prev_bar["open"], prev_bar["close"]) - prev_bar["low"]

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

        # -----------------------------------------------------------------
        # 1. BEARISH / SELL SETUP
        # -----------------------------------------------------------------
        is_sell_trend = prev_bar["ema_fast"] <= prev_bar["ema_slow"]
        valid_bear_pattern = (
            is_bear_live_break or is_bear_pinbar or is_bear_engulfing or 
            (is_sell_trend and (is_bear_momentum or is_bear_pullback)) or is_bear_sweep
        )

        if valid_bear_pattern:
            pattern_lbl = "Bearish Momentum / Pullback"
            if is_bear_sweep:
                pattern_lbl = "Bearish Liquidity Sweep"
            elif is_bear_pinbar:
                pattern_lbl = "Bearish Shooting Star Rejection"
            elif is_bear_engulfing:
                pattern_lbl = "Bearish Engulfing"

            rsi_ok_sell = (rsi >= 28.0 and rsi <= 70.0) or (is_bear_pinbar or is_bear_sweep)
            if rsi_ok_sell:
                score, breakdown, passed = self.calculate_quality_score(
                    symbol, tf_name, "SELL", trend_ctx, slope, rsi, vol_confirmed, pattern_lbl, current_spread, atr, quality_threshold
                )
                if passed:
                    max_chase = max(atr * 1.2, 3.50 if "XAU" in symbol else 200.0)
                    chase_dist = prev_bar["close"] - tick.bid
                    if chase_dist >= -1.50 and chase_dist <= max_chase:
                        entry = tick.bid
                        stop_loss = round(entry + sl_dist, digits)
                        take_profit = round(entry - tp_dist, digits)
                        candle_id = f"SCALP_SELL_{symbol}_{tf_name}_{c_time_str}"
                        reason = (
                            f"[SCALP SELL {tf_name}] {symbol} Pattern: {pattern_lbl} @ {entry:.2f} | "
                            f"Quality: {score}/100 | RSI: {rsi:.1f} | ATR: ${atr:.2f} | "
                            f"SL: {stop_loss:.2f} (-${sl_dist:.2f}) | TP: {take_profit:.2f} (+${tp_dist:.2f})"
                        )
                        return "SELL", entry, stop_loss, take_profit, candle_id, score, reason

        # -----------------------------------------------------------------
        # 2. BULLISH / BUY SETUP
        # -----------------------------------------------------------------
        is_buy_trend = prev_bar["ema_fast"] >= prev_bar["ema_slow"]
        valid_bull_pattern = (
            is_bull_live_break or is_bull_pinbar or is_bull_engulfing or 
            (is_buy_trend and (is_bull_momentum or is_bull_pullback)) or is_bull_sweep
        )

        if valid_bull_pattern:
            pattern_lbl = "Bullish Momentum / Breakout"
            if is_bull_sweep:
                pattern_lbl = "Bullish Liquidity Sweep"
            elif is_bull_pinbar:
                pattern_lbl = "Bullish Hammer Rejection"
            elif is_bull_engulfing:
                pattern_lbl = "Bullish Engulfing"

            rsi_ok_buy = (rsi >= 30.0 and rsi <= 72.0) or (is_bull_pinbar or is_bull_sweep)
            if rsi_ok_buy:
                score, breakdown, passed = self.calculate_quality_score(
                    symbol, tf_name, "BUY", trend_ctx, slope, rsi, vol_confirmed, pattern_lbl, current_spread, atr, quality_threshold
                )
                if passed:
                    max_chase = max(atr * 1.2, 3.50 if "XAU" in symbol else 200.0)
                    chase_dist = tick.ask - prev_bar["close"]
                    if chase_dist >= -1.50 and chase_dist <= max_chase:
                        entry = tick.ask
                        stop_loss = round(entry - sl_dist, digits)
                        take_profit = round(entry + tp_dist, digits)
                        candle_id = f"SCALP_BUY_{symbol}_{tf_name}_{c_time_str}"
                        reason = (
                            f"[SCALP BUY {tf_name}] {symbol} Pattern: {pattern_lbl} @ {entry:.2f} | "
                            f"Quality: {score}/100 | RSI: {rsi:.1f} | ATR: ${atr:.2f} | "
                            f"SL: {stop_loss:.2f} (-${sl_dist:.2f}) | TP: {take_profit:.2f} (+${tp_dist:.2f})"
                        )
                        return "BUY", entry, stop_loss, take_profit, candle_id, score, reason

        return None, 0.0, 0.0, 0.0, None, 0, f"No setup on {symbol} {tf_name}"

    def scan_for_scalp_candidates(
        self,
        symbol: str,
        quality_threshold: Optional[int] = None,
    ) -> Tuple[Optional[str], float, float, float, Optional[str], int, str, str, Optional[str], str]:
        """Active multi-timeframe micro-scalper scanning on symbol."""
        if not self.scalp_cfg.get("enabled", True):
            return None, 0.0, 0.0, 0.0, None, 0, "Scalper disabled", "DISABLED", None, "Disabled"

        info = mt5.symbol_info(symbol)
        if info is None:
            return None, 0.0, 0.0, 0.0, None, 0, "No symbol info", "NO_INFO", None, "No info"

        digits = info.digits
        current_spread = info.spread
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return None, 0.0, 0.0, 0.0, None, 0, "No tick info", "NO_TICK", None, "No tick"

        trend_ctx, trend_reason, slope = self.get_trend_context(symbol)
        latest_bar_time = None
        no_trade_reason = f"Scanning {symbol} micro timeframes..."

        for tf_name, tf_const in self.timeframes:
            df = self.fetch_rates(symbol, tf_const, count=30)
            if df is not None and len(df) >= 2:
                latest_bar_time = str(df.iloc[-2]["time"])

            sig, entry, sl, tp, cid, score, reason = self.evaluate_tf(
                symbol, tf_name, tf_const, digits, tick,
                trend_ctx=trend_ctx, slope=slope, current_spread=current_spread,
                quality_threshold=quality_threshold,
            )
            if sig:
                annotated_reason = f"{reason} | [Context: {trend_reason}]"
                return sig, entry, sl, tp, cid, score, annotated_reason, trend_reason, latest_bar_time, "Setup Valid"
            else:
                no_trade_reason = reason or "No setup on bar"

        return None, 0.0, 0.0, 0.0, None, 0, no_trade_reason, trend_reason, latest_bar_time, no_trade_reason
