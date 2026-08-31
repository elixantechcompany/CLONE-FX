"""
Connection State Machine and Status Tracking for Multi-Account MT5 Trading
Defines explicit lifecycle states and transition logic for:
  - CONNECTED_TRADING_ALLOWED
  - CONNECTED_TRADING_DISABLED
  - CONNECTION_LOST
  - RECONNECTING
  - SYNCHRONIZING
  - RECOVERED
  - ERROR_REQUIRES_ATTENTION
"""

import enum
import logging
import time
from typing import Optional, Dict, Any, List, Callable

logger = logging.getLogger("GoldBot.ConnectionState")


class ConnectionState(enum.Enum):
    CONNECTED_TRADING_ALLOWED = "CONNECTED_TRADING_ALLOWED"
    CONNECTED_TRADING_DISABLED = "CONNECTED_TRADING_DISABLED"
    CONNECTION_LOST = "CONNECTION_LOST"
    RECONNECTING = "RECONNECTING"
    SYNCHRONIZING = "SYNCHRONIZING"
    RECOVERED = "RECOVERED"
    ERROR_REQUIRES_ATTENTION = "ERROR_REQUIRES_ATTENTION"


class AccountConnectionStateMachine:
    """
    Manages explicit connection and algo trading lifecycle states for a single MT5 account.
    Tracks state entry timestamps, transition history, and emits status change events.
    """
    def __init__(self, account_id: str):
        self.account_id = account_id.lower()
        self.current_state: ConnectionState = ConnectionState.CONNECTION_LOST
        self.previous_state: Optional[ConnectionState] = None
        self.state_entry_time: float = time.time()
        self.last_transition_reason: str = "Initialized"
        
        # Diagnostics & Timestamps
        self.last_successful_tick_time: float = 0.0
        self.last_successful_sync_time: float = 0.0
        self.last_order_operation_time: float = 0.0
        self.last_error_message: str = ""
        self.reconnect_attempts: int = 0
        self.last_reconnect_attempt_time: float = 0.0
        
        # State transition history (capped at 50)
        self.history: List[Dict[str, Any]] = []
        
        # Listeners
        self.transition_callbacks: List[Callable] = []

    @property
    def is_trading_permitted(self) -> bool:
        """Returns True only when connection is active and Algo Trading is allowed."""
        return self.current_state == ConnectionState.CONNECTED_TRADING_ALLOWED

    @property
    def is_connected(self) -> bool:
        """Returns True if terminal and trade server connection is currently live."""
        return self.current_state in (
            ConnectionState.CONNECTED_TRADING_ALLOWED,
            ConnectionState.CONNECTED_TRADING_DISABLED,
            ConnectionState.SYNCHRONIZING,
            ConnectionState.RECOVERED,
        )

    def add_transition_callback(self, callback: Callable):
        """Registers a callback to be invoked on state transitions."""
        self.transition_callbacks.append(callback)

    def transition_to(self, new_state: ConnectionState, reason: str = "") -> bool:
        """
        Transitions the account to a new ConnectionState.
        Logs the transition and notifies registered callbacks.
        """
        if self.current_state == new_state and new_state not in (ConnectionState.RECONNECTING, ConnectionState.SYNCHRONIZING):
            return False

        old_state = self.current_state
        self.previous_state = old_state
        self.current_state = new_state
        now = time.time()
        self.state_entry_time = now
        self.last_transition_reason = reason

        entry = {
            "timestamp": now,
            "from_state": old_state.value,
            "to_state": new_state.value,
            "reason": reason,
        }
        self.history.append(entry)
        if len(self.history) > 50:
            self.history.pop(0)

        # Log with appropriate severity
        if new_state == ConnectionState.CONNECTED_TRADING_ALLOWED:
            logger.info(f"[{self.account_id.upper()}] [STATE TRANSITION] {old_state.value} -> {new_state.value} | Algo Trading: ON | Reason: {reason}")
        elif new_state == ConnectionState.CONNECTED_TRADING_DISABLED:
            logger.warning(f"[{self.account_id.upper()}] [STATE TRANSITION] {old_state.value} -> {new_state.value} | Algo Trading: OFF (New trades blocked, positions managed) | Reason: {reason}")
        elif new_state in (ConnectionState.CONNECTION_LOST, ConnectionState.ERROR_REQUIRES_ATTENTION):
            logger.error(f"[{self.account_id.upper()}] [STATE TRANSITION] {old_state.value} -> {new_state.value} | Reason: {reason}")
        else:
            logger.info(f"[{self.account_id.upper()}] [STATE TRANSITION] {old_state.value} -> {new_state.value} | Reason: {reason}")

        # Notify callbacks
        for cb in self.transition_callbacks:
            try:
                cb(self.account_id, old_state, new_state, reason)
            except Exception as e:
                logger.warning(f"[{self.account_id.upper()}] Error in state transition callback: {e}")

        return True

    def record_tick(self):
        """Records a successful market data tick."""
        self.last_successful_tick_time = time.time()

    def record_sync(self):
        """Records a successful account/position synchronization."""
        self.last_successful_sync_time = time.time()

    def record_order_op(self):
        """Records a successful order operation (open, modify, close)."""
        self.last_order_operation_time = time.time()

    def record_error(self, message: str):
        """Records error message and transitions to ERROR_REQUIRES_ATTENTION if critical."""
        self.last_error_message = message
        logger.error(f"[{self.account_id.upper()}] Connection error recorded: {message}")

    def get_summary(self) -> Dict[str, Any]:
        """Returns snapshot of current state machine diagnostics."""
        now = time.time()
        return {
            "account_id": self.account_id,
            "current_state": self.current_state.value,
            "previous_state": self.previous_state.value if self.previous_state else None,
            "time_in_state_seconds": round(now - self.state_entry_time, 1),
            "is_trading_permitted": self.is_trading_permitted,
            "is_connected": self.is_connected,
            "last_reason": self.last_transition_reason,
            "last_tick_age_seconds": round(now - self.last_successful_tick_time, 1) if self.last_successful_tick_time > 0 else None,
            "last_sync_age_seconds": round(now - self.last_successful_sync_time, 1) if self.last_successful_sync_time > 0 else None,
            "last_order_op_age_seconds": round(now - self.last_order_operation_time, 1) if self.last_order_operation_time > 0 else None,
            "reconnect_attempts": self.reconnect_attempts,
            "last_error": self.last_error_message,
        }
