"""
A/B Backtesting Benchmark Suite: Legacy Exits vs. Intelligent Position Management Engine
Compares:
  - Strategy A: Legacy Exits (Fixed $0.80 giveback, fixed $0.20 moves, blind holding)
  - Strategy B: Intelligent Position Management Engine (6 Position States, R-Multiples,
                Reversal Confidence Score 0-100, Dynamic Giveback, Stale Trade Timeout,
                Thesis Invalidation, Volatility-Aware ATR Trailing)
"""

import os
import yaml
import numpy as np
import pandas as pd
import MetaTrader5 as mt5

from src.position_manager import IntelligentExitEngine, PositionState, ExitDecision


class MockLiveTick:
    def __init__(self, bid: float, ask: float):
        self.bid = bid
        self.ask = ask


def run_ab_backtest(symbol="XAUUSDm", bars_count=5000):
    print("=" * 80)
    print(f"  RUNNING A/B BENCHMARK BACKTEST: Strategy A (Legacy) vs Strategy B (Intelligent)")
    print(f"  Symbol: {symbol} | Sample Size: {bars_count} M1 Bars")
    print("=" * 80)

    # Initialize MT5
    if not mt5.initialize():
        print("MT5 initialization failed. Generating synthetic market data for backtest...")
        # Fallback to realistic synthetic XAUUSD M1 data
        times = pd.date_range("2026-08-01", periods=bars_count, freq="1min")
        np.random.seed(42)
        returns = np.random.normal(0, 0.4, bars_count)
        # Add random walk drift and regime shifts
        prices = 2650.0 + np.cumsum(returns)
        rates_data = []
        for i in range(bars_count):
            p = prices[i]
            rates_data.append({
                "time": int(times[i].timestamp()),
                "open": p,
                "high": p + abs(np.random.normal(0, 0.5)),
                "low": p - abs(np.random.normal(0, 0.5)),
                "close": p + np.random.normal(0, 0.3),
                "tick_volume": int(np.random.randint(50, 500)),
            })
        df_m1 = pd.DataFrame(rates_data)
    else:
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, bars_count)
        if rates is None or len(rates) == 0:
            print("Failed to fetch M1 rates from MT5, using fallback data.")
            return
        df_m1 = pd.DataFrame(rates)

    # Load configuration
    with open("config/config.yaml", "r") as f:
        config = yaml.safe_load(f)

    exit_engine = IntelligentExitEngine(config)

    # Simple M1 breakout/pullback entry generator for simulation
    # Identifies signals: EMA 9 crosses EMA 21 with RSI filter
    df_m1["ema9"] = df_m1["close"].ewm(span=9, adjust=False).mean()
    df_m1["ema21"] = df_m1["close"].ewm(span=21, adjust=False).mean()
    
    # Calculate M1 ATR
    tr = pd.concat([
        df_m1["high"] - df_m1["low"],
        abs(df_m1["high"] - df_m1["close"].shift(1)),
        abs(df_m1["low"] - df_m1["close"].shift(1))
    ], axis=1).max(axis=1)
    df_m1["atr"] = tr.rolling(14).mean().fillna(1.50)

    signals = []
    for i in range(50, len(df_m1) - 60):
        row = df_m1.iloc[i]
        prev_row = df_m1.iloc[i-1]
        
        # Bullish signal
        if prev_row["ema9"] <= prev_row["ema21"] and row["ema9"] > row["ema21"]:
            signals.append({
                "bar_idx": i,
                "time": row["time"],
                "type": "BUY",
                "entry_price": row["close"],
                "sl": round(row["close"] - max(row["atr"] * 1.5, 2.0), 2),
                "tp": round(row["close"] + max(row["atr"] * 3.0, 4.0), 2),
                "atr": row["atr"],
            })
        # Bearish signal
        elif prev_row["ema9"] >= prev_row["ema21"] and row["ema9"] < row["ema21"]:
            signals.append({
                "bar_idx": i,
                "time": row["time"],
                "type": "SELL",
                "entry_price": row["close"],
                "sl": round(row["close"] + max(row["atr"] * 1.5, 2.0), 2),
                "tp": round(row["close"] - max(row["atr"] * 3.0, 4.0), 2),
                "atr": row["atr"],
            })

    print(f"Generated {len(signals)} entry signals across {len(df_m1)} bars for simulation.")

    # -------------------------------------------------------------
    # SIMULATION: STRATEGY A (Legacy Fixed Exits)
    # -------------------------------------------------------------
    strat_a_trades = []
    for sig in signals:
        idx = sig["bar_idx"]
        p_type = sig["type"]
        entry = sig["entry_price"]
        sl = sig["sl"]
        tp = sig["tp"]
        risk_dist = abs(entry - sl)
        initial_risk = risk_dist * 0.01 * 100.0 # 0.01 lot = $1 per dollar price
        peak_profit = 0.0
        closed = False

        for future_idx in range(idx + 1, min(idx + 120, len(df_m1))):
            bar = df_m1.iloc[future_idx]
            high = bar["high"]
            low = bar["low"]
            close = bar["close"]

            if p_type == "BUY":
                curr_profit = (close - entry) * 1.0
                bar_max_p = (high - entry) * 1.0
                bar_min_p = (low - entry) * 1.0
                peak_profit = max(peak_profit, bar_max_p)

                # TP Hit
                if high >= tp:
                    pnl = (tp - entry) * 1.0
                    strat_a_trades.append({"pnl": pnl, "r": pnl / initial_risk, "peak_r": peak_profit / initial_risk, "reason": "TP_HIT"})
                    closed = True
                    break
                # SL Hit
                elif low <= sl:
                    pnl = (sl - entry) * 1.0
                    strat_a_trades.append({"pnl": pnl, "r": pnl / initial_risk, "peak_r": peak_profit / initial_risk, "reason": "SL_HIT"})
                    closed = True
                    break
                # Legacy Giveback Cap ($0.80 peak, 40% giveback)
                elif peak_profit >= 0.80 and curr_profit <= peak_profit * 0.60:
                    strat_a_trades.append({"pnl": curr_profit, "r": curr_profit / initial_risk, "peak_r": peak_profit / initial_risk, "reason": "LEGACY_GIVEBACK"})
                    closed = True
                    break

            elif p_type == "SELL":
                curr_profit = (entry - close) * 1.0
                bar_max_p = (entry - low) * 1.0
                bar_min_p = (entry - high) * 1.0
                peak_profit = max(peak_profit, bar_max_p)

                # TP Hit
                if low <= tp:
                    pnl = (entry - tp) * 1.0
                    strat_a_trades.append({"pnl": pnl, "r": pnl / initial_risk, "peak_r": peak_profit / initial_risk, "reason": "TP_HIT"})
                    closed = True
                    break
                # SL Hit
                elif high >= sl:
                    pnl = (entry - sl) * 1.0
                    strat_a_trades.append({"pnl": pnl, "r": pnl / initial_risk, "peak_r": peak_profit / initial_risk, "reason": "SL_HIT"})
                    closed = True
                    break
                # Legacy Giveback Cap
                elif peak_profit >= 0.80 and curr_profit <= peak_profit * 0.60:
                    strat_a_trades.append({"pnl": curr_profit, "r": curr_profit / initial_risk, "peak_r": peak_profit / initial_risk, "reason": "LEGACY_GIVEBACK"})
                    closed = True
                    break

        if not closed:
            final_pnl = (df_m1.iloc[min(idx+120, len(df_m1)-1)]["close"] - entry) * (1.0 if p_type == "BUY" else -1.0)
            strat_a_trades.append({"pnl": final_pnl, "r": final_pnl / initial_risk, "peak_r": peak_profit / initial_risk, "reason": "END_OF_DATA"})

    # -------------------------------------------------------------
    # SIMULATION: STRATEGY B (Intelligent Exit Engine)
    # -------------------------------------------------------------
    strat_b_trades = []
    strat_b_reasons = {}

    for t_idx, sig in enumerate(signals):
        idx = sig["bar_idx"]
        p_type = sig["type"]
        entry = sig["entry_price"]
        orig_sl = sig["sl"]
        orig_tp = sig["tp"]
        ticket = 20000 + t_idx
        risk_dist = abs(entry - orig_sl)
        initial_risk = risk_dist * 0.01 * 100.0

        exit_engine.register_position(
            ticket=ticket,
            symbol=symbol,
            pos_type=p_type,
            volume=0.01,
            open_price=entry,
            sl=orig_sl,
            tp=orig_tp,
            magic=1001,
        )

        curr_sl = orig_sl
        curr_tp = orig_tp
        closed = False

        for future_idx in range(idx + 1, min(idx + 120, len(df_m1))):
            bar = df_m1.iloc[future_idx]
            high = bar["high"]
            low = bar["low"]
            close = bar["close"]
            live_price = close
            pnl = (live_price - entry) * (1.0 if p_type == "BUY" else -1.0)

            # Broker SL / TP checks
            if p_type == "BUY":
                if high >= curr_tp:
                    rec = exit_engine.records.get(ticket)
                    strat_b_trades.append({"pnl": (curr_tp - entry) * 1.0, "r": ((curr_tp - entry) * 1.0) / initial_risk, "peak_r": rec.peak_r if rec else 0.0, "reason": "TP_HIT"})
                    strat_b_reasons["TP_HIT"] = strat_b_reasons.get("TP_HIT", 0) + 1
                    closed = True
                    break
                elif low <= curr_sl:
                    rec = exit_engine.records.get(ticket)
                    strat_b_trades.append({"pnl": (curr_sl - entry) * 1.0, "r": ((curr_sl - entry) * 1.0) / initial_risk, "peak_r": rec.peak_r if rec else 0.0, "reason": "SL_HIT"})
                    strat_b_reasons["SL_HIT"] = strat_b_reasons.get("SL_HIT", 0) + 1
                    closed = True
                    break
            elif p_type == "SELL":
                if low <= curr_tp:
                    rec = exit_engine.records.get(ticket)
                    strat_b_trades.append({"pnl": (entry - curr_tp) * 1.0, "r": ((entry - curr_tp) * 1.0) / initial_risk, "peak_r": rec.peak_r if rec else 0.0, "reason": "TP_HIT"})
                    strat_b_reasons["TP_HIT"] = strat_b_reasons.get("TP_HIT", 0) + 1
                    closed = True
                    break
                elif high >= curr_sl:
                    rec = exit_engine.records.get(ticket)
                    strat_b_trades.append({"pnl": (entry - curr_sl) * 1.0, "r": ((entry - curr_sl) * 1.0) / initial_risk, "peak_r": rec.peak_r if rec else 0.0, "reason": "SL_HIT"})
                    strat_b_reasons["SL_HIT"] = strat_b_reasons.get("SL_HIT", 0) + 1
                    closed = True
                    break

            # Sliced M1 window for indicator evaluation
            sub_df_m1 = df_m1.iloc[max(0, future_idx - 25):future_idx + 1].copy()
            live_tick = MockLiveTick(bid=live_price, ask=live_price + 0.25)
            pos_dict = {
                "ticket": ticket,
                "symbol": symbol,
                "type": p_type,
                "volume": 0.01,
                "price_open": entry,
                "price_current": live_price,
                "sl": curr_sl,
                "tp": curr_tp,
                "profit": pnl,
                "magic": 1001,
            }

            decision, new_sl, reason = exit_engine.evaluate_position_lifecycle(
                pos_dict=pos_dict,
                df_m1=sub_df_m1,
                df_m5=None,
                df_m15=None,
                live_tick=live_tick,
                live_atr=sig["atr"],
                digits=2,
            )

            if decision == ExitDecision.CLOSE_MARKET:
                rec = exit_engine.records.get(ticket)
                clean_reason = reason.split()[0] if reason else "MARKET_CLOSE"
                strat_b_trades.append({"pnl": pnl, "r": pnl / initial_risk, "peak_r": rec.peak_r if rec else 0.0, "reason": clean_reason})
                strat_b_reasons[clean_reason] = strat_b_reasons.get(clean_reason, 0) + 1
                closed = True
                break
            elif decision in (ExitDecision.LOCK_BREAKEVEN, ExitDecision.TIGHTEN_PROTECTION, ExitDecision.TRAIL_ATR):
                if new_sl is not None:
                    curr_sl = new_sl

        if not closed:
            rec = exit_engine.records.get(ticket)
            final_pnl = (df_m1.iloc[min(idx+120, len(df_m1)-1)]["close"] - entry) * (1.0 if p_type == "BUY" else -1.0)
            strat_b_trades.append({"pnl": final_pnl, "r": final_pnl / initial_risk, "peak_r": rec.peak_r if rec else 0.0, "reason": "END_OF_DATA"})

        exit_engine.records.pop(ticket, None)

    # -------------------------------------------------------------
    # CALCULATE PERFORMANCE BENCHMARK METRICS
    # -------------------------------------------------------------
    df_a = pd.DataFrame(strat_a_trades)
    df_b = pd.DataFrame(strat_b_trades)

    def calc_metrics(df):
        total_trades = len(df)
        wins = df[df["pnl"] > 0]
        losses = df[df["pnl"] <= 0]
        win_rate = (len(wins) / total_trades * 100.0) if total_trades > 0 else 0.0
        avg_win_dol = wins["pnl"].mean() if len(wins) > 0 else 0.0
        avg_win_r = wins["r"].mean() if len(wins) > 0 else 0.0
        avg_loss_dol = losses["pnl"].mean() if len(losses) > 0 else 0.0
        avg_loss_r = losses["r"].mean() if len(losses) > 0 else 0.0
        tot_profit = wins["pnl"].sum() if len(wins) > 0 else 0.0
        tot_loss = abs(losses["pnl"].sum()) if len(losses) > 0 else 0.0
        profit_factor = (tot_profit / tot_loss) if tot_loss > 0 else 999.0
        net_profit = df["pnl"].sum()
        
        # Max Drawdown
        cum_pnl = df["pnl"].cumsum()
        peak = cum_pnl.cummax()
        drawdown = peak - cum_pnl
        max_dd = drawdown.max() if len(drawdown) > 0 else 0.0

        # Profit Capture Efficiency
        pos_peaks = df[df["peak_r"] > 0]
        eff_pct = (pos_peaks["r"].clip(lower=0).sum() / pos_peaks["peak_r"].sum() * 100.0) if len(pos_peaks) > 0 and pos_peaks["peak_r"].sum() > 0 else 0.0

        return {
            "total_trades": total_trades,
            "win_rate": win_rate,
            "avg_win_dol": avg_win_dol,
            "avg_win_r": avg_win_r,
            "avg_loss_dol": avg_loss_dol,
            "avg_loss_r": avg_loss_r,
            "profit_factor": profit_factor,
            "net_profit": net_profit,
            "max_dd": max_dd,
            "capture_eff": eff_pct,
        }

    mA = calc_metrics(df_a)
    mB = calc_metrics(df_b)

    # -------------------------------------------------------------
    # PRINT COMPARISON REPORT TABLE
    # -------------------------------------------------------------
    print("\n" + "=" * 80)
    print("           A/B COMPARATIVE BACKTEST PERFORMANCE BENCHMARK")
    print("=" * 80)
    print(f"{'Metric':<35} | {'Strategy A (Legacy)':<18} | {'Strategy B (Intelligent)':<22} | {'Delta':<10}")
    print("-" * 90)
    print(f"{'Total Trades Executed':<35} | {mA['total_trades']:<18} | {mB['total_trades']:<22} | {mB['total_trades'] - mA['total_trades']:+d}")
    print(f"{'Win Rate %':<35} | {mA['win_rate']:>17.1f}% | {mB['win_rate']:>21.1f}% | {mB['win_rate'] - mA['win_rate']:+5.1f}%")
    print(f"{'Average Win ($ / R)':<35} | ${mA['avg_win_dol']:>5.2f} ({mA['avg_win_r']:>4.2f}R)  | ${mB['avg_win_dol']:>5.2f} ({mB['avg_win_r']:>4.2f}R)       | {mB['avg_win_r'] - mA['avg_win_r']:+5.2f}R")
    print(f"{'Average Loss ($ / R)':<35} | ${mA['avg_loss_dol']:>5.2f} ({mA['avg_loss_r']:>4.2f}R)  | ${mB['avg_loss_dol']:>5.2f} ({mB['avg_loss_r']:>4.2f}R)       | {mB['avg_loss_r'] - mA['avg_loss_r']:+5.2f}R")
    print(f"{'Profit Factor':<35} | {mA['profit_factor']:>18.2f} | {mB['profit_factor']:>22.2f} | {mB['profit_factor'] - mA['profit_factor']:+5.2f}")
    print(f"{'Net Profit ($)':<35} | ${mA['net_profit']:>17.2f} | ${mB['net_profit']:>21.2f} | ${mB['net_profit'] - mA['net_profit']:+6.2f}")
    print(f"{'Max Peak Drawdown ($)':<35} | ${mA['max_dd']:>17.2f} | ${mB['max_dd']:>21.2f} | ${mB['max_dd'] - mA['max_dd']:+6.2f}")
    print(f"{'Profit Capture Efficiency %':<35} | {mA['capture_eff']:>17.1f}% | {mB['capture_eff']:>21.1f}% | {mB['capture_eff'] - mA['capture_eff']:+5.1f}%")
    print("-" * 90)
    print("\n[STRATEGY B EXIT REASON BREAKDOWN]")
    for r_key, r_count in strat_b_reasons.items():
        pct = (r_count / mB["total_trades"] * 100.0) if mB["total_trades"] > 0 else 0.0
        print(f"  - {r_key:<30}: {r_count:>3} trades ({pct:>5.1f}%)")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    run_ab_backtest()
