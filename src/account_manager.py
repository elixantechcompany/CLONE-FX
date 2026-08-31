"""
Multi-Account Manager & Account Context Isolation
Enforces strict multi-account isolation across 4 distinct accounts:
  - ACCOUNT A: $1,000 BrightFunded (Independent, Zero Copy)
  - ACCOUNT B: $1,000 BrightFunded (Independent, Zero Copy)
  - ACCOUNT C: $20 Personal Account (Copy Master)
  - ACCOUNT D: $20 Personal Account (Copy Follower, C -> D Only)

Integrates per-account Connection State Machine, MT5 Algo Trading detection,
and 10-Step Automatic State & Position Reconciliation.
"""

import logging
import os
import time
import datetime
from typing import Dict, List, Optional, Tuple, Any
from dotenv import load_dotenv
load_dotenv()
import MetaTrader5 as mt5

from src.connection import MT5Connector
from src.connection_state import AccountConnectionStateMachine, ConnectionState

logger = logging.getLogger("GoldBot.AccountManager")


class AccountContext:
    """Holds fully isolated trading state, connectors, state machine, and risk managers for a single account."""
    def __init__(
        self,
        account_id: str,
        name: str,
        login: Optional[int] = None,
        password: Optional[str] = None,
        server: Optional[str] = None,
        config: Optional[dict] = None,
        initial_balance: float = 1000.0,
        is_active: bool = True,
        account_type: str = "BRIGHTFUNDED",
        mode: str = "INDEPENDENT",
        copy_enabled: bool = False,
        copy_source: Optional[str] = None,
        mt5_path: Optional[str] = None,
    ):
        self.account_id = str(account_id).lower()
        self.name = name
        self.login = login
        self.password = password
        self.server = server
        self.mt5_path = mt5_path
        self.config = config or {}
        self.initial_balance = float(initial_balance)
        self.is_active = is_active
        
        # Account roles
        self.account_type = str(account_type).upper()
        self.mode = str(mode).upper()
        self.copy_enabled = copy_enabled
        self.copy_source = str(copy_source).lower() if copy_source else None

        # Connection instance for this account
        self.connector = MT5Connector(
            account=self.login,
            password=self.password,
            server=self.server,
            path=self.mt5_path,
            account_id=self.account_id,
        )

        # Connection State Machine
        self.state_machine = AccountConnectionStateMachine(account_id=self.account_id)

        # Lazy-bound submodules
        self.risk_manager = None
        self.executor = None

        # Financial tracking state (strictly isolated)
        self.balance: float = self.initial_balance
        self.equity: float = self.initial_balance
        self.free_margin: float = self.initial_balance
        self.daily_start_equity: float = self.initial_balance
        self.daily_high_water_equity: float = self.initial_balance
        self.daily_pnl: float = 0.0
        self.daily_drawdown_pct: float = 0.0

        # State & Safety Flags
        self.trading_state: str = "NORMAL"
        self.is_manually_paused: bool = False
        self.pause_reason: str = ""
        self.last_sync_time: float = 0.0

        # Algo Trading Status Cache
        self.is_algo_trading_allowed: bool = False

        # Diagnostic State ("Why Didn't I Trade?" Dashboard)
        self.last_evaluated_candidate: Optional[dict] = None
        self.last_decision: str = "NO_SIGNAL"
        self.last_blocking_stage: Optional[int] = None
        self.last_rejection_reason: str = "Scanning for valid market setups"
        self.last_order_retcode: Optional[int] = None
        self.last_order_retcode_name: str = ""
        self.last_order_result: str = "NONE"
        self.last_order_time: float = 0.0

    def record_candidate_audit(
        self,
        candidate: dict,
        decision: str,
        blocking_stage: Optional[int] = None,
        rejection_reason: str = "",
        retcode: Optional[int] = None,
        retcode_name: str = "",
    ):
        """Updates diagnostic state for real-time transparency dashboard."""
        self.last_evaluated_candidate = candidate
        self.last_decision = decision
        self.last_blocking_stage = blocking_stage
        self.last_rejection_reason = rejection_reason or "Setup accepted"
        if retcode is not None:
            self.last_order_retcode = retcode
            self.last_order_retcode_name = retcode_name

    @property
    def has_credentials(self) -> bool:
        return bool(
            self.login 
            and str(self.login).strip() 
            and str(self.login).isdigit() 
            and self.password 
            and str(self.password).strip() 
            and self.server 
            and str(self.server).strip()
        )

    @property
    def is_independent(self) -> bool:
        return self.mode == "INDEPENDENT"

    @property
    def is_copy_master(self) -> bool:
        return self.mode == "COPY_MASTER"

    @property
    def is_copy_follower(self) -> bool:
        return self.mode == "COPY_FOLLOWER"

    @property
    def runs_shared_strategy(self) -> bool:
        return self.mode in ("INDEPENDENT", "COPY_MASTER")

    @property
    def is_trading_permitted(self) -> bool:
        """Returns True only when state machine allows trading and account is not paused."""
        return (
            self.state_machine.is_trading_permitted
            and not self.is_manually_paused
            and self.is_active
        )

    def update_connection_state(self) -> ConnectionState:
        """
        Polls MT5 connection and native Algo Trading switch status.
        Transitions state machine appropriately without requiring manual user commands.
        """
        if not self.connector.is_connected():
            if not self.connector.check_internet():
                if self.state_machine.current_state not in (ConnectionState.CONNECTION_LOST, ConnectionState.RECONNECTING):
                    self.state_machine.transition_to(
                        ConnectionState.CONNECTION_LOST,
                        reason="Internet connection lost"
                    )
            else:
                if self.state_machine.current_state not in (ConnectionState.CONNECTION_LOST, ConnectionState.RECONNECTING):
                    self.state_machine.transition_to(
                        ConnectionState.CONNECTION_LOST,
                        reason="MT5 terminal or trade server disconnected"
                    )
            return self.state_machine.current_state

        # Terminal is connected -> check Account Identity & Server Verification
        valid, msg = self.connector.verify_pre_trade_identity(require_algo_on=False)
        if not valid:
            if self.state_machine.current_state != ConnectionState.ERROR_REQUIRES_ATTENTION:
                self.state_machine.transition_to(
                    ConnectionState.ERROR_REQUIRES_ATTENTION,
                    reason=msg
                )
            self.is_algo_trading_allowed = False
            return self.state_machine.current_state

        # Check Algo Trading master permission
        algo_status = self.connector.get_algo_trading_status()
        self.is_algo_trading_allowed = algo_status.get("is_algo_enabled", False)

        if self.is_algo_trading_allowed:
            if self.state_machine.current_state != ConnectionState.CONNECTED_TRADING_ALLOWED:
                self.state_machine.transition_to(
                    ConnectionState.CONNECTED_TRADING_ALLOWED,
                    reason="MT5 Algo Trading is ENABLED"
                )
        else:
            if self.state_machine.current_state != ConnectionState.CONNECTED_TRADING_DISABLED:
                self.state_machine.transition_to(
                    ConnectionState.CONNECTED_TRADING_DISABLED,
                    reason="MT5 Algo Trading is DISABLED in terminal settings (New trades blocked, positions managed)"
                )

        self.state_machine.record_tick()
        return self.state_machine.current_state

    def sync_account_metrics(self) -> dict:
        """Pulls fresh balance, equity, and margin for this specific account from MT5."""
        acc_info = self.connector.get_account_summary()
        if acc_info:
            self.balance = float(acc_info.get("balance", self.balance))
            self.equity = float(acc_info.get("equity", self.equity))
            self.free_margin = float(acc_info.get("free_margin", self.free_margin))

            if self.daily_start_equity <= 0:
                self.daily_start_equity = self.equity

            self.daily_high_water_equity = max(self.daily_high_water_equity, self.equity)
            self.daily_pnl = self.equity - self.daily_start_equity
            
            ref = max(self.daily_start_equity, 10.0)
            if self.daily_pnl < 0:
                self.daily_drawdown_pct = (abs(self.daily_pnl) / ref) * 100.0
            else:
                self.daily_drawdown_pct = 0.0

            self.last_sync_time = time.time()
            self.state_machine.record_sync()
        return acc_info

    def reconcile_account_state(self, active_broker_symbols: Dict[str, str]) -> bool:
        """
        10-STEP RECONCILIATION & RECOVERY SEQUENCE:
          1. Verify MT5 connection.
          2. Verify account identity.
          3. Verify trading permissions (MT5 Algo Trading status).
          4. Synchronize account balance/equity/margin.
          5. Retrieve currently open positions.
          6. Retrieve recent orders/deals from MT5 history.
          7. Reconcile local state with MT5.
          8. Detect any trades that occurred or closed while disconnected.
          9. Reconstruct position-management state (entry, SL, TP, volume, direction, peak profit, R-multiple, breakeven, trailing, giveback).
          10. Transition to RECOVERED and resume normal market analysis.
        """
        self.state_machine.transition_to(
            ConnectionState.SYNCHRONIZING,
            reason="Starting 10-Step State & Position Reconciliation"
        )
        logger.info(f"[{self.account_id.upper()}] [RECONCILIATION] Running 10-Step State & Position Reconciliation...")

        try:
            # Step 1: Verify MT5 connection
            if not self.connector.is_connected():
                logger.warning(f"[{self.account_id.upper()}] Step 1 Fail: MT5 not connected.")
                self.state_machine.transition_to(ConnectionState.CONNECTION_LOST, reason="Step 1 MT5 check failed")
                return False

            # Step 2: Verify account identity
            if not self.connector.verify_account_identity():
                logger.warning(f"[{self.account_id.upper()}] Step 2 Fail: Account identity mismatch.")
                self.state_machine.transition_to(ConnectionState.ERROR_REQUIRES_ATTENTION, reason="Step 2 identity mismatch")
                return False

            # Step 3: Verify trading permissions
            algo_status = self.connector.get_algo_trading_status()
            self.is_algo_trading_allowed = algo_status.get("is_algo_enabled", False)

            # Step 4: Synchronize account metrics
            self.sync_account_metrics()
            if self.risk_manager:
                self.risk_manager.reset_daily_metrics_if_needed(self.equity)

            # Step 5: Retrieve currently open positions from MT5
            open_positions_by_symbol = {}
            all_live_positions = []
            for canonical, broker_sym in active_broker_symbols.items():
                positions = self.executor.get_open_positions(broker_sym) if self.executor else []
                open_positions_by_symbol[broker_sym] = positions
                all_live_positions.extend(positions)

            live_tickets = {p["ticket"] for p in all_live_positions}

            # Step 6 & 7: Reconcile local tickets with MT5 & retrieve recent deals
            if self.executor:
                # Detect positions closed while offline
                for ticket in list(self.executor.known_tickets.keys()):
                    if ticket not in live_tickets:
                        deals = mt5.history_deals_get(position=ticket)
                        profit = sum(d.profit for d in deals) if deals else 0.0
                        logger.info(f"[{self.account_id.upper()}] [DISCONNECTED CLOSE DETECTED] Ticket #{ticket} closed while offline | P&L: ${profit:+.2f}")
                        self.executor._handle_ticket_closed(ticket, profit, reason="Closed_While_Disconnected")

                # Step 8 & 9: Reconstruct position management state for all open positions
                for pos in all_live_positions:
                    ticket = pos["ticket"]
                    sym = pos["symbol"]
                    pos_type = pos["type"]
                    vol = pos["volume"]
                    entry = pos["price_open"]
                    sl = pos["sl"]
                    tp = pos["tp"]
                    magic = pos["magic"]
                    current_profit = pos["profit"]

                    # Register with Intelligent Exit Engine
                    rec = self.executor.exit_engine.register_position(
                        ticket=ticket,
                        symbol=sym,
                        pos_type=pos_type,
                        volume=vol,
                        open_price=entry,
                        sl=sl,
                        tp=tp,
                        magic=magic,
                        account_id=self.account_id,
                    )

                    # Update peak profit & R multiple
                    if rec:
                        price_gain = (pos["price_current"] - entry) if pos_type == "BUY" else (entry - pos["price_current"])
                        current_r = price_gain / rec.initial_risk_dist if rec.initial_risk_dist > 0 else 0.0
                        rec.current_r = current_r
                        rec.peak_r = max(rec.peak_r, current_r)
                        rec.peak_profit_dollars = max(rec.peak_profit_dollars, current_profit)
                        if sl != 0 and abs(sl - entry) < (rec.initial_risk_dist * 0.5):
                            rec.be_applied = True

                    # Update executor known ticket state
                    self.executor.known_tickets[ticket] = {
                        "account_id": self.account_id,
                        "symbol": sym,
                        "type": pos_type,
                        "volume": vol,
                        "entry_price": entry,
                        "initial_sl": sl,
                        "initial_tp": tp,
                        "risk_distance": rec.initial_risk_dist if rec else 2.0,
                        "be_applied": rec.be_applied if rec else False,
                        "magic": magic,
                    }
                    self.executor.peak_profit[ticket] = max(self.executor.peak_profit.get(ticket, 0.0), current_profit)

                    logger.info(
                        f"[{self.account_id.upper()}] [POSITION RECONSTRUCTED] Ticket #{ticket} ({sym} {pos_type} {vol} lots @ {entry:.2f}, "
                        f"SL: {sl:.2f}, TP: {tp:.2f}, P&L: ${current_profit:+.2f}, Peak R: {rec.peak_r if rec else 0.0:+.2f}R)"
                    )

            # Step 10: Transition to RECOVERED and set operational state
            self.state_machine.transition_to(
                ConnectionState.RECOVERED,
                reason="10-Step Reconciliation completed successfully"
            )

            if self.is_algo_trading_allowed:
                self.state_machine.transition_to(
                    ConnectionState.CONNECTED_TRADING_ALLOWED,
                    reason="Reconciliation completed; MT5 Algo Trading is ON"
                )
            else:
                self.state_machine.transition_to(
                    ConnectionState.CONNECTED_TRADING_DISABLED,
                    reason="Reconciliation completed; MT5 Algo Trading is OFF"
                )

            logger.info(f"[{self.account_id.upper()}] [RECONCILIATION SUCCESS] All positions reconciled and management active.")
            return True

        except Exception as e:
            logger.exception(f"[{self.account_id.upper()}] Error during reconciliation: {e}")
            self.state_machine.transition_to(
                ConnectionState.ERROR_REQUIRES_ATTENTION,
                reason=f"Reconciliation error: {e}"
            )
            return False

    def get_summary(self) -> dict:
        """Returns snapshot of this account's independent status."""
        hwm = self.risk_manager.lifetime_high_water_equity if self.risk_manager else self.daily_high_water_equity
        challenge_pnl = self.equity - self.initial_balance
        daily_loss = abs(min(0.0, self.daily_pnl))
        trailing_dd = max(0.0, hwm - self.equity)
        rem_daily_buf = max(0.0, (self.risk_manager.daily_hard_stop_loss if self.risk_manager else 25.0) - daily_loss)
        rem_trailing_buf = max(0.0, (self.risk_manager.trailing_hard_stop_drawdown if self.risk_manager else 50.0) - trailing_dd)

        sm_summary = self.state_machine.get_summary()

        return {
            "account_id": self.account_id,
            "name": self.name,
            "account_type": self.account_type,
            "mode": self.mode,
            "copy_enabled": self.copy_enabled,
            "copy_source": self.copy_source,
            "login": self.login,
            "balance": round(self.balance, 2),
            "equity": round(self.equity, 2),
            "free_margin": round(self.free_margin, 2),
            "challenge_target": 100.0 if self.account_type == "BRIGHTFUNDED" else 2.0,
            "challenge_pnl": round(challenge_pnl, 2),
            "daily_start_equity": round(self.daily_start_equity, 2),
            "daily_high_water": round(self.daily_high_water_equity, 2),
            "lifetime_high_water": round(hwm, 2),
            "daily_pnl": round(self.daily_pnl, 2),
            "daily_drawdown_pct": round(self.daily_drawdown_pct, 2),
            "trailing_drawdown_dollars": round(trailing_dd, 2),
            "remaining_daily_buffer": round(rem_daily_buf, 2),
            "remaining_trailing_buffer": round(rem_trailing_buf, 2),
            "trading_state": self.risk_manager.trading_state if self.risk_manager else self.trading_state,
            "connection_state": sm_summary["current_state"],
            "algo_trading_allowed": self.is_algo_trading_allowed,
            "is_active": self.is_active,
            "is_paused": self.is_manually_paused,
            "pause_reason": self.pause_reason,
            "last_sync_age_seconds": sm_summary.get("last_sync_age_seconds"),
        }


class MultiAccountManager:
    """Manages collection of isolated trading accounts."""
    def __init__(self, config: dict):
        self.config = config
        self.accounts_cfg = config.get("accounts", {})
        self.accounts: Dict[str, AccountContext] = {}
        self._initialize_accounts()

    def _initialize_accounts(self):
        """Reads configuration and securely loads account credentials from environment variables."""
        account_list = self.accounts_cfg.get("account_list", [])
        
        for item in account_list:
            acc_id = str(item.get("id", "account_a")).lower()
            name = item.get("name", f"Account {acc_id.upper()}")
            acc_type = item.get("type", "BRIGHTFUNDED").upper()
            mode = item.get("mode", "INDEPENDENT").upper()
            copy_enabled = bool(item.get("copy_enabled", False))
            copy_source = item.get("copy_source")
            
            env_login = item.get("env_login_var", "")
            env_pass = item.get("env_password_var", "")
            env_server = item.get("env_server_var", "")
            env_path = item.get("env_path_var", "")
            
            fb_login = item.get("fallback_login_var", "")
            fb_pass = item.get("fallback_password_var", "")
            fb_server = item.get("fallback_server_var", "")

            raw_login = os.getenv(env_login) or (os.getenv(fb_login) if fb_login else None)
            login = int(raw_login) if raw_login and raw_login.isdigit() else None
            password = os.getenv(env_pass) or (os.getenv(fb_pass) if fb_pass else None)
            server = os.getenv(env_server) or (os.getenv(fb_server) if fb_server else None)
            mt5_path = os.getenv(env_path) or os.getenv("MT5_PATH") or None
            
            init_bal = float(item.get("balance", item.get("initial_balance", 1000.0)))
            is_active = bool(item.get("is_active", True))

            ctx = AccountContext(
                account_id=acc_id,
                name=name,
                login=login,
                password=password,
                server=server,
                config=self.config,
                initial_balance=init_bal,
                is_active=is_active,
                account_type=acc_type,
                mode=mode,
                copy_enabled=copy_enabled,
                copy_source=copy_source,
                mt5_path=mt5_path,
            )
            self.accounts[acc_id] = ctx
            logger.info(
                f"Configured Account [{acc_id.upper()}] '{name}' | Type: {acc_type} | Mode: {mode} | "
                f"Copy: {copy_enabled} (Source: {copy_source}) | Initial Balance: ${init_bal:.2f} | "
                f"Has Credentials: {bool(login)}"
            )

        # Fallback if no accounts configured: create default single account context
        if not self.accounts:
            raw_login = os.getenv("MT5_ACCOUNT_NUMBER")
            login = int(raw_login) if raw_login and raw_login.isdigit() else None
            password = os.getenv("MT5_PASSWORD")
            server = os.getenv("MT5_SERVER")
            ctx = AccountContext(
                account_id="account_a",
                name="BrightFunded Account A",
                login=login,
                password=password,
                server=server,
                config=self.config,
                initial_balance=1000.0,
                is_active=True,
                account_type="BRIGHTFUNDED",
                mode="INDEPENDENT",
            )
            self.accounts["account_a"] = ctx
            logger.info("Initialized default fallback account 'account_a'.")

    def get_account(self, account_id: str) -> Optional[AccountContext]:
        return self.accounts.get(account_id.lower())

    def get_active_accounts(self) -> List[AccountContext]:
        return [acc for acc in self.accounts.values() if acc.is_active]

    def get_strategy_accounts(self) -> List[AccountContext]:
        return [acc for acc in self.accounts.values() if acc.is_active and acc.runs_shared_strategy]

    def get_independent_accounts(self) -> List[AccountContext]:
        return [acc for acc in self.accounts.values() if acc.is_active and acc.is_independent]

    def get_copy_master(self) -> Optional[AccountContext]:
        for acc in self.accounts.values():
            if acc.is_active and acc.is_copy_master:
                return acc
        return None

    def get_copy_followers(self, master_id: str = "account_c") -> List[AccountContext]:
        target = master_id.lower()
        return [
            acc for acc in self.accounts.values()
            if acc.is_active and acc.is_copy_follower and acc.copy_source == target
        ]

    def pause_account(self, account_id: str, reason: str = "Manual Pause") -> bool:
        acc = self.get_account(account_id)
        if acc:
            acc.is_manually_paused = True
            acc.pause_reason = reason
            logger.warning(f"[{acc.account_id.upper()}] Paused: {reason}")
            return True
        return False

    def resume_account(self, account_id: str) -> bool:
        acc = self.get_account(account_id)
        if acc:
            acc.is_manually_paused = False
            acc.pause_reason = ""
            logger.info(f"[{acc.account_id.upper()}] Resumed trading.")
            return True
        return False

    def pause_all(self, reason: str = "Global Pause"):
        for acc in self.accounts.values():
            acc.is_manually_paused = True
            acc.pause_reason = reason
        logger.warning(f"All accounts paused: {reason}")

    def resume_all(self):
        for acc in self.accounts.values():
            acc.is_manually_paused = False
            acc.pause_reason = ""
        logger.info("All accounts resumed.")

    def get_all_summaries(self) -> List[dict]:
        return [acc.get_summary() for acc in self.accounts.values()]
