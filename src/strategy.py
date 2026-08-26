"""
High-Conviction Musumali Strategy Engine for Gold (XAUUSD)
Institutional Multi-Timeframe Scanner: M15, M30, H1.
Features:
  1. Strict Liquidity Sweep Verification (Sweeps true swing wicks).
  2. Rejection Candle Confirmation (reclaims zone with 25%+ rejection wick).
  3. Intraday EMA Trend Alignment (Trade ONLY with the dominant momentum).
  4. Breakout Confirmation Entry.
"""

import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple
import MetaTrader5 as mt5
import numpy as np
import pandas as pd

logger = logging.getLogger("GoldBot.MusumaliStrategy")

TIMEFRAME_MAP = {
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
}


@dataclass
class AreaOfBenefit:
    zone_type: str            # "SUPPLY" (for SELLS) or "DEMAND" (for BUYS)
    zone_top: float           # Upper body bound
    zone_bottom: float        # Lower body bound
    cluster_high_wick: float  # Highest wick in cluster (liquidity pool for SELLS)
    cluster_low_wick: float   # Lowest wick in cluster (liquidity pool for BUYS)
    bar_index: int


class MusumaliStrategy:
    def __init__(self, config: dict):
        self.config = config
        self.strat_cfg = config.get("musumali_strategy", {})
        self.wick_rejection_ratio = self.strat_cfg.get("wick_rejection_ratio", 1.20)
        self.min_rejection_wick_pct = self.strat_cfg.get("min_rejection_wick_pct", 0.25)
        self.risk_reward_ratio = self.strat_cfg.get("risk_reward_ratio", 2.0)
        self.max_sl_distance = self.strat_cfg.get("max_loss_dollars", 1.20)
        # Institutional timeframes (Eliminates noisy 1-min false breakouts)
        self.scan_timeframes = [mt5.TIMEFRAME_M15, mt5.TIMEFRAME_M30, mt5.TIMEFRAME_H1]

    def fetch_rates(self, symbol: str, mt5_timeframe: int, count: int = 60) -> Optional[pd.DataFrame]:
        """Fetches OHLCV candlestick data from MT5."""
        rates = mt5.copy_rates_from_pos(symbol, mt5_timeframe, 0, count)
        if rates is None or len(rates) < 25:
            return None

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        return df

    def find_all_recent_areas_of_benefit(self, df: pd.DataFrame) -> List[AreaOfBenefit]:
        """Scans price action for prominent Supply and Demand swing clusters."""
        zones = []
        lookback = min(len(df) - 3, 30)

        for i in range(len(df) - lookback, len(df) - 2):
            prev_bar = df.iloc[i - 1]
            curr_bar = df.iloc[i]
            next_bar = df.iloc[i + 1]

            # Swing High (SUPPLY for SELLS)
            if curr_bar["high"] >= prev_bar["high"] and curr_bar["high"] >= next_bar["high"]:
                cluster = [prev_bar, curr_bar, next_bar]
                zones.append(AreaOfBenefit(
                    zone_type="SUPPLY",
                    zone_top=max(max(b["open"], b["close"]) for b in cluster),
                    zone_bottom=min(min(b["open"], b["close"]) for b in cluster),
                    cluster_high_wick=max(b["high"] for b in cluster),
                    cluster_low_wick=min(b["low"] for b in cluster),
                    bar_index=i,
                ))

            # Swing Low (DEMAND for BUYS)
            if curr_bar["low"] <= prev_bar["low"] and curr_bar["low"] <= next_bar["low"]:
                cluster = [prev_bar, curr_bar, next_bar]
                zones.append(AreaOfBenefit(
                    zone_type="DEMAND",
                    zone_top=max(max(b["open"], b["close"]) for b in cluster),
                    zone_bottom=min(min(b["open"], b["close"]) for b in cluster),
                    cluster_high_wick=max(b["high"] for b in cluster),
                    cluster_low_wick=min(b["low"] for b in cluster),
                    bar_index=i,
                ))

        return list(reversed(zones))

    def evaluate_musumali_setup_on_timeframe(
        self,
        symbol: str,
        tf: int,
        point: float,
        digits: int,
    ) -> Tuple[Optional[str], float, float, float, Optional[str]]:
        """Evaluates a timeframe for clean institutional liquidity sweep setups."""
        df = self.fetch_rates(symbol, tf, count=60)
        if df is None or len(df) < 25:
            return None, 0.0, 0.0, 0.0, None

        # Intraday Trend Filter (EMA 20 vs EMA 50)
        df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
        df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()
        last_ema20 = df["ema20"].iloc[-1]
        last_ema50 = df["ema50"].iloc[-1]

        zones = self.find_all_recent_areas_of_benefit(df)
        if not zones:
            return None, 0.0, 0.0, 0.0, None

        active_bar = df.iloc[-1]
        recent_bars = df.iloc[-5:-1]

        for zone in zones:
            for idx, candle in recent_bars.iterrows():
                if idx <= zone.bar_index:
                    continue

                c_open, c_close, c_high, c_low = candle["open"], candle["close"], candle["high"], candle["low"]
                c_time_str = str(candle["time"])
                total_range = c_high - c_low
                if total_range <= 0:
                    continue

                lower_wick = min(c_open, c_close) - c_low
                upper_wick = c_high - max(c_open, c_close)
                is_bullish = c_close > c_open
                is_bearish = c_close < c_open

                # =============================================================
                # HIGH-PROBABILITY SELL: Sweep of Highs in Bearish Trend
                # =============================================================
                if zone.zone_type == "SUPPLY" and last_ema20 <= last_ema50:
                    has_swept_highs = c_high >= zone.cluster_high_wick
                    reclaimed_zone = c_close <= zone.zone_top
                    has_strong_rejection = (
                        is_bearish and
                        (upper_wick >= self.wick_rejection_ratio * lower_wick or (upper_wick / total_range) >= self.min_rejection_wick_pct)
                    )

                    if has_swept_highs and reclaimed_zone and has_strong_rejection:
                        musumali_low = c_low
                        musumali_high = c_high
                        tick = mt5.symbol_info_tick(symbol)
                        if tick is None:
                            continue

                        # Breakout trigger
                        if tick.bid <= musumali_low or active_bar["low"] <= musumali_low:
                            entry = tick.bid
                            # Structural Stop Loss with breathing room buffer
                            structural_sl = musumali_high + (15 * point)
                            stop_loss = round(min(structural_sl, entry + self.max_sl_distance), digits)
                            risk = stop_loss - entry
                            if risk <= 0:
                                risk = 0.60
                                stop_loss = round(entry + 0.60, digits)

                            take_profit = round(entry - (risk * self.risk_reward_ratio), digits)
                            logger.info(
                                f"[HIGH-CONVICTION SELL] TF: {tf} | Candle: {c_time_str} | Entry: {entry:.2f} | SL: {stop_loss:.2f} | TP: {take_profit:.2f}"
                            )
                            return "SELL", entry, stop_loss, take_profit, f"{tf}_{c_time_str}"

                # =============================================================
                # HIGH-PROBABILITY BUY: Sweep of Lows in Bullish Trend
                # =============================================================
                elif zone.zone_type == "DEMAND" and last_ema20 >= last_ema50:
                    has_swept_lows = c_low <= zone.cluster_low_wick
                    reclaimed_zone = c_close >= zone.zone_bottom
                    has_strong_rejection = (
                        is_bullish and
                        (lower_wick >= self.wick_rejection_ratio * upper_wick or (lower_wick / total_range) >= self.min_rejection_wick_pct)
                    )

                    if has_swept_lows and reclaimed_zone and has_strong_rejection:
                        musumali_high = c_high
                        musumali_low = c_low
                        tick = mt5.symbol_info_tick(symbol)
                        if tick is None:
                            continue

                        # Breakout trigger
                        if tick.ask >= musumali_high or active_bar["high"] >= musumali_high:
                            entry = tick.ask
                            # Structural Stop Loss with breathing room buffer
                            structural_sl = musumali_low - (15 * point)
                            stop_loss = round(max(structural_sl, entry - self.max_sl_distance), digits)
                            risk = entry - stop_loss
                            if risk <= 0:
                                risk = 0.60
                                stop_loss = round(entry - 0.60, digits)

                            take_profit = round(entry + (risk * self.risk_reward_ratio), digits)
                            logger.info(
                                f"[HIGH-CONVICTION BUY] TF: {tf} | Candle: {c_time_str} | Entry: {entry:.2f} | SL: {stop_loss:.2f} | TP: {take_profit:.2f}"
                            )
                            return "BUY", entry, stop_loss, take_profit, f"{tf}_{c_time_str}"

        return None, 0.0, 0.0, 0.0, None

    def generate_signal(self, symbol: str) -> Tuple[Optional[str], float, float, float, Optional[str]]:
        """Scans across M15, M30, and H1 for high-probability setups."""
        info = mt5.symbol_info(symbol)
        if info is None:
            return None, 0.0, 0.0, 0.0, None

        point = info.point
        digits = info.digits

        for tf in self.scan_timeframes:
            signal, entry, sl, tp, candle_id = self.evaluate_musumali_setup_on_timeframe(symbol, tf, point, digits)
            if signal:
                return signal, entry, sl, tp, candle_id

        return None, 0.0, 0.0, 0.0, None
