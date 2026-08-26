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
    print(f"    * Bid: {tick.bid:.2f} | Ask: {tick.ask:.2f} | Spread: {tick.ask - tick.bid:.2f}")

    print(f"\n[2] Component 1: Higher Timeframe Bias ({strategy.trend_tf_str}):")
    trend = strategy.get_market_trend_bias(sym)
    print(f"    * Evaluated Daily Bias: {trend}")
    if trend == "RANGING":
        print("    -> Market is currently ranging/consolidating on Daily.")
        print("       Strategy Rule: Filter active (No trade to protect capital from whipsaws).")
    elif trend in ("UPTREND", "DOWNTREND"):
        print(f"    -> Trend is {trend}. Looking only for {'BUY' if trend == 'UPTREND' else 'SELL'} setups.")

    print(f"\n[3] Component 2 & 3: Area of Benefit & Liquidity Sweep ({strategy.exec_tf_str}):")
    df_h1 = strategy.fetch_rates(sym, strategy.exec_mt5_tf, count=100)
    if df_h1 is not None and len(df_h1) > 0:
        zone = strategy.find_area_of_benefit(df_h1, trend)
        if zone:
            print(f"    * Area of Benefit Zone: {zone.zone_bottom:.2f} - {zone.zone_top:.2f}")
            print(f"    * Liquidity Peak Wick:  {zone.cluster_low_wick:.2f} (Low) / {zone.cluster_high_wick:.2f} (High)")
            
            # Check sweep
            info = connector.symbol_info
            idx, musumali_candle = strategy.evaluate_musumali_candle(df_h1, zone, trend, info.point)
            if musumali_candle is not None:
                print(f"    * Musumali Signal Candle: [DETECTED] at {musumali_candle['time']}")
                print(f"      High: {musumali_candle['high']:.2f}, Low: {musumali_candle['low']:.2f}")
            else:
                print("    * Musumali Signal Candle: [WAITING] Price has not swept liquidity and rejected yet.")
        else:
            print("    * No qualifying reaction cluster currently within range.")

    print("\n[4] Signal Check:")
    signal, entry, sl, tp = strategy.generate_signal(sym)
    if signal:
        print(f"    >>> ACTIVE SIGNAL: {signal} @ {entry:.2f} | SL: {sl:.2f} | TP: {tp:.2f}")
    else:
        print("    >>> Status: STANDBY / MONITORING (Bot is actively waiting for a valid setup to trigger).")

    print("\n" + "=" * 65)
    connector.shutdown()


if __name__ == "__main__":
    scan_live()
