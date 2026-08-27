"""
Live Market Scanner & Strategy Diagnostic
Shows exactly what the Musumali Bot sees on MT5 right now.
"""

import yaml
from dotenv import load_dotenv
import MetaTrader5 as mt5
from src.connection import MT5Connector
from src.strategy import MusumaliStrategy


def scan_live():
    print("=" * 65)
    print("        LIVE MUSUMALI STRATEGY MARKET DIAGNOSTIC")
    print("=" * 65)

    load_dotenv("config/.env")
    load_dotenv()

    with open("config/config.yaml", "r") as f:
        config = yaml.safe_load(f)

    connector = MT5Connector()
    if not connector.initialize():
        print("[ERROR] Cannot connect to MT5.")
        return

    sym = connector.resolve_symbol(config.get("symbols", {}).get("candidates", ["XAUUSDm"]))
    if not sym:
        print("[ERROR] Symbol not found.")
        connector.shutdown()
        return

    strategy = MusumaliStrategy(config)
    tick = mt5.symbol_info_tick(sym)

    print(f"\n[1] Current Market Price for {sym}:")
    print(f"    * Bid: {tick.bid:.2f} | Ask: {tick.ask:.2f} | Spread: {(tick.ask - tick.bid)*1000:.1f} pts")

    print(f"\n[2] Component 1: Daily Higher-Timeframe Trend Gate (D1):")
    trend, trend_reason = strategy.get_daily_market_trend(sym)
    print(f"    * Evaluated Daily Bias: {trend}")
    print(f"    * Reason: {trend_reason}")
    if trend == "RANGING":
        print("    -> Market is currently ranging/consolidating on Daily.")
        print("       Strategy Rule: Hard Gate Active (NO TRADES permitted to protect capital).")
    elif trend in ("UPTREND", "DOWNTREND"):
        print(f"    -> Trend is {trend}. Looking ONLY for {'BUY' if trend == 'UPTREND' else 'SELL'} setups.")

    print(f"\n[3] Component 2, 3 & 4: Multi-Timeframe Scan & Signal Check:")
    signal, entry, sl, tp, candle_id, zone_id, reason = strategy.generate_signal(sym)
    if signal:
        print(f"    >>> ACTIVE SIGNAL: {signal} @ {entry:.2f} | SL: {sl:.2f} | TP: {tp:.2f}")
        print(f"        Setup Reason: {reason}")
    else:
        print(f"    >>> Status: STANDBY / MONITORING ({reason})")

    print(f"\n[4] Component 5: 4-Stage Entry Filter Funnel Audit:")
    print(f"    - Zones (Area of Benefit) identified: {strategy.funnel.zones_identified}")
    print(f"    - Zones that got a liquidity sweep: {strategy.funnel.zones_swept}")
    print(f"    - Sweeps that produced a valid Musumali candle: {strategy.funnel.valid_musumali_candles}")
    print(f"    - Musumali candles that got a confirmed break (entry): {strategy.funnel.confirmed_break_entries}")

    print("\n" + "=" * 65)
    connector.shutdown()


if __name__ == "__main__":
    scan_live()

