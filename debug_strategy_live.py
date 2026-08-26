"""
Deep Strategy Diagnostic Script
Scans live MT5 Gold market for both SELL and BUY liquidity sweep setups.
"""

import yaml
from dotenv import load_dotenv
import MetaTrader5 as mt5
import pandas as pd
from src.connection import MT5Connector
from src.strategy import MusumaliStrategy


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
    info = connector.symbol_info
    tick = mt5.symbol_info_tick(sym)

    print("=" * 65)
    print(f"   LIVE BIDIRECTIONAL STRATEGY SCAN FOR {sym}")
    print(f"   Current Price: Ask={tick.ask:.2f}, Bid={tick.bid:.2f} | Spread={tick.ask - tick.bid:.2f}")
    print("=" * 65)

    # 1. Scan across timeframes (M15, M30, H1)
    for tf_name, tf in [("M15", mt5.TIMEFRAME_M15), ("M30", mt5.TIMEFRAME_M30), ("H1", mt5.TIMEFRAME_H1)]:
        df = strat.fetch_rates(sym, tf, count=60)
        if df is not None:
            zones = strat.find_all_recent_areas_of_benefit(df)
            sell_zones = [z for z in zones if z.zone_type == "SUPPLY"]
            buy_zones = [z for z in zones if z.zone_type == "DEMAND"]
            print(f"\n[{tf_name}] Active Zones Detected: {len(sell_zones)} SELL (Supply) | {len(buy_zones)} BUY (Demand)")
            if sell_zones:
                sz = sell_zones[0]
                print(f"    * Top SELL (Supply) Zone: {sz.zone_bottom:.2f} - {sz.zone_top:.2f} | Liquidity High: {sz.cluster_high_wick:.2f}")
            if buy_zones:
                bz = buy_zones[0]
                print(f"    * Top BUY (Demand) Zone:   {bz.zone_bottom:.2f} - {bz.zone_top:.2f} | Liquidity Low:  {bz.cluster_low_wick:.2f}")

    # 2. Check Signal Output
    signal, entry, sl, tp = strat.generate_signal(sym)
    print("\n" + "=" * 65)
    if signal:
        print(f">>> [TRIGGER ACTIVE] Signal: {signal} @ {entry:.2f}")
        print(f"    * Stop Loss:   {sl:.2f} (Hard Capped to -$1.00 max risk)")
        print(f"    * Take Profit: {tp:.2f} (Target +$2.00 profit)")
    else:
        print(">>> Scanner Status: Actively watching live ticks for both SELL & BUY triggers.")
    print("=" * 65)

    connector.shutdown()


if __name__ == "__main__":
    debug()
