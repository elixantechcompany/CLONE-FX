"""
Primary Strategy Engine (Multi-Symbol: XAUUSD & BTCUSD)
Engine 1 [Magic: 2001]: TwisterPro M15 Scalper Strategy (5-Layer Validation Matrix)
"""

import datetime
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any
import MetaTrader5 as mt5
import pandas as pd

from src.twister_strategy import TwisterProStrategy

logger = logging.getLogger("GoldBot.Strategy")

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
    """Tracks the 4-stage Musumali entry filter funnel."""
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
        self.symbols_cfg = config.get("symbols", {})

        self.magic_number = self.strat_cfg.get("magic_number", 2001)
        self.lookback_bars = self.strat_cfg.get("cluster_search_bars", 15)
        self.min_rejection_wick_pct = self.strat_cfg.get("min_rejection_wick_pct", 0.15)
        self.risk_reward_ratio = self.strat_cfg.get("risk_reward_ratio", 2.0)
        self.require_htf_alignment = self.strat_cfg.get("require_htf_alignment", False)

        self.atr_period = self.strat_cfg.get("atr_period", 14)
        self.atr_sl_multiplier = self.strat_cfg.get("atr_sl_multiplier", 1.5)

        # Configured execution scan timeframes (M30, H1)
        configured_tfs = self.strat_cfg.get("timeframes", ["M30", "H1"])
        self.scan_timeframes = [(tf, TIMEFRAME_MAP[tf]) for tf in configured_tfs if tf in TIMEFRAME_MAP]
        if not self.scan_timeframes:
            self.scan_timeframes = [("M30", mt5.TIMEFRAME_M30), ("H1", mt5.TIMEFRAME_H1)]

        # Funnel Instrumentation
        self.funnel = StrategyFunnelStats(current_date=datetime.date.today(), seen_events=set())

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
            return 2.0
        high = df["high"]
        low = df["low"]
        close_prev = df["close"].shift(1)
        tr = pd.concat([high - low, (high - close_prev).abs(), (low - close_prev).abs()], axis=1).max(axis=1)
        atr_series = tr.rolling(window=period).mean()
        latest_atr = atr_series.iloc[-2]
        return float(latest_atr) if pd.notna(latest_atr) and latest_atr > 0 else 2.0

    def get_symbol_settings(self, symbol: str) -> dict:
        """Returns symbol-specific parameters (XAUUSD vs BTCUSD)."""
        clean_sym = symbol.replace("m", "").replace("_i", "").replace("z", "").upper()
        if "BTC" in clean_sym:
            canonical = "BTCUSD"
        else:
            canonical = "XAUUSD"
        return self.symbols_cfg.get("symbol_settings", {}).get(canonical, {})

    def get_higher_timeframe_trend(self, symbol: str) -> Tuple[str, str]:
        """
        Evaluates H4 and D1 higher-timeframe trend and market structure.
        Returns: ("UPTREND" | "DOWNTREND" | "RANGING", explanation_str)
        """
        df_h1 = self.fetch_rates(symbol, mt5.TIMEFRAME_H1, count=60)
        df_h4 = self.fetch_rates(symbol, mt5.TIMEFRAME_H4, count=60)

        if df_h1 is None or len(df_h1) < 25:
            return "RANGING", "Insufficient H1 data"

        df_h1["ema20"] = df_h1["close"].ewm(span=20, adjust=False).mean()
        df_h1["ema50"] = df_h1["close"].ewm(span=50, adjust=False).mean()
        last_h1 = df_h1.iloc[-2]

        if last_h1["close"] > last_h1["ema20"] >= last_h1["ema50"]:
            return "UPTREND", f"H1/H4 UPTREND (Price {last_h1['close']:.2f} > EMA20 > EMA50)"
        elif last_h1["close"] < last_h1["ema20"] <= last_h1["ema50"]:
            return "DOWNTREND", f"H1/H4 DOWNTREND (Price {last_h1['close']:.2f} < EMA20 < EMA50)"

        # Check H4
        if df_h4 is not None and len(df_h4) >= 25:
            df_h4["ema20"] = df_h4["close"].ewm(span=20, adjust=False).mean()
            last_h4 = df_h4.iloc[-2]
            if last_h4["close"] > last_h4["ema20"]:
                return "UPTREND", "H4 Macro Bias Bullish"
            elif last_h4["close"] < last_h4["ema20"]:
                return "DOWNTREND", "H4 Macro Bias Bearish"

        return "NEUTRAL", f"Consolidating near EMA20 {last_h1['ema20']:.2f}"

    def calculate_setup_quality_score(
        self,
        symbol: str,
        sig: str,
        tf_name: str,
        htf_trend: str,
        rejection_wick_pct: float,
        sweep_depth: float,
        atr: float,
        current_spread: int,
    ) -> int:
        """Computes 0-100 conviction quality score for Musumali setups."""
        score = 0
        # 1. HTF Trend Alignment (30 pts)
        if (sig == "BUY" and htf_trend == "UPTREND") or (sig == "SELL" and htf_trend == "DOWNTREND"):
            score += 30
        elif htf_trend == "NEUTRAL":
            score += 15
        else:
            score += 5

        # 2. Rejection Quality (30 pts)
        if rejection_wick_pct >= 0.35:
            score += 30
        elif rejection_wick_pct >= 0.25:
            score += 25
        elif rejection_wick_pct >= 0.15:
            score += 18

        # 3. Sweep Depth & Cleanliness (20 pts)
        if sweep_depth >= (atr * 0.20):
            score += 20
        else:
            score += 10

        # 4. Spread Condition (10 pts)
        is_btc = "BTC" in symbol.upper()
        max_normal_spread = 2200 if is_btc else 280
        if current_spread <= max_normal_spread:
            score += 10
        else:
            score += 5

        # 5. Execution Timeframe Weight (10 pts)
        if tf_name == "H1":
            score += 10
        elif tf_name == "M30":
            score += 8
        else:
            score += 5

        return min(100, score)

    def evaluate_musumali_setup_on_timeframe(
        self,
        symbol: str,
        tf_name: str,
        tf_const: int,
        point: float,
        digits: int,
        htf_trend: str,
        htf_reason: str,
    ) -> Tuple[Optional[str], float, float, float, Optional[str], Optional[float], int, str]:
        """
        Scans M30 / H1 timeframe for institutional liquidity sweeps and candle-close reclaims.
        """
        df = self.fetch_rates(symbol, tf_const, count=50)
        if df is None or len(df) < 25:
            return None, 0.0, 0.0, 0.0, None, None, 0, ""

        sym_settings = self.get_symbol_settings(symbol)
        min_sl_dist = sym_settings.get("min_sl_distance_dollars", 2.00 if "XAU" in symbol else 150.0)
        max_sl_dist = sym_settings.get("max_sl_distance_dollars", 15.00 if "XAU" in symbol else 1200.0)
        zone_band_pts = sym_settings.get("zone_band_points", 2.0 if "XAU" in symbol else 100.0)

        atr = self.calculate_atr(df, period=self.atr_period)
        raw_sl_dist = atr * self.atr_sl_multiplier
        sl_dist = round(max(min(raw_sl_dist, max_sl_dist), min_sl_dist), digits)
        tp_dist = round(sl_dist * self.risk_reward_ratio, digits)

        # Check recent closed candles for sweep & rejection (offset -2, -3, -4)
        for offset in [-3, -4, -5]:
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

            bar_idx = len(df) + offset
            lookback_start = max(0, bar_idx - self.lookback_bars)
            window = df.iloc[lookback_start:bar_idx]
            if len(window) < 5:
                continue

            prev_swing_high = window["high"].max()
            prev_swing_low = window["low"].min()

            # Funnel Stage 1: Area of Benefit (Swing Level identified)
            zone_key = f"zone_{symbol}_{tf_name}_{c_time_str}"
            if zone_key not in self.funnel.seen_events:
                self.funnel.seen_events.add(zone_key)
                self.funnel.zones_identified += 1

            # -----------------------------------------------------------------
            # 4-STAGE SEQUENTIAL FUNNEL: SELL SETUP
            # -----------------------------------------------------------------
            # STAGE 2: Liquidity Sweep
            if sweep_bar["high"] >= prev_swing_high:
                sweep_key = f"sweep_{symbol}_{tf_name}_{c_time_str}"
                if sweep_key not in self.funnel.seen_events:
                    self.funnel.seen_events.add(sweep_key)
                    self.funnel.zones_swept += 1

                # STAGE 3: Rejection Candle Close
                reclaimed = sweep_bar["close"] < prev_swing_high or (upper_wick / tot_range >= self.min_rejection_wick_pct and is_bearish)
                if reclaimed:
                    musumali_key = f"musumali_{symbol}_{tf_name}_{c_time_str}"
                    if musumali_key not in self.funnel.seen_events:
                        self.funnel.seen_events.add(musumali_key)
                        self.funnel.valid_musumali_candles += 1

                    if self.require_htf_alignment and htf_trend == "UPTREND":
                        continue

                    # STAGE 4: Confirmed Closed-Candle Breakout Below Rejection Low
                    # Check the closed bars between sweep_bar and live candle
                    trigger_low = sweep_bar["low"]
                    invalidation_high = sweep_bar["high"]
                    
                    last_closed_bar = df.iloc[-2]
                    # Confirmation requires last closed candle to close firmly below trigger_low
                    breakout_confirmed = (last_closed_bar["close"] < trigger_low) and (last_closed_bar["close"] < last_closed_bar["open"])
                    is_invalidated = any(df["high"].iloc[offset + 1:-1] > invalidation_high) or (last_closed_bar["high"] > invalidation_high)
                    bars_since_sweep = abs(offset) - 1

                    # Expire if more than 3 bars without breakout, or if invalidated
                    if is_invalidated or bars_since_sweep > 3 or not breakout_confirmed:
                        continue

                    tick = mt5.symbol_info_tick(symbol)
                    if tick is None or tick.ask > invalidation_high:
                        continue

                    max_chase = max(sl_dist * 1.0, 4.0 if "XAU" in symbol else 250.0)
                    if (trigger_low - tick.bid) > max_chase:
                        continue

                    break_key = f"break_{symbol}_{tf_name}_{c_time_str}"
                    if break_key not in self.funnel.seen_events:
                        self.funnel.seen_events.add(break_key)
                        self.funnel.confirmed_break_entries += 1

                    entry = tick.bid
                    stop_loss = round(entry + sl_dist, digits)
                    take_profit = round(entry - tp_dist, digits)
                    zone_id = round(prev_swing_high / zone_band_pts) * zone_band_pts
                    candle_id = f"SWEEP_SELL_{symbol}_{tf_name}_{c_time_str}"

                    sweep_depth = sweep_bar["high"] - prev_swing_high
                    wick_pct = (upper_wick / tot_range) if tot_range > 0 else 0.0
                    info = mt5.symbol_info(symbol)
                    cur_spread = info.spread if info else 20

                    quality_score = self.calculate_setup_quality_score(
                        symbol=symbol,
                        sig="SELL",
                        tf_name=tf_name,
                        htf_trend=htf_trend,
                        rejection_wick_pct=wick_pct,
                        sweep_depth=sweep_depth,
                        atr=atr,
                        current_spread=cur_spread,
                    )

                    reason = (
                        f"[CONFIRMED MUSUMALI SELL {tf_name}] {symbol} Swept High {prev_swing_high:.2f} -> Closed Breakdown Below {trigger_low:.2f} | "
                        f"Quality: {quality_score}/100 | Entry: {entry:.2f} | SL: {stop_loss:.2f} (-${sl_dist:.2f}) | TP: {take_profit:.2f} (+${tp_dist:.2f}) | "
                        f"HTF Bias: {htf_trend}"
                    )
                    return "SELL", entry, stop_loss, take_profit, candle_id, zone_id, quality_score, reason

            # -----------------------------------------------------------------
            # 4-STAGE SEQUENTIAL FUNNEL: BUY SETUP
            # -----------------------------------------------------------------
            # STAGE 2: Liquidity Sweep
            if sweep_bar["low"] <= prev_swing_low:
                sweep_key = f"sweep_{symbol}_{tf_name}_{c_time_str}"
                if sweep_key not in self.funnel.seen_events:
                    self.funnel.seen_events.add(sweep_key)
                    self.funnel.zones_swept += 1

                # STAGE 3: Rejection Candle Close
                reclaimed = sweep_bar["close"] > prev_swing_low or (lower_wick / tot_range >= self.min_rejection_wick_pct and is_bullish)
                if reclaimed:
                    musumali_key = f"musumali_{symbol}_{tf_name}_{c_time_str}"
                    if musumali_key not in self.funnel.seen_events:
                        self.funnel.seen_events.add(musumali_key)
                        self.funnel.valid_musumali_candles += 1

                    if self.require_htf_alignment and htf_trend == "DOWNTREND":
                        continue

                    # STAGE 4: Confirmed Closed-Candle Breakout Above Rejection High
                    trigger_high = sweep_bar["high"]
                    invalidation_low = sweep_bar["low"]

                    last_closed_bar = df.iloc[-2]
                    # Confirmation requires last closed candle to close firmly above trigger_high
                    breakout_confirmed = (last_closed_bar["close"] > trigger_high) and (last_closed_bar["close"] > last_closed_bar["open"])
                    is_invalidated = any(df["low"].iloc[offset + 1:-1] < invalidation_low) or (last_closed_bar["low"] < invalidation_low)
                    bars_since_sweep = abs(offset) - 1

                    # Expire if more than 3 bars without breakout, or if invalidated
                    if is_invalidated or bars_since_sweep > 3 or not breakout_confirmed:
                        continue

                    tick = mt5.symbol_info_tick(symbol)
                    if tick is None or tick.bid < invalidation_low:
                        continue

                    max_chase = max(sl_dist * 1.0, 4.0 if "XAU" in symbol else 250.0)
                    if (tick.ask - trigger_high) > max_chase:
                        continue

                    break_key = f"break_{symbol}_{tf_name}_{c_time_str}"
                    if break_key not in self.funnel.seen_events:
                        self.funnel.seen_events.add(break_key)
                        self.funnel.confirmed_break_entries += 1

                    entry = tick.ask
                    stop_loss = round(entry - sl_dist, digits)
                    take_profit = round(entry + tp_dist, digits)
                    zone_id = round(prev_swing_low / zone_band_pts) * zone_band_pts
                    candle_id = f"SWEEP_BUY_{symbol}_{tf_name}_{c_time_str}"

                    sweep_depth = prev_swing_low - sweep_bar["low"]
                    wick_pct = (lower_wick / tot_range) if tot_range > 0 else 0.0
                    info = mt5.symbol_info(symbol)
                    cur_spread = info.spread if info else 20

                    quality_score = self.calculate_setup_quality_score(
                        symbol=symbol,
                        sig="BUY",
                        tf_name=tf_name,
                        htf_trend=htf_trend,
                        rejection_wick_pct=wick_pct,
                        sweep_depth=sweep_depth,
                        atr=atr,
                        current_spread=cur_spread,
                    )

                    reason = (
                        f"[CONFIRMED MUSUMALI BUY {tf_name}] {symbol} Swept Low {prev_swing_low:.2f} -> Closed Breakout Above {trigger_high:.2f} | "
                        f"Quality: {quality_score}/100 | Entry: {entry:.2f} | SL: {stop_loss:.2f} (-${sl_dist:.2f}) | TP: {take_profit:.2f} (+${tp_dist:.2f}) | "
                        f"HTF Bias: {htf_trend}"
                    )
                    return "BUY", entry, stop_loss, take_profit, candle_id, zone_id, quality_score, reason

        return None, 0.0, 0.0, 0.0, None, None, 0, ""

    def generate_signal(
        self, symbol: str, traded_candle_ids: Optional[set] = None
    ) -> Tuple[Optional[str], float, float, float, Optional[str], Optional[float], int, str]:
        """Scans across configured timeframes (M30, H1) for high-conviction liquidity sweep setups."""
        today = datetime.date.today()
        self.funnel.reset_if_new_day(today)

        info = mt5.symbol_info(symbol)
        if info is None:
            return None, 0.0, 0.0, 0.0, None, None, 0, "No symbol info"

        point = info.point
        digits = info.digits

        htf_trend, htf_reason = self.get_higher_timeframe_trend(symbol)

        for tf_name, tf_const in self.scan_timeframes:
            sig, entry, sl, tp, candle_id, zone_id, score, reason = self.evaluate_musumali_setup_on_timeframe(
                symbol, tf_name, tf_const, point, digits, htf_trend, htf_reason
            )
            if sig and candle_id:
                if traded_candle_ids and candle_id in traded_candle_ids:
                    continue
                return sig, entry, sl, tp, candle_id, zone_id, score, reason

        return None, 0.0, 0.0, 0.0, None, None, 0, f"Scanning M30/H1 sweeps on {symbol} (HTF: {htf_trend})"
