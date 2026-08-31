"""
Unit Tests for MT5 Multi-Terminal Process Isolation & Strict Pre-Trade Identity Verification.
Verifies:
  1. Terminal Identity Matching: Correct terminal + account credentials allow trading.
  2. Account ID Mismatch: Accidental cross-connection immediately triggers 'ACCOUNT ID MISMATCH — TRADING DISABLED' and blocks all orders.
  3. Server Mismatch: Incorrect server name blocks all orders.
  4. Independent Algo Trading Switches: Terminal A Algo ON / Terminal B Algo OFF operates in true isolation without cross-talk.
  5. Zero Automatic Switch Overrides: Bot never changes MT5 native Algo Trading switch.
"""

import unittest
from unittest.mock import MagicMock, patch
import yaml
import time
import os

from src.connection import MT5Connector, SymbolSpecification
from src.connection_state import AccountConnectionStateMachine, ConnectionState
from src.account_manager import AccountContext, MultiAccountManager
from src.execution import OrderExecutor
from src.risk_manager import RiskManager
from src.signal_ranker import TradeCandidate


class MockMT5Terminal:
    """Simulates an isolated MT5 terminal process with distinct logins and Algo Trading state."""
    def __init__(self, login: int, server: str, algo_allowed: bool = True, connected: bool = True, build: int = 6140):
        self.login = login
        self.server = server
        self.trade_allowed = algo_allowed
        self.trade_expert = algo_allowed
        self.connected = connected
        self.build = build
        self.balance = 1000.0 if login in (313812184, 314138473) else 20.0
        self.equity = self.balance
        self.margin = 0.0
        self.margin_free = self.balance
        self.currency = "USD"
        self.leverage = 100


class TestMultiTerminalIsolation(unittest.TestCase):
    def setUp(self):
        with open("config/config.yaml", "r") as f:
            self.config = yaml.safe_load(f)

    @patch("MetaTrader5.terminal_info")
    @patch("MetaTrader5.account_info")
    @patch("MetaTrader5.symbol_info")
    def test_01_correct_terminal_identity_allows_trading(self, mock_sym, mock_acc, mock_term):
        """Account A connecting to Terminal A with matching credentials passes 7-point check."""
        mock_acc.return_value = MockMT5Terminal(login=313812184, server="BrightFunded-Server", algo_allowed=True)
        mock_term.return_value = MockMT5Terminal(login=313812184, server="BrightFunded-Server", algo_allowed=True)
        
        sym_mock = MagicMock()
        sym_mock.visible = True
        mock_sym.return_value = sym_mock

        conn = MT5Connector(
            account=313812184,
            password="pass",
            server="BrightFunded-Server",
            path="C:\\Program Files\\MetaTrader 5 - Account A\\terminal64.exe",
            account_id="account_a",
        )

        valid, msg = conn.verify_pre_trade_identity(symbol="XAU/USD", require_algo_on=True)
        self.assertTrue(valid)
        self.assertEqual(msg, "OK")

    @patch("MetaTrader5.terminal_info")
    @patch("MetaTrader5.account_info")
    @patch("MetaTrader5.symbol_info")
    @patch("MetaTrader5.order_send")
    def test_02_account_id_mismatch_blocks_all_orders(self, mock_send, mock_sym, mock_acc, mock_term):
        """If Account A connector attaches to Account B's terminal, execution is IMMEDIATELY BLOCKED."""
        # Terminal is running Account B (314138473), but Connector is Account A (expects 313812184)
        mock_acc.return_value = MockMT5Terminal(login=314138473, server="BrightFunded-Server", algo_allowed=True)
        mock_term.return_value = MockMT5Terminal(login=314138473, server="BrightFunded-Server", algo_allowed=True)
        
        sym_mock = MagicMock()
        sym_mock.visible = True
        mock_sym.return_value = sym_mock

        conn_a = MT5Connector(
            account=313812184,
            password="pass",
            server="BrightFunded-Server",
            path="C:\\Program Files\\MetaTrader 5 - Account A\\terminal64.exe",
            account_id="account_a",
        )

        # 1. Check Pre-Trade Identity Verification
        valid, msg = conn_a.verify_pre_trade_identity(symbol="XAU/USD", require_algo_on=True)
        self.assertFalse(valid)
        self.assertIn("ACCOUNT ID MISMATCH — TRADING DISABLED", msg)
        self.assertIn("314138473", msg)

        # 2. Attempt to execute market order
        risk_mgr = RiskManager(self.config, conn_a, account_id="account_a", account_type="BRIGHTFUNDED")
        executor = OrderExecutor(self.config, conn_a, risk_manager=risk_mgr, account_id="account_a")

        ticket = executor.execute_market_order(
            symbol="XAU/USD",
            order_type="BUY",
            volume=0.01,
            sl=2350.0,
            tp=2360.0,
            magic=2001,
        )

        # Order must be None and order_send must NEVER be called
        self.assertIsNone(ticket)
        mock_send.assert_not_called()

    @patch("MetaTrader5.terminal_info")
    @patch("MetaTrader5.account_info")
    @patch("MetaTrader5.symbol_info")
    def test_03_server_mismatch_blocks_trading(self, mock_sym, mock_acc, mock_term):
        """If broker server does not match expected server, trading is disabled."""
        mock_acc.return_value = MockMT5Terminal(login=313812184, server="OtherBroker-Demo", algo_allowed=True)
        mock_term.return_value = MockMT5Terminal(login=313812184, server="OtherBroker-Demo", algo_allowed=True)

        conn = MT5Connector(
            account=313812184,
            password="pass",
            server="BrightFunded-Server",
            path="C:\\Program Files\\MetaTrader 5\\terminal64.exe",
            account_id="account_a",
        )

        valid, msg = conn.verify_pre_trade_identity(symbol="XAU/USD", require_algo_on=True)
        self.assertFalse(valid)
        self.assertIn("ACCOUNT ID MISMATCH — TRADING DISABLED", msg)
        self.assertIn("OtherBroker-Demo", msg)

    @patch("MetaTrader5.terminal_info")
    @patch("MetaTrader5.account_info")
    @patch("MetaTrader5.symbol_info")
    def test_04_independent_algo_trading_switch_isolation(self, mock_sym, mock_acc, mock_term):
        """
        Verify that Account A's Algo Trading OFF does not affect Account B's Algo Trading ON.
        Each terminal holds its own independent Algo Trading state.
        """
        sym_mock = MagicMock()
        sym_mock.visible = True
        mock_sym.return_value = sym_mock

        # Terminal A: Algo Trading OFF
        term_a_obj = MockMT5Terminal(login=313812184, server="BrightFunded-Server", algo_allowed=False)
        # Terminal B: Algo Trading ON
        term_b_obj = MockMT5Terminal(login=314138473, server="BrightFunded-Server", algo_allowed=True)

        conn_a = MT5Connector(313812184, "pass", "BrightFunded-Server", path="path_a", account_id="account_a")
        conn_b = MT5Connector(314138473, "pass", "BrightFunded-Server", path="path_b", account_id="account_b")

        acc_mgr = MultiAccountManager(self.config)
        acc_a = acc_mgr.get_account("account_a")
        acc_b = acc_mgr.get_account("account_b")

        acc_a.connector = conn_a
        acc_b.connector = conn_b

        # Simulate Account A poll
        mock_acc.return_value = term_a_obj
        mock_term.return_value = term_a_obj
        acc_a.update_connection_state()

        # Simulate Account B poll
        mock_acc.return_value = term_b_obj
        mock_term.return_value = term_b_obj
        acc_b.update_connection_state()

        # Check independent states
        self.assertEqual(acc_a.state_machine.current_state, ConnectionState.CONNECTED_TRADING_DISABLED)
        self.assertFalse(acc_a.is_trading_permitted)

        self.assertEqual(acc_b.state_machine.current_state, ConnectionState.CONNECTED_TRADING_ALLOWED)
        self.assertTrue(acc_b.is_trading_permitted)

    @patch("MetaTrader5.terminal_info")
    @patch("MetaTrader5.account_info")
    def test_05_bot_never_overrides_algo_trading_switch(self, mock_acc, mock_term):
        """Confirm that MT5Connector has no API calls to change terminal settings or force Algo Trading ON."""
        conn = MT5Connector(313812184, "pass", "BrightFunded-Server", account_id="account_a")
        
        # Verify MT5Connector class does not implement any method to enable algo trading
        self.assertFalse(hasattr(conn, "enable_algo_trading"))
        self.assertFalse(hasattr(conn, "set_algo_trading"))
        self.assertFalse(hasattr(conn, "override_algo_trading"))


if __name__ == "__main__":
    unittest.main()
