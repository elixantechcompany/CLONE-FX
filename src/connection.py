"""
MT5 and Exness Connection Manager
Handles initialization, authentication, symbol resolution, and connection recovery.
"""

import logging
import os
from typing import Optional, Tuple
import MetaTrader5 as mt5

logger = logging.getLogger("GoldBot.Connection")


class MT5Connector:
    def __init__(
        self,
        account: Optional[int] = None,
        password: Optional[str] = None,
        server: Optional[str] = None,
        path: Optional[str] = None,
    ):
        self.account = account or (int(os.getenv("MT5_ACCOUNT_NUMBER")) if os.getenv("MT5_ACCOUNT_NUMBER") else None)
        self.password = password or os.getenv("MT5_PASSWORD")
        self.server = server or os.getenv("MT5_SERVER")
        self.path = path or os.getenv("MT5_PATH") or None
        self.connected_symbol: Optional[str] = None
        self.symbol_info = None

    def initialize(self) -> bool:
        """Initializes the MT5 terminal connection and logs into the Exness account."""
        init_args = {}
        if self.path:
            init_args["path"] = self.path
        if self.account:
            init_args["login"] = self.account
        if self.password:
            init_args["password"] = self.password
        if self.server:
            init_args["server"] = self.server

        logger.info("Initializing MetaTrader 5 terminal connection...")
        if not mt5.initialize(**init_args):
            err_code, err_desc = mt5.last_error()
            logger.error(f"MT5 initialization failed: [{err_code}] {err_desc}")
            return False

        # If credentials were provided, ensure logged in
        if self.account and self.password and self.server:
            authorized = mt5.login(
                login=self.account,
                password=self.password,
                server=self.server,
            )
            if not authorized:
                err_code, err_desc = mt5.last_error()
                logger.error(f"Failed to authorize account {self.account} on server {self.server}: [{err_code}] {err_desc}")
                return False

        terminal_info = mt5.terminal_info()
        account_info = mt5.account_info()

        if terminal_info is None or account_info is None:
            logger.error("Could not fetch terminal/account info from MT5.")
            return False

        logger.info(f"Connected to MT5 Terminal (Build: {terminal_info.build})")
        logger.info(
            f"Logged into Account: {account_info.login} ({account_info.server}) | "
            f"Balance: {account_info.balance:.2f} {account_info.currency} | "
            f"Equity: {account_info.equity:.2f} {account_info.currency} | "
            f"Leverage: 1:{account_info.leverage}"
        )

        if not terminal_info.trade_allowed:
            logger.warning(
                "WARNING: Algo Trading is NOT allowed in your MT5 terminal settings! "
                "Please enable 'Allow Algo Trading' in MT5 > Tools > Options > Expert Advisors."
            )

        return True

    def resolve_symbol(self, candidate_symbols: list) -> Optional[str]:
        """
        Auto-detects which Gold symbol is available on the Exness broker account.
        Common variants: 'XAUUSD', 'XAUUSDm' (Exness Standard), 'XAUUSD_i', 'XAUUSDz', 'GOLD'.
        """
        for sym in candidate_symbols:
            info = mt5.symbol_info(sym)
            if info is not None:
                # Enable symbol in Market Watch if not visible
                if not info.visible:
                    if not mt5.symbol_select(sym, True):
                        logger.warning(f"Could not enable {sym} in Market Watch.")
                        continue
                    info = mt5.symbol_info(sym)

                self.connected_symbol = sym
                self.symbol_info = info
                logger.info(
                    f"Resolved active Gold symbol: '{sym}' | "
                    f"Digits: {info.digits} | Point: {info.point} | "
                    f"Spread: {info.spread} points | Min Lot: {info.volume_min} | Step: {info.volume_step}"
                )
                return sym

        logger.error(f"None of the candidate symbols {candidate_symbols} were found in MT5 Market Watch.")
        return None

    def get_account_summary(self) -> dict:
        """Returns fresh balance, equity, and margin metrics."""
        acc = mt5.account_info()
        if acc is None:
            return {}
        return {
            "balance": acc.balance,
            "equity": acc.equity,
            "margin": acc.margin,
            "free_margin": acc.margin_free,
            "profit": acc.profit,
            "currency": acc.currency,
        }

    def is_connected(self) -> bool:
        """Checks if MT5 terminal is actively running, initialized, and connected to the trade server."""
        try:
            terminal_info = mt5.terminal_info()
            if terminal_info is None or not getattr(terminal_info, "connected", False):
                return False
            account_info = mt5.account_info()
            return account_info is not None
        except Exception:
            return False

    @staticmethod
    def check_internet(host: str = "8.8.8.8", port: int = 53, timeout: float = 2.0) -> bool:
        """Verifies if the host machine has active internet connectivity."""
        import socket
        try:
            socket.setdefaulttimeout(timeout)
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((host, port))
            return True
        except Exception:
            try:
                # Fallback to Cloudflare DNS
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.connect(("1.1.1.1", 53))
                return True
            except Exception:
                return False

    def reconnect(self, candidate_symbols: Optional[list] = None) -> bool:
        """
        Attempts a full teardown and recovery cycle after internet disruption or terminal drop.
        Waits for internet, re-initializes MT5, re-authorizes account, and re-resolves symbol.
        """
        logger.warning("[AUTO-RECONNECT] Attempting to restore MT5 & internet connection...")
        try:
            mt5.shutdown()
        except Exception:
            pass

        if not self.check_internet():
            logger.warning("[AUTO-RECONNECT] Internet connection is currently down. Waiting for network recovery...")
            return False

        if not self.initialize():
            logger.warning("[AUTO-RECONNECT] MT5 initialization failed. Will retry shortly...")
            return False

        if candidate_symbols:
            resolved = self.resolve_symbol(candidate_symbols)
            if not resolved:
                logger.warning("[AUTO-RECONNECT] Could not re-resolve gold symbol yet.")
                return False

        logger.info("[AUTO-RECONNECT SUCCESS] Connection successfully restored and verified!")
        return True

    def shutdown(self):
        """Disconnects and cleanly shuts down the MT5 Python interface."""
        logger.info("Shutting down MT5 connection...")
        try:
            mt5.shutdown()
        except Exception:
            pass
