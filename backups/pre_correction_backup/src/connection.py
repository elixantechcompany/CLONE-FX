"""
MT5 and Broker Connection Manager (Multi-Symbol & Multi-Account Support)
Handles initialization, authentication, dynamic symbol resolution, and connection recovery.
Credentials are kept secure and never leaked or printed.
"""

import logging
import os
import time
from typing import Dict, List, Optional, Tuple, Any
import MetaTrader5 as mt5

logger = logging.getLogger("GoldBot.Connection")


class SymbolSpecification:
    """Holds dynamic MT5 symbol specification metrics."""
    def __init__(
        self,
        symbol: str,
        digits: int = 2,
        point: float = 0.01,
        tick_size: float = 0.01,
        tick_value: float = 1.0,
        contract_size: float = 100.0,
        volume_min: float = 0.01,
        volume_max: float = 100.0,
        volume_step: float = 0.01,
        stops_level: int = 0,
        freeze_level: int = 0,
        spread: int = 20,
    ):
        self.symbol = symbol
        self.digits = digits
        self.point = point
        self.tick_size = tick_size if tick_size > 0 else point
        self.tick_value = tick_value if tick_value > 0 else 1.0
        self.contract_size = contract_size if contract_size > 0 else 100.0
        self.volume_min = volume_min
        self.volume_max = volume_max
        self.volume_step = volume_step
        self.stops_level = stops_level
        self.freeze_level = freeze_level
        self.spread = spread


class MT5Connector:
    def __init__(
        self,
        account: Optional[int] = None,
        password: Optional[str] = None,
        server: Optional[str] = None,
        path: Optional[str] = None,
        account_id: str = "account_1",
    ):
        self.account_id = account_id
        self.account = account
        self.password = password
        self.server = server
        self.path = path or os.getenv("MT5_PATH") or None
        self.resolved_symbols: Dict[str, str] = {} # canonical_name (e.g. "XAUUSD") -> broker_symbol (e.g. "XAUUSDm")
        self.symbol_specs: Dict[str, SymbolSpecification] = {}
        self.connected_symbol: Optional[str] = None

    def initialize(self) -> bool:
        """Initializes the MT5 terminal connection and logs into the account securely."""
        logger.info(f"Initializing MetaTrader 5 terminal connection for [{self.account_id}]...")

        target_login = int(self.account) if (self.account and str(self.account).isdigit()) else None

        # 1. Attach directly to active running MT5 terminal
        init_ok = mt5.initialize()
        if not init_ok and self.path and os.path.exists(self.path):
            init_ok = mt5.initialize(path=self.path)

        if not init_ok:
            err_code, err_desc = mt5.last_error()
            logger.error(f"MT5 initialization failed: [{err_code}] {err_desc}")
            return False

        # 2. Check current terminal account & switch if target login is specified and different
        acc = mt5.account_info()
        if target_login and self.password and self.server and (acc is None or acc.login != target_login):
            logger.info(f"Logging into {target_login} on {self.server}...")
            authorized = mt5.login(
                login=target_login,
                password=str(self.password),
                server=str(self.server),
            )
            if not authorized:
                err_code, err_desc = mt5.last_error()
                logger.warning(f"Could not switch account to {target_login} on {self.server}: [{err_code}] {err_desc}")

        account_info = mt5.account_info()
        terminal_info = mt5.terminal_info()

        if terminal_info is None or account_info is None:
            logger.error(f"Could not fetch terminal/account info from MT5 for [{self.account_id}].")
            return False

        logger.info(f"Connected to MT5 Terminal for [{self.account_id}] (Build: {terminal_info.build})")
        logger.info(
            f"Account: {account_info.login} ({account_info.server}) | "
            f"Balance: ${account_info.balance:.2f} {account_info.currency} | "
            f"Equity: ${account_info.equity:.2f} | Leverage: 1:{account_info.leverage}"
        )

        if not terminal_info.trade_allowed:
            logger.warning(
                "WARNING: Algo Trading is NOT allowed in your MT5 terminal settings! "
                "Please enable 'Allow Algo Trading' in MT5 > Tools > Options > Expert Advisors."
            )

        return True

    def login_account(self, account: int, password: str, server: str) -> bool:
        """Switches active login on current MT5 terminal."""
        self.account = account
        self.password = password
        self.server = server
        authorized = mt5.login(login=int(account), password=password, server=server)
        if not authorized:
            err_code, err_desc = mt5.last_error()
            logger.error(f"Failed to switch to account {account} on server {server}: [{err_code}] {err_desc}")
            return False
        return True

    def resolve_symbol(self, candidate_symbols: list, canonical_name: str = "XAUUSD") -> Optional[str]:
        """
        Auto-detects which broker-specific symbol is available on the account.
        Queries and caches full dynamic specifications.
        """
        for sym in candidate_symbols:
            info = mt5.symbol_info(sym)
            if info is not None:
                if not info.visible:
                    if not mt5.symbol_select(sym, True):
                        logger.warning(f"Could not enable {sym} in Market Watch.")
                        continue
                    info = mt5.symbol_info(sym)

                self.resolved_symbols[canonical_name] = sym
                if not self.connected_symbol:
                    self.connected_symbol = sym

                # Cache full symbol specs
                spec = SymbolSpecification(
                    symbol=sym,
                    digits=info.digits,
                    point=info.point,
                    tick_size=info.trade_tick_size if info.trade_tick_size > 0 else info.point,
                    tick_value=info.trade_tick_value if info.trade_tick_value > 0 else 1.0,
                    contract_size=info.trade_contract_size if info.trade_contract_size > 0 else 100.0,
                    volume_min=info.volume_min,
                    volume_max=info.volume_max,
                    volume_step=info.volume_step,
                    stops_level=getattr(info, "trade_stops_level", getattr(info, "stops_level", 0)),
                    freeze_level=getattr(info, "trade_freeze_level", getattr(info, "freeze_level", 0)),
                    spread=info.spread,
                )
                self.symbol_specs[sym] = spec
                self.symbol_specs[canonical_name] = spec

                logger.info(
                    f"Resolved '{canonical_name}' -> Broker Symbol: '{sym}' | "
                    f"Digits: {spec.digits} | Point: {spec.point} | Tick Size: {spec.tick_size} | "
                    f"Tick Value: ${spec.tick_value:.2f} | Contract: {spec.contract_size} | "
                    f"Min Lot: {spec.volume_min} | Step: {spec.volume_step}"
                )
                return sym

        logger.error(f"None of the candidate symbols {candidate_symbols} were found in MT5 Market Watch.")
        return None

    def resolve_all_symbols(self, symbols_cfg: dict) -> Dict[str, str]:
        """Resolves all active trading symbols from configuration."""
        active_list = symbols_cfg.get("active_symbols", ["XAUUSD", "BTCUSD"])
        settings = symbols_cfg.get("symbol_settings", {})
        resolved = {}
        for canonical in active_list:
            sym_set = settings.get(canonical, {})
            candidates = sym_set.get("candidates", [canonical])
            res = self.resolve_symbol(candidates, canonical_name=canonical)
            if res:
                resolved[canonical] = res
        return resolved

    def get_symbol_specs(self, symbol: str) -> Optional[SymbolSpecification]:
        """Returns cached or fresh symbol specifications."""
        if symbol in self.symbol_specs:
            return self.symbol_specs[symbol]

        info = mt5.symbol_info(symbol)
        if info is not None:
            spec = SymbolSpecification(
                symbol=symbol,
                digits=info.digits,
                point=info.point,
                tick_size=info.trade_tick_size if info.trade_tick_size > 0 else info.point,
                tick_value=info.trade_tick_value if info.trade_tick_value > 0 else 1.0,
                contract_size=info.trade_contract_size if info.trade_contract_size > 0 else 100.0,
                volume_min=info.volume_min,
                volume_max=info.volume_max,
                volume_step=info.volume_step,
                stops_level=getattr(info, "trade_stops_level", getattr(info, "stops_level", 0)),
                freeze_level=getattr(info, "trade_freeze_level", getattr(info, "freeze_level", 0)),
                spread=info.spread,
            )
            self.symbol_specs[symbol] = spec
            return spec
        return None

    def get_account_summary(self) -> dict:
        """Returns fresh balance, equity, margin, and currency metrics."""
        acc = mt5.account_info()
        if acc is None:
            return {}
        return {
            "login": acc.login,
            "server": acc.server,
            "balance": acc.balance,
            "equity": acc.equity,
            "margin": acc.margin,
            "free_margin": acc.margin_free,
            "margin_level": acc.margin_level if acc.margin > 0 else 0.0,
            "profit": acc.profit,
            "currency": acc.currency,
            "leverage": acc.leverage,
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
        """Verifies if host machine has active internet connectivity."""
        import socket
        try:
            socket.setdefaulttimeout(timeout)
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((host, port))
            return True
        except Exception:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.connect(("1.1.1.1", 53))
                return True
            except Exception:
                return False

    def reconnect(self, symbols_cfg: Optional[dict] = None) -> bool:
        """Full teardown and recovery cycle after internet disruption or terminal drop."""
        logger.warning(f"[AUTO-RECONNECT] Attempting to restore MT5 connection for [{self.account_id}]...")
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

        if symbols_cfg:
            self.resolve_all_symbols(symbols_cfg)

        logger.info(f"[AUTO-RECONNECT SUCCESS] Connection successfully restored for [{self.account_id}]!")
        return True

    def shutdown(self):
        """Disconnects and cleanly shuts down MT5 Python interface."""
        logger.info(f"Shutting down MT5 connection for [{self.account_id}]...")
        try:
            mt5.shutdown()
        except Exception:
            pass
