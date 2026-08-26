"""
1-Minute (M1) Gold Micro-Scalper Engine
With Intraday Trend Alignment & Signal De-Duplication.
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
        self.magic_number = self.scalp_cfg.get("magic_number", 888777)
        self.fast_ema = self.scalp_cfg.get("fast_ema", 9)
        self.slow_ema = self.scalp_cfg.get("slow_ema", 21)
        self.sweep_lookback = self.scalp_cfg.get("sweep_lookback_bars", 10)
        self.wick_ratio = self.scalp_cfg.get("wick_rejection_ratio", 1.10)
        self.target_tp_dollars = self.scalp_cfg.get("target_profit_dollars", 1.50)
        self.max_sl_dollars = self.scalp_cfg.get("max_loss_dollars", 0.80)

    def fetch_m1_rates(self, symbol: str, count: int = 50) -> Optional[pd.DataFrame]:
        """Fetches the latest 1-minute OHLCV candles from MT5."""
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, count)
        if rates is None or len(rates) < 25:
            return None

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        return df

    def generate_scalp_signal(self, symbol: str) -> Tuple[Optional[str], float, float, float, Optional[str]]:
        """Evaluates 1-minute micro-trend and liquidity sweeps for rapid scalp entries."""
        if not self.enabled:
            return None, 0.0, 0.0, 0.0, None

        df = self.fetch_m1_rates(symbol, count=40)
        if df is None:
            return None, 0.0, 0.0, 0.0, None

        info = mt5.symbol_info(symbol)
        if info is None:
            return None, 0.0, 0.0, 0.0, None

        digits = info.digits
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return None, 0.0, 0.0, 0.0, None

        # Calculate Micro EMAs
        df["ema_fast"] = df["close"].ewm(span=self.fast_ema, adjust=False).mean()
        df["ema_slow"] = df["close"].ewm(span=self.slow_ema, adjust=False).mean()

        prev_bar = df.iloc[-2]
        curr_bar = df.iloc[-1]
        c_time_str = str(prev_bar["time"])
        window = df.iloc[-(self.sweep_lookback + 2):-2]

        recent_high_wick = window["high"].max()
        recent_low_wick = window["low"].min()

        price_move_for_tp = self.target_tp_dollars
        price_move_for_sl = self.max_sl_dollars

        # 1-MINUTE SCALP: SELL (Micro-Liquidity Sweep of Highs in Downtrend)
        if prev_bar["ema_fast"] <= prev_bar["ema_slow"]:
            has_swept_high = prev_bar["high"] >= recent_high_wick
            upper_wick = prev_bar["high"] - max(prev_bar["open"], prev_bar["close"])
            lower_wick = min(prev_bar["open"], prev_bar["close"]) - prev_bar["low"]
            is_bearish = prev_bar["close"] <= prev_bar["open"]
            has_rejection = is_bearish or (upper_wick >= self.wick_ratio * lower_wick)

            if has_swept_high and has_rejection:
                if tick.bid <= prev_bar["low"] or curr_bar["low"] <= prev_bar["low"]:
                    entry = tick.bid
                    stop_loss = round(entry + price_move_for_sl, digits)
                    take_profit = round(entry - price_move_for_tp, digits)
                    logger.info(
                        f"[M1 SCALP] SELL @ {entry:.2f} | Candle: {c_time_str} | SL: {stop_loss:.2f} (-${self.max_sl_dollars:.2f}) | TP: {take_profit:.2f} (+${self.target_tp_dollars:.2f})"
                    )
                    return "SELL", entry, stop_loss, take_profit, f"M1_{c_time_str}"

        # 1-MINUTE SCALP: BUY (Micro-Liquidity Sweep of Lows in Uptrend)
        if prev_bar["ema_fast"] >= prev_bar["ema_slow"]:
            has_swept_low = prev_bar["low"] <= recent_low_wick
            lower_wick = min(prev_bar["open"], prev_bar["close"]) - prev_bar["low"]
            upper_wick = prev_bar["high"] - max(prev_bar["open"], prev_bar["close"])
            is_bullish = prev_bar["close"] >= prev_bar["open"]
            has_rejection = is_bullish or (lower_wick >= self.wick_ratio * upper_wick)

            if has_swept_low and has_rejection:
                if tick.ask >= prev_bar["high"] or curr_bar["high"] >= prev_bar["high"]:
                    entry = tick.ask
                    stop_loss = round(entry - price_move_for_sl, digits)
                    take_profit = round(entry + price_move_for_tp, digits)
                    logger.info(
                        f"[M1 SCALP] BUY @ {entry:.2f} | Candle: {c_time_str} | SL: {stop_loss:.2f} (-${self.max_sl_dollars:.2f}) | TP: {take_profit:.2f} (+${self.target_tp_dollars:.2f})"
                    )
                    return "BUY", entry, stop_loss, take_profit, f"M1_{c_time_str}"

        return None, 0.0, 0.0, 0.0, None
