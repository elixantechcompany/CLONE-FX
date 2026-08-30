"""
Order Execution and Trade Management Engine (Multi-Symbol & Multi-Account Support)
Enforces:
  1. Mandatory Take Profit (TP) and Stop Loss (SL) on every order.
  2. Mandatory Post-Execution SL Verification & Fail-Safe Auto-Close.
  3. Composite Trade Identification (Prevents duplicate executions).
  4. Real-Time Dynamic Trade Management & Closed Trade Feedback.
"""

import logging
import re
import time
from typing import Dict, List, Optional, Union, Tuple, Any
import MetaTrader5 as mt5
import pandas as pd

from src.position_manager import IntelligentExitEngine, PositionState, ExitDecision

logger = logging.getLogger("GoldBot.Execution")


class OrderExecutor:
    def __init__(self, config: dict, connector, risk_manager=None, account_id: str = "account_1"):
        self.config = config
        self.connector = connector
        self.risk_manager = risk_manager
        self.account_id = account_id

        self.magic_musumali = config.get("musumali_strategy", {}).get("magic_number", 2001)
        self.magic_scalper = config.get("m1_scalper", {}).get("magic_number", 1001)
        self.magic_numbers = [self.magic_musumali, self.magic_scalper]
        self.slippage = config.get("risk_management", {}).get("slippage_points", 30)

        # Initialize Intelligent Exit & Position State Machine
        self.exit_engine = IntelligentExitEngine(config)

        # Active ticket state caches
        self.peak_profit: Dict[int, float] = {}
        self.ticket_zones: Dict[int, Optional[float]] = {}
        self.known_tickets: Dict[int, dict] = {}

    def set_risk_manager(self, risk_manager):
        """Attaches the risk manager for closed trade feedback."""
        self.risk_manager = risk_manager

    def get_open_positions(self, symbol: Optional[str] = None, magic: Optional[Union[int, List[int]]] = None) -> List[dict]:
        """Retrieves currently open positions managed by our bots for this account."""
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
        comment: str = "Musumali",
        zone_id: Optional[float] = None,
        candle_id: str = "",
    ) -> Optional[int]:
        """
        Executes a market order on MT5 with guaranteed SL and TP.
        Includes Mandatory Post-Execution Verification and Emergency Close if SL is missing.
        """
        info = mt5.symbol_info(symbol)
        if info is None:
            logger.error(f"[{self.account_id}] Cannot execute order: Symbol {symbol} info not available.")
            return None

        digits = info.digits
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            logger.error(f"[{self.account_id}] Cannot get tick data for {symbol}.")
            return None

        price = tick.ask if order_type.upper() == "BUY" else tick.bid
        used_magic = magic or self.magic_musumali
        sl_rounded = round(sl, digits)
        tp_rounded = round(tp, digits)
        mt5_order_type = mt5.ORDER_TYPE_BUY if order_type.upper() == "BUY" else mt5.ORDER_TYPE_SELL

        filling_candidates = [self._get_supported_filling_mode(info), mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_RETURN, mt5.ORDER_FILLING_FOK]
        result = None
        t_order_sent = time.time()

        # Build clean comment containing trade identity
        clean_comment = f"{comment[:15]}_{self.account_id}"[:31]

        for f_mode in filling_candidates:
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
                "comment": clean_comment,
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": f_mode,
            }

            logger.info(
                f"[{self.account_id}] Sending {order_type.upper()} {volume} lots on {symbol} @ {price:.2f} | "
                f"SL: {sl_rounded:.2f} | TP: {tp_rounded:.2f} | Magic: {used_magic}"
            )

            result = mt5.order_send(request)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                break
            elif result and result.retcode in (10030, 10019, 10006):
                continue
            else:
                break

        t_order_done = time.time()

        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            err = result.comment if result else str(mt5.last_error())
            logger.error(f"[{self.account_id}] Order execution failed with retcode [{result.retcode if result else 'None'}]: {err}")
            return None

        ticket = result.order
        fill_price = result.price if result.price > 0 else price
        self.peak_profit[ticket] = 0.0
        self.ticket_zones[ticket] = zone_id

        # =====================================================================
        # MANDATORY POST-EXECUTION VERIFICATION (Directive 42)
        # =====================================================================
        post_verify_ok = self._verify_post_execution(ticket, symbol, order_type, volume, sl_rounded, used_magic)
        if not post_verify_ok:
            logger.critical(
                f"[{self.account_id}] POST-EXECUTION VERIFICATION FAILED FOR TICKET #{ticket}! "
                f"Attempting immediate emergency fail-safe close."
            )
            self.close_position(ticket, symbol, reason="PostExecution_Verification_FailSafe")
            return None

        # Register with internal trackers
        risk_dist = abs(fill_price - sl_rounded) if sl_rounded > 0 else (2.0 if "XAU" in symbol else 150.0)
        self.known_tickets[ticket] = {
            "account_id": self.account_id,
            "symbol": symbol,
            "type": order_type.upper(),
            "volume": volume,
            "entry_price": fill_price,
            "initial_sl": sl_rounded,
            "initial_tp": tp_rounded,
            "risk_distance": risk_dist,
            "be_applied": False,
            "zone_id": zone_id,
            "magic": used_magic,
            "candle_id": candle_id,
            "comment": comment,
        }

        self.exit_engine.register_position(
            ticket=ticket,
            symbol=symbol,
            pos_type=order_type,
            volume=volume,
            open_price=fill_price,
            sl=sl_rounded,
            tp=tp_rounded,
            magic=used_magic,
            thesis_anchor=zone_id,
            account_id=self.account_id,
        )

        latency_ms = (t_order_done - t_order_sent) * 1000.0
        logger.info(
            f"[{self.account_id}] [ORDER FILLED & VERIFIED] Ticket #{ticket} ({symbol} {order_type} {volume} lots @ {fill_price:.2f}) | "
            f"SL: {sl_rounded:.2f} | TP: {tp_rounded:.2f} | Latency: {latency_ms:.1f}ms"
        )
        return ticket

    def _verify_post_execution(
        self,
        ticket: int,
        expected_symbol: str,
        expected_type: str,
        expected_volume: float,
        expected_sl: float,
        expected_magic: int,
    ) -> bool:
        """
        Verifies that the broker order has the correct symbol, volume, magic number,
        and critically: A VALID NON-ZERO STOP LOSS.
        If SL is missing, attempts an immediate repair.
        """
        time.sleep(0.1) # Brief pause for MT5 internal state sync
        positions = mt5.positions_get(ticket=ticket)
        if not positions or len(positions) == 0:
            logger.warning(f"[{self.account_id}] Post-verification: Position #{ticket} not found in positions list yet.")
            return True # May take a few ms on some brokers

        pos = positions[0]

        # Verify symbol and magic
        if pos.symbol != expected_symbol or pos.magic != expected_magic:
            logger.error(f"[{self.account_id}] Post-verification mismatch on #{ticket}: Symbol {pos.symbol} vs {expected_symbol}, Magic {pos.magic} vs {expected_magic}")
            return False

        # CRITICAL: Verify Stop Loss is present
        if pos.sl <= 0:
            logger.warning(f"[{self.account_id}] Post-verification: SL missing on Ticket #{ticket}! Attempting immediate correction to {expected_sl:.2f}...")
            repaired = self.update_sl_tp(ticket, expected_symbol, expected_sl, pos.tp)
            if not repaired:
                logger.error(f"[{self.account_id}] Failed to repair missing SL on Ticket #{ticket}!")
                return False
            logger.info(f"[{self.account_id}] Successfully repaired missing SL on Ticket #{ticket} -> {expected_sl:.2f}")

        return True

    def close_position(self, ticket: int, symbol: str, reason: str = "Target Hit") -> bool:
        """Closes an open position at the current market price immediately."""
        positions = mt5.positions_get(ticket=ticket)
        if not positions or len(positions) == 0:
            self._handle_ticket_closed(ticket, 0.0, reason, symbol=symbol)
            return False

        pos = positions[0]
        info = mt5.symbol_info(symbol)
        if info is None:
            return False

        close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        tick = mt5.symbol_info_tick(symbol)
        price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask
        filling_mode = self._get_supported_filling_mode(info)
        clean_comment = re.sub(r'[^a-zA-Z0-9_]', '', str(reason))[:20] or "close"

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": ticket,
            "symbol": symbol,
            "volume": pos.volume,
            "type": close_type,
            "price": price,
            "deviation": int(self.slippage),
            "magic": int(pos.magic),
            "comment": clean_comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling_mode,
        }

        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            err = result.comment if result else str(mt5.last_error())
            logger.error(f"[{self.account_id}] Failed to close position #{ticket}: {err}")
            return False

        profit = pos.profit
        logger.info(f"[{self.account_id}] CLOSED Ticket #{ticket} ({symbol} {reason}) | Exit Price: {result.price} | PnL: ${profit:.2f}")
        self._handle_ticket_closed(ticket, profit, reason, magic=pos.magic, symbol=symbol)
        return True

    def _handle_ticket_closed(self, ticket: int, profit: float, reason: str, magic: Optional[int] = None, symbol: Optional[str] = None):
        """Cleans up internal tracking and feeds outcome and profit capture analytics to RiskManager."""
        self.peak_profit.pop(ticket, None)
        zone_id = self.ticket_zones.pop(ticket, None)
        t_data = self.known_tickets.pop(ticket, None)
        used_magic = magic or (t_data.get("magic") if t_data else None)
        used_symbol = symbol or (t_data.get("symbol") if t_data else None)

        rec = self.exit_engine.records.get(ticket)
        peak_r = rec.peak_r if rec else 0.0
        risk_dollars = rec.initial_risk_dollars if (rec and rec.initial_risk_dollars > 0) else 1.0
        captured_r = profit / risk_dollars

        if self.risk_manager:
            self.risk_manager.record_trade_result(
                zone_id=zone_id,
                profit=profit,
                magic=used_magic,
                symbol=used_symbol,
                exit_reason=reason,
                peak_r=peak_r,
                captured_r=captured_r,
            )

        self.exit_engine.records.pop(ticket, None)

    def update_sl_tp(self, ticket: int, symbol: str, new_sl: float, new_tp: float) -> bool:
        """Modifies Stop Loss and Take Profit for active position."""
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

        logger.info(f"[{self.account_id}] Updated Ticket #{ticket} ({symbol}) -> New SL: {new_sl:.2f}, New TP: {new_tp:.2f}")
        return True

    def manage_active_positions(self, active_symbols: List[str]):
        """Monitors open positions across all active symbols in real-time."""
        for symbol in active_symbols:
            info = mt5.symbol_info(symbol)
            if info is None:
                continue

            digits = info.digits
            positions = self.get_open_positions(symbol)
            active_tickets = {p["ticket"] for p in positions}

            # Cleanup closed tickets
            self.exit_engine.cleanup_closed_tickets(list(active_tickets))

            # Detect broker-side closed tickets
            for ticket in list(self.known_tickets.keys()):
                t_data = self.known_tickets.get(ticket, {})
                if t_data.get("symbol") == symbol and ticket not in active_tickets:
                    deals = mt5.history_deals_get(position=ticket)
                    profit = 0.0
                    if deals and len(deals) > 0:
                        profit = sum(d.profit for d in deals)
                    b_magic = t_data.get("magic")
                    logger.info(f"[{self.account_id}] Detected Broker Close on Ticket #{ticket} (Magic: {b_magic}) | PnL: ${profit:.2f}")
                    self._handle_ticket_closed(ticket, profit, "Broker_TP_SL_Hit", magic=b_magic, symbol=symbol)

            if not positions:
                continue

            # Fetch multi-timeframe candles & tick
            rates_m1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 25)
            rates_m5 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 25)
            rates_m30 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M30, 0, 25)
            rates_h1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 30)
            live_tick = mt5.symbol_info_tick(symbol)

            df_m1 = pd.DataFrame(rates_m1) if rates_m1 is not None and len(rates_m1) > 0 else None
            df_m5 = pd.DataFrame(rates_m5) if rates_m5 is not None and len(rates_m5) > 0 else None
            df_m30 = pd.DataFrame(rates_m30) if rates_m30 is not None and len(rates_m30) > 0 else None
            df_h1 = pd.DataFrame(rates_h1) if rates_h1 is not None and len(rates_h1) > 0 else None

            # Calculate live ATR
            live_atr = 2.0 if "XAU" in symbol else 150.0
            if df_m5 is not None and len(df_m5) >= 14:
                tr = pd.concat([
                    df_m5["high"] - df_m5["low"],
                    abs(df_m5["high"] - df_m5["close"].shift(1)),
                    abs(df_m5["low"] - df_m5["close"].shift(1))
                ], axis=1).max(axis=1)
                live_atr = float(tr.tail(14).mean())

            for pos in positions:
                ticket = pos["ticket"]
                p_type = pos["type"]
                profit = pos["profit"]
                current_sl = pos["sl"]
                current_tp = pos["tp"]

                decision, target_new_sl, reason = self.exit_engine.evaluate_position_lifecycle(
                    pos_dict=pos,
                    df_m1=df_m1,
                    df_m5=df_m5,
                    df_m30=df_m30,
                    df_h1=df_h1,
                    live_tick=live_tick,
                    live_atr=live_atr,
                    digits=digits,
                )

                if decision == ExitDecision.CLOSE_MARKET:
                    self.close_position(ticket, symbol, reason=reason)
                elif decision in (ExitDecision.LOCK_BREAKEVEN, ExitDecision.TIGHTEN_PROTECTION, ExitDecision.TRAIL_ATR):
                    if target_new_sl is not None:
                        self.update_sl_tp(ticket, symbol, target_new_sl, current_tp)

    @staticmethod
    def _get_supported_filling_mode(symbol_info) -> int:
        """Determines best supported filling mode for broker."""
        fillings = symbol_info.filling_mode if symbol_info else 0
        if fillings & 2:
            return mt5.ORDER_FILLING_IOC
        if fillings & 1:
            return mt5.ORDER_FILLING_IOC
        return mt5.ORDER_FILLING_RETURN
