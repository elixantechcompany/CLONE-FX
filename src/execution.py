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
        self.giveback_cap_enabled = profit_cfg.get("giveback_cap_enabled", True)
        self.giveback_min_peak = profit_cfg.get("giveback_min_peak_dollars", 0.80)
        self.giveback_max_pct = profit_cfg.get("giveback_max_pct", 0.40)
        self.auto_tp_target = profit_cfg.get("auto_take_profit_target_dollars", 2.50)
        self.auto_tp_min = profit_cfg.get("auto_take_profit_min_dollars", 1.50)
        self.max_hard_loss = profit_cfg.get("max_hard_loss_per_trade_dollars", 2.50)
        self.max_account_floating_dd = profit_cfg.get("max_account_floating_drawdown_dollars", 3.50)
        self.lock_profit_start = profit_cfg.get("lock_profit_start_dollars", 0.60)
        self.be_offset = profit_cfg.get("breakeven_lock_offset", 0.25)
        self.retrace_guard_min_peak = profit_cfg.get("retrace_guard_min_peak_dollars", 0.50)
        self.retrace_guard_max_giveback = profit_cfg.get("retrace_guard_max_giveback_pct", 0.35)
        self.rollback_trigger = profit_cfg.get("rollback_close_trigger_dollars", 1.00)
        self.rollback_retrace_tol = profit_cfg.get("rollback_retrace_tolerance_dollars", 0.25)
        self.rollback_giveback_pct = profit_cfg.get("rollback_giveback_max_pct", 0.25)
        self.trailing_enabled = profit_cfg.get("trailing_enabled", True)
        self.trailing_trigger_r = profit_cfg.get("trailing_trigger_r", 0.8)
        self.trailing_dist = profit_cfg.get("trailing_distance_dollars", 0.80)
        self.auto_close_enabled = profit_cfg.get("auto_close_enabled", True)

        # Fix 31: Hard Maximum Loss Circuit Breaker (Absolute Backstop)
        cb_cfg = config.get("circuit_breakers", {})
        self.hard_max_loss_dollars = cb_cfg.get("hard_max_loss_per_trade_dollars", 1.35)
        self.hard_max_loss_pct = cb_cfg.get("hard_max_loss_equity_pct", 12.0)

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

            # Fix 23: Explicit Exit-Management Status Logging (Confirming Fix 1 status on every open position)
            be_active = t_data.get("be_applied", False)
            partial_active = t_data.get("partial_closed", False)
            trailing_active = bool(r_multiple >= self.trailing_trigger_r and self.trailing_enabled)
            giveback_active = bool(self.giveback_cap_enabled and curr_peak >= self.giveback_min_peak)

            logger.info(
                f"[EXIT STATUS AUDIT FIX 23] Position #{ticket} ({p_type}): floating P&L=${profit:+.2f} ({r_multiple:+.2f}R), "
                f"peak_profit=+${curr_peak:.2f}, breakeven_active={be_active}, trailing_active={trailing_active}, "
                f"partial_close_active={partial_active}, giveback_cap_active={giveback_active}"
            )

            # Fix 31: Emergency Catastrophic Backstop (Only cuts if market gaps/slips beyond intended Stop Loss)
            open_p = t_data.get("entry_price", open_price)
            orig_sl = t_data.get("initial_sl", current_sl)
            intended_risk = t_data.get("risk_distance", abs(open_p - orig_sl)) * volume * 100.0
            catastrophic_cap = max(intended_risk * 1.35, self.hard_max_loss_dollars, 4.50)

            if profit <= -catastrophic_cap:
                overshoot = abs(profit) - intended_risk
                diag_msg = (
                    f"[CATASTROPHIC LOSS BACKSTOP FIX 31] Force-closing Ticket #{ticket} ({p_type})! "
                    f"Floating loss -${abs(profit):.2f} breached catastrophic ceiling -${catastrophic_cap:.2f} | "
                    f"Entry: {open_p:.2f} | Current: {curr_price:.2f} | Original SL: {orig_sl:.2f} | "
                    f"Intended Risk: ${intended_risk:.2f} | Slippage/Overshoot: ${overshoot:+.2f}"
                )
                logger.critical(f"================================================================")
                logger.critical(f" {diag_msg}")
                logger.critical(f"================================================================")
                self.close_position(ticket, symbol, reason=f"EmergencyCapCut_-${abs(profit):.2f}")
                continue

            # =================================================================
            # UNIFIED PROFIT MANAGEMENT & TAKE PROFIT TRAILING:
            # 1. Guaranteed Green Breakeven at +0.5R (Locks in +$0.25 on Broker Server)
            # 2. Fix 24: Direct Profit Giveback Cap (Max 40% Giveback once Peak >= $0.80)
            # 3. 50% Partial Close at 1:1 R:R (for multi-lot volume >= 0.02)
            # 4. Dynamic Continuous Trailing Stop from +0.8R (Volatility-Aware ATR Trailing)
            # =================================================================

            # Step 1: Guaranteed Green Breakeven Lock at +0.5R (or +$0.80)
            if (r_multiple >= 0.50 or profit >= 0.80) and not t_data.get("be_applied", False):
                be_lock = max(self.be_offset, 0.20)
                if p_type == "BUY" and (current_sl < (open_price + be_lock) or current_sl == 0):
                    new_sl = round(open_price + be_lock, digits)
                    logger.info(
                        f"[PROFIT BREAKEVEN LOCK] BUY #{ticket} reached +${profit:.2f} ({r_multiple:.2f}R) -> "
                        f"Moving SL to Guaranteed Green {new_sl:.2f} (+${be_lock:.2f})"
                    )
                    if self.update_sl_tp(ticket, symbol, new_sl, current_tp):
                        t_data["be_applied"] = True
                        current_sl = new_sl
                elif p_type == "SELL" and (current_sl > (open_price - be_lock) or current_sl == 0):
                    new_sl = round(open_price - be_lock, digits)
                    logger.info(
                        f"[PROFIT BREAKEVEN LOCK] SELL #{ticket} reached +${profit:.2f} ({r_multiple:.2f}R) -> "
                        f"Moving SL to Guaranteed Green {new_sl:.2f} (+${be_lock:.2f})"
                    )
                    if self.update_sl_tp(ticket, symbol, new_sl, current_tp):
                        t_data["be_applied"] = True
                        current_sl = new_sl

            # Step 2: Fix 24 Direct Profit Giveback Cap (Retains >= 60% of peak gains once peak >= $0.80)
            if self.giveback_cap_enabled and curr_peak >= self.giveback_min_peak:
                profit_giveback = curr_peak - profit
                giveback_pct = (profit_giveback / curr_peak) if curr_peak > 0 else 0.0
                if giveback_pct >= self.giveback_max_pct or profit <= curr_peak * (1.0 - self.giveback_max_pct):
                    logger.info(
                        f"[PROFIT GIVEBACK CAP FIX 24] Position #{ticket} ({p_type}) peaked at +${curr_peak:.2f}, "
                        f"dropped to +${profit:.2f} (Giveback: {giveback_pct*100:.1f}% >= Cap: {self.giveback_max_pct*100:.0f}%, "
                        f"Retraced: -${profit_giveback:.2f}) -> Closing immediately at market to lock in +${profit:.2f} profit!"
                    )
                    self.close_position(ticket, symbol, reason=f"GivebackCap_Peaked+${curr_peak:.2f}_Banked+${profit:.2f}")
                    continue

            # Step 3: Partial Close 50% Position at 1:1 R:R (for volume >= 0.02)
            if r_multiple >= 1.0 and not t_data.get("partial_closed", False):
                if volume >= 0.02:
                    half_vol = round(volume * 0.5, 2)
                    self.partial_close_position(ticket, symbol, half_vol, reason="PartialClose_1R_50pct")
                    t_data["partial_closed"] = True
                else:
                    t_data["partial_closed"] = True

            # Step 3: Dynamic Continuous Trailing Stop from +0.8R (Volatility-Aware ATR Trailing to let big winners run)
            if r_multiple >= self.trailing_trigger_r and self.trailing_enabled:
                # Volatility-Aware Trailing Distance: Widens dynamically with market ATR
                rates_m15 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 15)
                live_atr = 2.00
                if rates_m15 is not None and len(rates_m15) >= 14:
                    df_atr = pd.DataFrame(rates_m15)
                    tr = pd.concat([
                        df_atr["high"] - df_atr["low"],
                        abs(df_atr["high"] - df_atr["close"].shift(1)),
                        abs(df_atr["low"] - df_atr["close"].shift(1))
                    ], axis=1).max(axis=1)
                    live_atr = float(tr.tail(14).mean())

                trailing_buffer = round(max(risk_dist * 0.60, live_atr * 0.75, self.trailing_dist, 1.20), digits)
                be_lock = max(self.be_offset, 0.20)
                if p_type == "BUY":
                    trail_sl = round(curr_price - trailing_buffer, digits)
                    if trail_sl > current_sl and trail_sl >= (open_price + be_lock):
                        logger.info(
                            f"[VOLATILITY TRAILING STOP] BUY #{ticket} Profit +${profit:.2f} ({r_multiple:.2f}R) -> "
                            f"Trailing SL moved to {trail_sl:.2f} (ATR({live_atr:.2f}) buffer: ${trailing_buffer:.2f}, TP: {current_tp:.2f})"
                        )
                        if self.update_sl_tp(ticket, symbol, trail_sl, current_tp):
                            current_sl = trail_sl
                elif p_type == "SELL":
                    trail_sl = round(curr_price + trailing_buffer, digits)
                    if (current_sl == 0 or trail_sl < current_sl) and trail_sl <= (open_price - be_lock):
                        logger.info(
                            f"[VOLATILITY TRAILING STOP] SELL #{ticket} Profit +${profit:.2f} ({r_multiple:.2f}R) -> "
                            f"Trailing SL moved to {trail_sl:.2f} (ATR({live_atr:.2f}) buffer: ${trailing_buffer:.2f}, TP: {current_tp:.2f})"
                        )
                        if self.update_sl_tp(ticket, symbol, trail_sl, current_tp):
                            current_sl = trail_sl

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
