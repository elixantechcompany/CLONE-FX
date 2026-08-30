"""
Quick MT5 & Exness Connection Test
Verifies terminal connection, login credentials, and Gold symbol availability.
"""

import sys
import yaml
from dotenv import load_dotenv

from src.connection import MT5Connector


def test():
    print("=" * 60)
    print("   TESTING BRIGHTFUNDED MT5 CONNECTION")
    print("=" * 60)

    load_dotenv("config/.env")
    load_dotenv()

    with open("config/config.yaml", "r") as f:
        config = yaml.safe_load(f)

    connector = MT5Connector()
    print("\n[1/3] Initializing connection to MT5 terminal...")
    if not connector.initialize():
        print("[FAIL] Could not connect to MT5 terminal.")
        print("Tip: Make sure your MetaTrader 5 application is OPEN on your desktop.")
        sys.exit(1)

    print("[OK] Successfully connected to MT5 Terminal and authorized account!")

    print("\n[2/3] Fetching account details...")
    summary = connector.get_account_summary()
    for k, v in summary.items():
        print(f"  * {k.capitalize()}: {v}")

    print("\n[3/3] Checking active Gold symbols on Broker...")
    sym_cfg = config.get("symbols", {}).get("symbol_settings", {}).get("XAUUSD", {})
    candidates = sym_cfg.get("candidates", ["XAUUSD", "XAUUSDm", "XAUUSD_i", "XAUUSDz", "GOLD"])
    sym = connector.resolve_symbol(candidates)
    if sym:
        info = connector.get_symbol_specs(sym)
        print(f"[OK] Found active Gold symbol: {sym}")
        print(f"  * Digits: {info.digits}")
        print(f"  * Point: {info.point}")
        print(f"  * Current Spread: {info.spread} points")
        print(f"  * Min Lot: {info.volume_min}")
        print(f"  * Max Lot: {info.volume_max}")
        print(f"  * Lot Step: {info.volume_step}")
    else:
        print("[WARN] Could not find Gold in Market Watch.")

    connector.shutdown()
    print("\n" + "=" * 60)
    print("   ALL CHECKS COMPLETED SUCCESSFULLY!")
    print("=" * 60)


if __name__ == "__main__":
    test()
