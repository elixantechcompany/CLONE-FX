"""
Order Execution and Trade Management Engine
Enforces:
  1. Mandatory Take Profit (TP) and Stop Loss (SL) on every order.
  2. Real-Time Dynamic Trade Management (Break-Even Lock, Profit Retracement Guardian).
  3. Closed Trade Outcome Feedback to RiskManager (Zone Cooldowns & Daily Drawdown).
"""

import logging
import time
from typing import Dict, List, Optional, Union, Tuple
import pandas as pd
import MetaTrader5 as mt5

logger = logging.getLogger("GoldBot.Execution")


class OrderExecutor:
    def __init__(self, config: dict, risk_manager=None):
        self.config = config
        self.risk_manager = risk_manager
        self.magic_musumali = config.get("musumali_strategy", {}).get("magic_number", 2001)
        self.magic_scalper = config.get("m1_scalper", {}).get("magic_number", 1001)
        self.magic_numbers = [self.magic_musumali, self.magic_scalper]

        self.slippage = config.get("risk_management", {}).get("slippage_points", 25)

        # Dynamic Profit Management Configuration
        profit_cfg = config.get("profit_management", {})
        self.max_hard_loss = profit_cfg.get("max_hard_loss_per_trade_dollars", 2.50)
        self.max_account_floating_dd = profit_cfg.get("max_account_floating_drawdown_dollars", 3.00)
        self.lock_profit_start = profit_cfg.get("lock_profit_start_dollars", 0.50)
        self.be_offset = profit_cfg.get("breakeven_lock_offset", 0.25)
        self.rollback_trigger = profit_cfg.get("rollback_close_trigger_dollars", 1.00)
        self.rollback_retrace_tol = profit_cfg.get("rollback_retrace_tolerance_dollars", 0.25)
        self.rollback_giveback_pct = profit_cfg.get("rollback_giveback_max_pct", 0.25)
        self.trailing_enabled = profit_cfg.get("trailing_enabled", True)
        self.trailing_trigger_r = profit_cfg.get("trailing_trigger_r", 0.8)
        self.trailing_dist = profit_cfg.get("trailing_distance_dollars", 0.80)
        self.auto_close_enabled = profit_cfg.get("auto_close_enabled", True)

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

        t_order_sent = time.time()
        result = mt5.order_send(request)
        t_order_done = time.time()

        if result is None:
            err = mt5.last_error()
            logger.error(f"Order send returned None: {err}")
            return None

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"Order failed with retcode [{result.retcode}]: {result.comment}")
            return None

        roundtrip_ms = (t_order_done - t_order_sent) * 1000.0
        ticket = result.order
        self.peak_profit[ticket] = 0.0
        self.ticket_zones[ticket] = zone_id
        
        # Track initial risk distance for +1R Break-Even & 1:1 R:R Partial Close
        risk_dist = abs(price - sl_rounded) if sl_rounded > 0 else 1.0
        self.known_tickets[ticket] = {
            "symbol": symbol,
            "type": order_type.upper(),
            "volume": volume,
            "entry_price": price,
            "initial_sl": sl_rounded,
            "initial_tp": tp_rounded,
            "risk_distance": risk_dist,
            "be_applied": False,
            "partial_closed": False,
            "zone_id": zone_id,
            "magic": used_magic,
            "comment": comment,
        }

        logger.info(
            f"ORDER LIVE! Ticket: #{ticket} ({comment}) | Entry Price: {result.price} | "
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

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": ticket,
            "symbol": symbol,
            "volume": float(close_vol),
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

        profit = pos.profit
        logger.info(f"CLOSED Ticket #{ticket} ({reason}) | Exit Price: {result.price} | PnL: ${profit:.2f}")
        self._handle_ticket_closed(ticket, profit, reason, magic=pos.magic)
        return True

    def _handle_ticket_closed(self, ticket: int, profit: float, reason: str, magic: Optional[int] = None):
        """Cleans up internal tracking and feeds outcome back to RiskManager."""
        self.peak_profit.pop(ticket, None)
        zone_id = self.ticket_zones.pop(ticket, None)
        t_data = self.known_tickets.pop(ticket, None)
        used_magic = magic or (t_data.get("magic") if t_data else None)

        if self.risk_manager:
            self.risk_manager.record_trade_result(zone_id, profit, magic=used_magic)

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
        Monitors active positions in real-time, executing Fix 1 Exit Management:
          1. Tier 0: Emergency Hard Loss Shield (Cuts runaway losses immediately)
          2. Tier 1: Move Stop-Loss to Breakeven (+1R Gain)
          3. Tier 2: Partial Close 50% Position at 1:1 R:R
          4. Tier 3: Trailing Stop after 1:1 R:R is reached
          5. Tier 4: Profit Retracement Decay Guardian & Target Profit Closers
        """
        info = mt5.symbol_info(symbol)
        if info is None:
            return

        digits = info.digits
        positions = self.get_open_positions(symbol)
        active_tickets = {p["ticket"] for p in positions}

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

        # Tier 0.5: Account-Wide Floating Drawdown Shield (Prevents Margin Depletion on Micro Accounts)
        total_floating_pnl = sum(pos["profit"] for pos in positions)
        if total_floating_pnl <= -self.max_account_floating_dd:
            logger.warning(
                f"[ACCOUNT-WIDE FLOATING DD SHIELD] Total open floating loss hit -${abs(total_floating_pnl):.2f} >= cap -${self.max_account_floating_dd:.2f}! "
                f"Emergency closing all open positions immediately to protect capital!"
            )
            for pos in positions:
                self.close_position(pos["ticket"], symbol, reason=f"AccountFloatingDDCut_-${abs(total_floating_pnl):.2f}")
            return

        for pos in positions:
            ticket = pos["ticket"]
            profit = pos["profit"]
            open_price = pos["price_open"]
            current_sl = pos["sl"]
            current_tp = pos["tp"]
            p_type = pos["type"]
            magic = pos["magic"]
            curr_price = pos["price_current"]
            volume = pos["volume"]

            # Lookup ticket tracking metadata or initialize defaults
            t_data = self.known_tickets.get(ticket)
            if not t_data:
                risk_dist = abs(open_price - current_sl) if current_sl > 0 else 1.0
                t_data = {
                    "symbol": symbol,
                    "type": p_type,
                    "volume": volume,
                    "entry_price": open_price,
                    "initial_sl": current_sl,
                    "initial_tp": current_tp,
                    "risk_distance": risk_dist,
                    "be_applied": False,
                    "partial_closed": False,
                    "zone_id": None,
                }
                self.known_tickets[ticket] = t_data

            risk_dist = t_data.get("risk_distance", 1.0)
            if risk_dist <= 0:
                risk_dist = 1.0

            # Calculate favorable move in price & R-multiple
            price_gain = (curr_price - open_price) if p_type == "BUY" else (open_price - curr_price)
            r_multiple = price_gain / risk_dist

            # Update Peak Profit Tracker
            curr_peak = max(self.peak_profit.get(ticket, 0.0), profit)
            self.peak_profit[ticket] = curr_peak

            # Tier 0: Emergency Hard Loss Shield (Scales to intended SL risk to prevent premature cuts on HTF)
            trade_max_loss = max(self.max_hard_loss, (risk_dist * volume * 100.0) * 1.15)
            if profit <= -trade_max_loss:
                logger.warning(
                    f"[HARD LOSS SHIELD] Ticket #{ticket} loss hit -${abs(profit):.2f} >= cap -${trade_max_loss:.2f}! "
                    f"Cutting loss immediately to protect capital."
                )
                self.close_position(ticket, symbol, reason=f"HardLossShield_-${abs(profit):.2f}")
                continue

            # =================================================================
            # UNIFIED PROFIT SECURING & ROLLBACK SHIELD:
            # 1. Profit Lock starting from $0.50 and above (Guaranteed Green)
            # 2. Rollback Protection starting from $1.00 and above (Auto-Close if reducing unless continuation assured)
            # 3. 50% Partial Close at +1.0R (if volume >= 0.02)
            # 4. Dynamic Continuous Trailing Stop from +0.8R
            # =================================================================

            # Step 1: Profit Lock starting from $0.50 and above (Guaranteed Risk-Free Green)
            if profit >= self.lock_profit_start or r_multiple >= 0.40:
                if not t_data.get("be_applied", False):
                    be_lock = max(self.be_offset, 0.25)
                    if p_type == "BUY" and (current_sl < (open_price + be_lock) or current_sl == 0):
                        new_sl = round(open_price + be_lock, digits)
                        logger.info(
                            f"[PROFIT LOCK >= $0.50] BUY #{ticket} reached +${profit:.2f} (Gain: {r_multiple:.2f}R) -> "
                            f"Moving SL from {current_sl:.2f} to Guaranteed Green {new_sl:.2f} (+${be_lock:.2f})"
                        )
                        if self.update_sl_tp(ticket, symbol, new_sl, current_tp):
                            t_data["be_applied"] = True
                            current_sl = new_sl
                    elif p_type == "SELL" and (current_sl > (open_price - be_lock) or current_sl == 0):
                        new_sl = round(open_price - be_lock, digits)
                        logger.info(
                            f"[PROFIT LOCK >= $0.50] SELL #{ticket} reached +${profit:.2f} (Gain: {r_multiple:.2f}R) -> "
                            f"Moving SL from {current_sl:.2f} to Guaranteed Green {new_sl:.2f} (+${be_lock:.2f})"
                        )
                        if self.update_sl_tp(ticket, symbol, new_sl, current_tp):
                            t_data["be_applied"] = True
                            current_sl = new_sl

            # Step 2: Rollback Protection starting from $1.00 and above
            # (Close if profit starts rolling back/reducing unless market is actively assuring continuation)
            if curr_peak >= self.rollback_trigger:
                # Progressive SL Lock: physically locks at least 65% of peak gains into MT5 Stop Loss
                lock_gain_dollars = max(self.be_offset, curr_peak * 0.65)
                if p_type == "BUY":
                    prog_sl = round(open_price + lock_gain_dollars, digits)
                    if prog_sl > current_sl:
                        logger.info(
                            f"[PROGRESSIVE PROFIT LOCK] BUY #{ticket} Peak +${curr_peak:.2f} -> Advancing SL to {prog_sl:.2f} (+${lock_gain_dollars:.2f})"
                        )
                        if self.update_sl_tp(ticket, symbol, prog_sl, current_tp):
                            current_sl = prog_sl
                elif p_type == "SELL":
                    prog_sl = round(open_price - lock_gain_dollars, digits)
                    if current_sl == 0 or prog_sl < current_sl:
                        logger.info(
                            f"[PROGRESSIVE PROFIT LOCK] SELL #{ticket} Peak +${curr_peak:.2f} -> Advancing SL to {prog_sl:.2f} (+${lock_gain_dollars:.2f})"
                        )
                        if self.update_sl_tp(ticket, symbol, prog_sl, current_tp):
                            current_sl = prog_sl

                # Rollback Detection from peak
                profit_reduction = curr_peak - profit
                is_rolling_back = (profit_reduction >= self.rollback_retrace_tol) or (profit <= curr_peak * (1.0 - self.rollback_giveback_pct))

                if is_rolling_back:
                    assuring, ass_reason = self.is_market_assuring_continuation(symbol, p_type)
                    if not assuring:
                        logger.info(
                            f"[PROFIT ROLLBACK CLOSER >= $1.00] Ticket #{ticket} peaked at +${curr_peak:.2f} but rolled back to +${profit:.2f} "
                            f"(-${profit_reduction:.2f}) | Continuation check failed: {ass_reason} -> Closing immediately to bank +${profit:.2f} profit!"
                        )
                        self.close_position(ticket, symbol, reason=f"ProfitRollback_Peaked+${curr_peak:.2f}_Banked+${profit:.2f}")
                        continue
                    else:
                        logger.info(
                            f"[CONTINUATION ASSURED] Ticket #{ticket} profit at +${profit:.2f} (peaked +${curr_peak:.2f}) -> Holding trade: {ass_reason}"
                        )

            # Step 3: Partial Close 50% Position at 1:1 R:R (for multi-lot trades)
            if r_multiple >= 1.0 and not t_data.get("partial_closed", False):
                if volume >= 0.02:
                    half_vol = round(volume * 0.5, 2)
                    success = self.partial_close_position(ticket, symbol, half_vol, reason="PartialClose_1R_50pct")
                    t_data["partial_closed"] = True
                else:
                    logger.info(
                        f"[1:1 R:R HIT] Ticket #{ticket} reached +1.0R (+${profit:.2f}). "
                        f"Position is {volume} lot (min micro lot), breakeven locked and trailing stop activated."
                    )
                    t_data["partial_closed"] = True

            # Step 4: Dynamic Continuous Trailing Stop from +0.8R (Scaled to Trade Risk Distance)
            if r_multiple >= self.trailing_trigger_r and self.trailing_enabled:
                trailing_buffer = max(risk_dist * 0.50, self.trailing_dist)
                be_lock = max(self.be_offset, 0.25)
                if p_type == "BUY":
                    trail_sl = round(curr_price - trailing_buffer, digits)
                    if trail_sl > current_sl and trail_sl >= (open_price + be_lock):
                        logger.info(
                            f"[TRAILING STOP] BUY #{ticket} Profit +${profit:.2f} ({r_multiple:.2f}R) -> "
                            f"Trailing SL moved to {trail_sl:.2f} (buffer: ${trailing_buffer:.2f})"
                        )
                        self.update_sl_tp(ticket, symbol, trail_sl, current_tp)
                elif p_type == "SELL":
                    trail_sl = round(curr_price + trailing_buffer, digits)
                    if (current_sl == 0 or trail_sl < current_sl) and trail_sl <= (open_price - be_lock):
                        logger.info(
                            f"[TRAILING STOP] SELL #{ticket} Profit +${profit:.2f} ({r_multiple:.2f}R) -> "
                            f"Trailing SL moved to {trail_sl:.2f} (buffer: ${trailing_buffer:.2f})"
                        )
                        self.update_sl_tp(ticket, symbol, trail_sl, current_tp)

    def is_market_assuring_continuation(self, symbol: str, p_type: str) -> Tuple[bool, str]:
        """
        Evaluates whether the live 1-minute market price action is actively pushing
        in the trade's direction to justify holding through a minor pullback.
        """
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 10)
        if rates is None or len(rates) < 5:
            return False, "No candle data"

        df = pd.DataFrame(rates)
        df["ema7"] = df["close"].ewm(span=7, adjust=False).mean()
        latest = df.iloc[-1]
        prev = df.iloc[-2]

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return False, "No tick data"

        if p_type == "BUY":
            # Assuring continuation: Current price > EMA7, and current candle is pushing green or previous closed strong green
            is_above_ema7 = tick.bid >= latest["ema7"]
            is_pushing_higher = tick.bid >= prev["high"] or (latest["close"] >= latest["open"] and tick.bid >= prev["close"])
            if is_above_ema7 and is_pushing_higher:
                return True, f"Bullish continuation active (Bid {tick.bid:.2f} >= EMA7 {latest['ema7']:.2f})"
            else:
                return False, f"Momentum weakening (Bid {tick.bid:.2f} < EMA7 or forming pullback)"

        elif p_type == "SELL":
            # Assuring continuation: Current price < EMA7, and current candle is pushing red or previous closed strong red
            is_below_ema7 = tick.ask <= latest["ema7"]
            is_pushing_lower = tick.ask <= prev["low"] or (latest["close"] <= latest["open"] and tick.ask <= prev["close"])
            if is_below_ema7 and is_pushing_lower:
                return True, f"Bearish continuation active (Ask {tick.ask:.2f} <= EMA7 {latest['ema7']:.2f})"
            else:
                return False, f"Momentum weakening (Ask {tick.ask:.2f} > EMA7 or forming bounce)"

        return False, "Neutral"

    @staticmethod
    def _get_supported_filling_mode(symbol_info) -> int:
        """Determines best supported filling mode for broker (FOK, IOC, or RETURN)."""
        fillings = symbol_info.filling_mode
        if fillings & 2:
            return mt5.ORDER_FILLING_IOC
        if fillings & 1:
            return mt5.ORDER_FILLING_FOK
        return mt5.ORDER_FILLING_RETURN
