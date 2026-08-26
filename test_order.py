"""
Test Demo Order Placement Script
Opens a 0.01 lot test trade on Gold (XAUUSDm) on your demo account
to visually verify that Python can place orders on your MT5 screen.
"""

import time
import yaml
from dotenv import load_dotenv
import MetaTrader5 as mt5
from src.connection import MT5Connector
from src.execution import OrderExecutor


def place_test_demo_trade():
    print("=" * 60)
    print("   PLACING 0.01 LOT TEST DEMO TRADE ON GOLD (XAUUSDm)")
    print("=" * 60)

    load_dotenv("config/.env")
    load_dotenv()

    with open("config/config.yaml", "r") as f:
        config = yaml.safe_load(f)

    connector = MT5Connector()
    if not connector.initialize():
        print("[ERROR] Failed to connect to MT5.")
        return

    sym = connector.resolve_symbol(config.get("symbols", {}).get("candidates", ["XAUUSDm"]))
    if not sym:
        print("[ERROR] Symbol not found.")
        connector.shutdown()
        return

    tick = mt5.symbol_info_tick(sym)
    executor = OrderExecutor(config)

    # Place a test BUY order with 50 point SL and 100 point TP
    info = connector.symbol_info
    point = info.point
    digits = info.digits

    entry = tick.ask
    sl = round(entry - (1000 * point), digits)  # $1.00 below entry
    tp = round(entry + (1000 * point), digits)  # $1.00 above entry

    print(f"\nSending 0.01 BUY order on {sym} @ {entry:.2f}...")
    ticket = executor.execute_market_order(
        symbol=sym,
        order_type="BUY",
        volume=0.01,
        sl=sl,
        tp=tp,
        comment="Musumali_TestTrade",
    )

    if ticket:
        print(f"\n>>> SUCCESS! Order #{ticket} is now LIVE on your MT5 screen!")
        print(f"    Check your MT5 terminal 'Trade' tab at the bottom to see it.")
    else:
        print("\n>>> Order failed. Please check if 'Allow Algo Trading' is enabled in MT5 Options.")

    connector.shutdown()


if __name__ == "__main__":
    place_test_demo_trade()
