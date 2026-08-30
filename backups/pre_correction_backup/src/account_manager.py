"""
Multi-Account Manager & Account Context Isolation
Enforces complete isolation between Account 1 and Account 2:
  1. Independent Balance, Equity, Daily P&L, Daily Starting Equity, High-Water Mark.
  2. Independent Risk Budgets, Consecutive Losses, Position Tracking, and Circuit Breakers.
  3. Secure Credential Management (No credentials logged or exposed).
"""

import logging
import os
import time
import datetime
from typing import Dict, List, Optional, Tuple, Any

from src.connection import MT5Connector

logger = logging.getLogger("GoldBot.AccountManager")


class AccountContext:
    """Holds fully isolated trading state, connectors, and risk managers for a single account."""
    def __init__(
        self,
        account_id: str,
        name: str,
        login: Optional[int],
        password: Optional[str],
        server: Optional[str],
        config: dict,
        initial_balance: float = 1000.0,
        is_active: bool = True,
    ):
        self.account_id = account_id
        self.name = name
        self.login = login
        self.password = password
        self.server = server
        self.config = config
        self.initial_balance = initial_balance
        self.is_active = is_active

        # Connection instance
        self.connector = MT5Connector(
            account=self.login,
            password=self.password,
            server=self.server,
            account_id=self.account_id,
        )

        # Lazy-bound submodules (initialized on start)
        self.risk_manager = None
        self.executor = None

        # Financial tracking state
        self.balance: float = initial_balance
        self.equity: float = initial_balance
        self.free_margin: float = initial_balance
        self.daily_start_equity: float = initial_balance
        self.daily_high_water_equity: float = initial_balance
        self.daily_pnl: float = 0.0
        self.daily_drawdown_pct: float = 0.0

        # State flags
        self.trading_state: str = "NORMAL" # NORMAL, CAUTION, REDUCED_RISK, CRITICAL, EMERGENCY, HARD_STOP, PROFIT_PROTECTION, TARGET_REACHED
        self.is_manually_paused: bool = False
        self.pause_reason: str = ""
        self.last_sync_time: float = 0.0

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
        return acc_info

    def get_summary(self) -> dict:
        """Returns snapshot of this account's independent status."""
        hwm = self.risk_manager.lifetime_high_water_equity if self.risk_manager else self.daily_high_water_equity
        challenge_pnl = self.equity - self.initial_balance
        daily_loss = abs(min(0.0, self.daily_pnl))
        trailing_dd = max(0.0, hwm - self.equity)
        rem_daily_buf = max(0.0, (self.risk_manager.daily_hard_stop_loss if self.risk_manager else 25.0) - daily_loss)
        rem_trailing_buf = max(0.0, (self.risk_manager.trailing_hard_stop_drawdown if self.risk_manager else 50.0) - trailing_dd)

        return {
            "account_id": self.account_id,
            "name": self.name,
            "login": self.login,
            "balance": round(self.balance, 2),
            "equity": round(self.equity, 2),
            "free_margin": round(self.free_margin, 2),
            "challenge_target": 100.0,
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
            "is_active": self.is_active,
            "is_paused": self.is_manually_paused,
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
            acc_id = item.get("id", "account_1")
            name = item.get("name", f"Account {acc_id}")
            env_login = item.get("env_login_var", "")
            env_pass = item.get("env_password_var", "")
            env_server = item.get("env_server_var", "")
            
            fb_login = item.get("fallback_login_var", "MT5_ACCOUNT_NUMBER")
            fb_pass = item.get("fallback_password_var", "MT5_PASSWORD")
            fb_server = item.get("fallback_server_var", "MT5_SERVER")

            raw_login = os.getenv(env_login) or os.getenv(fb_login)
            login = int(raw_login) if raw_login and raw_login.isdigit() else None
            password = os.getenv(env_pass) or os.getenv(fb_pass) or None
            server = os.getenv(env_server) or os.getenv(fb_server) or None
            init_bal = float(item.get("initial_balance", 1000.0))
            is_active = bool(item.get("is_active", True))

            if login:
                ctx = AccountContext(
                    account_id=acc_id,
                    name=name,
                    login=login,
                    password=password,
                    server=server,
                    config=self.config,
                    initial_balance=init_bal,
                    is_active=is_active,
                )
                self.accounts[acc_id] = ctx
                # Never log credentials
                logger.info(f"Loaded Account [{acc_id}] '{name}' (Login: {login}, Server: {server}, Active: {is_active})")
            else:
                logger.info(f"Account [{acc_id}] '{name}' skipped (No login credentials found in environment).")

        # Fallback if no accounts configured: create default single account context
        if not self.accounts:
            raw_login = os.getenv("MT5_ACCOUNT_NUMBER")
            login = int(raw_login) if raw_login and raw_login.isdigit() else None
            password = os.getenv("MT5_PASSWORD")
            server = os.getenv("MT5_SERVER")
            ctx = AccountContext(
                account_id="account_1",
                name="Funded Account 1",
                login=login,
                password=password,
                server=server,
                config=self.config,
                initial_balance=1000.0,
                is_active=True,
            )
            self.accounts["account_1"] = ctx
            logger.info("Initialized default single account context 'account_1'.")

    def get_account(self, account_id: str) -> Optional[AccountContext]:
        return self.accounts.get(account_id)

    def get_active_accounts(self) -> List[AccountContext]:
        return [acc for acc in self.accounts.values() if acc.is_active]

    def get_all_summaries(self) -> List[dict]:
        return [acc.get_summary() for acc in self.accounts.values()]
