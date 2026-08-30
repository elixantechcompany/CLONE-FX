"""
Deep Strategy Diagnostic Script
Scans live MT5 Gold market for confirmed Musumali sweeps, HTF bias, ATR stop loss, and zone diagnostics.
"""

import yaml
from dotenv import load_dotenv
import MetaTrader5 as mt5
import pandas as pd
from src.connection import MT5Connector
from src.strategy import MusumaliStrategy
from src.risk_manager import RiskManager


def debug():
    load_dotenv("config/.env")
    load_dotenv()

    with open("config/config.yaml", "r") as f:
        config = yaml.safe_load(f)

    connector = MT5Connector()
    if not connector.initialize():
        print("[FAIL] Cannot connect to MT5.")
        return

    sym = connector.resolve_symbol(config.get("symbols", {}).get("candidates", ["XAUUSDm"]))
    if not sym:
        print("[FAIL] Gold symbol not found.")
        connector.shutdown()
        return

    strat = MusumaliStrategy(config)
    risk_mgr = RiskManager(config, connector)
    tick = mt5.symbol_info_tick(sym)

    print("=" * 70)
    print(f"   LIVE BIDIRECTIONAL STRATEGY DIAGNOSTIC FOR {sym}")
    print(f"   Current Price: Ask={tick.ask:.2f}, Bid={tick.bid:.2f} | Spread={(tick.ask - tick.bid)*1000:.1f} pts")
    print("=" * 70)

    # 1. HTF Structural Bias
    htf_bias, htf_reason = strat.get_htf_structural_bias(sym)
    print(f"\n>>> [PRIORITY 5] H1 Structural Bias: {htf_bias}")
    print(f"    Details: {htf_reason}")

    # 2. Dynamic ATR Sizing across timeframes
    print(f"\n>>> [PRIORITY 2] ATR(14) Volatility Profile:")
    for tf_name, tf in [("M5", mt5.TIMEFRAME_M5), ("M15", mt5.TIMEFRAME_M15), ("M30", mt5.TIMEFRAME_M30), ("H1", mt5.TIMEFRAME_H1)]:
        df = strat.fetch_rates(sym, tf, count=60)
        if df is not None:
            atr = strat.calculate_atr(df, period=14)
            sl_dist = max(min(atr * strat.atr_sl_multiplier, strat.max_sl_distance), strat.min_sl_distance)
            tp_dist = sl_dist * strat.risk_reward_ratio
            print(f"    * {tf_name}: ATR(14) = ${atr:.2f} | SL Distance (1.2x) = ${sl_dist:.2f} | TP Target (1:2) = ${tp_dist:.2f}")

    # 3. Generate Signal Output
    sig, entry, sl, tp, candle_id, zone_id, score, reason = strat.generate_signal(sym)
    print("\n" + "=" * 70)
    if sig:
        print(f">>> [CONFIRMED SIGNAL TRIGGERED]")
        print(f"    * Side:        {sig}")
        print(f"    * Entry Price: {entry:.2f}")
        print(f"    * Stop Loss:   {sl:.2f} (-${abs(entry - sl):.2f})")
        print(f"    * Take Profit: {tp:.2f} (+${abs(tp - entry):.2f})")
        print(f"    * Zone ID:     {zone_id}")
        print(f"    * Reason:      {reason}")
    else:
        print(f">>> [SCANNER STATUS] No confirmed sweep reclaims on current tick.")
        print(f"    Filter State: Monitoring market across M5/M15/M30/H1.")
    print("=" * 70)

    connector.shutdown()


if __name__ == "__main__":
    debug()

