"""
Immediate Entry Script for Gold (XAUUSDm)
Places market orders for both modules (Engine 1 Musumali #2001 and Engine 2 Scalper #1001)
aligned with the active UPTREND market structure, allowing the 24/7 daemon to manage exits.
"""

import os
import sys
import yaml
import MetaTrader5 as mt5

def load_config():
    cfg_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", "config.yaml"))
    with open(cfg_path, "r") as f:
        return yaml.safe_load(f)

def execute_immediate_entries():
    if not mt5.initialize():
        print("[ERROR] MT5 could not be initialized.")
        return

    cfg = load_config()
    symbol = cfg.get("symbol", "XAUUSDm")
    info = mt5.symbol_info(symbol)
    if info is None:
        print(f"[ERROR] Symbol {symbol} not found.")
        mt5.shutdown()
        return

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        print(f"[ERROR] Could not get tick data for {symbol}.")
        mt5.shutdown()
        return

    digits = info.digits
    ask = tick.ask
    bid = tick.bid
    spread_pts = info.spread
    volume = 0.01

    print("=" * 80)
    print(f" EXECUTING IMMEDIATE LIVE ENTRIES ON {symbol}")
    print(f" Current Market Price -> Ask: {ask:.2f} | Bid: {bid:.2f} | Spread: {spread_pts} pts")
    print("=" * 80)

    # Check open positions first to prevent duplicate stacking
    open_positions = mt5.positions_get(symbol=symbol)
    open_magics = [p.magic for p in open_positions] if open_positions else []

    # 1. Engine 1: Musumali Institutional Trend Entry (Magic 2001)
    if 2001 in open_magics:
        print("[INFO] Musumali trade (Magic 2001) is already open. Skipping duplicate.")
    else:
        sl_m = round(ask - 3.50, digits)
        tp_m = round(ask + 7.00, digits)
        filling_mode = mt5.ORDER_FILLING_IOC if (info.filling_mode & mt5.ORDER_FILLING_IOC) else mt5.ORDER_FILLING_FOK
        
        req_m = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": mt5.ORDER_TYPE_BUY,
            "price": ask,
            "sl": sl_m,
            "tp": tp_m,
            "deviation": 25,
            "magic": 2001,
            "comment": "Musumali_Sweep",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling_mode,
        }
        res_m = mt5.order_send(req_m)
        if res_m and res_m.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"[SUCCESS] Engine 1 (Musumali) LIVE! Ticket: #{res_m.order} | BUY {volume} @ {res_m.price:.2f} | SL: {sl_m:.2f} | TP: {tp_m:.2f}")
        else:
            err = res_m.comment if res_m else mt5.last_error()
            print(f"[ERROR] Engine 1 order failed: {err}")

    # 2. Engine 2: High-Conviction Scalper Entry (Magic 1001)
    if 1001 in open_magics:
        print("[INFO] Scalper trade (Magic 1001) is already open. Skipping duplicate.")
    else:
        # Refresh tick for accurate fill
        tick = mt5.symbol_info_tick(symbol)
        ask = tick.ask
        sl_s = round(ask - 2.50, digits)
        tp_s = round(ask + 5.00, digits)
        filling_mode = mt5.ORDER_FILLING_IOC if (info.filling_mode & mt5.ORDER_FILLING_IOC) else mt5.ORDER_FILLING_FOK

        req_s = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": mt5.ORDER_TYPE_BUY,
            "price": ask,
            "sl": sl_s,
            "tp": tp_s,
            "deviation": 25,
            "magic": 1001,
            "comment": "M1_Scalp",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling_mode,
        }
        res_s = mt5.order_send(req_s)
        if res_s and res_s.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"[SUCCESS] Engine 2 (Scalper) LIVE! Ticket: #{res_s.order} | BUY {volume} @ {res_s.price:.2f} | SL: {sl_s:.2f} | TP: {tp_s:.2f}")
        else:
            err = res_s.comment if res_s else mt5.last_error()
            print(f"[ERROR] Engine 2 order failed: {err}")

    print("=" * 80)
    mt5.shutdown()

if __name__ == "__main__":
    execute_immediate_entries()
