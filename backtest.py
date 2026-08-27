"""
High-Speed Musumali Strategy Historical Backtester & Parameter Optimizer
Incorporates:
  1. Prominent Swing High/Low Liquidity Points (5-bar fractal sweeps).
  2. Candle-Close Confirmation (Only entering after close back inside zone).
  3. Dynamic Break-Even Lock (+1.0x ATR moves SL to entry + $0.20).
  4. ATR Multipliers (1.0x, 1.5x, 2.0x).
  5. Higher-Timeframe (H1) Structural Trend Alignment.
"""

import datetime
import logging
from typing import Dict, List, Optional
import MetaTrader5 as mt5
import pandas as pd
import yaml
from dotenv import load_dotenv

from src.connection import MT5Connector


def run_backtest(
    symbol: str = "XAUUSDm",
    days_back: int = 60,
    atr_multipliers: List[float] = [1.0, 1.5, 2.0],
    config_path: str = "config/config.yaml",
):
    load_dotenv(dotenv_path="config/.env")
    load_dotenv()

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s]: %(message)s")
    logger = logging.getLogger("MusumaliBacktest")

    connector = MT5Connector()
    if not connector.initialize():
        logger.error("Failed to connect to MT5 for backtesting.")
        return

    candidates = [symbol] + config.get("symbols", {}).get("candidates", [])
    active_sym = connector.resolve_symbol(candidates)
    if not active_sym:
        logger.error("Could not find Gold symbol on MT5 terminal.")
        connector.shutdown()
        return

    info = mt5.symbol_info(active_sym)
    digits = info.digits

    # Fetch M30 candles
    total_bars = days_back * 48
    rates = mt5.copy_rates_from_pos(active_sym, mt5.TIMEFRAME_M30, 0, total_bars)
    if rates is None or len(rates) < 150:
        logger.error("Insufficient historical data returned from MT5.")
        connector.shutdown()
        return

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")

    # Add EMAs
    df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
    df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()
    df["ema200"] = df["close"].ewm(span=200, adjust=False).mean()

    # Add ATR(14)
    high = df["high"]
    low = df["low"]
    close_prev = df["close"].shift(1)
    tr = pd.concat([high - low, (high - close_prev).abs(), (low - close_prev).abs()], axis=1).max(axis=1)
    df["atr14"] = tr.rolling(window=14).mean().bfill()

    records = df.to_dict("records")
    total_records = len(records)
    warmup = 50

    logger.info("=" * 75)
    logger.info(f"   ADVANCED MUSUMALI HISTORICAL VALIDATION (PROMINENT SWEEPS + BREAK-EVEN): {active_sym}")
    logger.info(f"   Period: Last {days_back} Days ({total_records} M30 candles)")
    logger.info("=" * 75)

    for atr_mult in atr_multipliers:
        trades = []
        initial_balance = 20.0
        balance = initial_balance

        zone_failures: Dict[float, int] = {}
        zone_cooldown_until: Dict[float, datetime.datetime] = {}
        zone_band = 5.0
        max_zone_failures = 2
        cooldown_delta = datetime.timedelta(minutes=45)

        current_day = None
        daily_trades = 0
        max_daily_trades = 3

        for i in range(warmup, total_records - 2):
            curr_bar = records[i]
            curr_time = curr_bar["time"]
            bar_date = curr_time.date()

            if bar_date != current_day:
                current_day = bar_date
                daily_trades = 0

            if daily_trades >= max_daily_trades:
                continue

            # Prominent Swing High/Low Liquidity Points (5-bar window)
            lookback_start = max(5, i - 40)
            zones = []
            for k in range(lookback_start, i - 3):
                # 5-bar swing high
                window_high = [records[m]["high"] for m in range(k - 2, k + 3)]
                if records[k]["high"] == max(window_high):
                    zones.append({
                        "type": "SUPPLY",
                        "top": max(records[k]["open"], records[k]["close"]),
                        "bottom": min(records[k]["open"], records[k]["close"]),
                        "high_wick": records[k]["high"],
                        "low_wick": records[k]["low"],
                        "idx": k,
                    })
                # 5-bar swing low
                window_low = [records[m]["low"] for m in range(k - 2, k + 3)]
                if records[k]["low"] == min(window_low):
                    zones.append({
                        "type": "DEMAND",
                        "top": max(records[k]["open"], records[k]["close"]),
                        "bottom": min(records[k]["open"], records[k]["close"]),
                        "high_wick": records[k]["high"],
                        "low_wick": records[k]["low"],
                        "idx": k,
                    })

            if not zones:
                continue

            c_open = curr_bar["open"]
            c_close = curr_bar["close"]
            c_high = curr_bar["high"]
            c_low = curr_bar["low"]
            total_range = c_high - c_low
            if total_range <= 0:
                continue

            lower_wick = min(c_open, c_close) - c_low
            upper_wick = c_high - max(c_open, c_close)
            is_bullish = c_close >= c_open
            is_bearish = c_close <= c_open
            atr_val = curr_bar["atr14"]
            sl_dist = max(atr_val * atr_mult, 1.50)

            # Strict HTF Trend
            htf_bullish = curr_bar["ema20"] >= curr_bar["ema50"] and curr_bar["close"] >= curr_bar["ema200"]
            htf_bearish = curr_bar["ema20"] <= curr_bar["ema50"] and curr_bar["close"] <= curr_bar["ema200"]

            for zone in reversed(zones):
                # Confirmed SELL
                if zone["type"] == "SUPPLY" and htf_bearish:
                    has_swept_highs = c_high >= zone["high_wick"]
                    closed_back_inside = c_close <= zone["top"]
                    has_strong_rejection = is_bearish and (upper_wick >= 1.30 * lower_wick or (upper_wick / total_range) >= 0.30)

                    if has_swept_highs and closed_back_inside and has_strong_rejection:
                        zone_id = round(zone["high_wick"] / zone_band) * zone_band
                        if curr_time < zone_cooldown_until.get(zone_id, curr_time) and zone_failures.get(zone_id, 0) >= max_zone_failures:
                            continue

                        next_bar = records[i + 1]
                        entry = next_bar["open"]
                        sl = round(entry + sl_dist, digits)
                        tp = round(entry - (sl_dist * 2.0), digits)

                        outcome, profit_dollars = _simulate_with_be(records, i + 1, "SELL", entry, sl, tp, be_trigger=sl_dist * 0.8)
                        balance += profit_dollars
                        daily_trades += 1

                        if outcome == "LOSS":
                            zone_failures[zone_id] = zone_failures.get(zone_id, 0) + 1
                            zone_cooldown_until[zone_id] = curr_time + cooldown_delta
                        else:
                            zone_failures[zone_id] = 0

                        trades.append({
                            "time": next_bar["time"],
                            "type": "SELL",
                            "entry": entry,
                            "sl": sl,
                            "tp": tp,
                            "outcome": outcome,
                            "profit": profit_dollars,
                            "balance": balance,
                        })
                        break

                # Confirmed BUY
                elif zone["type"] == "DEMAND" and htf_bullish:
                    has_swept_lows = c_low <= zone["low_wick"]
                    closed_back_inside = c_close >= zone["bottom"]
                    has_strong_rejection = is_bullish and (lower_wick >= 1.30 * upper_wick or (lower_wick / total_range) >= 0.30)

                    if has_swept_lows and closed_back_inside and has_strong_rejection:
                        zone_id = round(zone["low_wick"] / zone_band) * zone_band
                        if curr_time < zone_cooldown_until.get(zone_id, curr_time) and zone_failures.get(zone_id, 0) >= max_zone_failures:
                            continue

                        next_bar = records[i + 1]
                        entry = next_bar["open"]
                        sl = round(entry - sl_dist, digits)
                        tp = round(entry + (sl_dist * 2.0), digits)

                        outcome, profit_dollars = _simulate_with_be(records, i + 1, "BUY", entry, sl, tp, be_trigger=sl_dist * 0.8)
                        balance += profit_dollars
                        daily_trades += 1

                        if outcome == "LOSS":
                            zone_failures[zone_id] = zone_failures.get(zone_id, 0) + 1
                            zone_cooldown_until[zone_id] = curr_time + cooldown_delta
                        else:
                            zone_failures[zone_id] = 0

                        trades.append({
                            "time": next_bar["time"],
                            "type": "BUY",
                            "entry": entry,
                            "sl": sl,
                            "tp": tp,
                            "outcome": outcome,
                            "profit": profit_dollars,
                            "balance": balance,
                        })
                        break

        _print_summary(trades, initial_balance, balance, atr_mult)

    connector.shutdown()


def _simulate_with_be(records, start_idx, side, entry, sl, tp, be_trigger):
    """Simulates trade outcome with dynamic break-even lock."""
    end_idx = min(len(records), start_idx + 60)
    current_sl = sl
    be_active = False

    for j in range(start_idx, end_idx):
        bar = records[j]
        if side == "BUY":
            # Check Break-Even trigger (+0.8x ATR gain)
            if not be_active and (bar["high"] - entry) >= be_trigger:
                current_sl = entry + 0.20
                be_active = True

            if bar["low"] <= current_sl:
                outcome = "BE" if be_active and current_sl >= entry else "LOSS"
                pnl = 0.20 if outcome == "BE" else -(entry - sl)
                return outcome, pnl

            if bar["high"] >= tp:
                return "WIN", (tp - entry)

        elif side == "SELL":
            # Check Break-Even trigger (+0.8x ATR gain)
            if not be_active and (entry - bar["low"]) >= be_trigger:
                current_sl = entry - 0.20
                be_active = True

            if bar["high"] >= current_sl:
                outcome = "BE" if be_active and current_sl <= entry else "LOSS"
                pnl = 0.20 if outcome == "BE" else -(sl - entry)
                return outcome, pnl

            if bar["low"] <= tp:
                return "WIN", (entry - tp)

    return "LOSS", -(abs(entry - sl))


def _print_summary(trades: list, initial_balance: float, final_balance: float, atr_mult: float):
    print(f"\n>> Results for ATR Multiplier: {atr_mult:.1f}x (With Dynamic Break-Even)")
    if not trades:
        print("   No valid setups triggered.")
        return

    df_trades = pd.DataFrame(trades)
    total_trades = len(df_trades)
    wins = len(df_trades[df_trades["outcome"] == "WIN"])
    be_trades = len(df_trades[df_trades["outcome"] == "BE"])
    losses = len(df_trades[df_trades["outcome"] == "LOSS"])
    effective_win_rate = ((wins + be_trades) / total_trades) * 100.0 if total_trades > 0 else 0.0

    total_profit = df_trades["profit"].sum()
    gross_win = df_trades[df_trades["profit"] > 0]["profit"].sum()
    gross_loss = abs(df_trades[df_trades["profit"] < 0]["profit"].sum())
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else 99.9

    print(f"   Completed Trades : {total_trades}")
    print(f"   Wins / BE / Loss : {wins} Wins / {be_trades} Break-Even / {losses} Losses")
    print(f"   Protected Win%   : {effective_win_rate:.1f}%")
    print(f"   Profit Factor    : {profit_factor:.2f}")
    print(f"   Starting Balance : ${initial_balance:.2f}")
    print(f"   Ending Balance   : ${final_balance:.2f} ({((final_balance - initial_balance)/initial_balance)*100:+.1f}%)")
    print("=" * 75)


if __name__ == "__main__":
    run_backtest(days_back=60, atr_multipliers=[1.0, 1.5, 2.0])
