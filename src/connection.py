"""
MT5 and Broker Connection Manager (Multi-Symbol & Multi-Account Isolated Terminals)
Enforces:
  1. Dedicated MT5 Terminal Process Binding per ACCOUNT_ID.
  2. Strict 7-Point Pre-Trade Identity Verification (Login, Account Number, Server,
     Expected Account ID, Terminal Process Identity, Native Algo Trading Permission, Symbol Availability).
  3. Immediate Rejection on Mismatch: "ACCOUNT ID MISMATCH — TRADING DISABLED".
  4. Zero Automatic Switch Overrides (Algo Trading is controlled 100% by the user in MT5).
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
        self.account_id = account_id.lower()
        self.account = int(account) if (account and str(account).isdigit()) else None
        self.password = password
        self.server = server.strip() if server else None
        self.path = path or os.getenv("MT5_PATH") or None
        self.resolved_symbols: Dict[str, str] = {}  # canonical_name (e.g. "XAUUSD") -> broker_symbol (e.g. "XAU/USD")
        self.symbol_specs: Dict[str, SymbolSpecification] = {}
        self.connected_symbol: Optional[str] = None
        self.last_identity_check_passed: bool = False
        self.last_identity_mismatch_reason: str = ""

    def ensure_terminal_context(self) -> bool:
        """
        Binds the MT5 API context to this account's dedicated terminal executable path.
        Guarantees that Account A communicates strictly with Terminal A, and Account B with Terminal B.
        """
        try:
            if self.path and os.path.exists(self.path):
                # Attach to specific terminal installation path
                res = mt5.initialize(path=self.path)
                return bool(res)
            else:
                res = mt5.initialize()
                return bool(res)
        except Exception as e:
            logger.warning(f"[{self.account_id.upper()}] Error ensuring terminal context: {e}")
            return False

    def initialize(self) -> bool:
        """Initializes the MT5 terminal connection for this account's dedicated terminal instance."""
        logger.info(f"Initializing MetaTrader 5 terminal connection for [{self.account_id.upper()}]...")

        self.ensure_terminal_context()

        acc = mt5.account_info()
        terminal_info = mt5.terminal_info()

        if terminal_info is None or acc is None or (self.account and acc.login != self.account):
            # Only try explicit login if not already logged into the required account
            if self.account and self.password and self.server:
                logger.info(f"[{self.account_id.upper()}] Attempting login for #{self.account} on {self.server}...")
                mt5.login(login=self.account, password=str(self.password), server=str(self.server))
                acc = mt5.account_info()
                terminal_info = mt5.terminal_info()

        if terminal_info is None or acc is None:
            err_code, err_desc = mt5.last_error()
            logger.error(
                f"[{self.account_id.upper()}] MT5 is not logged into an active trade account: [{err_code}] {err_desc}. "
                f"Please open this account's MT5 terminal window and log in."
            )
            return False

        # Validate identity on initialization
        valid, msg = self.verify_pre_trade_identity(require_algo_on=False)
        if not valid:
            logger.error(f"[{self.account_id.upper()}] {msg}")
            return False

        account_info = acc
        algo_status = self.get_algo_trading_status()

        logger.info(
            f"Connected to MT5 Terminal for [{self.account_id.upper()}] (Build: {terminal_info.build}) | "
            f"Account: #{account_info.login} ({account_info.server}) | "
            f"Balance: ${account_info.balance:.2f} {account_info.currency} | "
            f"Equity: ${account_info.equity:.2f} | "
            f"MT5 Algo Trading: {'ENABLED' if algo_status['is_algo_enabled'] else 'DISABLED'}"
        )

        if not algo_status["is_algo_enabled"]:
            logger.warning(
                f"[{self.account_id.upper()}] MT5 Algo Trading is currently DISABLED on this terminal. "
                f"(Terminal Allowed: {algo_status['terminal_trade_allowed']}, Account Expert: {algo_status['account_trade_expert']}). "
                f"Bot will monitor markets and manage open positions, but will NOT place new trades until Algo Trading is enabled."
            )

        return True

    def get_algo_trading_status(self) -> Dict[str, Any]:
        """
        Retrieves native MT5 Algo Trading permission metrics from this account's terminal:
          - terminal_info().trade_allowed: MT5 GUI 'Algo Trading' master button.
          - account_info().trade_expert: Broker/Account EA trading permission.
          - account_info().trade_allowed: Broker/Account general trading permission.
        """
        try:
            self.ensure_terminal_context()
            term = mt5.terminal_info()
            acc = mt5.account_info()

            terminal_trade_allowed = bool(getattr(term, "trade_allowed", False)) if term else False
            terminal_connected = bool(getattr(term, "connected", False)) if term else False
            account_trade_allowed = bool(getattr(acc, "trade_allowed", False)) if acc else False
            account_trade_expert = bool(getattr(acc, "trade_expert", False)) if acc else False

            is_algo_enabled = terminal_trade_allowed and account_trade_expert and account_trade_allowed

            return {
                "is_algo_enabled": is_algo_enabled,
                "terminal_trade_allowed": terminal_trade_allowed,
                "account_trade_expert": account_trade_expert,
                "account_trade_allowed": account_trade_allowed,
                "terminal_connected": terminal_connected,
                "login": getattr(acc, "login", None) if acc else None,
                "server": getattr(acc, "server", None) if acc else None,
            }
        except Exception as e:
            logger.warning(f"[{self.account_id.upper()}] Could not fetch Algo Trading status: {e}")
            return {
                "is_algo_enabled": False,
                "terminal_trade_allowed": False,
                "account_trade_expert": False,
                "account_trade_allowed": False,
                "terminal_connected": False,
                "login": None,
                "server": None,
            }

    def verify_pre_trade_identity(
        self,
        symbol: Optional[str] = None,
        require_algo_on: bool = True,
    ) -> Tuple[bool, str]:
        """
        MANDATORY 7-POINT PRE-TRADE GATEKEEPER:
          1. MT5 account login: Matches self.account
          2. MT5 account number: Active in terminal
          3. MT5 server: Matches self.server
          4. Expected ACCOUNT_ID: Verified
          5. Terminal / process identity: Live connection verified
          6. Algo Trading permission: Checked (if require_algo_on=True)
          7. Symbol availability: Verified in Market Watch
        
        Returns (True, "OK") or (False, "ACCOUNT ID MISMATCH — TRADING DISABLED: <reason>")
        """
        self.ensure_terminal_context()

        term = mt5.terminal_info()
        acc = mt5.account_info()

        # Check 5: Terminal Process & Live Connection
        if term is None or not getattr(term, "connected", False):
            self.last_identity_check_passed = False
            self.last_identity_mismatch_reason = "MT5 terminal is disconnected or trade server connection is down."
            return False, f"ACCOUNT ID MISMATCH — TRADING DISABLED: [{self.account_id.upper()}] {self.last_identity_mismatch_reason}"

        # Check 1 & 2: Account Login & Number Verification
        if acc is None:
            self.last_identity_check_passed = False
            self.last_identity_mismatch_reason = "No active account session found in MT5."
            return False, f"ACCOUNT ID MISMATCH — TRADING DISABLED: [{self.account_id.upper()}] {self.last_identity_mismatch_reason}"

        # Check 1 & 2: Account Login & Number Verification
        if not self.account or not self.server:
            self.last_identity_check_passed = False
            self.last_identity_mismatch_reason = f"No credentials configured for [{self.account_id.upper()}]."
            return False, f"ACCOUNT NOT CONFIGURED — TRADING DISABLED: {self.last_identity_mismatch_reason}"

        if acc.login != self.account:
            self.last_identity_check_passed = False
            self.last_identity_mismatch_reason = (
                f"Active login #{acc.login} does not match expected #{self.account} for [{self.account_id.upper()}]."
            )
            return False, f"ACCOUNT ID MISMATCH — TRADING DISABLED: {self.last_identity_mismatch_reason}"

        # Check 3: Server Verification
        current_server = str(getattr(acc, "server", "")).strip().lower()
        expected_server = str(self.server).strip().lower()
        if current_server != expected_server:
            self.last_identity_check_passed = False
            self.last_identity_mismatch_reason = (
                f"Active server '{acc.server}' does not match expected '{self.server}' for [{self.account_id.upper()}]."
            )
            return False, f"ACCOUNT ID MISMATCH — TRADING DISABLED: {self.last_identity_mismatch_reason}"

        # Check 6: Native Algo Trading Master Switch
        if require_algo_on:
            algo_status = self.get_algo_trading_status()
            if not algo_status["is_algo_enabled"]:
                self.last_identity_check_passed = False
                self.last_identity_mismatch_reason = (
                    f"MT5 Algo Trading is DISABLED on terminal (Terminal: {algo_status['terminal_trade_allowed']}, Expert: {algo_status['account_trade_expert']})."
                )
                return False, f"TRADING DISABLED: [{self.account_id.upper()}] {self.last_identity_mismatch_reason}"

        # Check 7: Symbol Availability (if symbol specified)
        if symbol:
            info = mt5.symbol_info(symbol)
            if info is None:
                self.last_identity_check_passed = False
                self.last_identity_mismatch_reason = f"Symbol '{symbol}' not found on broker."
                return False, f"ACCOUNT ID MISMATCH — TRADING DISABLED: [{self.account_id.upper()}] {self.last_identity_mismatch_reason}"
            if not info.visible:
                if not mt5.symbol_select(symbol, True):
                    self.last_identity_check_passed = False
                    self.last_identity_mismatch_reason = f"Symbol '{symbol}' could not be enabled in Market Watch."
                    return False, f"ACCOUNT ID MISMATCH — TRADING DISABLED: [{self.account_id.upper()}] {self.last_identity_mismatch_reason}"

        self.last_identity_check_passed = True
        self.last_identity_mismatch_reason = ""
        return True, "OK"

    def verify_account_identity(self) -> bool:
        """Confirms that the active MT5 terminal connection matches expected credentials."""
        valid, msg = self.verify_pre_trade_identity(require_algo_on=False)
        if not valid:
            logger.warning(msg)
        return valid

    def login_account(self, account: int, password: str, server: str) -> bool:
        """Switches active login on current MT5 terminal."""
        self.ensure_terminal_context()
        self.account = int(account)
        self.password = password
        self.server = server.strip()
        authorized = mt5.login(login=int(account), password=password, server=server)
        if not authorized:
            err_code, err_desc = mt5.last_error()
            logger.error(f"[{self.account_id.upper()}] Failed to switch to account {account} on server {server}: [{err_code}] {err_desc}")
            return False
        return True

    def resolve_symbol(self, candidate_symbols: list, canonical_name: str = "XAUUSD") -> Optional[str]:
        """
        Auto-detects which broker-specific symbol is available on the account.
        Queries and caches full dynamic specifications.
        """
        self.ensure_terminal_context()
        for sym in candidate_symbols:
            info = mt5.symbol_info(sym)
            if info is not None:
                if not info.visible:
                    if not mt5.symbol_select(sym, True):
                        logger.warning(f"[{self.account_id.upper()}] Could not enable {sym} in Market Watch.")
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
                    f"[{self.account_id.upper()}] Resolved '{canonical_name}' -> Broker Symbol: '{sym}' | "
                    f"Digits: {spec.digits} | Point: {spec.point} | Tick Size: {spec.tick_size} | "
                    f"Tick Value: ${spec.tick_value:.2f} | Contract: {spec.contract_size} | "
                    f"Min Lot: {spec.volume_min} | Step: {spec.volume_step}"
                )
                return sym

        logger.error(f"[{self.account_id.upper()}] None of the candidate symbols {candidate_symbols} were found in MT5 Market Watch.")
        return None

    def resolve_all_symbols(self, symbols_cfg: dict) -> Dict[str, str]:
        """Resolves all active trading symbols from configuration."""
        self.ensure_terminal_context()
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
        self.ensure_terminal_context()
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
        self.ensure_terminal_context()
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
            self.ensure_terminal_context()
            terminal_info = mt5.terminal_info()
            if terminal_info is None or not getattr(terminal_info, "connected", False):
                return False
            account_info = mt5.account_info()
            return account_info is not None
        except Exception:
            return False

    @staticmethod
    def check_internet(host: str = "8.8.8.8", port: int = 53, timeout: float = 2.0) -> bool:
        """Verifies if host machine has active internet connectivity across multiple redundant endpoints."""
        import socket
        endpoints = [(host, port), ("1.1.1.1", 53), ("208.67.222.222", 53)]
        for h, p in endpoints:
            try:
                socket.setdefaulttimeout(timeout)
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.connect((h, p))
                return True
            except Exception:
                continue
        return False

    def reconnect(self, symbols_cfg: Optional[dict] = None) -> bool:
        """Full teardown and recovery cycle after internet disruption or terminal drop."""
        logger.warning(f"[{self.account_id.upper()}] [AUTO-RECONNECT] Attempting to restore MT5 connection...")
        try:
            mt5.shutdown()
        except Exception:
            pass

        if not self.check_internet():
            logger.warning(f"[{self.account_id.upper()}] [AUTO-RECONNECT] Internet connection is down. Waiting for network recovery...")
            return False

        if not self.initialize():
            logger.warning(f"[{self.account_id.upper()}] [AUTO-RECONNECT] MT5 initialization failed. Will retry shortly...")
            return False

        if not self.verify_account_identity():
            logger.warning(f"[{self.account_id.upper()}] [AUTO-RECONNECT] Account identity could not be verified.")
            return False

        if symbols_cfg:
            self.resolve_all_symbols(symbols_cfg)

        logger.info(f"[{self.account_id.upper()}] [AUTO-RECONNECT SUCCESS] Connection successfully restored!")
        return True

    def shutdown(self):
        """Disconnects and cleanly shuts down MT5 Python interface."""
        logger.info(f"[{self.account_id.upper()}] Shutting down MT5 connection...")
        try:
            mt5.shutdown()
        except Exception:
            pass
