import os
import unittest
from unittest.mock import MagicMock, patch
import yaml

from src.account_manager import MultiAccountManager, AccountContext
from src.connection import MT5Connector, SymbolSpecification
from src.connection_state import ConnectionState
from src.risk_manager import RiskManager
from src.execution import OrderExecutor
from src.copy_engine import CopyTradingEngine


class TestBrightFundedExclusiveProtection(unittest.TestCase):
    """
    Acceptance Test Suite for BRIGHT FUNDED $1,000 ACCOUNT — EXCLUSIVE PROTECTION PATCH.
    Validates all 13 required acceptance tests from Section 22.
    """

    def setUp(self):
        with open("config/config.yaml", "r") as f:
            self.config = yaml.safe_load(f)
        self.config["accounts"]["account_list"] = [
            {"id": "account_a", "name": "Account A", "type": "BRIGHTFUNDED", "balance": 1000.0, "mode": "INDEPENDENT", "is_active": True},
            {"id": "account_b", "name": "Account B", "type": "BRIGHTFUNDED", "balance": 1000.0, "mode": "INDEPENDENT", "is_active": True},
            {"id": "account_c", "name": "Account C", "type": "PERSONAL", "balance": 20.0, "mode": "COPY_MASTER", "copy_enabled": True, "is_active": True},
            {"id": "account_d", "name": "Account D", "type": "PERSONAL", "balance": 20.0, "mode": "COPY_FOLLOWER", "copy_enabled": True, "copy_source": "account_c", "is_active": True},
        ]
        self.config["copy_engine"]["enabled"] = True
        self.config["copy_engine"]["master_account_id"] = "account_c"
        self.config["copy_engine"]["follower_account_id"] = "account_d"

    # TEST 1: Correct account identification
    def test_01_account_identification(self):
        connector = MT5Connector(account=312128694, password="pwd", server="BrightFunded-Server", account_id="account_a")
        with patch("src.connection.mt5") as mock_mt5:
            mock_term = MagicMock()
            mock_term.connected = True
            mock_term.trade_allowed = True
            mock_term.tradeapi_disabled = False
            mock_mt5.terminal_info.return_value = mock_term

            # Matching account
            mock_acc = MagicMock()
            mock_acc.login = 312128694
            mock_acc.server = "BrightFunded-Server"
            mock_acc.trade_allowed = True
            mock_acc.trade_expert = True
            mock_mt5.account_info.return_value = mock_acc

            valid, msg = connector.verify_pre_trade_identity(require_algo_on=False)
            self.assertTrue(valid)
            self.assertEqual(msg, "OK")

            # Mismatched account
            mock_acc.login = 999999999
            valid, msg = connector.verify_pre_trade_identity(require_algo_on=False)
            self.assertFalse(valid)
            self.assertIn("ACCOUNT ID MISMATCH", msg)

    # TEST 2: Correct server identification
    def test_02_server_identification(self):
        connector = MT5Connector(account=312128694, password="pwd", server="BrightFunded-Server", account_id="account_a")
        with patch("src.connection.mt5") as mock_mt5:
            mock_term = MagicMock()
            mock_term.connected = True
            mock_term.trade_allowed = True
            mock_mt5.terminal_info.return_value = mock_term

            # Mismatched server
            mock_acc = MagicMock()
            mock_acc.login = 312128694
            mock_acc.server = "Wrong-Broker-Server"
            mock_acc.trade_allowed = True
            mock_acc.trade_expert = True
            mock_mt5.account_info.return_value = mock_acc

            valid, msg = connector.verify_pre_trade_identity(require_algo_on=False)
            self.assertFalse(valid)
            self.assertIn("does not match expected 'BrightFunded-Server'", msg)

    # TEST 3: Algo Trading OFF blocks new entries
    def test_03_algo_trading_off_blocks_entries(self):
        connector = MT5Connector(account=312128694, password="pwd", server="BrightFunded-Server", account_id="account_a")
        with patch("src.connection.mt5") as mock_mt5:
            mock_term = MagicMock()
            mock_term.connected = True
            mock_term.trade_allowed = False  # Algo button OFF
            mock_mt5.terminal_info.return_value = mock_term

            mock_acc = MagicMock()
            mock_acc.login = 312128694
            mock_acc.server = "BrightFunded-Server"
            mock_acc.trade_allowed = True
            mock_acc.trade_expert = True
            mock_mt5.account_info.return_value = mock_acc

            valid, msg = connector.verify_pre_trade_identity(require_algo_on=True)
            self.assertFalse(valid)
            self.assertIn("MT5 Algo Trading is DISABLED", msg)

    # TEST 4: Algo Trading ON resumes monitoring
    def test_04_algo_trading_on_resumes_monitoring(self):
        mgr = MultiAccountManager(self.config)
        acc = mgr.get_account("account_a")
        self.assertIsNotNone(acc)

        with patch.object(acc.connector, "is_connected", return_value=True), \
             patch.object(acc.connector, "check_internet", return_value=True), \
             patch.object(acc.connector, "verify_pre_trade_identity", return_value=(True, "OK")), \
             patch.object(acc.connector, "get_algo_trading_status") as mock_algo:
            
            # First Algo OFF
            mock_algo.return_value = {"is_algo_enabled": False, "terminal_trade_allowed": False, "account_trade_expert": True, "account_trade_allowed": True}
            state = acc.update_connection_state()
            self.assertEqual(state, ConnectionState.CONNECTED_TRADING_DISABLED)
            self.assertFalse(acc.is_trading_permitted)

            # Then Algo ON -> automatically transitions to CONNECTED_TRADING_ALLOWED without restart
            mock_algo.return_value = {"is_algo_enabled": True, "terminal_trade_allowed": True, "account_trade_expert": True, "account_trade_allowed": True}
            state = acc.update_connection_state()
            self.assertEqual(state, ConnectionState.CONNECTED_TRADING_ALLOWED)
            self.assertTrue(acc.is_trading_permitted)

    # TEST 5: Internet OFF does not create missed trades
    def test_05_internet_off_blocks_execution(self):
        mgr = MultiAccountManager(self.config)
        acc = mgr.get_account("account_a")
        with patch.object(acc.connector, "is_connected", return_value=False), \
             patch.object(acc.connector, "check_internet", return_value=False):
            state = acc.update_connection_state()
            self.assertEqual(state, ConnectionState.CONNECTION_LOST)
            self.assertFalse(acc.is_trading_permitted)

    # TEST 6: Internet recovery reassesses CURRENT market
    def test_06_internet_recovery_reassesses_current_market(self):
        mgr = MultiAccountManager(self.config)
        acc = mgr.get_account("account_a")
        acc.risk_manager = RiskManager(self.config, acc.connector, account_id="account_a", account_type="BRIGHTFUNDED")
        acc.executor = OrderExecutor(self.config, acc.connector, risk_manager=acc.risk_manager, account_id="account_a")

        with patch.object(acc.connector, "is_connected", return_value=True), \
             patch.object(acc.connector, "check_internet", return_value=True), \
             patch.object(acc.connector, "verify_account_identity", return_value=True), \
             patch.object(acc.connector, "get_algo_trading_status", return_value={"is_algo_enabled": True}), \
             patch.object(acc.connector, "get_account_summary", return_value={"balance": 1000.0, "equity": 1000.0, "free_margin": 1000.0, "currency": "USD"}), \
             patch.object(acc.executor, "get_open_positions", return_value=[]):
            
            res = acc.reconcile_account_state({"XAUUSD": "XAU/USD"})
            self.assertTrue(res)
            self.assertEqual(acc.state_machine.current_state, ConnectionState.CONNECTED_TRADING_ALLOWED)

    # TEST 7: No unconfirmed setup can execute
    def test_07_unconfirmed_setup_rejected(self):
        connector = MagicMock()
        connector.verify_pre_trade_identity.return_value = (True, "OK")
        rm = RiskManager(self.config, connector, account_id="account_a", account_type="BRIGHTFUNDED")
        executor = OrderExecutor(self.config, connector, risk_manager=rm, account_id="account_a")
        gate = executor.final_entry_gate

        passed, reason, _ = gate.evaluate_final_gate(
            symbol="XAU/USD",
            order_type="BUY",
            volume=0.01,
            sl=4447.0,
            tp=4457.0,
            magic=1001,
            candle_id="SCALP_BUY_UNCONFIRMED",
            quality_score=95,
            confirmation_verified=False,  # Unconfirmed!
            funnel_stage="PENDING",
        )
        self.assertFalse(passed)
        self.assertIn("WAITING_FOR_CONFIRMATION", reason)

    # TEST 8: Daily loss protection works (Internal -$25 hard stop & -$20 reduced risk)
    def test_08_daily_loss_protection(self):
        connector = MagicMock()
        rm = RiskManager(self.config, connector, account_id="account_a", account_type="BRIGHTFUNDED")
        rm.reset_daily_metrics_if_needed(1000.0)

        # Drawdown -$21.00 -> Reduced Risk / Stop entries
        allowed, reason = rm.check_circuit_breakers(979.0)
        self.assertTrue(allowed)
        self.assertEqual(rm.trading_state, "REDUCED_RISK")
        self.assertEqual(rm.risk_reduction_multiplier, 0.40)

        # Drawdown -$26.00 -> Internal Hard Stop (trips circuit breaker with $4 buffer before firm limit)
        allowed, reason = rm.check_circuit_breakers(974.0)
        self.assertFalse(allowed)
        self.assertEqual(rm.trading_state, "DAILY_HARD_STOP")
        self.assertIn("INTERNAL DAILY HARD STOP", reason)

    # TEST 9: Loss-streak protection works (3 consecutive losses pause engine)
    def test_09_loss_streak_protection(self):
        connector = MagicMock()
        rm = RiskManager(self.config, connector, account_id="account_a", account_type="BRIGHTFUNDED")

        # 3 consecutive losses on Magic #1001 (Scalper)
        rm.record_trade_result(None, -3.00, magic=1001, symbol="XAU/USD")
        self.assertFalse(rm.is_engine_in_cooldown(1001)[0])

        rm.record_trade_result(None, -2.50, magic=1001, symbol="XAU/USD")
        self.assertFalse(rm.is_engine_in_cooldown(1001)[0])

        rm.record_trade_result(None, -2.80, magic=1001, symbol="XAU/USD")
        in_cd, msg = rm.is_engine_in_cooldown(1001)
        self.assertTrue(in_cd)
        self.assertIn("Engine Scalp in cooldown", msg)

    # TEST 10: Invalid order requests are rejected safely
    def test_10_invalid_order_requests_rejected(self):
        connector = MagicMock()
        connector.is_connected.return_value = True
        rm = RiskManager(self.config, connector, account_id="account_a", account_type="BRIGHTFUNDED")
        rm.reset_daily_metrics_if_needed(1000.0)

        # Huge SL distance causing $50 potential loss (exceeds $3.50 hard reject limit)
        spec = SymbolSpecification("XAU/USD", 2, 0.01, 0.01, 1.0, 100.0, 0.01, 10.0, 0.01, 0, 0, 20)
        connector.get_symbol_specs.return_value = spec

        passed, reasons, _ = rm.pre_trade_risk_check(
            symbol="XAU/USD",
            engine_magic=1001,
            order_type="BUY",
            entry_price=4450.0,
            stop_loss_price=4400.0,
            take_profit_price=4550.0,
            volume=0.01,
            quality_score=90,
            all_open_positions=[],
            equity=1000.0,
            free_margin=1000.0,
            candle_id="CANDLE_1",
            traded_candle_ids=set(),
            last_trade_time=0.0,
        )
        self.assertFalse(passed)
        self.assertIn("Check 20 Fail", reasons[0])

    # TEST 11: Successful orders are verified as actual positions
    def test_11_successful_orders_verified_as_actual_positions(self):
        connector = MagicMock()
        rm = RiskManager(self.config, connector, account_id="account_a", account_type="BRIGHTFUNDED")
        executor = OrderExecutor(self.config, connector, risk_manager=rm, account_id="account_a")

        with patch("src.execution.mt5") as mock_mt5:
            # Position verification mock
            mock_pos = MagicMock()
            mock_pos.ticket = 555555
            mock_pos.symbol = "XAU/USD"
            mock_pos.price_open = 4450.50
            mock_pos.volume = 0.01
            mock_pos.sl = 4447.50
            mock_pos.tp = 4457.50
            mock_pos.type = 0  # POSITION_TYPE_BUY
            mock_pos.magic = 1001
            mock_pos.profit = 0.0
            mock_mt5.positions_get.return_value = (mock_pos,)

            positions = executor.get_open_positions("XAU/USD")
            self.assertEqual(len(positions), 1)
            self.assertEqual(positions[0]["ticket"], 555555)

    # TEST 12: Bright Funded Account A cannot accidentally trade Bright Funded Account B
    def test_12_account_isolation_a_and_b(self):
        mgr = MultiAccountManager(self.config)
        acc_a = mgr.get_account("account_a")
        acc_b = mgr.get_account("account_b")
        self.assertIsNotNone(acc_a)
        self.assertIsNotNone(acc_b)

        # Different terminals and logins
        self.assertNotEqual(acc_a.account_id, acc_b.account_id)
        self.assertEqual(acc_a.mode, "INDEPENDENT")
        self.assertEqual(acc_b.mode, "INDEPENDENT")
        self.assertFalse(acc_a.is_copy_follower)
        self.assertFalse(acc_b.is_copy_follower)

    # TEST 13: Bright Funded accounts cannot accidentally use $20 copy-trading logic
    def test_13_brightfunded_isolated_from_copy_trading(self):
        mgr = MultiAccountManager(self.config)
        acc_a = mgr.get_account("account_a")
        acc_d = mgr.get_account("account_d")

        copy_engine = CopyTradingEngine(self.config, mgr)
        self.assertEqual(copy_engine.master_id, "account_c")
        self.assertEqual(copy_engine.follower_id, "account_d")

        # Account A attempts copy event -> rejected
        event = copy_engine.create_copy_event(
            origin_account_id="account_a",
            symbol="XAU/USD",
            direction="BUY",
            entry=4450.0,
            sl=4447.0,
            tp=4457.0,
            volume=0.01,
            master_ticket=12345,
            event_type="OPEN",
            magic=1001,
        )
        self.assertIsNone(event)


if __name__ == "__main__":
    unittest.main()
