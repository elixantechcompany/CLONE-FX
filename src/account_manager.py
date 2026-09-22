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
load_dotenv("config/.env")
load_dotenv()
import MetaTrader5 as mt5

from src.connection import MT5Connector
from src.connection_state import AccountConnectionStateMachine, ConnectionState
import sys
import json
import subprocess
from pathlib import Path
import yaml

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


class AccountManager:
    def __init__(self, config_path: str = "config/config.yaml", env_path: str = "config/.env"):
        self.config_path = Path(config_path)
        self.env_path = Path(env_path)
        self.config: Dict[str, Any] = {}
        self.accounts: List[Dict[str, Any]] = []
        self.daily_baselines: Dict[str, float] = {}
        self.high_water_marks: Dict[str, float] = {}
        self.load_all()

    def load_all(self):
        """Loads configuration and accounts from YAML and environment variables."""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    self.config = yaml.safe_load(f) or {}
            except Exception as e:
                logger.error(f"Failed to load {self.config_path}: {e}")
                self.config = {}

        if self.env_path.exists():
            load_dotenv(self.env_path)
        load_dotenv()

        acc_cfg = self.config.get("accounts", {})
        raw_list = acc_cfg.get("account_list", [])
        self.accounts = []

        for item in raw_list:
            acc_id = item.get("id", "").lower()
            if not acc_id:
                continue

            # Resolve credentials from env
            login_var = item.get("env_login_var")
            pass_var = item.get("env_password_var")
            srv_var = item.get("env_server_var")
            path_var = item.get("env_path_var")

            login = os.getenv(login_var) if login_var else None
            password = os.getenv(pass_var) if pass_var else None
            server = os.getenv(srv_var) if srv_var else None
            mt5_path = os.getenv(path_var) if path_var else None

            # Check fallbacks
            if not login and item.get("fallback_login_var"):
                login = os.getenv(item.get("fallback_login_var"))
            if not password and item.get("fallback_password_var"):
                password = os.getenv(item.get("fallback_password_var"))
            if not server and item.get("fallback_server_var"):
                server = os.getenv(item.get("fallback_server_var"))

            acc_data = {
                "id": acc_id,
                "name": item.get("name", f"Account {acc_id.upper()}"),
                "type": item.get("type", "PERSONAL"),  # PERSONAL, BRIGHTFUNDED, PROP_FIRM
                "balance": float(item.get("balance", 20.0)),
                "equity": float(item.get("balance", 20.0)),
                "mode": item.get("mode", "INDEPENDENT"),  # INDEPENDENT, COPY_MASTER, COPY_FOLLOWER
                "execution_mode": item.get("execution_mode", "AUTOMATED_EA"),  # AUTOMATED_EA, VISUAL_SCANNER
                "max_daily_loss_pct": float(item.get("max_daily_loss_pct", 4.0 if item.get("type") == "BRIGHTFUNDED" else 10.0)),
                "risk_per_trade_pct": float(item.get("risk_per_trade_pct", 0.25 if item.get("type") == "BRIGHTFUNDED" else 1.0)),
                "min_rr": float(item.get("min_rr", 2.0)),
                "login": login,
                "password": password,
                "server": server,
                "path": mt5_path or self._detect_default_mt5_path(acc_id),
                "is_active": item.get("is_active", True),
                "connection_state": "DISCONNECTED",
                "circuit_breaker_tripped": False,
                "daily_pnl": 0.0,
            }

            # Initialize daily baseline tracking
            if acc_id not in self.daily_baselines:
                self.daily_baselines[acc_id] = acc_data["balance"]
            if acc_id not in self.high_water_marks:
                self.high_water_marks[acc_id] = acc_data["balance"]

            self.accounts.append(acc_data)

    def _detect_default_mt5_path(self, acc_id: str) -> str:
        """Autodetects common MT5 terminal installations on Windows."""
        common_paths = [
            r"C:\Program Files\MetaTrader 5\terminal64.exe",
            r"C:\Users\PwezaCore\Desktop\MT5_Account_C\terminal64.exe",
            r"C:\Users\PwezaCore\Desktop\MT5 NEW ACC\FBS DEMO\terminal64.exe",
            r"C:\Program Files\Exness MetaTrader 5\terminal64.exe",
            r"C:\Program Files\HFM MetaTrader 5\terminal64.exe",
        ]
        if "c" in acc_id and os.path.exists(r"C:\Users\PwezaCore\Desktop\MT5_Account_C\terminal64.exe"):
            return r"C:\Users\PwezaCore\Desktop\MT5_Account_C\terminal64.exe"
        if "d" in acc_id and os.path.exists(r"C:\Users\PwezaCore\Desktop\MT5 NEW ACC\FBS DEMO\terminal64.exe"):
            return r"C:\Users\PwezaCore\Desktop\MT5 NEW ACC\FBS DEMO\terminal64.exe"
        for p in common_paths:
            if os.path.exists(p):
                return p
        return r"C:\Program Files\MetaTrader 5\terminal64.exe"

    def add_account(
        self,
        name: str,
        account_type: str,
        balance: float,
        login: str,
        password: str,
        server: str,
        path: Optional[str] = None,
        mode: str = "INDEPENDENT",
        execution_mode: str = "AUTOMATED_EA",
        max_daily_loss_pct: Optional[float] = None,
        risk_per_trade_pct: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Creates and registers a new trading account.
        Enforces a minimum balance floor of $20.00 USD.
        """
        # Strict $20 Minimum Validation
        balance_float = float(balance)
        if balance_float < 20.0:
            raise ValueError(f"Account creation rejected: Minimum balance required is $20.00 USD (Got: ${balance_float:.2f})")

        acc_num = len(self.accounts) + 1
        acc_id = f"account_{chr(96 + acc_num)}"  # account_e, account_f, etc.

        # Auto-configure safe prop-firm risk limits
        is_prop = (account_type or "").upper() in ["BRIGHTFUNDED", "PROP_FIRM", "CHALLENGE"]
        loss_pct = max_daily_loss_pct if max_daily_loss_pct is not None else (4.0 if is_prop else 10.0)
        risk_pct = risk_per_trade_pct if risk_per_trade_pct is not None else (0.25 if is_prop else 1.0)

        terminal_path = path or self._detect_default_mt5_path(acc_id)

        # 1. Update .env variables
        env_prefix = acc_id.upper()
        self._append_to_env({
            f"{env_prefix}_LOGIN": str(login).strip(),
            f"{env_prefix}_PASSWORD": str(password).strip(),
            f"{env_prefix}_SERVER": str(server).strip(),
            f"{env_prefix}_MT5_PATH": str(terminal_path).strip(),
        })

        # 2. Add to config.yaml account_list
        yaml_entry = {
            "id": acc_id,
            "name": name.strip(),
            "type": account_type.upper(),
            "balance": balance_float,
            "mode": mode.upper(),
            "execution_mode": execution_mode.upper(),
            "copy_enabled": (mode.upper() == "COPY_FOLLOWER" or mode.upper() == "COPY_MASTER"),
            "max_daily_loss_pct": loss_pct,
            "risk_per_trade_pct": risk_pct,
            "min_rr": 2.0,
            "env_login_var": f"{env_prefix}_LOGIN",
            "env_password_var": f"{env_prefix}_PASSWORD",
            "env_server_var": f"{env_prefix}_SERVER",
            "env_path_var": f"{env_prefix}_MT5_PATH",
            "is_active": True,
        }

        if "accounts" not in self.config:
            self.config["accounts"] = {"enabled": True, "multi_account_mode": True, "account_list": []}
        if "account_list" not in self.config["accounts"]:
            self.config["accounts"]["account_list"] = []

        self.config["accounts"]["account_list"].append(yaml_entry)
        self._save_config()

        # 3. Reload in-memory list
        self.load_all()

        # 4. Sync to Supabase
        self.sync_account_to_supabase(yaml_entry)

        logger.info(f"Successfully created and registered {acc_id.upper()}: {name} (${balance_float:.2f})")
        return yaml_entry

    def toggle_execution_mode(self, acc_id: str, new_mode: str) -> Dict[str, Any]:
        """Toggles an account between 'AUTOMATED_EA' and 'VISUAL_SCANNER'."""
        acc_id = acc_id.lower()
        if new_mode not in ["AUTOMATED_EA", "VISUAL_SCANNER"]:
            raise ValueError("Mode must be either 'AUTOMATED_EA' or 'VISUAL_SCANNER'")

        for item in self.config.get("accounts", {}).get("account_list", []):
            if item.get("id") == acc_id:
                item["execution_mode"] = new_mode
                self._save_config()
                self.load_all()
                logger.info(f"[{acc_id.upper()}] Execution mode updated to {new_mode}")
                return item

        raise KeyError(f"Account {acc_id} not found")

    def remove_account(self, acc_id: str) -> bool:
        """Removes an account from configuration and in-memory fleet."""
        acc_id = acc_id.lower()
        acc_list = self.config.get("accounts", {}).get("account_list", [])
        original_len = len(acc_list)
        filtered = [a for a in acc_list if a.get("id", "").lower() != acc_id]

        if len(filtered) < original_len:
            self.config["accounts"]["account_list"] = filtered
            self._save_config()
            self.load_all()
            logger.info(f"Account [{acc_id.upper()}] removed from fleet.")
            return True
        return False

    @staticmethod
    def resolve_system_mt5_path(custom_path: Optional[str] = None) -> Optional[str]:
        """Resolves valid MT5 terminal64.exe executable from custom path or standard Windows locations."""
        if custom_path and os.path.exists(custom_path):
            return custom_path

        candidates = [
            r"C:\Program Files\MetaTrader 5\terminal64.exe",
            r"C:\Program Files\Exness MT5\terminal64.exe",
            r"C:\Program Files\Exness MetaTrader 5\terminal64.exe",
            r"C:\Program Files\FTMO MetaTrader 5\terminal64.exe",
            r"C:\Program Files\BrightFunded MT5\terminal64.exe",
            r"C:\Program Files\MetaTrader 5 Terminal\terminal64.exe",
            os.path.expanduser(r"~\AppData\Local\Programs\MetaTrader 5\terminal64.exe"),
        ]
        for c in candidates:
            if os.path.exists(c):
                return c
        return None

    def launch_terminal(self, acc_id: str) -> bool:
        """
        Launches the dedicated MT5 terminal executable for this account locally.
        Runs terminal64.exe as a detached background process.
        """
        acc_id = acc_id.lower()
        acc = next((a for a in self.accounts if a["id"] == acc_id), None)

        path = self.resolve_system_mt5_path(acc.get("path") if acc else None)
        if not path:
            logger.error("Cannot launch terminal: MT5 executable not found on system")
            return False

        try:
            terminal_dir = str(Path(path).parent)
            logger.info(f"Launching MT5 terminal process for [{acc_id.upper() if acc else 'DEFAULT'}] -> {path}")
            subprocess.Popen([path], cwd=terminal_dir, shell=False)
            return True
        except Exception as e:
            logger.error(f"Failed to launch terminal for {acc_id}: {e}")
            return False

    def launch_all_terminals(self) -> List[Dict[str, Any]]:
        """Launches all distinct MT5 terminals across configured active accounts."""
        results = []
        launched_paths = set()

        for acc in self.accounts:
            if not acc.get("is_active"):
                continue
            path = acc.get("path")
            if path and path not in launched_paths:
                success = self.launch_terminal(acc["id"])
                results.append({"id": acc["id"], "path": path, "launched": success})
                if success:
                    launched_paths.add(path)
        return results

    def update_account_equity(self, acc_id: str, equity: float) -> Dict[str, Any]:
        """
        Updates live equity and checks Prop Firm Drawdown circuit breaker.
        Circuit Breaker triggers if (Baseline - Equity) >= Max Allowed Loss.
        """
        acc_id = acc_id.lower()
        acc = next((a for a in self.accounts if a["id"] == acc_id), None)
        if not acc:
            return {}

        baseline = self.daily_baselines.get(acc_id, acc["balance"])
        max_allowed_loss = baseline * (acc["max_daily_loss_pct"] / 100.0)
        current_loss = baseline - equity

        acc["equity"] = equity
        acc["daily_pnl"] = equity - baseline
        acc["daily_drawdown_dollars"] = max(0.0, current_loss)
        acc["daily_drawdown_pct"] = (max(0.0, current_loss) / baseline) * 100.0

        # Update high water mark
        if equity > self.high_water_marks.get(acc_id, 0.0):
            self.high_water_marks[acc_id] = equity

        # Check Circuit Breaker
        if current_loss >= max_allowed_loss:
            acc["circuit_breaker_tripped"] = True
            logger.warning(f"⚠️ [CIRCUIT BREAKER TRIGGERED] {acc_id.upper()} ({acc['name']}): Loss ${current_loss:.2f} >= Limit ${max_allowed_loss:.2f}! Trading Halted.")
        else:
            acc["circuit_breaker_tripped"] = False

        return acc

    def get_fleet_summary(self) -> List[Dict[str, Any]]:
        """Returns structured status of all trading accounts for the UI."""
        self.load_all()
        summary = []
        for a in self.accounts:
            balance = a["balance"]
            equity = a.get("equity", balance)
            daily_pnl = a.get("daily_pnl", 0.0)
            connection_state = a.get("connection_state", "DISCONNECTED")

            # Check live MT5 terminal connection if available
            try:
                import MetaTrader5 as mt5
                term_path = self.resolve_system_mt5_path(a.get("path"))
                init_ok = mt5.initialize(path=term_path) if term_path else mt5.initialize()
                if init_ok:
                    acc_info = mt5.account_info()
                    term_info = mt5.terminal_info()
                    if acc_info and (not a.get("login") or str(acc_info.login) == str(a.get("login"))):
                        balance = float(acc_info.balance)
                        equity = float(acc_info.equity)
                        daily_pnl = float(acc_info.profit)
                        connection_state = "CONNECTED" if (term_info and term_info.connected) else "TERMINAL_OPEN"
                        a["balance"] = balance
                        a["equity"] = equity
                        a["daily_pnl"] = daily_pnl
                        a["connection_state"] = connection_state
            except Exception as e:
                logger.debug(f"Live MT5 sync check: {e}")

            baseline = self.daily_baselines.get(a["id"], balance)
            max_loss_dollars = baseline * (a["max_daily_loss_pct"] / 100.0)
            cur_loss = baseline - equity
            drawdown_pct = max(0.0, (cur_loss / baseline) * 100.0)

            summary.append({
                "id": a["id"],
                "name": a["name"],
                "type": a["type"],
                "balance": balance,
                "equity": equity,
                "daily_pnl": daily_pnl,
                "daily_drawdown_pct": round(drawdown_pct, 2),
                "max_daily_loss_pct": a["max_daily_loss_pct"],
                "max_daily_loss_dollars": round(max_loss_dollars, 2),
                "risk_per_trade_pct": a["risk_per_trade_pct"],
                "min_rr": a["min_rr"],
                "mode": a["mode"],
                "execution_mode": a.get("execution_mode", "AUTOMATED_EA"),
                "circuit_breaker_tripped": a.get("circuit_breaker_tripped", False),
                "connection_state": connection_state,
                "path": a.get("path"),
                "is_active": a.get("is_active", True),
            })
        return summary

    def sync_account_to_supabase(self, acc_entry: Dict[str, Any]):
        """Persists account entry into Supabase accounts_overview table."""
        try:
            import urllib.request
            url = os.getenv("NEXT_PUBLIC_SUPABASE_URL") or "https://xeckbeavsvyoporldjzm.supabase.co"
            key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY")
            if not key:
                return

            rest_url = f"{url}/rest/v1/accounts_overview"
            payload = json.dumps({
                "account_id": acc_entry["id"],
                "name": acc_entry["name"],
                "account_type": acc_entry["type"],
                "balance": acc_entry["balance"],
                "equity": acc_entry["balance"],
                "daily_pnl": 0.0,
                "daily_drawdown_pct": 0.0,
                "is_active": acc_entry["is_active"],
            }).encode("utf-8")

            req = urllib.request.Request(
                rest_url,
                data=payload,
                headers={
                    "apikey": key,
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                    "Prefer": "resolution=merge-duplicates",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as res:
                logger.info(f"Synced account {acc_entry['id']} to Supabase: status {res.status}")
        except Exception as e:
            logger.warning(f"Supabase sync notice: {e}")

    def _append_to_env(self, key_values: Dict[str, str]):
        """Appends new credential environment variables to .env."""
        try:
            existing_lines = []
            if self.env_path.exists():
                with open(self.env_path, "r", encoding="utf-8") as f:
                    existing_lines = f.readlines()

            keys_written = set()
            new_lines = []
            for line in existing_lines:
                found = False
                for k, v in key_values.items():
                    if line.strip().startswith(f"{k}="):
                        new_lines.append(f"{k}={v}\n")
                        keys_written.add(k)
                        found = True
                        break
                if not found:
                    new_lines.append(line)

            for k, v in key_values.items():
                if k not in keys_written:
                    new_lines.append(f"{k}={v}\n")

            with open(self.env_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
        except Exception as e:
            logger.error(f"Failed to update {self.env_path}: {e}")

    def _save_config(self):
        """Serializes updated config back to config/config.yaml."""
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(self.config, f, default_flow_style=False, sort_keys=False)
        except Exception as e:
            logger.error(f"Failed to write config: {e}")
