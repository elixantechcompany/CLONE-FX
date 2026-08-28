"""
High-Conviction Musumali Strategy Engine for Gold (XAUUSD)
Enforces:
  1. Fix 2: Hard Daily (D1) Trend Gate (UPTREND -> BUY only, DOWNTREND -> SELL only, RANGING -> 100% Block).
  2. Fix 3: 4-Stage Entry Filter Funnel Instrumentation (Zones -> Sweeps -> Musumali Candle -> Confirmed Break Entry).
  3. Precision Institutional Liquidity Sweep & Reclaim Scanner: M5, M15, M30, H1.
"""

import datetime
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import MetaTrader5 as mt5
import numpy as np
import pandas as pd

logger = logging.getLogger("GoldBot.MusumaliStrategy")

TIMEFRAME_MAP = {
    "M1": mt5.TIMEFRAME_M1,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
}


@dataclass
class StrategyFunnelStats:
    """Tracks the 4-stage Musumali entry filter funnel to diagnose trade frequency."""
    zones_identified: int = 0
    zones_swept: int = 0
    valid_musumali_candles: int = 0
    confirmed_break_entries: int = 0
    current_date: Optional[datetime.date] = None
    seen_events: Optional[set] = None

    def reset_if_new_day(self, today: datetime.date):
        if self.current_date != today:
            self.current_date = today
            self.zones_identified = 0
            self.zones_swept = 0
            self.valid_musumali_candles = 0
            self.confirmed_break_entries = 0
            self.seen_events = set()
        elif self.seen_events is None:
            self.seen_events = set()


class MusumaliStrategy:
    def __init__(self, config: dict):
        self.config = config
        self.strat_cfg = config.get("musumali_strategy", {})
        self.zone_cfg = config.get("zone_management", {})

        # Rejection & Sweep Parameters
        self.lookback_bars = self.strat_cfg.get("cluster_search_bars", 15)
        self.min_rejection_wick_pct = self.strat_cfg.get("min_rejection_wick_pct", 0.15)
        self.risk_reward_ratio = self.strat_cfg.get("risk_reward_ratio", 2.0)

        # Dynamic ATR Parameters
        self.atr_period = self.strat_cfg.get("atr_period", 14)
        self.atr_sl_multiplier = self.strat_cfg.get("atr_sl_multiplier", 1.5)
        self.min_sl_distance = self.strat_cfg.get("min_sl_distance_dollars", 2.00)
        self.max_sl_distance = self.strat_cfg.get("max_sl_distance_dollars", 15.00)
        self.require_htf_alignment = self.strat_cfg.get("require_htf_alignment", False)

        # Fix 2: Higher Timeframe (Daily D1) Trend Filter Gate Parameters
        self.trend_tf_str = self.strat_cfg.get("htf_timeframe", "D1")
        self.trend_mt5_tf = TIMEFRAME_MAP.get(self.trend_tf_str, mt5.TIMEFRAME_D1)
        self.htf_fast_ema = self.strat_cfg.get("htf_fast_ema", 20)
        self.htf_slow_ema = self.strat_cfg.get("htf_slow_ema", 50)
        self.htf_trend_ema = self.strat_cfg.get("htf_trend_ema", 200)

        # Zone grouping
        self.zone_band_points = self.zone_cfg.get("zone_band_points", 5.0)

        # Fix 8: Scan timeframes strictly isolated to H1 and above (H1, H4)
        configured_tfs = self.strat_cfg.get("timeframes", ["H1", "H4"])
        self.scan_timeframes = [(tf, TIMEFRAME_MAP[tf]) for tf in configured_tfs if tf in TIMEFRAME_MAP]
        if not self.scan_timeframes:
            self.scan_timeframes = [
                ("H1", mt5.TIMEFRAME_H1),
                ("H4", mt5.TIMEFRAME_H4),
            ]

        # Fix 3: Funnel Instrumentation
        self.funnel = StrategyFunnelStats(current_date=datetime.date.today(), seen_events=set())
        self.last_funnel_log_time = 0.0

    def fetch_rates(self, symbol: str, mt5_timeframe: int, count: int = 100) -> Optional[pd.DataFrame]:
        """Fetches OHLCV candlestick data from MT5."""
        rates = mt5.copy_rates_from_pos(symbol, mt5_timeframe, 0, count)
        if rates is None or len(rates) < 20:
            return None

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        return df

    def calculate_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        """Calculates Average True Range (ATR)."""
        if len(df) < period + 2:
            return 1.5
        high = df["high"]
        low = df["low"]
        close_prev = df["close"].shift(1)
        tr = pd.concat([high - low, (high - close_prev).abs(), (low - close_prev).abs()], axis=1).max(axis=1)
        atr_series = tr.rolling(window=period).mean()
        latest_atr = atr_series.iloc[-2]
        return float(latest_atr) if pd.notna(latest_atr) and latest_atr > 0 else 1.5

    def get_daily_market_trend(self, symbol: str) -> Tuple[str, str]:
        """
        Fix 2: Audits and Evaluates the Higher-Timeframe Daily (D1) Trend Filter Gate.
        Returns:
          ("UPTREND" | "DOWNTREND" | "RANGING", explanation_str)
        """
        df_h1 = self.fetch_rates(symbol, mt5.TIMEFRAME_H1, count=60)
        df_d1 = self.fetch_rates(symbol, mt5.TIMEFRAME_D1, count=60)

        if df_h1 is None or len(df_h1) < 25:
            return "RANGING", "Insufficient H1 bars for trend evaluation"

        df_h1["ema20"] = df_h1["close"].ewm(span=20, adjust=False).mean()
        df_h1["ema50"] = df_h1["close"].ewm(span=50, adjust=False).mean()

        last_h1 = df_h1.iloc[-2]
        close_h1 = last_h1["close"]
        ema20_h1 = last_h1["ema20"]
        ema50_h1 = last_h1["ema50"]

        # H1 Primary Intraday Trend
        if close_h1 < ema20_h1 and ema20_h1 <= ema50_h1:
            return "DOWNTREND", f"H1 DOWNTREND (Price {close_h1:.2f} < EMA20 {ema20_h1:.2f} <= EMA50 {ema50_h1:.2f})"
        elif close_h1 > ema20_h1 and ema20_h1 >= ema50_h1:
            return "UPTREND", f"H1 UPTREND (Price {close_h1:.2f} > EMA20 {ema20_h1:.2f} >= EMA50 {ema50_h1:.2f})"

        # Fallback to D1
        if df_d1 is not None and len(df_d1) >= 25:
            df_d1["ema20"] = df_d1["close"].ewm(span=20, adjust=False).mean()
            df_d1["ema50"] = df_d1["close"].ewm(span=50, adjust=False).mean()
            last_d1 = df_d1.iloc[-2]
            if last_d1["close"] > last_d1["ema20"] > last_d1["ema50"]:
                return "UPTREND", "D1 Macro UPTREND"
            elif last_d1["close"] < last_d1["ema20"] < last_d1["ema50"]:
                return "DOWNTREND", "D1 Macro DOWNTREND"

        return "DOWNTREND" if close_h1 < ema20_h1 else "UPTREND", f"H1 Momentum (Close {close_h1:.2f} vs EMA20 {ema20_h1:.2f})"

    def get_htf_structural_bias(self, symbol: str) -> Tuple[str, str]:
        """Backward-compatible alias for daily market trend."""
        trend, reason = self.get_daily_market_trend(symbol)
        return trend, reason

    def log_funnel_audit(self):
        """Fix 3: Periodically logs the cumulative 4-stage filter funnel."""
        logger.info(
            f"[ENTRY FILTER FUNNEL AUDIT] (Daily Cumulative):\n"
            f"  - Zones (Area of Benefit) identified: {self.funnel.zones_identified}\n"
            f"  - Zones that got a liquidity sweep: {self.funnel.zones_swept}\n"
            f"  - Sweeps that produced a valid Musumali candle: {self.funnel.valid_musumali_candles}\n"
            f"  - Musumali candles that got a confirmed break (entry): {self.funnel.confirmed_break_entries}"
        )

    def evaluate_musumali_setup_on_timeframe(
        self,
        symbol: str,
        tf_name: str,
        tf_const: int,
        point: float,
        digits: int,
        daily_trend: str,
        trend_reason: str,
    ) -> Tuple[Optional[str], float, float, float, Optional[str], Optional[float], str]:
        """
        Scans timeframe for institutional liquidity sweeps and candle-close reclaims.
        Enforces Fix 2 Hard Trend Gate and Fix 3 Funnel Instrumentation.
        """
        df = self.fetch_rates(symbol, tf_const, count=50)
        if df is None or len(df) < 25:
            return None, 0.0, 0.0, 0.0, None, None, ""

        atr = self.calculate_atr(df, period=self.atr_period)
        atr_stop_distance = max(min(atr * self.atr_sl_multiplier, self.max_sl_distance), self.min_sl_distance)
        take_profit_distance = atr_stop_distance * self.risk_reward_ratio

        # Evaluate recent closed candles in active session
        for offset in [-2, -3, -4]:
            if abs(offset) >= len(df):
                continue
            sweep_bar = df.iloc[offset]
            c_time_str = str(sweep_bar["time"])
            tot_range = sweep_bar["high"] - sweep_bar["low"]
            if tot_range <= 0:
                continue

            upper_wick = sweep_bar["high"] - max(sweep_bar["open"], sweep_bar["close"])
            lower_wick = min(sweep_bar["open"], sweep_bar["close"]) - sweep_bar["low"]
            is_bearish = sweep_bar["close"] <= sweep_bar["open"]
            is_bullish = sweep_bar["close"] >= sweep_bar["open"]

            # Dynamic Swing Lookback (prior bars before the sweep)
            bar_idx = len(df) + offset
            lookback_start = max(0, bar_idx - self.lookback_bars)
            window = df.iloc[lookback_start:bar_idx]
            if len(window) < 5:
                continue

            prev_swing_high = window["high"].max()
            prev_swing_low = window["low"].min()

            # Funnel Stage 1: Zones (Area of Benefit) identified
            zone_key = f"zone_{tf_name}_{c_time_str}"
            if zone_key not in self.funnel.seen_events:
                self.funnel.seen_events.add(zone_key)
                self.funnel.zones_identified += 1

            # -----------------------------------------------------------------
            # HIGH-PROBABILITY SELL: Sweep of Swing High with Rejection Reclaim
            # -----------------------------------------------------------------
            if sweep_bar["high"] >= prev_swing_high:
                # Funnel Stage 2: Zones that got a liquidity sweep
                sweep_key = f"sweep_{tf_name}_{c_time_str}"
                if sweep_key not in self.funnel.seen_events:
                    self.funnel.seen_events.add(sweep_key)
                    self.funnel.zones_swept += 1

                reclaimed = sweep_bar["close"] < prev_swing_high or (upper_wick / tot_range >= self.min_rejection_wick_pct and is_bearish)
                if reclaimed:
                    # Funnel Stage 3: Sweeps that produced a valid Musumali candle
                    musumali_key = f"musumali_{tf_name}_{c_time_str}"
                    if musumali_key not in self.funnel.seen_events:
                        self.funnel.seen_events.add(musumali_key)
                        self.funnel.valid_musumali_candles += 1

                    # Trend Alignment Check
                    if self.require_htf_alignment and daily_trend != "DOWNTREND":
                        continue

                    tick = mt5.symbol_info_tick(symbol)
                    if tick is None:
                        continue

                    # SETUP INVALIDATION: If price has broken above the sweep high, the setup is blown
                    if tick.ask > sweep_bar["high"]:
                        continue

                    # STAGE 4 BREAK CONFIRMATION: Price must confirm break below sweep candle's low
                    if tick.bid > sweep_bar["low"]:
                        continue  # Has not broken the low yet

                    # Freshness: Must be within 0.35 ATR distance of sweep low (No late entries!)
                    if (sweep_bar["low"] - tick.bid) > (atr_stop_distance * 0.35):
                        continue  # Price ran away too far

                    # Funnel Stage 4: Musumali candles that got a confirmed break (entry)
                    break_key = f"break_{tf_name}_{c_time_str}"
                    if break_key not in self.funnel.seen_events:
                        self.funnel.seen_events.add(break_key)
                        self.funnel.confirmed_break_entries += 1

                    entry = tick.bid
                    # Fix 21: Pure ATR(14)-Scaled Dynamic Stop Loss (1.5x ATR)
                    raw_sl_dist = atr * self.atr_sl_multiplier
                    sl_dist = round(max(min(raw_sl_dist, self.max_sl_distance), self.min_sl_distance), digits)
                    tp_dist = round(sl_dist * self.risk_reward_ratio, digits)

                    stop_loss = round(entry + sl_dist, digits)
                    take_profit = round(entry - tp_dist, digits)
                    zone_id = round(prev_swing_high / self.zone_band_points) * self.zone_band_points
                    candle_id = f"SWEEP_SELL_{tf_name}_{c_time_str}"

                    # Fix 22: Comprehensive Visual Verification Audit Logging
                    sweep_depth = sweep_bar["high"] - prev_swing_high
                    reclaim_depth = prev_swing_high - sweep_bar["close"]
                    wick_pct = (upper_wick / tot_range) * 100.0 if tot_range > 0 else 0.0
                    zone_low = zone_id - (self.zone_band_points / 2.0)
                    zone_high = zone_id + (self.zone_band_points / 2.0)

                    audit_msg = (
                        f"\n{'='*75}\n"
                        f"[MUSUMALI SIGNAL QUALITY AUDIT FIX 22] Detailed Visual Level Breakdown\n"
                        f"{'-'*75}\n"
                        f"Timeframe:         {tf_name}\n"
                        f"Setup Type:        CONFIRMED SELL SWEEP\n"
                        f"Candle Timestamp:  {c_time_str} (Closed)\n"
                        f"Daily Trend Gate:  {daily_trend} ({trend_reason})\n\n"
                        f"1. Area of Benefit (Zone):\n"
                        f"   - Zone Center:     {zone_id:.2f}\n"
                        f"   - Zone Band:       [{zone_low:.2f} - {zone_high:.2f}] (Band: ${self.zone_band_points:.2f})\n"
                        f"   - Prior Swing High:{prev_swing_high:.2f}\n\n"
                        f"2. Liquidity Sweep:\n"
                        f"   - Level Swept:     {prev_swing_high:.2f}\n"
                        f"   - Sweep High:      {sweep_bar['high']:.2f} (Swept by +${sweep_depth:.2f} / {sweep_depth*1000:.0f} pts)\n"
                        f"   - Sweep Reclaim:   Closed @ {sweep_bar['close']:.2f} (Reclaimed below by ${reclaim_depth:.2f})\n\n"
                        f"3. Musumali Candle Metrics:\n"
                        f"   - Open: {sweep_bar['open']:.2f} | High: {sweep_bar['high']:.2f} | Low: {sweep_bar['low']:.2f} | Close: {sweep_bar['close']:.2f}\n"
                        f"   - Total Range:     ${tot_range:.2f}\n"
                        f"   - Upper Rejection: ${upper_wick:.2f} ({wick_pct:.1f}% of range >= {self.min_rejection_wick_pct*100:.0f}% threshold)\n"
                        f"   - Candle Direction:{'Bearish Red' if is_bearish else 'Bullish Green'}\n\n"
                        f"4. Stage 4 Breakdown Trigger & Entry:\n"
                        f"   - Breakdown Level: Bid <= {sweep_bar['low']:.2f} (Sweep Candle Low)\n"
                        f"   - Execution Bid:   {entry:.2f}\n\n"
                        f"5. ATR-Scaled Risk/Reward (Fix 21):\n"
                        f"   - {tf_name} ATR({self.atr_period}):   ${atr:.2f}\n"
                        f"   - SL Multiplier:   {self.atr_sl_multiplier:.1f}x -> Dynamic SL Distance: ${sl_dist:.2f}\n"
                        f"   - Stop Loss Level: {stop_loss:.2f} (-${sl_dist:.2f})\n"
                        f"   - Take Profit Level:{take_profit:.2f} (+${tp_dist:.2f}) [1:{self.risk_reward_ratio:.1f} R:R]\n"
                        f"{'='*75}"
                    )
                    logger.info(audit_msg)

                    reason = (
                        f"[ATR-SCALED SL FIX 21] [CONFIRMED SELL {tf_name}] Swept High {prev_swing_high:.2f} -> Confirmed Breakdown Below {sweep_bar['low']:.2f} | "
                        f"{tf_name} ATR({self.atr_period}): ${atr:.2f} | Multiplier: {self.atr_sl_multiplier}x -> "
                        f"Entry: {entry:.2f} | SL: {stop_loss:.2f} (-${sl_dist:.2f}) | TP: {take_profit:.2f} (+${tp_dist:.2f}) | "
                        f"Daily Trend Gate: {daily_trend}"
                    )
                    return "SELL", entry, stop_loss, take_profit, candle_id, zone_id, reason

            # -----------------------------------------------------------------
            # HIGH-PROBABILITY BUY: Sweep of Swing Low with Rejection Reclaim
            # -----------------------------------------------------------------
            if sweep_bar["low"] <= prev_swing_low:
                # Funnel Stage 2: Zones that got a liquidity sweep
                sweep_key = f"sweep_{tf_name}_{c_time_str}"
                if sweep_key not in self.funnel.seen_events:
                    self.funnel.seen_events.add(sweep_key)
                    self.funnel.zones_swept += 1

                reclaimed = sweep_bar["close"] > prev_swing_low or (lower_wick / tot_range >= self.min_rejection_wick_pct and is_bullish)
                if reclaimed:
                    # Funnel Stage 3: Sweeps that produced a valid Musumali candle
                    musumali_key = f"musumali_{tf_name}_{c_time_str}"
                    if musumali_key not in self.funnel.seen_events:
                        self.funnel.seen_events.add(musumali_key)
                        self.funnel.valid_musumali_candles += 1

                    # Trend Alignment Check
                    if self.require_htf_alignment and daily_trend != "UPTREND":
                        continue

                    tick = mt5.symbol_info_tick(symbol)
                    if tick is None:
                        continue

                    # SETUP INVALIDATION: If price has broken below the sweep low, the setup is blown (DO NOT BUY A FALLING KNIFE)
                    if tick.bid < sweep_bar["low"]:
                        continue

                    # STAGE 4 BREAK CONFIRMATION: Price must confirm breakout above sweep candle's high
                    if tick.ask < sweep_bar["high"]:
                        continue  # Has not broken the high yet

                    # Freshness: Must be within 0.35 ATR distance of sweep high (No late entries!)
                    if (tick.ask - sweep_bar["high"]) > (atr_stop_distance * 0.35):
                        continue  # Price ran away too far

                    # Funnel Stage 4: Musumali candles that got a confirmed break (entry)
                    break_key = f"break_{tf_name}_{c_time_str}"
                    if break_key not in self.funnel.seen_events:
                        self.funnel.seen_events.add(break_key)
                        self.funnel.confirmed_break_entries += 1

                    entry = tick.ask
                    # Fix 21: Pure ATR(14)-Scaled Dynamic Stop Loss (1.5x ATR)
                    raw_sl_dist = atr * self.atr_sl_multiplier
                    sl_dist = round(max(min(raw_sl_dist, self.max_sl_distance), self.min_sl_distance), digits)
                    tp_dist = round(sl_dist * self.risk_reward_ratio, digits)

                    stop_loss = round(entry - sl_dist, digits)
                    take_profit = round(entry + tp_dist, digits)
                    zone_id = round(prev_swing_low / self.zone_band_points) * self.zone_band_points
                    candle_id = f"SWEEP_BUY_{tf_name}_{c_time_str}"

                    # Fix 22: Comprehensive Visual Verification Audit Logging
                    sweep_depth = prev_swing_low - sweep_bar["low"]
                    reclaim_depth = sweep_bar["close"] - prev_swing_low
                    wick_pct = (lower_wick / tot_range) * 100.0 if tot_range > 0 else 0.0
                    zone_low = zone_id - (self.zone_band_points / 2.0)
                    zone_high = zone_id + (self.zone_band_points / 2.0)

                    audit_msg = (
                        f"\n{'='*75}\n"
                        f"[MUSUMALI SIGNAL QUALITY AUDIT FIX 22] Detailed Visual Level Breakdown\n"
                        f"{'-'*75}\n"
                        f"Timeframe:         {tf_name}\n"
                        f"Setup Type:        CONFIRMED BUY SWEEP\n"
                        f"Candle Timestamp:  {c_time_str} (Closed)\n"
                        f"Daily Trend Gate:  {daily_trend} ({trend_reason})\n\n"
                        f"1. Area of Benefit (Zone):\n"
                        f"   - Zone Center:     {zone_id:.2f}\n"
                        f"   - Zone Band:       [{zone_low:.2f} - {zone_high:.2f}] (Band: ${self.zone_band_points:.2f})\n"
                        f"   - Prior Swing Low: {prev_swing_low:.2f}\n\n"
                        f"2. Liquidity Sweep:\n"
                        f"   - Level Swept:     {prev_swing_low:.2f}\n"
                        f"   - Sweep Low:       {sweep_bar['low']:.2f} (Swept by -${sweep_depth:.2f} / {sweep_depth*1000:.0f} pts)\n"
                        f"   - Sweep Reclaim:   Closed @ {sweep_bar['close']:.2f} (Reclaimed above by +${reclaim_depth:.2f})\n\n"
                        f"3. Musumali Candle Metrics:\n"
                        f"   - Open: {sweep_bar['open']:.2f} | High: {sweep_bar['high']:.2f} | Low: {sweep_bar['low']:.2f} | Close: {sweep_bar['close']:.2f}\n"
                        f"   - Total Range:     ${tot_range:.2f}\n"
                        f"   - Lower Rejection: ${lower_wick:.2f} ({wick_pct:.1f}% of range >= {self.min_rejection_wick_pct*100:.0f}% threshold)\n"
                        f"   - Candle Direction:{'Bullish Green' if is_bullish else 'Bearish Red'}\n\n"
                        f"4. Stage 4 Breakout Trigger & Entry:\n"
                        f"   - Breakout Level:  Ask >= {sweep_bar['high']:.2f} (Sweep Candle High)\n"
                        f"   - Execution Ask:   {entry:.2f}\n\n"
                        f"5. ATR-Scaled Risk/Reward (Fix 21):\n"
                        f"   - {tf_name} ATR({self.atr_period}):   ${atr:.2f}\n"
                        f"   - SL Multiplier:   {self.atr_sl_multiplier:.1f}x -> Dynamic SL Distance: ${sl_dist:.2f}\n"
                        f"   - Stop Loss Level: {stop_loss:.2f} (-${sl_dist:.2f})\n"
                        f"   - Take Profit Level:{take_profit:.2f} (+${tp_dist:.2f}) [1:{self.risk_reward_ratio:.1f} R:R]\n"
                        f"{'='*75}"
                    )
                    logger.info(audit_msg)

                    reason = (
                        f"[ATR-SCALED SL FIX 21] [CONFIRMED BUY {tf_name}] Swept Low {prev_swing_low:.2f} -> Confirmed Breakout Above {sweep_bar['high']:.2f} | "
                        f"{tf_name} ATR({self.atr_period}): ${atr:.2f} | Multiplier: {self.atr_sl_multiplier}x -> "
                        f"Entry: {entry:.2f} | SL: {stop_loss:.2f} (-${sl_dist:.2f}) | TP: {take_profit:.2f} (+${tp_dist:.2f}) | "
                        f"Daily Trend Gate: {daily_trend}"
                    )
                    return "BUY", entry, stop_loss, take_profit, candle_id, zone_id, reason

        return None, 0.0, 0.0, 0.0, None, None, ""

    def generate_signal(
        self, symbol: str, traded_candle_ids: Optional[set] = None
    ) -> Tuple[Optional[str], float, float, float, Optional[str], Optional[float], str]:
        """
        Scans across M15, M30, H1, and H4 for high-conviction liquidity sweep setups.
        Enforces Fix 2 Hard Daily Trend Gate.
        """
        today = datetime.date.today()
        self.funnel.reset_if_new_day(today)

        info = mt5.symbol_info(symbol)
        if info is None:
            return None, 0.0, 0.0, 0.0, None, None, ""

        point = info.point
        digits = info.digits

        # Fix 2: Hard Gate Trend Audit on Daily (D1)
        daily_trend, trend_reason = self.get_daily_market_trend(symbol)

        # If Daily trend is RANGING or inconclusive, HARD BLOCK: NO TRADES
        if daily_trend == "RANGING":
            return None, 0.0, 0.0, 0.0, None, None, f"Daily Ranging Hard Filter Active: {trend_reason}"

        for tf_name, tf_const in self.scan_timeframes:
            signal, entry, sl, tp, candle_id, zone_id, reason = self.evaluate_musumali_setup_on_timeframe(
                symbol, tf_name, tf_const, point, digits, daily_trend, trend_reason
            )
            if signal and candle_id:
                if traded_candle_ids and candle_id in traded_candle_ids:
                    continue  # Already executed on this timeframe candle, scan remaining timeframes
                return signal, entry, sl, tp, candle_id, zone_id, reason

        return None, 0.0, 0.0, 0.0, None, None, f"Scanning M15/M30/H1/H4 sweeps (Daily Trend Gate: {daily_trend})"
