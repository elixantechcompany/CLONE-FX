"""
Isolated $20 Copy Trading Engine (Account C -> Account D Only)
Enforces:
  1. Strict Isolation: Master is ACCOUNT_C, Follower is ACCOUNT_D.
     - Accounts A and B are NEVER monitored or copied under any circumstances.
  2. 8-Step Pre-Execution Safety Validation on Account D before executing any copied trade.
  3. Dynamic Risk-Based Volume Sizing: Never blindly copy Master lot sizes.
  4. Safe Failure Handling: Rejects copy if minimum volume is too risky for $20 account.
  5. Trade Lifecycle Synchronization: SL/TP modification, partial close, full close.
  6. Independent Risk Boundaries: If Follower closes on its own risk rules, NEVER reopen.
  7. Dedicated Emergency Kill Switch: Pausing copy engine has zero impact on Accounts A, B, or C.
"""

import logging
import os
import time
import datetime
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any

from src.account_manager import AccountContext

logger = logging.getLogger("GoldBot.CopyEngine")


@dataclass
class CopyEvent:
    """Represents an atomic copy-trading action emitted from Account C to Account D."""
    event_id: str
    master_account_id: str
    follower_account_id: str
    symbol: str
    direction: str                     # "BUY" / "SELL"
    master_entry: float
    master_sl: float
    master_tp: float
    master_volume: float
    master_ticket: int
    event_type: str                    # "OPEN", "CLOSE", "SL_MODIFY", "TP_MODIFY", "PARTIAL_CLOSE"
    magic: int
    timestamp: float = field(default_factory=time.time)
    partial_volume: float = 0.0
    status: str = "PENDING"            # "EXECUTED", "REJECTED", "SKIPPED"
    rejection_reason: str = ""
    follower_ticket: Optional[int] = None
    follower_volume: float = 0.0
    follower_risk_dollars: float = 0.0


class CopyTradingEngine:
    """Manages the isolated Master (Account C) -> Follower (Account D) copy trading relationship."""
    def __init__(self, config: dict, account_manager):
        self.config = config
        self.account_manager = account_manager
        self.copy_cfg = config.get("copy_engine", {})
        
        self.enabled = bool(self.copy_cfg.get("enabled", True))
        self.master_id = str(self.copy_cfg.get("master_account_id", "account_c")).lower()
        self.follower_id = str(self.copy_cfg.get("follower_account_id", "account_d")).lower()
        
        # Risk & Safety Constraints for $20 Follower Account
        self.max_follower_risk = float(self.copy_cfg.get("max_follower_risk_dollars", 0.50))
        self.hard_reject_risk = float(self.copy_cfg.get("hard_reject_risk_dollars", 1.00))
        self.max_spread_gold = int(self.copy_cfg.get("max_spread_points_gold", 320))
        self.max_spread_btc = int(self.copy_cfg.get("max_spread_points_btc", 60000))
        self.slippage = int(self.copy_cfg.get("slippage_points", 30))
        
        self.sync_sl_tp = bool(self.copy_cfg.get("sync_sl_tp_modifications", True))
        self.sync_partial = bool(self.copy_cfg.get("sync_partial_closes", True))
        self.sync_full = bool(self.copy_cfg.get("sync_full_closes", True))
        self.auto_reopen = bool(self.copy_cfg.get("auto_reopen_on_master_open", False)) # Strictly False

        # Independent Kill Switch
        self.is_paused: bool = False
        self.pause_reason: str = ""

        # State tracking: master_ticket -> follower_ticket
        self.active_copied_trades: Dict[int, int] = {}
        # History of completed / closed master tickets (to avoid reopening)
        self.closed_master_tickets: set = set()
        # Processed event IDs
        self.processed_event_ids: set = set()
        self._event_counter = 0

    def pause_copy_engine(self, reason: str = "Manual Copy Pause"):
        """Emergency kill switch for copy engine only."""
        self.is_paused = True
        self.pause_reason = reason
        logger.warning(f"[COPY ENGINE PAUSED] Copying from [{self.master_id.upper()}] to [{self.follower_id.upper()}] is PAUSED: {reason}")

    def resume_copy_engine(self):
        """Resumes copy engine."""
        self.is_paused = False
        self.pause_reason = ""
        logger.info(f"[COPY ENGINE RESUMED] Copying from [{self.master_id.upper()}] to [{self.follower_id.upper()}] is ACTIVE.")

    def generate_event_id(self) -> str:
        """Generates sequential unique copy event identifier."""
        self._event_counter += 1
        year = time.strftime("%Y")
        return f"COPY-{year}-{self._event_counter:06d}"

    def create_copy_event(
        self,
        origin_account_id: str,
        symbol: str,
        direction: str,
        entry: float,
        sl: float,
        tp: float,
        volume: float,
        master_ticket: int,
        event_type: str = "OPEN",
        magic: int = 1001,
        partial_volume: float = 0.0,
    ) -> Optional[CopyEvent]:
        """
        Creates a copy event.
        STRICT ISOLATION ENFORCEMENT:
        Only emits copy events if origin_account_id is Account C (Master).
        Accounts A and B are strictly rejected with zero copy propagation.
        """
        origin = origin_account_id.lower()
        if origin != self.master_id:
            # Under no circumstances will Account A or Account B generate copy events
            return None

        if not self.enabled or self.is_paused:
            logger.info(f"[COPY ENGINE] Copy event ignored (Engine enabled: {self.enabled}, Paused: {self.is_paused})")
            return None

        event = CopyEvent(
            event_id=self.generate_event_id(),
            master_account_id=self.master_id,
            follower_account_id=self.follower_id,
            symbol=symbol,
            direction=direction.upper(),
            master_entry=entry,
            master_sl=sl,
            master_tp=tp,
            master_volume=volume,
            master_ticket=master_ticket,
            event_type=event_type.upper(),
            magic=magic,
            timestamp=time.time(),
            partial_volume=partial_volume,
        )
        return event

    def process_copy_event(self, event: CopyEvent) -> Tuple[bool, str]:
        """
        Processes a CopyEvent for Account D.
        Executes the 8-Step Validation Process for OPEN events,
        or synchronization logic for SL/TP modification and exits.
        """
        if not event or event.event_id in self.processed_event_ids:
            return False, "Duplicate or null event"

        self.processed_event_ids.add(event.event_id)

        master_acc = self.account_manager.get_account(self.master_id)
        follower_acc = self.account_manager.get_account(self.follower_id)

        if not follower_acc or not follower_acc.is_active:
            event.status = "REJECTED"
            event.rejection_reason = f"Follower [{self.follower_id.upper()}] is not active in account manager."
            logger.warning(f"[{self.follower_id.upper()}] [COPY REJECTED] {event.rejection_reason}")
            return False, event.rejection_reason

        if follower_acc.is_manually_paused:
            event.status = "REJECTED"
            event.rejection_reason = f"Follower [{self.follower_id.upper()}] is manually paused."
            logger.warning(f"[{self.follower_id.upper()}] [COPY REJECTED] {event.rejection_reason}")
            return False, event.rejection_reason

        # Handle different event types
        if event.event_type == "OPEN":
            return self._handle_open_event(event, follower_acc)
        elif event.event_type in ("SL_MODIFY", "TP_MODIFY"):
            return self._handle_modify_event(event, follower_acc)
        elif event.event_type == "PARTIAL_CLOSE":
            return self._handle_partial_close_event(event, follower_acc)
        elif event.event_type == "CLOSE":
            return self._handle_close_event(event, follower_acc)
        else:
            event.status = "REJECTED"
            event.rejection_reason = f"Unknown event type {event.event_type}"
            return False, event.rejection_reason

    def _handle_open_event(self, event: CopyEvent, follower_acc: AccountContext) -> Tuple[bool, str]:
        """
        8-STEP PRE-EXECUTION SAFETY VERIFICATION FOR ACCOUNT D:
          STEP 1: Confirm Account D is connected.
          STEP 2: Confirm symbol is available.
          STEP 3: Check spread.
          STEP 4: Check margin.
          STEP 5: Calculate safe follower volume.
          STEP 6: Check maximum risk.
          STEP 7: Check duplicate event.
          STEP 8: Execute only if all checks pass.
        """
        sym = event.symbol
        executor = follower_acc.executor
        connector = follower_acc.connector
        risk_mgr = follower_acc.risk_manager

        # Check Weekend Crypto Filter (Honor config settings)
        if "BTC" in sym.upper():
            symbols_cfg = self.config.get("symbols", {}) if hasattr(self, "config") and self.config else {}
            risk_cfg = self.config.get("risk_management", {}) if hasattr(self, "config") and self.config else {}
            block_crypto_weekends = (
                symbols_cfg.get("block_crypto_on_weekends", False)
                or not risk_cfg.get("crypto_weekend_trading_enabled", True)
                or symbols_cfg.get("symbol_settings", {}).get("BTCUSD", {}).get("block_weekend_trading", False)
            )
            if block_crypto_weekends:
                now_utc = datetime.datetime.now(datetime.timezone.utc)
                if now_utc.weekday() in (5, 6):
                    event.status = "REJECTED"
                    event.rejection_reason = "WEEKEND CRYPTO FILTER: Bitcoin copying is strictly disabled on weekends (Saturday & Sunday UTC)."
                    logger.warning(f"[{follower_acc.account_id.upper()}] [COPY REJECTED] {event.rejection_reason}")
                    return False, event.rejection_reason

        # STEP 1: Confirm Account D is connected
        if not connector or not connector.is_connected():
            event.status = "REJECTED"
            event.rejection_reason = "STEP 1 FAIL: Account D is not connected to MT5."
            logger.warning(f"[{follower_acc.account_id.upper()}] [COPY REJECTED] {event.rejection_reason}")
            return False, event.rejection_reason

        # STEP 2: Confirm symbol is available
        spec = connector.get_symbol_specs(sym)
        if spec is None:
            event.status = "REJECTED"
            event.rejection_reason = f"STEP 2 FAIL: Symbol '{sym}' specifications not available on Account D broker."
            logger.warning(f"[{follower_acc.account_id.upper()}] [COPY REJECTED] {event.rejection_reason}")
            return False, event.rejection_reason

        # STEP 3: Check spread
        max_allowed_spread = self.max_spread_btc if "BTC" in sym.upper() else self.max_spread_gold
        if spec.spread > max_allowed_spread:
            event.status = "REJECTED"
            event.rejection_reason = f"STEP 3 FAIL: Spread {spec.spread} exceeds limit {max_allowed_spread} on {sym}."
            logger.warning(f"[{follower_acc.account_id.upper()}] [COPY REJECTED] {event.rejection_reason}")
            return False, event.rejection_reason

        # Sync latest follower account metrics
        follower_acc.sync_account_metrics()

        # STEP 4: Check margin
        min_required_margin = 2.00
        if follower_acc.free_margin < min_required_margin:
            event.status = "REJECTED"
            event.rejection_reason = f"STEP 4 FAIL: Insufficient free margin (${follower_acc.free_margin:.2f} < ${min_required_margin:.2f})."
            logger.warning(f"[{follower_acc.account_id.upper()}] [COPY REJECTED] {event.rejection_reason}")
            return False, event.rejection_reason

        # STEP 5: Calculate safe follower volume
        # Do NOT blindly copy Master lot size!
        safe_volume = 0.01
        if risk_mgr:
            safe_volume = risk_mgr.calculate_lot_size(
                symbol=sym,
                entry_price=event.master_entry,
                stop_loss_price=event.master_sl,
                equity=follower_acc.equity,
                quality_score=60,
                open_trades_count=len(executor.get_open_positions()) if executor else 0,
            )
        else:
            safe_volume = spec.volume_min or 0.01

        if safe_volume <= 0.0:
            event.status = "REJECTED"
            event.rejection_reason = "STEP 5 FAIL: Dynamic sizing calculated 0.00 lots (SL too wide or risk buffer exhausted)."
            logger.warning(f"[{follower_acc.account_id.upper()}] [COPY REJECTED] {event.rejection_reason}")
            return False, event.rejection_reason

        # STEP 6: Check maximum risk
        expected_loss = 0.0
        if risk_mgr:
            expected_loss = risk_mgr.calculate_monetary_loss(sym, event.master_entry, event.master_sl, safe_volume)
        else:
            sl_dist = abs(event.master_entry - event.master_sl)
            c_size = spec.contract_size if spec.contract_size > 0 else 100.0
            expected_loss = round(sl_dist * c_size * safe_volume, 2)

        if expected_loss > self.hard_reject_risk:
            event.status = "REJECTED"
            event.rejection_reason = (
                f"STEP 6 FAIL: Expected loss ${expected_loss:.2f} on {safe_volume} lots exceeds $20 account risk ceiling "
                f"${self.hard_reject_risk:.2f}."
            )
            logger.warning(f"[{follower_acc.account_id.upper()}] [COPY REJECTED] {event.rejection_reason}")
            return False, event.rejection_reason

        # STEP 7: Check duplicate event / duplicate position
        if event.master_ticket in self.active_copied_trades:
            event.status = "REJECTED"
            event.rejection_reason = f"STEP 7 FAIL: Master ticket #{event.master_ticket} is already copied to Account D."
            logger.warning(f"[{follower_acc.account_id.upper()}] [COPY REJECTED] {event.rejection_reason}")
            return False, event.rejection_reason

        if event.master_ticket in self.closed_master_tickets and not self.auto_reopen:
            event.status = "REJECTED"
            event.rejection_reason = f"STEP 7 FAIL: Master ticket #{event.master_ticket} was previously closed."
            logger.warning(f"[{follower_acc.account_id.upper()}] [COPY REJECTED] {event.rejection_reason}")
            return False, event.rejection_reason

        # STEP 8: Execute only if all checks pass
        if not executor:
            event.status = "REJECTED"
            event.rejection_reason = "STEP 8 FAIL: Order executor is not initialized on Account D."
            logger.error(f"[{follower_acc.account_id.upper()}] [COPY REJECTED] {event.rejection_reason}")
            return False, event.rejection_reason

        copy_comment = f"CP_{event.master_account_id[:4]}_{event.master_ticket}"
        follower_ticket = executor.execute_market_order(
            symbol=sym,
            order_type=event.direction,
            volume=safe_volume,
            sl=event.master_sl,
            tp=event.master_tp,
            magic=event.magic,
            comment=copy_comment,
        )

        if follower_ticket:
            event.status = "EXECUTED"
            event.follower_ticket = follower_ticket
            event.follower_volume = safe_volume
            event.follower_risk_dollars = expected_loss
            self.active_copied_trades[event.master_ticket] = follower_ticket

            logger.info(
                f"[{follower_acc.account_id.upper()}] [{sym}] [COPY_FROM_{event.master_account_id.upper()}] "
                f"{event.direction} {safe_volume} lots @ {event.master_entry:.2f} | "
                f"SL: {event.master_sl:.2f} | TP: {event.master_tp:.2f} | Risk: ${expected_loss:.2f} | Status=EXECUTED "
                f"(Master Ticket #{event.master_ticket} -> Follower Ticket #{follower_ticket})"
            )
            return True, f"Executed Ticket #{follower_ticket}"
        else:
            event.status = "REJECTED"
            event.rejection_reason = "STEP 8 FAIL: Order send failed on broker terminal."
            logger.error(f"[{follower_acc.account_id.upper()}] [COPY REJECTED] {event.rejection_reason}")
            return False, event.rejection_reason

    def _handle_modify_event(self, event: CopyEvent, follower_acc: AccountContext) -> Tuple[bool, str]:
        """Synchronizes SL / TP adjustments on open copied positions."""
        if not self.sync_sl_tp:
            return False, "SL/TP sync disabled"

        follower_ticket = self.active_copied_trades.get(event.master_ticket)
        if not follower_ticket:
            return False, f"No active follower trade found for master ticket #{event.master_ticket}"

        executor = follower_acc.executor
        if not executor:
            return False, "Executor not available"

        # Check if follower position is still open on Account D
        open_pos = executor.get_open_positions(event.symbol)
        matching = [p for p in open_pos if p["ticket"] == follower_ticket]
        if not matching:
            # Follower closed independently
            self.active_copied_trades.pop(event.master_ticket, None)
            return False, f"Follower ticket #{follower_ticket} is already closed on Account D"

        success = executor.modify_position_stops(follower_ticket, event.symbol, event.master_sl, event.master_tp)
        if success:
            logger.info(
                f"[{follower_acc.account_id.upper()}] [COPY_MODIFY] Updated Ticket #{follower_ticket} "
                f"SL: {event.master_sl:.2f}, TP: {event.master_tp:.2f} (from Master #{event.master_ticket})"
            )
            return True, "Modified"
        return False, "Modification failed"

    def _handle_partial_close_event(self, event: CopyEvent, follower_acc: AccountContext) -> Tuple[bool, str]:
        """Synchronizes partial closes if allowed by follower broker volume step."""
        if not self.sync_partial:
            return False, "Partial close sync disabled"

        follower_ticket = self.active_copied_trades.get(event.master_ticket)
        if not follower_ticket:
            return False, f"No active follower trade found for master ticket #{event.master_ticket}"

        executor = follower_acc.executor
        if not executor:
            return False, "Executor not available"

        open_pos = executor.get_open_positions(event.symbol)
        matching = [p for p in open_pos if p["ticket"] == follower_ticket]
        if not matching:
            self.active_copied_trades.pop(event.master_ticket, None)
            return False, f"Follower ticket #{follower_ticket} already closed"

        current_vol = matching[0]["volume"]
        spec = follower_acc.connector.get_symbol_specs(event.symbol)
        min_vol = spec.volume_min if spec else 0.01

        # If current volume is already at micro-lot minimum, close full position or maintain
        if current_vol <= min_vol:
            logger.info(f"[{follower_acc.account_id.upper()}] [COPY_PARTIAL] Follower volume {current_vol} is at minimum ({min_vol}), skipping partial close.")
            return True, "Skipped partial on minimum volume"

        close_vol = round(current_vol / 2.0, 2)
        success = executor.partial_close_position(follower_ticket, event.symbol, close_vol, reason="Copy_Partial_Close")
        return success, "Partial close handled"

    def _handle_close_event(self, event: CopyEvent, follower_acc: AccountContext) -> Tuple[bool, str]:
        """Synchronizes full position exit."""
        if not self.sync_full:
            return False, "Full close sync disabled"

        follower_ticket = self.active_copied_trades.pop(event.master_ticket, None)
        self.closed_master_tickets.add(event.master_ticket)

        if not follower_ticket:
            return False, f"No active follower trade for master #{event.master_ticket}"

        executor = follower_acc.executor
        if not executor:
            return False, "Executor not available"

        open_pos = executor.get_open_positions(event.symbol)
        matching = [p for p in open_pos if p["ticket"] == follower_ticket]
        if not matching:
            return True, "Follower position already closed on Account D"

        success = executor.close_position(follower_ticket, event.symbol, reason=f"Copy_Close_Master_{event.master_ticket}")
        if success:
            logger.info(
                f"[{follower_acc.account_id.upper()}] [COPY_CLOSE] Closed Follower Ticket #{follower_ticket} "
                f"(Master Ticket #{event.master_ticket} closed)"
            )
            return True, "Closed"
        return False, "Close failed"

    def get_status(self) -> dict:
        """Returns diagnostic status of the isolated copy engine."""
        return {
            "enabled": self.enabled,
            "is_paused": self.is_paused,
            "pause_reason": self.pause_reason,
            "master_account_id": self.master_id,
            "follower_account_id": self.follower_id,
            "active_copied_count": len(self.active_copied_trades),
            "max_follower_risk": self.max_follower_risk,
            "hard_reject_risk": self.hard_reject_risk,
        }
