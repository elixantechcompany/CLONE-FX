"""
Musumali Strategy Backtester & Historical Validator
Tests the exact 4-step Musumali logic on historical MT5 Gold data.
Generates comprehensive performance statistics, win rate, profit factor, and trade logs.
"""

import datetime
import logging
from typing import List
import MetaTrader5 as mt5
import pandas as pd
import yaml
from dotenv import load_dotenv

from src.connection import MT5Connector
from src.strategy import MusumaliStrategy


def run_backtest(
    symbol: str = "XAUUSDm",
    days_back: int = 90,
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

    # Check candidates if symbol not found
    candidates = [symbol] + config.get("symbols", {}).get("candidates", [])
    active_sym = connector.resolve_symbol(candidates)
    if not active_sym:
        logger.error("Could not find Gold symbol on MT5 terminal.")
        connector.shutdown()
        return

    strat = MusumaliStrategy(config)
    info = mt5.symbol_info(active_sym)
    point = info.point
    digits = info.digits

    logger.info("=" * 65)
    logger.info(f"   STARTING HISTORICAL BACKTEST: {active_sym}")
    logger.info(f"   Lookback Period: Last {days_back} Days | Exec Timeframe: {strat.exec_tf_str}")
    logger.info(f"   Target R:R: 1:{strat.risk_reward_ratio} | Risk per Trade: {config['risk_management'].get('risk_per_trade_percent', 1.0)}%")
    logger.info("=" * 65)

    # Fetch historical H1 bars
    total_h1_bars = days_back * 24
    rates_h1 = mt5.copy_rates_from_pos(active_sym, strat.exec_mt5_tf, 0, total_h1_bars)
    if rates_h1 is None or len(rates_h1) < 100:
        logger.error("Insufficient historical data returned from MT5.")
        connector.shutdown()
        return

    df_all_h1 = pd.DataFrame(rates_h1)
    df_all_h1["time"] = pd.to_datetime(df_all_h1["time"], unit="s")

    trades = []
    initial_balance = 10000.0
    balance = initial_balance
    equity_curve = [balance]

    # Walk forward bar-by-bar
    warmup = 100
    current_day = None
    daily_trades = 0
    max_daily_trades = config.get("risk_management", {}).get("max_daily_trades", 2)

    logger.info(f"Simulating across {len(df_all_h1) - warmup} historical candles...")

    for i in range(warmup, len(df_all_h1) - 1):
        bar = df_all_h1.iloc[i]
        bar_date = bar["time"].date()

        if bar_date != current_day:
            current_day = bar_date
            daily_trades = 0

        if daily_trades >= max_daily_trades:
            continue

        # Slice historical window up to bar i
        sub_df = df_all_h1.iloc[: i + 1].copy()

        # Step 1: Market Nature / Trend Bias
        trend = strat.get_market_trend_bias(active_sym)
        if trend not in ("UPTREND", "DOWNTREND"):
            continue

        # Step 2: Area of Benefit
        zone = strat.find_area_of_benefit(sub_df, trend)
        if zone is None:
            continue

        # Step 3 & 4: Liquidity Sweep & Musumali Candle
        musumali_idx, musumali_candle = strat.evaluate_musumali_candle(sub_df, zone, trend, point)
        if musumali_candle is None or musumali_idx is None:
            continue

        # Step 5: Entry Trigger check on subsequent bars (i+1 to i+break_timeout)
        sl_buffer = strat.sl_buffer_points * point

        if trend == "UPTREND":
            m_high = musumali_candle["high"]
            m_low = musumali_candle["low"]

            # Next bar test
            next_bar = df_all_h1.iloc[i + 1]
            if next_bar["high"] > m_high:
                entry = m_high + (1 * point)
                sl = round(m_low - sl_buffer, digits)
                risk = entry - sl
                if risk <= 0:
                    continue

                tp = round(entry + (risk * strat.risk_reward_ratio), digits)

                # Forward simulate outcome
                outcome, exit_time, exit_price = _simulate_trade_outcome(
                    df_all_h1, i + 1, "BUY", entry, sl, tp
                )

                risk_dollars = balance * 0.01
                profit_dollars = (
                    risk_dollars * strat.risk_reward_ratio if outcome == "WIN" else -risk_dollars
                )
                balance += profit_dollars
                daily_trades += 1

                trades.append({
                    "entry_time": next_bar["time"],
                    "type": "BUY",
                    "entry": entry,
                    "sl": sl,
                    "tp": tp,
                    "outcome": outcome,
                    "profit": profit_dollars,
                    "balance": balance,
                })

        elif trend == "DOWNTREND":
            m_high = musumali_candle["high"]
            m_low = musumali_candle["low"]

            next_bar = df_all_h1.iloc[i + 1]
            if next_bar["low"] < m_low:
                entry = m_low - (1 * point)
                sl = round(m_high + sl_buffer, digits)
                risk = sl - entry
                if risk <= 0:
                    continue

                tp = round(entry - (risk * strat.risk_reward_ratio), digits)

                outcome, exit_time, exit_price = _simulate_trade_outcome(
                    df_all_h1, i + 1, "SELL", entry, sl, tp
                )

                risk_dollars = balance * 0.01
                profit_dollars = (
                    risk_dollars * strat.risk_reward_ratio if outcome == "WIN" else -risk_dollars
                )
                balance += profit_dollars
                daily_trades += 1

                trades.append({
                    "entry_time": next_bar["time"],
                    "type": "SELL",
                    "entry": entry,
                    "sl": sl,
                    "tp": tp,
                    "outcome": outcome,
                    "profit": profit_dollars,
                    "balance": balance,
                })

    # Summary Statistics
    _print_backtest_results(trades, initial_balance, balance)
    connector.shutdown()


def _simulate_trade_outcome(df, start_idx, side, entry, sl, tp):
    """Walks forward through future bars to determine if TP or SL was hit first."""
    for j in range(start_idx, min(len(df), start_idx + 120)):
        bar = df.iloc[j]
        if side == "BUY":
            if bar["low"] <= sl:
                return "LOSS", bar["time"], sl
            if bar["high"] >= tp:
                return "WIN", bar["time"], tp
        elif side == "SELL":
            if bar["high"] >= sl:
                return "LOSS", bar["time"], sl
            if bar["low"] <= tp:
                return "WIN", bar["time"], tp
    return "OPEN", df.iloc[-1]["time"], entry


def _print_backtest_results(trades: list, initial_balance: float, final_balance: float):
    print("\n" + "=" * 65)
    print("                MUSUMALI STRATEGY BACKTEST RESULTS")
    print("=" * 65)

    if not trades:
        print("No valid setups triggered during this historical period.")
        return

    df_trades = pd.DataFrame(trades)
    total_trades = len(df_trades)
    wins = len(df_trades[df_trades["outcome"] == "WIN"])
    losses = len(df_trades[df_trades["outcome"] == "LOSS"])
    win_rate = (wins / total_trades) * 100.0 if total_trades > 0 else 0.0

    total_profit = df_trades["profit"].sum()
    gross_win = df_trades[df_trades["profit"] > 0]["profit"].sum()
    gross_loss = abs(df_trades[df_trades["profit"] < 0]["profit"].sum())
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else 99.9

    print(f"Total Completed Trades : {total_trades}")
    print(f"Wins / Losses          : {wins} W / {losses} L")
    print(f"Win Rate               : {win_rate:.2f}%")
    print(f"Profit Factor          : {profit_factor:.2f}")
    print(f"Starting Balance       : ${initial_balance:.2f}")
    print(f"Final Balance          : ${final_balance:.2f} ({((final_balance - initial_balance)/initial_balance)*100:+.2f}%)")
    print("=" * 65)
    print("\nSample Recent Trades:")
    print(df_trades.tail(10)[["entry_time", "type", "entry", "sl", "tp", "outcome", "profit"]].to_string(index=False))
    print("=" * 65 + "\n")


if __name__ == "__main__":
    run_backtest(days_back=60)
