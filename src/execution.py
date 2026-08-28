"""
Order Execution and Trade Management Engine
Enforces:
  1. Mandatory Take Profit (TP) and Stop Loss (SL) on every order.
  2. Real-Time Dynamic Trade Management (Break-Even Lock, Profit Retracement Guardian).
  3. Closed Trade Outcome Feedback to RiskManager (Zone Cooldowns & Daily Drawdown).
"""

import logging
import re
import time
from typing import Dict, List, Optional, Union, Tuple
import pandas as pd
import MetaTrader5 as mt5

from src.position_manager import IntelligentExitEngine, PositionState, ExitDecision

logger = logging.getLogger("GoldBot.Execution")


class OrderExecutor:
    def __init__(self, config: dict, risk_manager=None):
        self.config = config
        self.risk_manager = risk_manager
        self.magic_musumali = config.get("musumali_strategy", {}).get("magic_number", 2001)
        self.magic_scalper = config.get("m1_scalper", {}).get("magic_number", 1001)
        self.magic_numbers = [self.magic_musumali, self.magic_scalper]

        self.slippage = config.get("risk_management", {}).get("slippage_points", 25)

        # Initialize Intelligent Exit & Position State Machine
        self.exit_engine = IntelligentExitEngine(config)

        # Dynamic Profit Management Configuration
        profit_cfg = config.get("profit_management", {})
        self.giveback_cap_enabled = profit_cfg.get("giveback_cap_enabled", True)
        self.giveback_min_peak = profit_cfg.get("giveback_min_peak_dollars", 0.80)
        self.giveback_max_pct = profit_cfg.get("giveback_max_pct", 0.40)
        self.auto_tp_target = profit_cfg.get("auto_take_profit_target_dollars", 2.50)
        self.auto_tp_min = profit_cfg.get("auto_take_profit_min_dollars", 1.50)
        self.max_hard_loss = profit_cfg.get("max_hard_loss_per_trade_dollars", 2.50)
        self.max_account_floating_dd = profit_cfg.get("max_account_floating_drawdown_dollars", 3.50)
        self.trailing_enabled = profit_cfg.get("trailing_enabled", True)
        self.auto_close_enabled = profit_cfg.get("auto_close_enabled", True)

        # Hard Maximum Loss Circuit Breaker
        cb_cfg = config.get("circuit_breakers", {})
        self.hard_max_loss_dollars = cb_cfg.get("hard_max_loss_per_trade_dollars", 5.00)
        self.hard_max_loss_pct = cb_cfg.get("hard_max_loss_equity_pct", 15.0)

        # Peak Profit Tracker for each active ticket
        self.peak_profit: Dict[int, float] = {}
        # Zone tracking per ticket for feedback loop
        self.ticket_zones: Dict[int, Optional[float]] = {}
        # Track active tickets for detecting broker-side closes (TP/SL)
        self.known_tickets: Dict[int, dict] = {}

    def set_risk_manager(self, risk_manager):
        """Attaches the risk manager for closed trade feedback."""
        self.risk_manager = risk_manager

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
        comment: str = "Musumali",
        zone_id: Optional[float] = None,
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
        filling_candidates = [self._get_supported_filling_mode(info), mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_RETURN, mt5.ORDER_FILLING_FOK]
        result = None
        t_order_sent = time.time()
        
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
                "comment": comment[:31],
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": f_mode,
            }

            logger.info(
                f"Placing {order_type.upper()} ({comment}) {volume} lots on {symbol} @ {price:.2f} (Filling: {f_mode}) | "
                f"SL: {sl_rounded:.2f} | TP: {tp_rounded:.2f} | Magic: {used_magic}"
            )

            result = mt5.order_send(request)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                break
            elif result and result.retcode in (10030, 10019, 10006): # Unsupported filling mode or temporary rejection
                continue
            else:
                break

        t_order_done = time.time()

        if result is None:
            err = mt5.last_error()
            logger.error(f"Order send returned None: {err}")
            return None

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"[SLIPPAGE PROTECTION FIX 26] Order failed with retcode [{result.retcode}]: {result.comment}")
            return None

        roundtrip_ms = (t_order_done - t_order_sent) * 1000.0
        ticket = result.order
        fill_price = result.price if result.price > 0 else price
        slippage_pts = abs(fill_price - price) / info.point if info.point > 0 else 0
        self.peak_profit[ticket] = 0.0
        self.ticket_zones[ticket] = zone_id

        # Fix 28: Identify active trading session
        session_name = "Session"
        if self.risk_manager and hasattr(self.risk_manager, "get_current_trading_session"):
            session_name = self.risk_manager.get_current_trading_session()

        # Track initial risk distance for +1R Break-Even & 1:1 R:R Partial Close
        risk_dist = abs(fill_price - sl_rounded) if sl_rounded > 0 else 1.0
        self.known_tickets[ticket] = {
            "symbol": symbol,
            "type": order_type.upper(),
            "volume": volume,
            "entry_price": fill_price,
            "initial_sl": sl_rounded,
            "initial_tp": tp_rounded,
            "risk_distance": risk_dist,
            "be_applied": False,
            "partial_closed": False,
            "zone_id": zone_id,
            "magic": used_magic,
            "comment": comment,
            "session": session_name,
        }

        # Register with Intelligent Exit Engine
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
        )

        logger.info(
            f"[SLIPPAGE & SESSION AUDIT FIX 26 & 28] Order #{ticket} ({comment}) filled in {session_name} Session @ {fill_price:.2f} "
            f"(Req: {price:.2f}, Slippage: {slippage_pts:.1f} pts / Limit: {self.slippage} pts) | "
            f"SL: {sl_rounded:.2f} (Risk: ${risk_dist:.2f}) | TP: {tp_rounded:.2f} | Zone: {zone_id}"
        )
        return ticket

    def partial_close_position(self, ticket: int, symbol: str, volume: float, reason: str = "PartialClose_1R_50pct") -> bool:
        """
        Closes a partial volume (e.g. 50%) of an active position once 1:1 R:R is reached.
        """
        positions = mt5.positions_get(ticket=ticket)
        if not positions or len(positions) == 0:
            return False

        pos = positions[0]
        info = mt5.symbol_info(symbol)
        if info is None:
            return False

        min_lot = info.volume_min
        volume_step = info.volume_step
        
        # Round volume to valid broker lot step
        close_vol = round(volume / volume_step) * volume_step
        close_vol = round(close_vol, 2)

        if close_vol < min_lot or close_vol >= pos.volume:
            logger.warning(
                f"[PARTIAL CLOSE SKIP] Cannot partially close {close_vol} lots on Ticket #{ticket} "
                f"(Pos volume: {pos.volume}, Min Lot: {min_lot})."
            )
            return False

        close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        tick = mt5.symbol_info_tick(symbol)
        price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask
        filling_mode = self._get_supported_filling_mode(info)
        clean_comment = re.sub(r'[^a-zA-Z0-9_]', '', str(reason))[:20] or "part_close"

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": ticket,
            "symbol": symbol,
            "volume": float(close_vol),
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
            logger.error(f"Failed partial close on #{ticket} ({close_vol} lots): {err}")
            return False

        remaining_vol = round(pos.volume - close_vol, 2)
        logger.info(
            f"[PARTIAL CLOSE 1:1 R:R] Ticket #{ticket} closed 50% ({close_vol} lots @ {result.price:.2f})! "
            f"Remaining {remaining_vol} lots running to TP with BE SL."
        )
        return True

    def close_position(self, ticket: int, symbol: str, reason: str = "Target Hit") -> bool:
        """Closes an open position at the current market price immediately."""
        positions = mt5.positions_get(ticket=ticket)
        if not positions or len(positions) == 0:
            self._handle_ticket_closed(ticket, 0.0, reason)
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
            logger.error(f"Failed to close position #{ticket}: {err}")
            return False

        profit = pos.profit
        logger.info(f"CLOSED Ticket #{ticket} ({reason}) | Exit Price: {result.price} | PnL: ${profit:.2f}")
        self._handle_ticket_closed(ticket, profit, reason, magic=pos.magic)
        return True

    def _handle_ticket_closed(self, ticket: int, profit: float, reason: str, magic: Optional[int] = None):
        """Cleans up internal tracking and feeds outcome and profit capture analytics to RiskManager."""
        self.peak_profit.pop(ticket, None)
        zone_id = self.ticket_zones.pop(ticket, None)
        t_data = self.known_tickets.pop(ticket, None)
        used_magic = magic or (t_data.get("magic") if t_data else None)

        rec = self.exit_engine.records.get(ticket)
        peak_r = rec.peak_r if rec else 0.0
        risk_dollars = rec.initial_risk_dollars if (rec and rec.initial_risk_dollars > 0) else 1.0
        captured_r = profit / risk_dollars

        if self.risk_manager:
            self.risk_manager.record_trade_result(
                zone_id,
                profit,
                magic=used_magic,
                exit_reason=reason,
                peak_r=peak_r,
                captured_r=captured_r,
            )

        self.exit_engine.records.pop(ticket, None)

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
        Monitors active positions in real-time through the Intelligent Exit Engine:
          1. Position State Machine (INITIAL -> PROFITABLE -> STRONG_WINNER -> MOMENTUM_WEAKENING -> CONFIRMED_REVERSAL)
          2. Multi-Signal Continuation vs. Reversal Scoring (0 - 100)
          3. Dynamic R-Multiple Profit Locking (+0.5R, +0.8R, +1.0R, +1.5R)
          4. Stale Trade Timeout & Thesis Invalidation
          5. Volatility-Aware Trailing Stop & Dynamic Giveback Protection
        """
        info = mt5.symbol_info(symbol)
        if info is None:
            return

        digits = info.digits
        positions = self.get_open_positions(symbol)
        active_tickets = {p["ticket"] for p in positions}

        # Clean up closed records
        self.exit_engine.cleanup_closed_tickets(list(active_tickets))

        # Detect broker-side closed tickets (e.g. SL or TP hit by broker)
        for ticket in list(self.known_tickets.keys()):
            if ticket not in active_tickets:
                deals = mt5.history_deals_get(position=ticket)
                profit = 0.0
                if deals and len(deals) > 0:
                    profit = sum(d.profit for d in deals)
                t_data = self.known_tickets.get(ticket)
                b_magic = t_data.get("magic") if t_data else None
                logger.info(f"Detected Broker Close on Ticket #{ticket} (Magic: {b_magic}) | PnL: ${profit:.2f}")
                self._handle_ticket_closed(ticket, profit, "Broker_TP_SL_Hit", magic=b_magic)

        if len(positions) == 0:
            return

        # Fetch multi-timeframe candles & tick for intelligent exit analysis
        rates_m1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 25)
        rates_m5 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 25)
        rates_m15 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 35)
        live_tick = mt5.symbol_info_tick(symbol)

        df_m1 = pd.DataFrame(rates_m1) if rates_m1 is not None and len(rates_m1) > 0 else None
        df_m5 = pd.DataFrame(rates_m5) if rates_m5 is not None and len(rates_m5) > 0 else None
        df_m15 = pd.DataFrame(rates_m15) if rates_m15 is not None and len(rates_m15) > 0 else None

        # Calculate live M15 ATR
        live_atr = 2.0
        if df_m15 is not None and len(df_m15) >= 14:
            tr = pd.concat([
                df_m15["high"] - df_m15["low"],
                abs(df_m15["high"] - df_m15["close"].shift(1)),
                abs(df_m15["low"] - df_m15["close"].shift(1))
            ], axis=1).max(axis=1)
            live_atr = float(tr.tail(14).mean())

        for pos in positions:
            ticket = pos["ticket"]
            p_type = pos["type"]
            profit = pos["profit"]
            current_sl = pos["sl"]
            current_tp = pos["tp"]

            # Evaluate lifecycle decision via IntelligentExitEngine
            decision, target_new_sl, reason = self.exit_engine.evaluate_position_lifecycle(
                pos_dict=pos,
                df_m1=df_m1,
                df_m5=df_m5,
                df_m15=df_m15,
                live_tick=live_tick,
                live_atr=live_atr,
                digits=digits,
            )

            rec = self.exit_engine.records.get(ticket)
            rev_score = rec.reversal_score if rec else 50
            cont_score = rec.continuation_score if rec else 50
            state_name = rec.state.value if rec else "INITIAL"
            peak_r = rec.peak_r if rec else 0.0
            curr_r = rec.current_r if rec else 0.0

            logger.info(
                f"[INTELLIGENT EXIT AUDIT] Ticket #{ticket} ({p_type}) | State: {state_name} | "
                f"P&L: ${profit:+.2f} ({curr_r:+.2f}R, Peak: {peak_r:+.2f}R) | "
                f"Continuation: {cont_score}/100, Reversal: {rev_score}/100 | Action: {decision.value} ({reason})"
            )

            if decision == ExitDecision.CLOSE_MARKET:
                self.close_position(ticket, symbol, reason=reason)
            elif decision in (ExitDecision.LOCK_BREAKEVEN, ExitDecision.TIGHTEN_PROTECTION, ExitDecision.TRAIL_ATR):
                if target_new_sl is not None:
                    self.update_sl_tp(ticket, symbol, target_new_sl, current_tp)

    @staticmethod
    def _get_supported_filling_mode(symbol_info) -> int:
        """Determines best supported filling mode for broker (IOC, RETURN, or FOK)."""
        fillings = symbol_info.filling_mode if symbol_info else 0
        if fillings & 2:
            return mt5.ORDER_FILLING_IOC
        if fillings & 1:
            return mt5.ORDER_FILLING_IOC
        return mt5.ORDER_FILLING_RETURN
