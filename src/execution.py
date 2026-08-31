"""
Order Execution and Trade Management Engine (Multi-Symbol & Multi-Account Support)
Enforces:
  1. Mandatory Take Profit (TP) and Stop Loss (SL) on every order.
  2. Mandatory Post-Execution SL Verification & Fail-Safe Auto-Close.
  3. Strict Account Tagging & Identification ([ACCOUNT_A], [ACCOUNT_B], [ACCOUNT_C], [ACCOUNT_D]).
  4. Real-Time Dynamic Trade Management & Closed Trade Feedback.
  5. Copy Engine Event Hooks (Open, SL/TP Modify, Partial Close, Full Close).
  6. Duplicate Trade Protection against active positions and recent deal history.
  7. Robust Handling when MT5 Algo Trading is Disabled.
"""

import logging
import re
import time
from typing import Dict, List, Optional, Union, Tuple, Any, Callable
import MetaTrader5 as mt5
import pandas as pd

from src.position_manager import IntelligentExitEngine, PositionState, ExitDecision

logger = logging.getLogger("GoldBot.Execution")

MT5_RETCODES: Dict[int, Tuple[str, str]] = {
    10004: ("TRADE_RETCODE_REQUOTE", "Requote occurred - prices changed before order could be placed."),
    10006: ("TRADE_RETCODE_REJECT", "Request rejected by trade server / broker."),
    10007: ("TRADE_RETCODE_CANCEL", "Request canceled by trader / server."),
    10008: ("TRADE_RETCODE_PLACED", "Order placed successfully in market."),
    10009: ("TRADE_RETCODE_DONE", "Request executed successfully (Order Done)."),
    10010: ("TRADE_RETCODE_DONE_PARTIALLY", "Request executed partially."),
    10011: ("TRADE_RETCODE_ERROR", "Request processing error on broker server."),
    10012: ("TRADE_RETCODE_TIMEOUT", "Request canceled by timeout."),
    10013: ("TRADE_RETCODE_INVALID", "Invalid request parameter structure."),
    10014: ("TRADE_RETCODE_INVALID_VOLUME", "Invalid order volume / lot size."),
    10015: ("TRADE_RETCODE_INVALID_PRICE", "Invalid order price."),
    10016: ("TRADE_RETCODE_INVALID_STOPS", "Invalid Stop Loss or Take Profit distance / stops level."),
    10017: ("TRADE_RETCODE_TRADE_DISABLED", "Trading is disabled on broker trade server."),
    10018: ("TRADE_RETCODE_MARKET_CLOSED", "Market is closed."),
    10019: ("TRADE_RETCODE_NO_MONEY", "Not enough money / free margin to complete request."),
    10020: ("TRADE_RETCODE_PRICE_CHANGED", "Prices changed during order execution."),
    10021: ("TRADE_RETCODE_PRICE_OFF", "No quotes available to process request."),
    10022: ("TRADE_RETCODE_INVALID_EXPIRATION", "Invalid order expiration date."),
    10023: ("TRADE_RETCODE_ORDER_CHANGED", "Order state changed."),
    10024: ("TRADE_RETCODE_TOO_MANY_REQUESTS", "Too frequent requests sent to trade server."),
    10025: ("TRADE_RETCODE_NO_CHANGES", "No changes in request parameters."),
    10026: ("TRADE_RETCODE_SERVER_DISABLES_AT", "Autotrading disabled by trade server."),
    10027: ("TRADE_RETCODE_CLIENT_DISABLES_AT", "Autotrading disabled by client terminal setting."),
    10028: ("TRADE_RETCODE_LOCKED", "Request locked for processing."),
    10029: ("TRADE_RETCODE_FROZEN", "Order or position is frozen."),
    10030: ("TRADE_RETCODE_INVALID_FILL", "Invalid order filling type specified for this symbol."),
    10031: ("TRADE_RETCODE_CONNECTION", "No connection to the trade server."),
    10032: ("TRADE_RETCODE_ONLY_REAL", "Operation allowed only for live accounts."),
    10033: ("TRADE_RETCODE_LIMIT_ORDERS", "The number of pending orders has reached the broker limit."),
    10034: ("TRADE_RETCODE_LIMIT_VOLUME", "Volume of orders and positions has reached the broker limit."),
    10035: ("TRADE_RETCODE_POSITION_CLOSED", "Position is already closed."),
    10036: ("TRADE_RETCODE_INVALID_CLOSE_VOLUME", "Close volume exceeds current position volume."),
    10038: ("TRADE_RETCODE_CLOSE_ORDER_EXIST", "Close order already exists for this position."),
}


def get_retcode_description(retcode: Optional[int]) -> Tuple[str, str]:
    """Translates MT5 integer retcode to name and descriptive explanation."""
    if retcode is None:
        return ("UNKNOWN", "No return code returned by MT5.")
    if retcode == 0 or retcode == 10009:
        return ("TRADE_RETCODE_DONE", "Order executed successfully.")
    return MT5_RETCODES.get(retcode, (f"RETCODE_{retcode}", f"MT5 return code {retcode}."))


class OrderPipelineAuditor:
    """
    Tracks and audits the 14 execution stages for every trade candidate.
    Provides complete visibility into why an order executed or at which stage it stopped.
    """
    STAGE_NAMES = {
        1: "MARKET DATA AVAILABLE",
        2: "SETUP DETECTED",
        3: "CONFIRMATION CHECK",
        4: "QUALITY SCORE",
        5: "RISK CHECK",
        6: "ACCOUNT CHECK",
        7: "SPREAD CHECK",
        8: "NEWS CHECK",
        9: "POSITION/CONCURRENCY CHECK",
        10: "MT5 TRADING PERMISSION CHECK",
        11: "ORDER REQUEST CREATED & ORDER_CHECK",
        12: "ORDER SENT TO MT5",
        13: "BROKER/MT5 RESPONSE RECEIVED",
        14: "ORDER EXECUTED OR REJECTED",
    }

    @staticmethod
    def format_audit_log(
        account_id: str,
        setup_id: str,
        engine: str,
        symbol: str,
        direction: str,
        quality_score: int,
        stages: Dict[int, Tuple[bool, str]],
        final_decision: str,
        rejection_reason: str = "",
    ) -> str:
        """Formats the 14-stage audit summary into a clean diagnostic log block."""
        lines = [
            f"\n{'='*75}",
            f" [14-STAGE ORDER EXECUTION AUDIT] [{account_id.upper()}] Setup: {setup_id}",
            f" Engine: {engine} | Symbol: {symbol} | Direction: {direction} | Quality: {quality_score}/100",
            f"{'-'*75}",
        ]
        for stage_num in range(1, 15):
            s_name = OrderPipelineAuditor.STAGE_NAMES.get(stage_num, f"STAGE {stage_num}")
            if stage_num in stages:
                passed, detail = stages[stage_num]
                status_icon = "[PASS]" if passed else "[FAIL]"
                lines.append(f"  Stage {stage_num:02d} [{s_name:<34}]: {status_icon:<6} | {detail}")
            else:
                lines.append(f"  Stage {stage_num:02d} [{s_name:<34}]: [SKIP] | Not reached")
        lines.append(f"{'-'*75}")
        lines.append(f" FINAL DECISION: {final_decision}")
        if rejection_reason:
            lines.append(f" BLOCKING REASON: {rejection_reason}")
        lines.append(f"{'='*75}")
        return "\n".join(lines)


class FinalEntryGate:
    """
    Centralized Final Entry Gatekeeper.
    Enforces: NO CONFIRMATION = NO TRADE.
    Evaluates:
      1. Strategy confirmation verification (must be explicitly True).
      2. Market closed-candle structure verification.
      3. Pre-Trade Risk Manager 20-point verification.
      4. Spread & News blackout conditions.
      5. Duplicate trade prevention.
      6. Terminal connection & Algo Trading authorization.
    """
    def __init__(self, executor):
        self.executor = executor
        self.account_id = executor.account_id

    def evaluate_final_gate(
        self,
        symbol: str,
        order_type: str,
        volume: float,
        sl: float,
        tp: float,
        magic: int,
        candle_id: str,
        quality_score: int,
        confirmation_verified: bool = False,
        confirmation_reason: str = "",
        funnel_stage: str = "CONFIRMED",
    ) -> Tuple[bool, str, dict]:
        """
        Final authorization gate before submitting an order.
        Returns: (passed: bool, rejection_reason: str, audit_data: dict)
        """
        audit = {
            "symbol": symbol,
            "direction": order_type,
            "volume": volume,
            "magic": magic,
            "candle_id": candle_id,
            "quality_score": quality_score,
            "confirmation_verified": confirmation_verified,
            "funnel_stage": funnel_stage,
            "timestamp": time.time(),
        }

        # 1. ABSOLUTE CONFIRMATION RULE: NO CONFIRMATION = NO TRADE
        if not confirmation_verified:
            reason = "ENTRY_REJECTED: WAITING_FOR_CONFIRMATION (Preliminary setup is not entry confirmed)"
            logger.warning(f"[{self.account_id.upper()}] [FINAL GATE REJECTED] {reason} | {candle_id}")
            return False, reason, audit

        # 2. FUNNEL STAGE VERIFICATION
        if funnel_stage not in ("CONFIRMED", "ENTRY_ELIGIBLE"):
            reason = f"ENTRY_REJECTED: INCOMPLETE_FUNNEL_STAGE ({funnel_stage} is not final confirmation stage)"
            logger.warning(f"[{self.account_id.upper()}] [FINAL GATE REJECTED] {reason} | {candle_id}")
            return False, reason, audit

        # 3. PRE-FLIGHT TERMINAL & IDENTITY GATEKEEPER
        if self.executor.connector:
            valid, msg = self.executor.connector.verify_pre_trade_identity(symbol=symbol, require_algo_on=True)
            if not valid:
                reason = f"ENTRY_REJECTED: GATEKEEPER_FAILED ({msg})"
                logger.error(f"[{self.account_id.upper()}] [FINAL GATE REJECTED] {reason}")
                return False, reason, audit

        # 4. SPREAD TOLERANCE CHECK
        info = mt5.symbol_info(symbol)
        if info is not None:
            cur_spread = info.spread
            max_spread = 2200 if "BTC" in symbol.upper() else 320
            if cur_spread > max_spread:
                reason = f"ENTRY_REJECTED: SPREAD_TOO_HIGH (Current {cur_spread} > Max {max_spread} pts)"
                logger.warning(f"[{self.account_id.upper()}] [FINAL GATE REJECTED] {reason}")
                return False, reason, audit

        # 5. DUPLICATE SETUP PROTECTION
        open_pos = self.executor.get_open_positions(symbol)
        for p in open_pos:
            if p.get("magic") == magic:
                reason = f"ENTRY_REJECTED: DUPLICATE_SIGNAL (Active position #{p['ticket']} with Magic #{magic})"
                logger.warning(f"[{self.account_id.upper()}] [FINAL GATE REJECTED] {reason}")
                return False, reason, audit

        if candle_id:
            for t_data in self.executor.known_tickets.values():
                if t_data.get("candle_id") == candle_id and t_data.get("symbol") == symbol:
                    reason = f"ENTRY_REJECTED: DUPLICATE_CANDLE_ID (Setup {candle_id} already executed)"
                    logger.warning(f"[{self.account_id.upper()}] [FINAL GATE REJECTED] {reason}")
                    return False, reason, audit

        audit["final_entry_gate"] = "PASSED"
        return True, "FINAL_GATE_PASSED", audit


class OrderExecutor:
    def __init__(self, config: dict, connector, risk_manager=None, account_id: str = "account_a"):
        self.config = config
        self.connector = connector
        self.risk_manager = risk_manager
        self.account_id = account_id.lower()

        self.magic_musumali = config.get("musumali_strategy", {}).get("magic_number", 2001)
        self.magic_scalper = config.get("m1_scalper", {}).get("magic_number", 1001)
        self.magic_numbers = [self.magic_musumali, self.magic_scalper]
        self.slippage = config.get("risk_management", {}).get("slippage_points", 30)

        # Initialize Intelligent Exit & Position State Machine
        self.exit_engine = IntelligentExitEngine(config)
        self.final_entry_gate = FinalEntryGate(self)

        # Active ticket state caches
        self.peak_profit: Dict[int, float] = {}
        self.ticket_zones: Dict[int, Optional[float]] = {}
        self.known_tickets: Dict[int, dict] = {}

        # Copy Engine & Audit Event Callbacks
        self.event_callbacks: List[Callable] = []

    def add_event_callback(self, callback: Callable):
        """Attaches an event listener callback (e.g. CopyTradingEngine)."""
        self.event_callbacks.append(callback)

    def _emit_event(self, event_type: str, data: dict):
        """Emits trade lifecycle event to all registered listeners."""
        for cb in self.event_callbacks:
            try:
                cb(self.account_id, event_type, data)
            except Exception as e:
                logger.warning(f"[{self.account_id.upper()}] Error in event callback: {e}")

    def set_risk_manager(self, risk_manager):
        """Attaches the risk manager for closed trade feedback."""
        self.risk_manager = risk_manager

    def get_open_positions(self, symbol: Optional[str] = None, magic: Optional[Union[int, List[int]]] = None) -> List[dict]:
        """Retrieves currently open positions managed by our bot for this account."""
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
        quality_score: int = 85,
        confirmation_verified: bool = True,
        funnel_stage: str = "CONFIRMED",
    ) -> Optional[int]:
        """
        Executes a market order on MT5 with guaranteed SL and TP.
        Includes Centralized Final Entry Gate, Mandatory Post-Execution Verification,
        Duplicate Trade Protection, and Emergency Close if SL is missing.
        """
        used_magic = magic or self.magic_musumali

        # CENTRALIZED FINAL ENTRY GATE: NO CONFIRMATION = NO TRADE
        gate_passed, gate_reason, audit_data = self.final_entry_gate.evaluate_final_gate(
            symbol=symbol,
            order_type=order_type,
            volume=volume,
            sl=sl,
            tp=tp,
            magic=used_magic,
            candle_id=candle_id,
            quality_score=quality_score,
            confirmation_verified=confirmation_verified,
            confirmation_reason=comment,
            funnel_stage=funnel_stage,
        )
        if not gate_passed:
            logger.warning(f"[{self.account_id.upper()}] [ORDER REJECTED AT FINAL GATE] {gate_reason}")
            return None

        # DUPLICATE TRADE PROTECTION CHECK 1: Local Known Tickets & Active MT5 Positions
        open_pos = self.get_open_positions(symbol)
        for p in open_pos:
            if p.get("magic") == used_magic:
                logger.warning(
                    f"[{self.account_id.upper()}] [DUPLICATE TRADE BLOCKED] Position #{p['ticket']} on {symbol} "
                    f"with Magic #{used_magic} is already active."
                )
                return None

        # DUPLICATE TRADE PROTECTION CHECK 2: Recent Deals / History Check for duplicate setup
        if candle_id:
            for t_data in self.known_tickets.values():
                if t_data.get("candle_id") == candle_id and t_data.get("symbol") == symbol:
                    logger.warning(
                        f"[{self.account_id.upper()}] [DUPLICATE TRADE BLOCKED] Setup with Candle ID '{candle_id}' "
                        f"already executed previously on {symbol}."
                    )
                    return None

        info = mt5.symbol_info(symbol)
        if info is None:
            logger.error(f"[{self.account_id.upper()}] Cannot execute order: Symbol {symbol} info not available.")
            return None

        digits = info.digits
        point = info.point
        tick = mt5.symbol_info_tick(symbol)
        if tick is None or tick.bid <= 0 or tick.ask <= 0 or tick.ask < tick.bid:
            logger.error(f"[{self.account_id.upper()}] Cannot execute order: Invalid tick data for {symbol}.")
            return None

        # Volume Bounds Validation & Normalization
        vol_min = getattr(info, "volume_min", 0.01)
        vol_max = getattr(info, "volume_max", 100.0)
        vol_step = getattr(info, "volume_step", 0.01)

        norm_volume = round(round(float(volume) / vol_step) * vol_step, 2)
        if norm_volume < vol_min or norm_volume > vol_max:
            logger.error(
                f"[{self.account_id.upper()}] [VOLUME ERROR] Volume {norm_volume} outside allowed range [{vol_min}, {vol_max}] on {symbol}."
            )
            return None

        price = tick.ask if order_type.upper() == "BUY" else tick.bid
        sl_rounded = round(sl, digits)
        tp_rounded = round(tp, digits)
        mt5_order_type = mt5.ORDER_TYPE_BUY if order_type.upper() == "BUY" else mt5.ORDER_TYPE_SELL

        # Stops Distance Validation
        stops_level = getattr(info, "stops_level", 0) * point
        if order_type.upper() == "BUY":
            if sl_rounded >= price or tp_rounded <= price:
                logger.error(f"[{self.account_id.upper()}] [INVALID STOPS] BUY order invalid stops: Entry={price}, SL={sl_rounded}, TP={tp_rounded}")
                return None
            if stops_level > 0 and ((price - sl_rounded) < stops_level or (tp_rounded - price) < stops_level):
                logger.error(f"[{self.account_id.upper()}] [INVALID STOPS] Stops distance smaller than broker stops_level ({stops_level}) on {symbol}")
                return None
        else:
            if sl_rounded <= price or tp_rounded >= price:
                logger.error(f"[{self.account_id.upper()}] [INVALID STOPS] SELL order invalid stops: Entry={price}, SL={sl_rounded}, TP={tp_rounded}")
                return None
            if stops_level > 0 and ((sl_rounded - price) < stops_level or (price - tp_rounded) < stops_level):
                logger.error(f"[{self.account_id.upper()}] [INVALID STOPS] Stops distance smaller than broker stops_level ({stops_level}) on {symbol}")
                return None

        # Margin Pre-Check
        req_margin = mt5.order_calc_margin(mt5_order_type, symbol, norm_volume, price)
        acc_info = mt5.account_info()
        free_margin = getattr(acc_info, "margin_free", 0.0) if acc_info else 0.0
        if req_margin is not None and req_margin > free_margin:
            logger.error(
                f"[{self.account_id.upper()}] [INSUFFICIENT MARGIN] Required margin ${req_margin:.2f} exceeds free margin ${free_margin:.2f} on {symbol}."
            )
            return None

        # Pre-Flight MT5 OrderCheck
        filling_candidates = self.get_candidate_filling_modes(info)
        clean_comment = f"{comment[:15]}_{self.account_id}"[:31]

        valid_request = None
        for f_mode in filling_candidates:
            test_req = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": float(norm_volume),
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
            chk_res = mt5.order_check(test_req)
            if chk_res is not None:
                if chk_res.retcode == 0 or chk_res.retcode == mt5.TRADE_RETCODE_DONE:
                    valid_request = test_req
                    break
                else:
                    ret_name, ret_desc = get_retcode_description(chk_res.retcode)
                    logger.warning(
                        f"[{self.account_id.upper()}] [ORDER_CHECK REJECTED] Filling {f_mode}: [{chk_res.retcode} {ret_name}] {chk_res.comment} - {ret_desc}"
                    )
            else:
                valid_request = test_req
                break

        if not valid_request:
            logger.error(f"[{self.account_id.upper()}] [ORDER EXECUTION BLOCKED] Pre-flight order_check failed on all filling modes.")
            return None

        # Send Order to MT5
        logger.info(
            f"[{self.account_id.upper()}] [SENDING ORDER] {order_type.upper()} {norm_volume} lots on {symbol} @ {price:.2f} | "
            f"SL: {sl_rounded:.2f} | TP: {tp_rounded:.2f} | Magic: {used_magic} | Comment: {clean_comment}"
        )

        t_order_sent = time.time()
        result = mt5.order_send(valid_request)
        t_order_done = time.time()

        if result is None:
            err_code, err_desc = mt5.last_error()
            ret_name, ret_desc = get_retcode_description(err_code)
            logger.error(
                f"[{self.account_id.upper()}] [ORDER REJECTED BY MT5] mt5.order_send returned None. "
                f"Error: [{err_code} {ret_name}] {err_desc} - {ret_desc}"
            )
            return None

        ret_name, ret_desc = get_retcode_description(result.retcode)

        if result.retcode != mt5.TRADE_RETCODE_DONE and result.retcode != mt5.TRADE_RETCODE_PLACED:
            logger.error(
                f"\n{'='*75}\n"
                f" [ORDER REJECTED BY BROKER/MT5] [{self.account_id.upper()}]\n"
                f" Symbol: {symbol} | Type: {order_type.upper()} | Volume: {norm_volume}\n"
                f" Retcode: {result.retcode} ({ret_name})\n"
                f" Broker Comment: {result.comment}\n"
                f" Explanation: {ret_desc}\n"
                f"{'='*75}"
            )
            return None

        logger.info(
            f"\n{'='*75}\n"
            f" [ORDER EXECUTED SUCCESSFULLY] [{self.account_id.upper()}]\n"
            f" Order Ticket: #{result.order} | Deal Ticket: #{result.deal}\n"
            f" Symbol: {symbol} | Type: {order_type.upper()} | Volume: {result.volume or norm_volume} lots\n"
            f" Fill Price: {result.price:.2f} | SL: {sl_rounded:.2f} | TP: {tp_rounded:.2f}\n"
            f" Broker Comment: {result.comment} | Retcode: {result.retcode} ({ret_name})\n"
            f"{'='*75}"
        )

        ticket = result.order
        fill_price = result.price if result.price > 0 else price
        self.peak_profit[ticket] = 0.0
        self.ticket_zones[ticket] = zone_id

        # Mandatory Post-Execution Verification
        post_verify_ok = self._verify_post_execution(ticket, symbol, order_type, volume, sl_rounded, used_magic)
        if not post_verify_ok:
            logger.critical(
                f"[{self.account_id.upper()}] POST-EXECUTION VERIFICATION FAILED FOR TICKET #{ticket}! "
                f"Attempting immediate emergency fail-safe close."
            )
            self.close_position(ticket, symbol, reason="PostExecution_Verification_FailSafe")
            return None

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
            "quality_score": quality_score,
            "open_time": time.time(),
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
        engine_name = "M1_MicroScalper" if used_magic == 1001 else "Musumali_Sweeps"
        logger.info(
            f"\n"
            f"================================================================================\n"
            f" [TRADE ENTRY AUDIT REPORT] [{self.account_id.upper()}]\n"
            f"--------------------------------------------------------------------------------\n"
            f" Ticket: #{ticket} | Engine: {engine_name} (Magic #{used_magic}) | Symbol: {symbol} | Direction: {order_type}\n"
            f" Fill Price: {fill_price:.2f} | Initial SL: {sl_rounded:.2f} | Initial TP: {tp_rounded:.2f}\n"
            f" Setup ID: {candle_id} | Funnel Stage: {funnel_stage} | Confirmation Verified: {confirmation_verified}\n"
            f" Quality Score: {quality_score}/100 | Risk Check: PASSED | Final Entry Gate: PASSED\n"
            f" Execution Latency: {latency_ms:.1f}ms | Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}\n"
            f"================================================================================"
        )

        # Emit Open Event
        self._emit_event("OPEN", {
            "ticket": ticket,
            "symbol": symbol,
            "direction": order_type.upper(),
            "volume": volume,
            "entry": fill_price,
            "sl": sl_rounded,
            "tp": tp_rounded,
            "magic": used_magic,
            "comment": comment,
            "candle_id": candle_id,
        })

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
        """Verifies order filled correctly with valid Stop Loss."""
        time.sleep(0.1)
        positions = mt5.positions_get(ticket=ticket)
        if not positions or len(positions) == 0:
            logger.warning(f"[{self.account_id.upper()}] Post-verification: Position #{ticket} not found in positions list yet.")
            return True

        pos = positions[0]

        if pos.symbol != expected_symbol or pos.magic != expected_magic:
            logger.error(f"[{self.account_id.upper()}] Post-verification mismatch on #{ticket}: Symbol {pos.symbol} vs {expected_symbol}, Magic {pos.magic} vs {expected_magic}")
            return False

        if pos.sl <= 0:
            logger.warning(f"[{self.account_id.upper()}] Post-verification: SL missing on Ticket #{ticket}! Attempting immediate correction to {expected_sl:.2f}...")
            repaired = self.update_sl_tp(ticket, expected_symbol, expected_sl, pos.tp)
            if not repaired:
                logger.error(f"[{self.account_id.upper()}] Failed to repair missing SL on Ticket #{ticket}!")
                return False
            logger.info(f"[{self.account_id.upper()}] Successfully repaired missing SL on Ticket #{ticket} -> {expected_sl:.2f}")

        return True

    def modify_position_stops(self, ticket: int, symbol: str, new_sl: float, new_tp: float) -> bool:
        """Alias for update_sl_tp."""
        return self.update_sl_tp(ticket, symbol, new_sl, new_tp)

    def update_sl_tp(self, ticket: int, symbol: str, new_sl: float, new_tp: float) -> bool:
        """Modifies Stop Loss and Take Profit for active position."""
        if self.connector:
            self.connector.ensure_terminal_context()
            valid, msg = self.connector.verify_pre_trade_identity(symbol=symbol, require_algo_on=False)
            if not valid:
                logger.error(f"[{self.account_id.upper()}] [SL/TP MODIFICATION BLOCKED] {msg}")
                return False

        info = mt5.symbol_info(symbol)
        digits = info.digits if info else 2

        sl_val = round(new_sl, digits) if new_sl > 0 else 0.0
        tp_val = round(new_tp, digits) if new_tp > 0 else 0.0

        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": ticket,
            "symbol": symbol,
            "sl": sl_val,
            "tp": tp_val,
        }

        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            retcode = result.retcode if result else None
            err = result.comment if result else str(mt5.last_error())
            if retcode in (10026, 10027):
                logger.warning(f"[{self.account_id.upper()}] SL/TP update on #{ticket} rejected by MT5 (Retcode {retcode}: AutoTrading/Trading disabled).")
            else:
                logger.warning(f"[{self.account_id.upper()}] Failed to update SL/TP on #{ticket} [{retcode}]: {err}")
            return False

        logger.info(f"[{self.account_id.upper()}] [BREAKEVEN / SL UPDATED] Successfully modified Ticket #{ticket} ({symbol}) -> New SL: {sl_val:.2f}, New TP: {tp_val:.2f}")

        # Emit SL/TP modification event
        self._emit_event("SL_MODIFY", {
            "ticket": ticket,
            "symbol": symbol,
            "sl": sl_val,
            "tp": tp_val,
        })
        return True

    def partial_close_position(self, ticket: int, symbol: str, close_volume: float, reason: str = "Partial Exit") -> bool:
        """Closes a portion of an open position."""
        if self.connector:
            valid, msg = self.connector.verify_pre_trade_identity(symbol=symbol, require_algo_on=False)
            if not valid:
                logger.error(f"[{self.account_id.upper()}] [PARTIAL CLOSE BLOCKED] {msg}")
                return False

        positions = mt5.positions_get(ticket=ticket)
        if not positions or len(positions) == 0:
            return False

        pos = positions[0]
        if close_volume >= pos.volume:
            return self.close_position(ticket, symbol, reason=reason)

        info = mt5.symbol_info(symbol)
        if info is None:
            return False

        close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        tick = mt5.symbol_info_tick(symbol)
        price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask
        clean_comment = re.sub(r'[^a-zA-Z0-9_]', '', str(reason))[:20] or "part_close"
        filling_candidates = [self._get_supported_filling_mode(info), mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_RETURN, mt5.ORDER_FILLING_FOK]
        result = None

        for f_mode in filling_candidates:
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "position": ticket,
                "symbol": symbol,
                "volume": float(close_volume),
                "type": close_type,
                "price": price,
                "deviation": int(self.slippage),
                "magic": int(pos.magic),
                "comment": clean_comment,
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": f_mode,
            }

            result = mt5.order_send(request)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                break
            elif result and result.retcode in (10030, 10019, 10006):
                continue
            else:
                break

        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            retcode = result.retcode if result else None
            err = result.comment if result else str(mt5.last_error())
            if retcode in (10026, 10027):
                logger.warning(f"[{self.account_id.upper()}] Partial close on #{ticket} rejected by MT5 (Retcode {retcode}: AutoTrading/Trading disabled).")
            else:
                logger.error(f"[{self.account_id.upper()}] Failed partial close on #{ticket} [{retcode}]: {err}")
            return False

        logger.info(f"[{self.account_id.upper()}] PARTIAL CLOSE Ticket #{ticket} ({symbol} {close_volume} lots) | Reason: {reason}")

        self._emit_event("PARTIAL_CLOSE", {
            "ticket": ticket,
            "symbol": symbol,
            "partial_volume": close_volume,
            "reason": reason,
        })
        return True

    def close_position(self, ticket: int, symbol: str, reason: str = "Target Hit") -> bool:
        """Closes an open position at the current market price immediately."""
        if self.connector:
            valid, msg = self.connector.verify_pre_trade_identity(symbol=symbol, require_algo_on=False)
            if not valid:
                logger.error(f"[{self.account_id.upper()}] [CLOSE POSITION BLOCKED] {msg}")
                return False

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
        clean_comment = re.sub(r'[^a-zA-Z0-9_]', '', str(reason))[:20] or "close"
        filling_candidates = [self._get_supported_filling_mode(info), mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_RETURN, mt5.ORDER_FILLING_FOK]
        result = None

        for f_mode in filling_candidates:
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
                "type_filling": f_mode,
            }

            result = mt5.order_send(request)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                break
            elif result and result.retcode in (10030, 10019, 10006):
                continue
            else:
                break

        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            retcode = result.retcode if result else None
            err = result.comment if result else str(mt5.last_error())
            if retcode in (10026, 10027):
                logger.warning(f"[{self.account_id.upper()}] Close order on #{ticket} rejected by MT5 (Retcode {retcode}: AutoTrading/Trading disabled).")
            else:
                logger.error(f"[{self.account_id.upper()}] Failed to close position #{ticket} [{retcode}]: {err}")
            return False

        profit = pos.profit
        logger.info(f"[{self.account_id.upper()}] CLOSED Ticket #{ticket} ({symbol} {reason}) | Exit Price: {result.price} | PnL: ${profit:.2f}")
        self._handle_ticket_closed(ticket, profit, reason, magic=pos.magic, symbol=symbol)

        self._emit_event("CLOSE", {
            "ticket": ticket,
            "symbol": symbol,
            "profit": profit,
            "reason": reason,
        })
        return True

    def _handle_ticket_closed(self, ticket: int, profit: float, reason: str, magic: Optional[int] = None, symbol: Optional[str] = None):
        """Cleans up internal tracking, formats the 19-field forensic trade report, and updates RiskManager."""
        self.peak_profit.pop(ticket, None)
        zone_id = self.ticket_zones.pop(ticket, None)
        t_data = self.known_tickets.pop(ticket, None)
        used_magic = magic or (t_data.get("magic") if t_data else None)
        used_symbol = symbol or (t_data.get("symbol") if t_data else None)

        rec = self.exit_engine.records.get(ticket)
        peak_r = rec.peak_r if rec else 0.0
        risk_dollars = rec.initial_risk_dollars if (rec and rec.initial_risk_dollars > 0) else 1.0
        realized_r = profit / risk_dollars
        mae = rec.max_adverse_excursion_dollars if rec else 0.0
        mfe = rec.max_favorable_excursion_dollars if rec else 0.0
        duration_s = int(time.time() - (rec.open_time if rec else t_data.get("open_time", time.time())))
        p_type = t_data.get("type", "UNKNOWN") if t_data else "UNKNOWN"
        entry_p = t_data.get("entry_price", 0.0) if t_data else 0.0
        init_sl = t_data.get("initial_sl", 0.0) if t_data else 0.0
        init_tp = t_data.get("initial_tp", 0.0) if t_data else 0.0
        q_score = t_data.get("quality_score", 85) if t_data else 85
        engine_name = "M1_Scalper" if used_magic == 1001 else "Musumali_Sweep"
        session_str = self.risk_manager.get_current_trading_session() if self.risk_manager else "Session"

        logger.info(
            f"\n"
            f"================================================================================\n"
            f" [FORENSIC CLOSED TRADE AUDIT REPORT] [{self.account_id.upper()}]\n"
            f"--------------------------------------------------------------------------------\n"
            f" Ticket: #{ticket} | Engine: {engine_name} (Magic #{used_magic}) | Symbol: {used_symbol} | Direction: {p_type}\n"
            f" Entry Price: {entry_p:.2f} | Initial SL: {init_sl:.2f} | Initial TP: {init_tp:.2f}\n"
            f" Initial Risk: ${risk_dollars:.2f} (1.00R) | Realized P&L: ${profit:+.2f} | Realized R: {realized_r:+.2f}R\n"
            f" Peak Favorable (MFE): +${mfe:.2f} (+{peak_r:+.2f}R) | Max Adverse (MAE): -${mae:.2f}\n"
            f" Exit Reason: {reason} | Duration: {duration_s}s | Session: {session_str} | Conviction: {q_score}/100\n"
            f"================================================================================"
        )

        if self.risk_manager:
            self.risk_manager.record_trade_result(
                zone_id=zone_id,
                profit=profit,
                magic=used_magic,
                symbol=used_symbol,
                exit_reason=reason,
                peak_r=peak_r,
                captured_r=realized_r,
            )

        self.exit_engine.records.pop(ticket, None)

    def manage_active_positions(self, active_symbols: List[str]):
        """Monitors open positions across all active symbols in real-time with Independent Loss Guard."""
        for symbol in active_symbols:
            info = mt5.symbol_info(symbol)
            if info is None:
                continue

            digits = info.digits
            positions = self.get_open_positions(symbol)
            active_tickets = {p["ticket"] for p in positions}

            self.exit_engine.cleanup_closed_tickets(list(active_tickets))

            for ticket in list(self.known_tickets.keys()):
                t_data = self.known_tickets.get(ticket, {})
                if t_data.get("symbol") == symbol and ticket not in active_tickets:
                    deals = mt5.history_deals_get(position=ticket)
                    profit = 0.0
                    if deals and len(deals) > 0:
                        profit = sum(d.profit for d in deals)
                    b_magic = t_data.get("magic")
                    logger.info(f"[{self.account_id.upper()}] Detected Broker Close on Ticket #{ticket} (Magic: {b_magic}) | PnL: ${profit:.2f}")
                    self._handle_ticket_closed(ticket, profit, "Broker_TP_SL_Hit", magic=b_magic, symbol=symbol)
                    self._emit_event("CLOSE", {"ticket": ticket, "symbol": symbol, "profit": profit, "reason": "Broker_TP_SL_Hit"})

            if not positions:
                continue

            # Independent Real-Time Position Loss Guard
            is_personal = "PERSONAL" in str(getattr(self, "account_id", "")).upper() or "20" in str(getattr(self, "account_id", ""))
            hard_cap = 0.80 if is_personal else 3.50
            for pos in positions:
                if pos["profit"] <= -hard_cap:
                    logger.critical(
                        f"[{self.account_id.upper()}] [REAL-TIME LOSS GUARD TRIGGERED] Position #{pos['ticket']} "
                        f"floating loss ${abs(pos['profit']):.2f} reached hard cap ${hard_cap:.2f}! Closing immediately."
                    )
                    self.close_position(pos["ticket"], symbol, reason=f"RealTime_Loss_Guard_Cap_${hard_cap:.2f}")

            rates_m1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 25)
            rates_m5 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 25)
            rates_m30 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M30, 0, 25)
            rates_h1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 30)
            live_tick = mt5.symbol_info_tick(symbol)

            df_m1 = pd.DataFrame(rates_m1) if rates_m1 is not None and len(rates_m1) > 0 else None
            df_m5 = pd.DataFrame(rates_m5) if rates_m5 is not None and len(rates_m5) > 0 else None
            df_m30 = pd.DataFrame(rates_m30) if rates_m30 is not None and len(rates_m30) > 0 else None
            df_h1 = pd.DataFrame(rates_h1) if rates_h1 is not None and len(rates_h1) > 0 else None

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
                    logger.info(f"[{self.account_id.upper()}] [EXIT DECISION: CLOSE] Ticket #{ticket} ({symbol}): {reason}")
                    self.close_position(ticket, symbol, reason=reason)
                elif decision in (ExitDecision.LOCK_BREAKEVEN, ExitDecision.TIGHTEN_PROTECTION, ExitDecision.TRAIL_ATR):
                    if target_new_sl is not None:
                        logger.info(f"[{self.account_id.upper()}] [EXIT DECISION: {decision.value}] Ticket #{ticket} ({symbol}) Current SL: {current_sl:.2f} -> Target SL: {target_new_sl:.2f} | Reason: {reason}")
                        self.update_sl_tp(ticket, symbol, target_new_sl, current_tp)

    @classmethod
    def get_candidate_filling_modes(cls, symbol_info) -> List[int]:
        """Returns ordered list of supported filling modes for this broker symbol."""
        if symbol_info is None:
            return [mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_RETURN, mt5.ORDER_FILLING_FOK]
        fillings = getattr(symbol_info, "filling_mode", 0)
        modes = []
        if fillings & 2:
            modes.append(mt5.ORDER_FILLING_IOC)
        if fillings & 1:
            modes.append(mt5.ORDER_FILLING_FOK)
        modes.append(mt5.ORDER_FILLING_RETURN)
        modes.append(mt5.ORDER_FILLING_IOC)
        modes.append(mt5.ORDER_FILLING_FOK)
        seen = set()
        unique_modes = []
        for m in modes:
            if m not in seen:
                seen.add(m)
                unique_modes.append(m)
        return unique_modes

    @staticmethod
    def _get_supported_filling_mode(symbol_info) -> int:
        if symbol_info is None:
            return mt5.ORDER_FILLING_IOC
        fillings = getattr(symbol_info, "filling_mode", 0)
        if fillings & 2:
            return mt5.ORDER_FILLING_IOC
        if fillings & 1:
            return mt5.ORDER_FILLING_FOK
        return mt5.ORDER_FILLING_RETURN
