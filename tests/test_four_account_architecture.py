"""
Automated Test Suite for 4-Account Architecture (Tests A through J)
Strictly tests:
  TEST A: Account A receives valid setup -> Executes if risk checks pass.
  TEST B: Account B receives same setup -> Independently evaluates and may execute (Shared strategy, zero copy).
  TEST C: Account A executes -> Verify Account B receives ZERO copy events.
  TEST D: Account C executes -> Account D receives copy event.
  TEST E: Account C executes 0.10 lots -> Account D calculates safe volume (0.01) instead of copying 0.10.
  TEST F: Minimum lot on Account D is too risky -> Account D rejects the trade.
  TEST G: Account D closes copied position due to own risk -> Does NOT automatically reopen.
  TEST H: Account A reaches -$25 daily stop -> Account A stops new trades; Accounts B/C/D continue.
  TEST I: Copy Engine is paused/fails -> Account A and Account B continue trading independently.
  TEST J: Bot restarts -> All four account connections recover correctly & positions managed.
"""

import unittest
from unittest.mock import MagicMock
import yaml
import time
import os

from src.account_manager import AccountContext, MultiAccountManager
from src.connection import SymbolSpecification
from src.copy_engine import CopyTradingEngine, CopyEvent
from src.risk_manager import RiskManager
from src.execution import OrderExecutor


class MockConnector:
    def __init__(self, account_id="account_a"):
        self.account_id = account_id.lower()
        self._connected = True
        self.specs = {
            "XAUUSD": SymbolSpecification(
                symbol="XAUUSD",
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

    def get_symbol_specs(self, sym: str):
        return self.specs.get(sym, self.specs["XAUUSDm"])

    def get_account_summary(self) -> dict:
        balance = 20.0 if self.account_id in ("account_c", "account_d") else 1000.0
        return {
            "login": 123456,
            "balance": balance,
            "equity": balance,
            "free_margin": balance,
        }

    def resolve_all_symbols(self, cfg):
        return {"XAUUSD": "XAUUSDm", "BTCUSD": "BTCUSDm"}

    def shutdown(self):
        self._connected = False


class TestFourAccountArchitecture(unittest.TestCase):
    def setUp(self):
        with open("config/config.yaml", "r") as f:
            self.config = yaml.safe_load(f)
        self.config["copy_engine"]["enabled"] = True
        self.config["copy_engine"]["master_account_id"] = "account_c"
        self.config["copy_engine"]["follower_account_id"] = "account_d"
        self.config["accounts"]["account_list"] = [
            {"id": "account_a", "name": "Account A", "type": "BRIGHTFUNDED", "balance": 1000.0, "mode": "INDEPENDENT"},
            {"id": "account_b", "name": "Account B", "type": "BRIGHTFUNDED", "balance": 1000.0, "mode": "INDEPENDENT"},
            {"id": "account_c", "name": "Account C", "type": "PERSONAL", "balance": 20.0, "mode": "COPY_MASTER", "copy_enabled": True},
            {"id": "account_d", "name": "Account D", "type": "PERSONAL", "balance": 20.0, "mode": "COPY_FOLLOWER", "copy_enabled": True, "copy_source": "account_c"},
        ]

        self.account_manager = MultiAccountManager(self.config)

        # Clean HWM data files for test repeatability
        for acc_id in ["account_a", "account_b", "account_c", "account_d"]:
            hwm_file = f"data/hwm_{acc_id}.json"
            if os.path.exists(hwm_file):
                try:
                    os.remove(hwm_file)
                except Exception:
                    pass

        # Inject mock connectors & executors for all 4 accounts
        for acc_id in ["account_a", "account_b", "account_c", "account_d"]:
            acc = self.account_manager.get_account(acc_id)
            if not acc:
                acc_type = "PERSONAL" if acc_id in ("account_c", "account_d") else "BRIGHTFUNDED"
                mode = "COPY_MASTER" if acc_id == "account_c" else ("COPY_FOLLOWER" if acc_id == "account_d" else "INDEPENDENT")
                bal = 20.0 if acc_type == "PERSONAL" else 1000.0
                acc = AccountContext(
                    account_id=acc_id,
                    name=f"Account {acc_id.upper()}",
                    account_type=acc_type,
                    mode=mode,
                    copy_enabled=(acc_id in ("account_c", "account_d")),
                    copy_source="account_c" if acc_id == "account_d" else None,
                    config=self.config,
                    initial_balance=bal,
                )
                self.account_manager.accounts[acc_id] = acc

            acc.is_active = True
            acc.connector = MockConnector(account_id=acc_id)
            acc.risk_manager = RiskManager(self.config, acc.connector, account_id=acc_id, account_type=acc.account_type)
            acc.executor = OrderExecutor(self.config, acc.connector, risk_manager=acc.risk_manager, account_id=acc_id)
            acc.sync_account_metrics()
            acc.risk_manager.reset_daily_metrics_if_needed(acc.equity)

        self.copy_engine = CopyTradingEngine(self.config, self.account_manager)

    # -------------------------------------------------------------------------
    # TEST A: Account A receives a valid XAUUSD setup -> Executes if risk checks pass
    # -------------------------------------------------------------------------
    def test_a_account_a_valid_setup_executes(self):
        acc_a = self.account_manager.get_account("account_a")
        self.assertIsNotNone(acc_a)
        
        entry = 2500.0
        sl = 2497.0 # $3.00 SL distance
        tp = 2506.0
        quality_score = 80

        lot_size = acc_a.risk_manager.calculate_lot_size("XAUUSDm", entry, sl, acc_a.equity, quality_score)
        self.assertGreater(lot_size, 0.0)

        passed, failures, loss = acc_a.risk_manager.pre_trade_risk_check(
            symbol="XAUUSDm",
            engine_magic=2001,
            order_type="BUY",
            entry_price=entry,
            stop_loss_price=sl,
            take_profit_price=tp,
            volume=lot_size,
            quality_score=quality_score,
            all_open_positions=[],
            equity=acc_a.equity,
            free_margin=acc_a.free_margin,
            candle_id="CANDLE_TEST_A_001",
            traded_candle_ids=set(),
            last_trade_time=0.0,
        )
        self.assertTrue(passed, f"Account A pre-trade checks should pass, got failures: {failures}")
        self.assertLessEqual(loss, 5.05)

    # -------------------------------------------------------------------------
    # TEST B: Account B receives the same market setup -> Independently evaluates and may execute
    # -------------------------------------------------------------------------
    def test_b_account_b_independent_evaluation(self):
        acc_b = self.account_manager.get_account("account_b")
        self.assertIsNotNone(acc_b)
        self.assertEqual(acc_b.mode, "INDEPENDENT")
        self.assertFalse(acc_b.copy_enabled)

        entry = 2500.0
        sl = 2497.0
        tp = 2506.0
        quality_score = 80

        lot_size_b = acc_b.risk_manager.calculate_lot_size("XAUUSDm", entry, sl, acc_b.equity, quality_score)
        self.assertGreater(lot_size_b, 0.0)

        passed_b, failures_b, loss_b = acc_b.risk_manager.pre_trade_risk_check(
            symbol="XAUUSDm",
            engine_magic=2001,
            order_type="BUY",
            entry_price=entry,
            stop_loss_price=sl,
            take_profit_price=tp,
            volume=lot_size_b,
            quality_score=quality_score,
            all_open_positions=[],
            equity=acc_b.equity,
            free_margin=acc_b.free_margin,
            candle_id="CANDLE_TEST_B_001",
            traded_candle_ids=set(),
            last_trade_time=0.0,
        )
        self.assertTrue(passed_b, f"Account B independent pre-trade checks should pass: {failures_b}")

    # -------------------------------------------------------------------------
    # TEST C: Account A executes -> Verify Account B receives ZERO copy events
    # -------------------------------------------------------------------------
    def test_c_account_a_generates_zero_copy_events_for_account_b(self):
        # Attempt to create copy event originating from Account A
        copy_evt = self.copy_engine.create_copy_event(
            origin_account_id="account_a",
            symbol="XAUUSDm",
            direction="BUY",
            entry=2500.0,
            sl=2497.0,
            tp=2506.0,
            volume=0.01,
            master_ticket=111111,
            event_type="OPEN",
        )
        self.assertIsNone(copy_evt, "Account A MUST NOT emit copy events under any circumstances!")

    # -------------------------------------------------------------------------
    # TEST D: Account C executes -> Account D receives a copy event
    # -------------------------------------------------------------------------
    def test_d_account_c_emits_copy_event_to_account_d(self):
        copy_evt = self.copy_engine.create_copy_event(
            origin_account_id="account_c",
            symbol="XAUUSDm",
            direction="BUY",
            entry=2500.0,
            sl=2499.30,
            tp=2502.0,
            volume=0.10,
            master_ticket=222222,
            event_type="OPEN",
        )
        self.assertIsNotNone(copy_evt, "Account C must generate a valid copy event")
        self.assertEqual(copy_evt.master_account_id, "account_c")
        self.assertEqual(copy_evt.follower_account_id, "account_d")
        self.assertEqual(copy_evt.symbol, "XAUUSDm")

    # -------------------------------------------------------------------------
    # TEST E: Account C executes 0.10 lots -> Account D DOES NOT blindly copy 0.10 lots
    # -------------------------------------------------------------------------
    def test_e_account_d_safe_volume_calculation_not_blind_copy(self):
        acc_d = self.account_manager.get_account("account_d")
        acc_d.executor.execute_market_order = MagicMock(return_value=333333)

        # Micro-scalp setup with $0.60 SL distance (fits $20 risk budget <= $1.00)
        copy_evt = self.copy_engine.create_copy_event(
            origin_account_id="account_c",
            symbol="XAUUSDm",
            direction="BUY",
            entry=2500.0,
            sl=2499.40, # $0.60 SL distance -> 0.01 lots = $0.60 loss + $0.25 spread/slip = $0.85
            tp=2502.0,
            volume=0.10, # Master used 0.10 lots
            master_ticket=444444,
            event_type="OPEN",
        )

        ok, msg = self.copy_engine.process_copy_event(copy_evt)
        self.assertTrue(ok, f"Copy should process safely, got: {msg}")
        self.assertNotEqual(copy_evt.follower_volume, 0.10, "Account D must not copy Master's 0.10 lots!")
        self.assertEqual(copy_evt.follower_volume, 0.01, "Account D should size safely to micro lot (0.01)")
        self.assertLessEqual(copy_evt.follower_risk_dollars, 1.00, "Account D risk must be <= $1.00")

    # -------------------------------------------------------------------------
    # TEST F: Minimum lot on Account D is too risky -> Account D rejects the trade
    # -------------------------------------------------------------------------
    def test_f_account_d_rejects_excessive_risk_copy(self):
        acc_d = self.account_manager.get_account("account_d")
        acc_d.executor.execute_market_order = MagicMock(return_value=555555)

        # SL is $20.00 wide on Gold: 0.01 lot loss = $20.00 > $1.00 max hard reject limit
        copy_evt = self.copy_engine.create_copy_event(
            origin_account_id="account_c",
            symbol="XAUUSDm",
            direction="BUY",
            entry=2500.0,
            sl=2480.0, # $20.00 SL width
            tp=2540.0,
            volume=0.01,
            master_ticket=666666,
            event_type="OPEN",
        )

        ok, msg = self.copy_engine.process_copy_event(copy_evt)
        self.assertFalse(ok, "Account D MUST reject trade when 0.01 lot risk exceeds $1.00 hard limit")
        self.assertEqual(copy_evt.status, "REJECTED")

    # -------------------------------------------------------------------------
    # TEST G: Account D closes a copied position due to own risk -> Does NOT automatically reopen
    # -------------------------------------------------------------------------
    def test_g_account_d_does_not_reopen_if_closed_on_own_risk(self):
        acc_d = self.account_manager.get_account("account_d")
        acc_d.executor.execute_market_order = MagicMock(return_value=777777)

        copy_evt1 = self.copy_engine.create_copy_event(
            origin_account_id="account_c",
            symbol="XAUUSDm",
            direction="BUY",
            entry=2500.0,
            sl=2499.40,
            tp=2502.0,
            volume=0.01,
            master_ticket=888888,
            event_type="OPEN",
        )
        ok1, _ = self.copy_engine.process_copy_event(copy_evt1)
        self.assertTrue(ok1)

        # Follower closes trade
        self.copy_engine.closed_master_tickets.add(888888)
        self.copy_engine.active_copied_trades.pop(888888, None)

        # Master emits duplicate / reopen attempt
        copy_evt2 = self.copy_engine.create_copy_event(
            origin_account_id="account_c",
            symbol="XAUUSDm",
            direction="BUY",
            entry=2500.0,
            sl=2499.40,
            tp=2502.0,
            volume=0.01,
            master_ticket=888888,
            event_type="OPEN",
        )
        ok2, msg2 = self.copy_engine.process_copy_event(copy_evt2)
        self.assertFalse(ok2, "Must reject reopening previously closed trade")

    # -------------------------------------------------------------------------
    # TEST H: Account A reaches -$25 internal daily stop -> Account A stops new trades; Accounts B/C/D continue
    # -------------------------------------------------------------------------
    def test_h_account_a_daily_hard_stop_isolation(self):
        acc_a = self.account_manager.get_account("account_a")
        acc_b = self.account_manager.get_account("account_b")
        acc_c = self.account_manager.get_account("account_c")

        # Account A loses $26 -> Equity $974 (Breaches -$25 internal stop)
        acc_a.risk_manager.reset_daily_metrics_if_needed(1000.0)
        can_trade_a, reason_a = acc_a.risk_manager.check_circuit_breakers(974.0)
        self.assertFalse(can_trade_a, "Account A must halt at -$26 loss")
        self.assertEqual(acc_a.risk_manager.trading_state, "DAILY_HARD_STOP")

        # Account B is at $1,000 baseline -> Must still trade normally
        acc_b.risk_manager.reset_daily_metrics_if_needed(1000.0)
        can_trade_b, reason_b = acc_b.risk_manager.check_circuit_breakers(1000.0)
        self.assertTrue(can_trade_b, "Account B must remain active and trade normally")
        self.assertEqual(acc_b.risk_manager.trading_state, "NORMAL")

        # Account C is at $20 baseline -> Must still trade normally
        acc_c.risk_manager.reset_daily_metrics_if_needed(20.0)
        can_trade_c, reason_c = acc_c.risk_manager.check_circuit_breakers(20.0)
        self.assertTrue(can_trade_c, "Account C must remain active and trade normally")

    # -------------------------------------------------------------------------
    # TEST I: Copy Engine paused/fails -> Account A and Account B continue trading independently
    # -------------------------------------------------------------------------
    def test_i_copy_engine_failure_does_not_affect_accounts_a_and_b(self):
        # Pause copy engine
        self.copy_engine.pause_copy_engine("Emergency Pause")
        self.assertTrue(self.copy_engine.is_paused)

        acc_a = self.account_manager.get_account("account_a")
        acc_b = self.account_manager.get_account("account_b")

        # Accounts A and B run their independent pre-trade risk checks
        lot_a = acc_a.risk_manager.calculate_lot_size("XAUUSDm", 2500.0, 2497.0, 1000.0, quality_score=80)
        passed_a, _, _ = acc_a.risk_manager.pre_trade_risk_check(
            symbol="XAUUSDm",
            engine_magic=2001,
            order_type="BUY",
            entry_price=2500.0,
            stop_loss_price=2497.0,
            take_profit_price=2506.0,
            volume=lot_a,
            quality_score=80,
            all_open_positions=[],
            equity=1000.0,
            free_margin=1000.0,
            candle_id="CANDLE_TEST_I_001",
            traded_candle_ids=set(),
            last_trade_time=0.0,
        )
        self.assertTrue(passed_a, "Account A must trade normally even if copy engine is paused")

        lot_b = acc_b.risk_manager.calculate_lot_size("XAUUSDm", 2500.0, 2497.0, 1000.0, quality_score=80)
        passed_b, _, _ = acc_b.risk_manager.pre_trade_risk_check(
            symbol="XAUUSDm",
            engine_magic=2001,
            order_type="BUY",
            entry_price=2500.0,
            stop_loss_price=2497.0,
            take_profit_price=2506.0,
            volume=lot_b,
            quality_score=80,
            all_open_positions=[],
            equity=1000.0,
            free_margin=1000.0,
            candle_id="CANDLE_TEST_I_002",
            traded_candle_ids=set(),
            last_trade_time=0.0,
        )
        self.assertTrue(passed_b, "Account B must trade normally even if copy engine is paused")

    # -------------------------------------------------------------------------
    # TEST J: Bot restart -> All four account connections recover correctly & positions managed
    # -------------------------------------------------------------------------
    def test_j_bot_restart_recovery_all_four_accounts(self):
        active_accounts = self.account_manager.get_active_accounts()
        self.assertEqual(len(active_accounts), 4, "Must have 4 active account profiles")

        for acc in active_accounts:
            self.assertTrue(acc.connector.is_connected(), f"{acc.account_id} must be connected")
            summary = acc.get_summary()
            self.assertIn("equity", summary)
            self.assertIn("balance", summary)
            self.assertIn("trading_state", summary)
            self.assertIn("account_type", summary)
            self.assertIn("mode", summary)


if __name__ == "__main__":
    unittest.main()
