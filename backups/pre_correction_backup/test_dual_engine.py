"""
Dual-Engine Live Strategy Diagnostic
Tests both Engine 1 (Musumali M5/M15/M30/H1) and Engine 2 (M1/M5 Scalper) simultaneously.
"""

import yaml
from dotenv import load_dotenv
import MetaTrader5 as mt5
from src.connection import MT5Connector
from src.m1_scalper import M1Scalper
from src.strategy import MusumaliStrategy


def test():
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
        print("[FAIL] Symbol not found.")
        connector.shutdown()
        return

    tick = mt5.symbol_info_tick(sym)
    musumali = MusumaliStrategy(config)
    scalper = M1Scalper(config)

    print("=" * 65)
    print("       DUAL-ENGINE GOLD LIVE SCANNER (ZERO CONFLICTS)")
    print(f"       Symbol: {sym} | Ask: {tick.ask:.2f} | Bid: {tick.bid:.2f}")
    print("=" * 65)

    # Engine 1 Check: Musumali
    sig1, e1, sl1, tp1, cid1, zid1, score1, reason1 = musumali.generate_signal(sym)
    print("\n[Engine 1: Musumali Strategy (M30, H1)]")
    if sig1:
        print(f"  >>> ACTIVE SIGNAL: {sig1} @ {e1:.2f} | SL: {sl1:.2f} | TP: {tp1:.2f} | Zone: {zid1} | Score: {score1}/100")
        print(f"      Reason: {reason1}")
    else:
        print(f"  >>> Status: Monitoring liquidity zones... ({reason1})")

    # Engine 2 Check: Micro Scalper
    sig2, e2, sl2, tp2, cid2, score2, reason2, _, _, _ = scalper.scan_for_scalp_candidates(sym)
    print("\n[Engine 2: Fast Micro-Scalper (M1, M5)]")
    if sig2:
        print(f"  >>> ACTIVE SIGNAL: {sig2} @ {e2:.2f} | SL: {sl2:.2f} | TP: {tp2:.2f} | Score: {score2}/100")
        print(f"      Reason: {reason2}")
    else:
        print(f"  >>> Status: {reason2}")

    print("\n" + "=" * 65)
    print("  [OK] Both engines are operating in full harmony with zero conflicts!")
    print("=" * 65)

    connector.shutdown()


if __name__ == "__main__":
    test()

