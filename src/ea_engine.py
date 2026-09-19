"""
Autonomous EA Execution Engine
Handles automated trade placement and management for confirmed Higher-Timeframe Setups.
Operates with isolated Magic Number (#2001) so it NEVER interferes with or modifies manual trades (Magic #0).
"""

import os
import json
import time
import logging
from typing import Dict, List, Optional, Any, Set

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

logger = logging.getLogger("GoldBot.EAEngine")


class EAExecutionEngine:
    def __init__(self, config: Optional[dict] = None, magic_number: int = 2001, account_id: str = "account_d"):
        self.config = config or {}
        self.magic_number = magic_number
        self.account_id = account_id.lower()
        self.max_open_trades_per_symbol = 1
        self.default_volume = 0.01
        self.traded_setups_file = "data/ea_traded_setups.json"
        self.traded_setups: Set[str] = set()
        self._load_traded_setups()

    def _load_traded_setups(self):
        """Loads previously executed setup IDs to prevent duplicate trades across cycles."""
        try:
            if os.path.exists(self.traded_setups_file):
                with open(self.traded_setups_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.traded_setups = set(data.get("traded_ids", [])[-100:])
        except Exception as e:
            logger.warning(f"Could not load traded setups: {e}")

    def _save_traded_setups(self):
        """Persists traded setup IDs."""
        try:
            os.makedirs(os.path.dirname(self.traded_setups_file), exist_ok=True)
            temp_file = self.traded_setups_file + ".tmp"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump({"traded_ids": list(self.traded_setups)[-100:]}, f, indent=2)
            os.replace(temp_file, self.traded_setups_file)
        except Exception as e:
            logger.warning(f"Could not save traded setups: {e}")

    def get_ea_open_positions(self, symbol: Optional[str] = None) -> List[Any]:
        """Retrieves only positions opened by this EA (matching self.magic_number). Excludes manual trades (magic=0)."""
        if mt5 is None:
            return []
        try:
            all_pos = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
            if not all_pos:
                return []
            return [p for p in all_pos if p.magic == self.magic_number]
        except Exception as e:
            logger.warning(f"Error fetching EA positions: {e}")
            return []

    def get_symbol_filling_type(self, symbol_info) -> int:
        """Determines best supported filling mode for this broker symbol."""
        filling = getattr(symbol_info, "filling_mode", 0)
        # Check standard flags: 1 = FOK, 2 = IOC, 0 = RETURN/Normal
        if filling & 2:
            return mt5.ORDER_FILLING_IOC
        if filling & 1:
            return mt5.ORDER_FILLING_FOK
        return mt5.ORDER_FILLING_RETURN

    def process_active_setups(self, active_setups: List[Dict[str, Any]], is_ea_enabled: bool) -> List[Dict[str, Any]]:
        """
        Evaluates active A+/Grade A setups and automatically submits market orders on MT5
        when Algo Trading is enabled. Manual trades are strictly untouched.
        """
        if not is_ea_enabled:
            return []

        if mt5 is None:
            logger.warning("[EA Engine] MetaTrader 5 module not available.")
            return []

        # Check MT5 terminal connection & algo trading switch
        term_info = mt5.terminal_info()
        if not term_info or not term_info.connected:
            logger.warning("[EA Engine] MT5 terminal not connected.")
            return []

        if not term_info.trade_allowed:
            logger.warning("[EA Engine] Algo Trading is turned OFF in MT5 terminal settings! Please enable Algo Trading button in MT5.")
            return []

        executed_orders = []

        for setup in active_setups:
            setup_id = setup.get("id", "")
            if not setup_id or setup_id in self.traded_setups:
                continue

            score = setup.get("conviction_score", 0)
            if score < 70:
                continue

            broker_sym = setup.get("symbol", "BTCUSDm")
            # Verify symbol on MT5
            sym_info = mt5.symbol_info(broker_sym)
            if sym_info is None:
                # Try fallback
                alt_sym = broker_sym.replace("m", "") if broker_sym.endswith("m") else broker_sym + "m"
                sym_info = mt5.symbol_info(alt_sym)
                if sym_info is not None:
                    broker_sym = alt_sym

            if sym_info is None or not sym_info.visible:
                if sym_info is not None and not sym_info.visible:
                    mt5.symbol_select(broker_sym, True)
                else:
                    logger.warning(f"[EA Engine] Symbol {broker_sym} not available in MT5 MarketWatch.")
                    continue

            # Duplicate protection: Check if EA already has an open position on this symbol
            ea_open = self.get_ea_open_positions(broker_sym)
            if len(ea_open) >= self.max_open_trades_per_symbol:
                logger.info(f"[EA Engine] Active EA position already exists on {broker_sym} (#{ea_open[0].ticket}). Skipping duplicate.")
                continue

            tick = mt5.symbol_info_tick(broker_sym)
            if not tick or tick.bid <= 0 or tick.ask <= 0:
                logger.warning(f"[EA Engine] No valid tick data for {broker_sym}.")
                continue

            direction = str(setup.get("direction", "BUY")).upper()
            digits = sym_info.digits
            point = sym_info.point
            stops_level = getattr(sym_info, "stops_level", 0) * point

            price = tick.ask if direction == "BUY" else tick.bid
            raw_sl = float(setup.get("stop_loss", 0.0))
            raw_tp = float(setup.get("tp1", 0.0))

            # Validate and format SL and TP
            if direction == "BUY":
                if raw_sl >= price:
                    raw_sl = price - (15.0 if "XAU" in broker_sym else 1000.0)
                if raw_tp <= price:
                    raw_tp = price + abs(price - raw_sl) * 2.0
            else:
                if raw_sl <= price:
                    raw_sl = price + (15.0 if "XAU" in broker_sym else 1000.0)
                if raw_tp >= price:
                    raw_tp = price - abs(raw_sl - price) * 2.0

            sl = round(raw_sl, digits)
            tp = round(raw_tp, digits)

            # Volume calculation (micro-lot 0.01 standard)
            vol_min = getattr(sym_info, "volume_min", 0.01)
            vol_step = getattr(sym_info, "volume_step", 0.01)
            volume = max(vol_min, round(round(self.default_volume / vol_step) * vol_step, 2))

            filling_mode = self.get_symbol_filling_type(sym_info)
            mt5_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL
            clean_comment = f"EA_{direction}_{setup_id[-6:]}"

            order_request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": broker_sym,
                "volume": float(volume),
                "type": mt5_type,
                "price": float(price),
                "sl": float(sl),
                "tp": float(tp),
                "deviation": 35,
                "magic": self.magic_number,
                "comment": clean_comment,
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": filling_mode,
            }

            logger.info(
                f"[EA Engine] 🚀 [SUBMITTING AUTONOMOUS ORDER] {direction} {volume} lots on {broker_sym} @ {price:.2f} | "
                f"SL: {sl:.2f} | TP: {tp:.2f} | Magic: {self.magic_number} | Setup: {setup_id}"
            )

            result = mt5.order_send(order_request)

            if result is None:
                err_code, err_msg = mt5.last_error()
                logger.error(f"[EA Engine] Order send failed (None returned). Error: {err_code} - {err_msg}")
                continue

            if result.retcode in (mt5.TRADE_RETCODE_DONE, mt5.TRADE_RETCODE_PLACED):
                logger.info(
                    f"[EA Engine] ✅ [AUTONOMOUS TRADE EXECUTED] Ticket: #{result.order} | Deal: #{result.deal} | "
                    f"Symbol: {broker_sym} | Type: {direction} | Price: {result.price:.2f} | Retcode: {result.retcode}"
                )
                self.traded_setups.add(setup_id)
                self._save_traded_setups()
                executed_orders.append({
                    "ticket": result.order,
                    "deal": result.deal,
                    "symbol": broker_sym,
                    "direction": direction,
                    "price": result.price,
                    "sl": sl,
                    "tp": tp,
                    "setup_id": setup_id,
                    "time": time.time(),
                })
            else:
                logger.warning(
                    f"[EA Engine] ❌ [ORDER REJECTED BY MT5] Retcode: {result.retcode} | Comment: {result.comment}"
                )

        # Also manage trailing stops on open EA trades
        self.manage_open_positions()

        return executed_orders

    def manage_open_positions(self):
        """
        Manages breakeven & intelligent profit trailing for EA trades (magic == 2001).
        NEVER touches manual trades (magic == 0).
        """
        if mt5 is None:
            return

        try:
            ea_positions = self.get_ea_open_positions()
            for pos in ea_positions:
                ticket = pos.ticket
                symbol = pos.symbol
                pos_type = pos.type
                open_price = pos.price_open
                current_price = pos.price_current
                cur_sl = pos.sl
                cur_tp = pos.tp
                profit = pos.profit

                # Breakeven logic: If in profit by >= 1.5R or $1.00 USD, move SL to open_price + 0.1 pip buffer
                sym_info = mt5.symbol_info(symbol)
                if not sym_info:
                    continue
                digits = sym_info.digits
                point = sym_info.point

                if pos_type == mt5.ORDER_TYPE_BUY:
                    profit_dist = current_price - open_price
                    sl_dist = abs(open_price - cur_sl) if cur_sl > 0 else (10.0 if "XAU" in symbol else 500.0)
                    # If profit is >= 1.5 * initial risk and SL is still below entry
                    if profit_dist >= (sl_dist * 1.5) and (cur_sl < open_price):
                        new_sl = round(open_price + (10 * point), digits)
                        mod_req = {
                            "action": mt5.TRADE_ACTION_SLTP,
                            "position": ticket,
                            "symbol": symbol,
                            "sl": new_sl,
                            "tp": cur_tp,
                        }
                        res = mt5.order_send(mod_req)
                        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                            logger.info(f"[EA Engine] 🛡️ Moved Position #{ticket} ({symbol}) to Breakeven @ {new_sl}")
                elif pos_type == mt5.ORDER_TYPE_SELL:
                    profit_dist = open_price - current_price
                    sl_dist = abs(cur_sl - open_price) if cur_sl > 0 else (10.0 if "XAU" in symbol else 500.0)
                    if profit_dist >= (sl_dist * 1.5) and (cur_sl > open_price or cur_sl == 0):
                        new_sl = round(open_price - (10 * point), digits)
                        mod_req = {
                            "action": mt5.TRADE_ACTION_SLTP,
                            "position": ticket,
                            "symbol": symbol,
                            "sl": new_sl,
                            "tp": cur_tp,
                        }
                        res = mt5.order_send(mod_req)
                        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                            logger.info(f"[EA Engine] 🛡️ Moved Position #{ticket} ({symbol}) to Breakeven @ {new_sl}")
        except Exception as e:
            logger.debug(f"Position management error: {e}")
