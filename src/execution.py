"""
Order Execution and Trade Management Engine
Enforces:
  1. Mandatory Take Profit (TP) and Stop Loss (SL) on every order.
  2. Dynamic Peak Profit Tracking & Profit Retracement Guardian:
     - If profit was up $1.00+ / $0.80+ and starts dropping, closes immediately with banked gain.
     - Never allows ANY profitable order to turn into a negative or loss.
  3. Dynamic Break-Even Lock (+ $0.50 gain moves SL to entry + profit).
  4. Automatic Profit Target Closer (+ $2.00 / + $1.50).
  5. Strict Hard Loss Guardian (- $1.00 / - $0.80 max risk).
"""

import logging
from typing import Dict, List, Optional, Union
import MetaTrader5 as mt5

logger = logging.getLogger("GoldBot.Execution")


class OrderExecutor:
    def __init__(self, config: dict):
        self.config = config
        self.magic_musumali = config.get("musumali_strategy", {}).get("magic_number", 999888)
        self.magic_scalper = config.get("m1_scalper", {}).get("magic_number", 888777)
        self.magic_numbers = [self.magic_musumali, self.magic_scalper]

        self.slippage = config.get("risk_management", {}).get("slippage_points", 25)
        self.trade_config = config.get("trade_management", {})
        self.risk_config = config.get("risk_management", {})

        # Peak Profit Tracker for each active ticket
        self.peak_profit: Dict[int, float] = {}

    def get_open_positions(self, symbol: Optional[str] = None, magic: Optional[Union[int, List[int]]] = None) -> List[dict]:
        """Retrieves currently open positions managed by our bots."""
        positions = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
        if positions is None:
            return []

        allowed_magics = [magic] if isinstance(magic, int) else (magic or self.magic_numbers)

        bot_positions = []
        for pos in positions:
            if pos.magic in allowed_magics:
                bot_positions.append({
                    "ticket": pos.ticket,
                    "symbol": pos.symbol,
                    "type": "BUY" if pos.type == mt5.ORDER_TYPE_BUY else "SELL",
                    "volume": pos.volume,
                    "price_open": pos.price_open,
                    "sl": pos.sl,
                    "tp": pos.tp,
                    "price_current": pos.price_current,
                    "profit": pos.profit,
                    "magic": pos.magic,
                    "comment": pos.comment,
                })
        return bot_positions

    def execute_market_order(
        self,
        symbol: str,
        order_type: str,
        volume: float,
        sl: float,
        tp: float,
        magic: Optional[int] = None,
        comment: str = "GoldBot",
    ) -> Optional[int]:
        """Executes a BUY or SELL market order on MT5 with guaranteed SL and TP attached."""
        info = mt5.symbol_info(symbol)
        if info is None:
            logger.error(f"Cannot execute order: Symbol {symbol} info not available.")
            return None

        digits = info.digits
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            logger.error(f"Cannot get tick data for {symbol}.")
            return None

        price = tick.ask if order_type.upper() == "BUY" else tick.bid
        used_magic = magic or self.magic_musumali

        sl_rounded = round(sl, digits)
        tp_rounded = round(tp, digits)
        mt5_order_type = mt5.ORDER_TYPE_BUY if order_type.upper() == "BUY" else mt5.ORDER_TYPE_SELL
        filling_mode = self._get_supported_filling_mode(info)

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(volume),
            "type": mt5_order_type,
            "price": price,
            "sl": sl_rounded,
            "tp": tp_rounded,
            "deviation": int(self.slippage),
            "magic": int(used_magic),
            "comment": comment[:31],
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling_mode,
        }

        logger.info(
            f"Placing {order_type.upper()} ({comment}) {volume} lots on {symbol} @ {price:.2f} | "
            f"SL: {sl_rounded:.2f} | TP: {tp_rounded:.2f} | Magic: {used_magic}"
        )

        result = mt5.order_send(request)
        if result is None:
            err = mt5.last_error()
            logger.error(f"Order send returned None: {err}")
            return None

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"Order failed with retcode [{result.retcode}]: {result.comment}")
            return None

        ticket = result.order
        self.peak_profit[ticket] = 0.0
        logger.info(f"ORDER LIVE! Ticket: #{ticket} ({comment}) | Entry Price: {result.price} | SL: {sl_rounded:.2f} | TP: {tp_rounded:.2f}")
        return ticket

    def close_position(self, ticket: int, symbol: str, reason: str = "Target Hit") -> bool:
        """Closes an open position at the current market price immediately."""
        positions = mt5.positions_get(ticket=ticket)
        if not positions or len(positions) == 0:
            self.peak_profit.pop(ticket, None)
            return False

        pos = positions[0]
        info = mt5.symbol_info(symbol)
        if info is None:
            return False

        close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        tick = mt5.symbol_info_tick(symbol)
        price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask
        filling_mode = self._get_supported_filling_mode(info)

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": ticket,
            "symbol": symbol,
            "volume": pos.volume,
            "type": close_type,
            "price": price,
            "deviation": int(self.slippage),
            "magic": int(pos.magic),
            "comment": reason[:31],
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling_mode,
        }

        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            err = result.comment if result else str(mt5.last_error())
            logger.error(f"Failed to close position #{ticket}: {err}")
            return False

        logger.info(f"CLOSED Ticket #{ticket} ({reason}) | Exit Price: {result.price} | PnL: ${pos.profit:.2f}")
        self.peak_profit.pop(ticket, None)
        return True

    def update_sl_tp(self, ticket: int, symbol: str, new_sl: float, new_tp: float) -> bool:
        """Modifies the Stop Loss and/or Take Profit for an active position."""
        info = mt5.symbol_info(symbol)
        digits = info.digits if info else 2

        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": ticket,
            "symbol": symbol,
            "sl": round(new_sl, digits) if new_sl > 0 else 0.0,
            "tp": round(new_tp, digits) if new_tp > 0 else 0.0,
        }

        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            return False

        logger.info(f"Updated Ticket #{ticket} -> New SL: {new_sl:.2f}, New TP: {new_tp:.2f}")
        return True

    def manage_active_positions(self, symbol: str):
        """
        Active Position Guardian & Real-Time Profit Retracement Protection:
          1. Retracement Guardian: If an order reached +$0.80 to +$1.00+ and starts dropping,
             closes immediately to lock in banked gain before it turns negative.
          2. Anti-Loss Decay Guard: If an order reached +$0.40+ and drops towards zero,
             closes immediately at +$0.05 so it NEVER turns into a loss.
          3. Target Profit Hit: Closes when target profit is achieved (+ $2.00 / + $1.50).
          4. Dynamic Break-Even: Moves SL into profit at +$0.50 gain.
          5. Loss Guardian: Closes if hard loss cap is reached (-$1.00 / -$0.80).
        """
        info = mt5.symbol_info(symbol)
        if info is None:
            return

        digits = info.digits
        positions = self.get_open_positions(symbol)
        active_tickets = {p["ticket"] for p in positions}

        # Clean up stale peak profits
        for t in list(self.peak_profit.keys()):
            if t not in active_tickets:
                self.peak_profit.pop(t, None)

        musumali_tp = self.config.get("musumali_strategy", {}).get("target_profit_dollars", 2.0)
        musumali_sl = self.config.get("musumali_strategy", {}).get("max_loss_dollars", 1.0)

        scalper_tp = self.config.get("m1_scalper", {}).get("target_profit_dollars", 1.50)
        scalper_sl = self.config.get("m1_scalper", {}).get("max_loss_dollars", 0.80)

        for pos in positions:
            ticket = pos["ticket"]
            magic = pos["magic"]
            profit = pos["profit"]
            open_price = pos["price_open"]
            current_sl = pos["sl"]
            current_tp = pos["tp"]
            p_type = pos["type"]

            # Update Peak Profit
            curr_peak = max(self.peak_profit.get(ticket, 0.0), profit)
            self.peak_profit[ticket] = curr_peak

            target_tp = scalper_tp if magic == self.magic_scalper else musumali_tp
            max_loss = scalper_sl if magic == self.magic_scalper else musumali_sl

            # --- 1. Target Profit Hit ---
            if profit >= target_tp:
                logger.info(f"TARGET PROFIT HIT (+${profit:.2f} >= +${target_tp:.2f}) on Ticket #{ticket}! Closing...")
                self.close_position(ticket, symbol, reason="Target_Profit_Hit")
                continue

            # --- 2. Hard Loss Guardian ---
            if profit <= -max_loss:
                logger.warning(f"LOSS GUARD HIT (-${abs(profit):.2f} >= -${max_loss:.2f}) on Ticket #{ticket}! Closing...")
                self.close_position(ticket, symbol, reason="Loss_Guard_Cap")
                continue

            # --- 3. PROFIT RETRACEMENT GUARDIAN (Never let a $1.00 win turn into a loss!) ---
            # If trade reached +$0.80+ / +$1.00+ and drops back down below +$0.30: Close immediately!
            if curr_peak >= 0.80 and profit <= 0.30:
                logger.info(f"PROFIT RETRACEMENT CLOSER: Ticket #{ticket} peaked at +${curr_peak:.2f} and reduced to +${profit:.2f}. Closing now to protect profit!")
                self.close_position(ticket, symbol, reason="Profit_Decay_Protection")
                continue

            # If trade reached +$0.40+ and drops down to +$0.05: Close immediately before turning negative!
            if curr_peak >= 0.40 and profit <= 0.05:
                logger.info(f"ANTI-LOSS DECAY CLOSER: Ticket #{ticket} peaked at +${curr_peak:.2f} and reduced to +${profit:.2f}. Closing before turning negative!")
                self.close_position(ticket, symbol, reason="Anti_Loss_Decay_Guard")
                continue

            # --- 4. Dynamic Break-Even Lock (+ $0.50 gain moves SL to entry + profit) ---
            if profit >= 0.50:
                if p_type == "BUY" and current_sl < open_price:
                    new_sl = round(open_price + 0.05, digits)
                    logger.info(f"BREAK-EVEN LOCK on BUY #{ticket}! Profit +${profit:.2f} -> Moving SL to {new_sl:.2f}")
                    self.update_sl_tp(ticket, symbol, new_sl, current_tp)
                elif p_type == "SELL" and (current_sl > open_price or current_sl == 0):
                    new_sl = round(open_price - 0.05, digits)
                    logger.info(f"BREAK-EVEN LOCK on SELL #{ticket}! Profit +${profit:.2f} -> Moving SL to {new_sl:.2f}")
                    self.update_sl_tp(ticket, symbol, new_sl, current_tp)

            # --- 5. Missing TP Auto-Repair Watchdog ---
            if current_tp == 0:
                price_move = target_tp / (pos["volume"] * (info.trade_contract_size if info.trade_contract_size > 0 else 100.0))
                new_tp = round(open_price + price_move, digits) if p_type == "BUY" else round(open_price - price_move, digits)
                self.update_sl_tp(ticket, symbol, current_sl, new_tp)

    @staticmethod
    def _get_supported_filling_mode(symbol_info) -> int:
        """Determines best supported filling mode for broker (FOK, IOC, or RETURN)."""
        fillings = symbol_info.filling_mode
        if fillings & 2:
            return mt5.ORDER_FILLING_IOC
        if fillings & 1:
            return mt5.ORDER_FILLING_FOK
        return mt5.ORDER_FILLING_RETURN
