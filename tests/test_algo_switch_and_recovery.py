"""
Automated Test Suite for MT5 Algo Trading Master Switch, 7-Stage Connection State Machine,
and Auto-Recovery with Zero-Stale-Trade Enforcement.
"""

import unittest
from unittest.mock import MagicMock, patch
import yaml
import time
import os

from src.connection_state import AccountConnectionStateMachine, ConnectionState
from src.account_manager import AccountContext, MultiAccountManager
from src.connection import SymbolSpecification
from src.execution import OrderExecutor
from src.risk_manager import RiskManager
from src.signal_ranker import TradeCandidate


class MockMT5Connector:
    def __init__(self, account_id="account_a", is_connected_val=True, algo_enabled_val=True):
        self.account_id = account_id.lower()
        self._connected = is_connected_val
        self._algo_enabled = algo_enabled_val
        self._internet_ok = True
        self.account = 123456
        self.password = "pass"
        self.server = "server"
        self.specs = {
            "XAUUSDm": SymbolSpecification(
                symbol="XAUUSDm",
                digits=2,
                point=0.01,
                tick_size=0.01,
                tick_value=1.0,
                contract_size=100.0,
                volume_min=0.01,
                volume_max=20.0,
                volume_step=0.01,
                spread=20,
            ),
            "BTCUSDm": SymbolSpecification(
                symbol="BTCUSDm",
                digits=2,
                point=0.01,
                tick_size=0.01,
                tick_value=0.01,
                contract_size=1.0,
                volume_min=0.01,
                volume_max=10.0,
                volume_step=0.01,
                spread=100,
            ),
        }

    def is_connected(self) -> bool:
        return self._connected

    def check_internet(self, host="8.8.8.8", port=53, timeout=2.0) -> bool:
        return self._internet_ok

    def get_algo_trading_status(self) -> dict:
        return {
            "is_algo_enabled": self._algo_enabled and self._connected,
            "terminal_trade_allowed": self._algo_enabled,
            "account_trade_expert": self._algo_enabled,
            "account_trade_allowed": self._algo_enabled,
            "terminal_connected": self._connected,
            "login": self.account,
            "server": self.server,
        }

    def ensure_terminal_context(self) -> bool:
        return True

    def verify_account_identity(self) -> bool:
        return True

    def verify_pre_trade_identity(self, symbol=None, require_algo_on=True) -> tuple:
        if not self._connected:
            return False, "Terminal disconnected"
        if require_algo_on and not self._algo_enabled:
            return False, "Algo trading disabled"
        return True, "OK"

    def get_symbol_specs(self, sym: str):
        return self.specs.get(sym, self.specs["XAUUSDm"])

    def get_account_summary(self) -> dict:
        balance = 20.0 if self.account_id in ("account_c", "account_d") else 1000.0
        return {
            "login": self.account,
            "balance": balance,
            "equity": balance,
            "free_margin": balance,
        }

    def resolve_all_symbols(self, cfg):
        return {"XAUUSD": "XAUUSDm", "BTCUSD": "BTCUSDm"}

    def reconnect(self, symbols_cfg=None) -> bool:
        if self._internet_ok:
            self._connected = True
            return True
        return False

    def shutdown(self):
        self._connected = False


class TestAlgoSwitchAndAutoRecovery(unittest.TestCase):
    def setUp(self):
        with open("config/config.yaml", "r") as f:
            self.config = yaml.safe_load(f)

        self.account_manager = MultiAccountManager(self.config)
        for acc in self.account_manager.accounts.values():
            acc.is_active = True
            acc.login = 12345
            acc.password = "mock_pass"
            acc.server = "mock_server"

    def test_01_state_machine_transitions(self):
        """Test 7 explicit lifecycle states and transition callback."""
        sm = AccountConnectionStateMachine("account_a")
        self.assertEqual(sm.current_state, ConnectionState.CONNECTION_LOST)
        self.assertFalse(sm.is_trading_permitted)

        transitions = []
        sm.add_transition_callback(lambda acc, old_s, new_s, r: transitions.append((old_s, new_s)))

        # Transition to CONNECTED_TRADING_ALLOWED
        sm.transition_to(ConnectionState.CONNECTED_TRADING_ALLOWED, reason="MT5 Algo ON")
        self.assertEqual(sm.current_state, ConnectionState.CONNECTED_TRADING_ALLOWED)
        self.assertTrue(sm.is_trading_permitted)
        self.assertTrue(sm.is_connected)

        # Transition to CONNECTED_TRADING_DISABLED
        sm.transition_to(ConnectionState.CONNECTED_TRADING_DISABLED, reason="MT5 Algo OFF")
        self.assertEqual(sm.current_state, ConnectionState.CONNECTED_TRADING_DISABLED)
        self.assertFalse(sm.is_trading_permitted)
        self.assertTrue(sm.is_connected)

        # Transition to CONNECTION_LOST -> RECONNECTING -> SYNCHRONIZING -> RECOVERED -> CONNECTED_TRADING_ALLOWED
        sm.transition_to(ConnectionState.CONNECTION_LOST, reason="Lost connection")
        sm.transition_to(ConnectionState.RECONNECTING, reason="Reconnecting")
        sm.transition_to(ConnectionState.SYNCHRONIZING, reason="Syncing")
        sm.transition_to(ConnectionState.RECOVERED, reason="Recovered")
        sm.transition_to(ConnectionState.CONNECTED_TRADING_ALLOWED, reason="Trading active")

        self.assertEqual(len(transitions), 7)
        self.assertEqual(sm.current_state, ConnectionState.CONNECTED_TRADING_ALLOWED)

    def test_02_mt5_algo_trading_on_vs_off(self):
        """Test that MT5 Algo Trading switch controls trading permission without killing the process."""
        acc = self.account_manager.get_account("account_a")
        mock_conn = MockMT5Connector(account_id="account_a", is_connected_val=True, algo_enabled_val=True)
        acc.connector = mock_conn

        # 1. When Algo is ON
        acc.update_connection_state()
        self.assertEqual(acc.state_machine.current_state, ConnectionState.CONNECTED_TRADING_ALLOWED)
        self.assertTrue(acc.is_trading_permitted)

        # 2. When user turns Algo OFF in MT5
        mock_conn._algo_enabled = False
        acc.update_connection_state()
        self.assertEqual(acc.state_machine.current_state, ConnectionState.CONNECTED_TRADING_DISABLED)
        self.assertFalse(acc.is_trading_permitted)
        self.assertTrue(acc.state_machine.is_connected)  # Process is running & connected!

        # 3. When user turns Algo back ON in MT5 (No Telegram /start command needed)
        mock_conn._algo_enabled = True
        acc.update_connection_state()
        self.assertEqual(acc.state_machine.current_state, ConnectionState.CONNECTED_TRADING_ALLOWED)
        self.assertTrue(acc.is_trading_permitted)

    def test_03_internet_disconnection_preserves_state(self):
        """Test that connection loss enters CONNECTION_LOST and preserves risk memory & state."""
        acc = self.account_manager.get_account("account_a")
        mock_conn = MockMT5Connector(account_id="account_a", is_connected_val=True, algo_enabled_val=True)
        acc.connector = mock_conn
        acc.risk_manager = RiskManager(self.config, mock_conn, account_id="account_a", account_type="BRIGHTFUNDED")
        acc.executor = OrderExecutor(self.config, mock_conn, risk_manager=acc.risk_manager, account_id="account_a")

        acc.update_connection_state()
        self.assertEqual(acc.state_machine.current_state, ConnectionState.CONNECTED_TRADING_ALLOWED)

        # Record some activity and stats
        acc.risk_manager.account_consecutive_losses = 2
        acc.daily_pnl = 15.0
        acc.daily_high_water_equity = 1015.0

        # Disconnect internet
        mock_conn._internet_ok = False
        mock_conn._connected = False
        acc.update_connection_state()

        self.assertEqual(acc.state_machine.current_state, ConnectionState.CONNECTION_LOST)
        self.assertFalse(acc.is_trading_permitted)

        # Confirm local states are intact and not wiped
        self.assertEqual(acc.risk_manager.account_consecutive_losses, 2)
        self.assertEqual(acc.daily_pnl, 15.0)
        self.assertEqual(acc.daily_high_water_equity, 1015.0)

    @patch("MetaTrader5.positions_get")
    @patch("MetaTrader5.history_deals_get")
    def test_04_automatic_reconnection_and_10_step_reconciliation(self, mock_deals, mock_positions):
        """Test full 10-step reconciliation upon connection recovery."""
        mock_deals.return_value = []
        
        # Mock an open position that was open before disconnect
        mock_pos = MagicMock()
        mock_pos.ticket = 999111
        mock_pos.symbol = "XAUUSDm"
        mock_pos.type = 0  # BUY
        mock_pos.volume = 0.02
        mock_pos.price_open = 2350.00
        mock_pos.sl = 2345.00
        mock_pos.tp = 2360.00
        mock_pos.price_current = 2355.00
        mock_pos.profit = 10.00
        mock_pos.magic = 2001
        mock_pos.comment = "Musumali"
        mock_positions.return_value = [mock_pos]

        acc = self.account_manager.get_account("account_a")
        mock_conn = MockMT5Connector(account_id="account_a", is_connected_val=False, algo_enabled_val=True)
        mock_conn._internet_ok = False
        acc.connector = mock_conn
        acc.risk_manager = RiskManager(self.config, mock_conn, account_id="account_a", account_type="BRIGHTFUNDED")
        acc.executor = OrderExecutor(self.config, mock_conn, risk_manager=acc.risk_manager, account_id="account_a")

        acc.update_connection_state()
        self.assertEqual(acc.state_machine.current_state, ConnectionState.CONNECTION_LOST)

        # Internet restored
        mock_conn._internet_ok = True
        reconnected = mock_conn.reconnect()
        self.assertTrue(reconnected)

        # Run 10-step reconciliation
        sync_ok = acc.reconcile_account_state({"XAUUSD": "XAUUSDm"})
        self.assertTrue(sync_ok)

        # State should be restored to CONNECTED_TRADING_ALLOWED
        self.assertEqual(acc.state_machine.current_state, ConnectionState.CONNECTED_TRADING_ALLOWED)
        self.assertTrue(acc.is_trading_permitted)

        # Position should be registered and state reconstructed with peak R
        rec = acc.executor.exit_engine.records.get(999111)
        self.assertIsNotNone(rec)
        self.assertEqual(rec.ticket, 999111)
        self.assertGreater(rec.peak_r, 0.0)

    def test_05_multi_account_fault_isolation(self):
        """Test that Account A disconnection leaves Accounts B, C, D running normally."""
        acc_a = self.account_manager.get_account("account_a")
        acc_b = self.account_manager.get_account("account_b")
        acc_c = self.account_manager.get_account("account_c")
        acc_d = self.account_manager.get_account("account_d")

        conn_a = MockMT5Connector("account_a", is_connected_val=True, algo_enabled_val=True)
        conn_b = MockMT5Connector("account_b", is_connected_val=True, algo_enabled_val=True)
        conn_c = MockMT5Connector("account_c", is_connected_val=True, algo_enabled_val=True)
        conn_d = MockMT5Connector("account_d", is_connected_val=True, algo_enabled_val=True)

        acc_a.connector = conn_a
        acc_b.connector = conn_b
        acc_c.connector = conn_c
        acc_d.connector = conn_d

        acc_a.update_connection_state()
        acc_b.update_connection_state()
        acc_c.update_connection_state()
        acc_d.update_connection_state()

        self.assertTrue(acc_a.is_trading_permitted)
        self.assertTrue(acc_b.is_trading_permitted)
        self.assertTrue(acc_c.is_trading_permitted)
        self.assertTrue(acc_d.is_trading_permitted)

        # Account A loses connection
        conn_a._connected = False
        conn_a._internet_ok = False
        acc_a.update_connection_state()

        # Verify Account A is down, but B, C, D are unaffected
        self.assertEqual(acc_a.state_machine.current_state, ConnectionState.CONNECTION_LOST)
        self.assertFalse(acc_a.is_trading_permitted)

        self.assertEqual(acc_b.state_machine.current_state, ConnectionState.CONNECTED_TRADING_ALLOWED)
        self.assertTrue(acc_b.is_trading_permitted)

        self.assertEqual(acc_c.state_machine.current_state, ConnectionState.CONNECTED_TRADING_ALLOWED)
        self.assertTrue(acc_c.is_trading_permitted)

        self.assertEqual(acc_d.state_machine.current_state, ConnectionState.CONNECTED_TRADING_ALLOWED)
        self.assertTrue(acc_d.is_trading_permitted)

    def test_06_duplicate_trade_protection(self):
        """Test that duplicate orders for the same candle ID or active magic are blocked."""
        acc = self.account_manager.get_account("account_a")
        mock_conn = MockMT5Connector("account_a", is_connected_val=True, algo_enabled_val=True)
        acc.connector = mock_conn
        acc.risk_manager = RiskManager(self.config, mock_conn, account_id="account_a", account_type="BRIGHTFUNDED")
        acc.executor = OrderExecutor(self.config, mock_conn, risk_manager=acc.risk_manager, account_id="account_a")

        # Fake an already open ticket with Magic 2001 and Candle ID "CANDLE_123"
        acc.executor.known_tickets[112233] = {
            "account_id": "account_a",
            "symbol": "XAUUSDm",
            "type": "BUY",
            "volume": 0.02,
            "entry_price": 2350.0,
            "initial_sl": 2345.0,
            "initial_tp": 2360.0,
            "risk_distance": 5.0,
            "be_applied": False,
            "magic": 2001,
            "candle_id": "CANDLE_123",
        }

        # Attempt to execute duplicate market order for same candle ID
        result_ticket = acc.executor.execute_market_order(
            symbol="XAUUSDm",
            order_type="BUY",
            volume=0.02,
            sl=2345.0,
            tp=2360.0,
            magic=2001,
            candle_id="CANDLE_123",
        )
        self.assertIsNone(result_ticket)

    def test_07_emergency_kill_switch_persists_across_reconnect(self):
        """Test that manual emergency stop is not overridden merely because internet reconnects."""
        acc = self.account_manager.get_account("account_a")
        mock_conn = MockMT5Connector("account_a", is_connected_val=True, algo_enabled_val=True)
        acc.connector = mock_conn

        acc.update_connection_state()
        self.assertTrue(acc.is_trading_permitted)

        # Trigger manual emergency pause
        self.account_manager.pause_account("account_a", reason="Telegram /stop_a (Emergency Stop)")
        self.assertTrue(acc.is_manually_paused)
        self.assertFalse(acc.is_trading_permitted)

        # Simulate network drop and reconnect
        mock_conn._connected = False
        acc.update_connection_state()
        self.assertFalse(acc.is_trading_permitted)

        mock_conn._connected = True
        mock_conn.reconnect()
        acc.update_connection_state()

        # Account should still be paused until explicit resume!
        self.assertTrue(acc.is_manually_paused)
        self.assertFalse(acc.is_trading_permitted)

        # Now explicitly resume
        self.account_manager.resume_account("account_a")
        self.assertFalse(acc.is_manually_paused)
        self.assertTrue(acc.is_trading_permitted)


if __name__ == "__main__":
    unittest.main()
