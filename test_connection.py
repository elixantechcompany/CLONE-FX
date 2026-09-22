"""
Quick MT5 & Exness Connection Test
Verifies terminal connection, login credentials, and Gold symbol availability.
"""

import sys
import time
import os
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

    import os
    acc_login = os.getenv("ACCOUNT_D_LOGIN") or os.getenv("MT5_ACCOUNT_NUMBER")
    acc_pass = os.getenv("ACCOUNT_D_PASSWORD") or os.getenv("MT5_PASSWORD")
    acc_server = os.getenv("ACCOUNT_D_SERVER") or os.getenv("MT5_SERVER")
    acc_path = os.getenv("ACCOUNT_D_MT5_PATH") or os.getenv("MT5_PATH")
    connector = MT5Connector(account=acc_login, password=acc_pass, server=acc_server, path=acc_path, account_id="account_d")
    print("\n[1/3] Initializing connection to MT5 terminal...")
    connected = False
    for attempt in range(1, 4):
        if connector.initialize():
            connected = True
            break
        print(f"  Attempt {attempt}/3 waiting for MT5 terminal IPC...")
        time.sleep(2)

    if not connected:
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
