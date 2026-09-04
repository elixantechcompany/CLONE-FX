"""
Unit Test Suite for Weekend Bitcoin Trading Restriction
Verifies:
  1. is_crypto_weekend accurately identifies Saturday and Sunday in UTC.
  2. pre_trade_risk_check strictly rejects Bitcoin (BTCUSD/BTCUSDm) on weekends.
  3. pre_trade_risk_check allows Bitcoin on normal weekdays (Monday through Friday).
  4. pre_trade_risk_check allows Gold (XAUUSD/XAUUSDm) on open market sessions.
  5. Copy Trading Engine rejects BTC copy execution on weekends.
"""

import unittest
from unittest.mock import MagicMock, patch
import datetime
import yaml

from src.risk_manager import RiskManager
from src.connection import SymbolSpecification
from src.copy_engine import CopyTradingEngine, CopyEvent
from src.account_manager import AccountContext, MultiAccountManager


class MockConnector:
    def __init__(self, account_id="account_c"):
        self.account_id = account_id
        self._connected = True
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
                tick_value=1.0,
                contract_size=1.0,
                volume_min=0.01,
                volume_max=10.0,
                volume_step=0.01,
                spread=500,
            ),
        }

    def is_connected(self):
        return self._connected

    def get_symbol_specs(self, symbol):
        return self.specs.get(symbol)


class TestWeekendCryptoFilter(unittest.TestCase):
    def setUp(self):
        with open("config/config.yaml", "r") as f:
            self.config = yaml.safe_load(f)

        self.connector = MockConnector("account_c")
        self.risk_mgr = RiskManager(
            config=self.config,
            connector=self.connector,
            account_id="account_c",
            account_type="PERSONAL",
        )

    def test_is_crypto_weekend_identification(self):
        """Test Saturday and Sunday are identified as crypto weekend, weekdays are not."""
        # 2026-09-05 is Saturday (weekday 5)
        saturday = datetime.datetime(2026, 9, 5, 12, 0, 0, tzinfo=datetime.timezone.utc)
        self.assertTrue(self.risk_mgr.is_crypto_weekend(saturday))

        # 2026-09-06 is Sunday (weekday 6)
        sunday = datetime.datetime(2026, 9, 6, 18, 0, 0, tzinfo=datetime.timezone.utc)
        self.assertTrue(self.risk_mgr.is_crypto_weekend(sunday))

        # 2026-09-07 is Monday (weekday 0)
        monday = datetime.datetime(2026, 9, 7, 10, 0, 0, tzinfo=datetime.timezone.utc)
        self.assertFalse(self.risk_mgr.is_crypto_weekend(monday))

        # 2026-09-04 is Friday (weekday 4)
        friday = datetime.datetime(2026, 9, 4, 15, 0, 0, tzinfo=datetime.timezone.utc)
        self.assertFalse(self.risk_mgr.is_crypto_weekend(friday))

    def test_btc_rejected_on_weekend_when_disabled(self):
        """Bitcoin pre-trade risk check MUST be rejected on weekend (Saturday/Sunday) when disabled."""
        saturday = datetime.datetime(2026, 9, 5, 14, 0, 0, tzinfo=datetime.timezone.utc)
        self.risk_mgr.risk_config["crypto_weekend_trading_enabled"] = False
        
        with patch.object(self.risk_mgr, "is_crypto_weekend", return_value=True):
            passed, failures, loss = self.risk_mgr.pre_trade_risk_check(
                symbol="BTCUSDm",
                engine_magic=1001,
                order_type="BUY",
                entry_price=60000.0,
                stop_loss_price=59850.0,
                take_profit_price=60350.0,
                volume=0.01,
                quality_score=85,
                all_open_positions=[],
                equity=50.0,
                free_margin=45.0,
                candle_id="BTC_CANDLE_SATURDAY",
                traded_candle_ids=set(),
                last_trade_time=0.0,
            )
            self.assertFalse(passed)
            self.assertTrue(any("Check 19b Fail: Bitcoin trading is strictly disabled on weekends" in f for f in failures))

    def test_btc_allowed_on_weekend_when_enabled(self):
        """Bitcoin pre-trade risk check is ALLOWED on weekend when crypto_weekend_trading_enabled is True."""
        self.risk_mgr.risk_config["crypto_weekend_trading_enabled"] = True
        self.risk_mgr.symbols_cfg["block_crypto_on_weekends"] = False
        self.risk_mgr.symbols_cfg.get("symbol_settings", {}).get("BTCUSD", {})["block_weekend_trading"] = False
        
        with patch.object(self.risk_mgr, "is_crypto_weekend", return_value=True), \
             patch.object(self.risk_mgr, "is_session_allowed", return_value=True):
            passed, failures, loss = self.risk_mgr.pre_trade_risk_check(
                symbol="BTCUSDm",
                engine_magic=1001,
                order_type="BUY",
                entry_price=60000.0,
                stop_loss_price=59850.0,
                take_profit_price=60350.0,
                volume=0.01,
                quality_score=85,
                all_open_positions=[],
                equity=50.0,
                free_margin=45.0,
                candle_id="BTC_CANDLE_SATURDAY_ALLOWED",
                traded_candle_ids=set(),
                last_trade_time=0.0,
            )
            self.assertTrue(passed, f"Expected BTC check to pass on weekend when enabled, failed with: {failures}")

    def test_btc_allowed_on_weekday(self):
        """Bitcoin pre-trade risk check is allowed on weekdays when risk rules pass."""
        with patch.object(self.risk_mgr, "is_crypto_weekend", return_value=False), \
             patch.object(self.risk_mgr, "is_session_allowed", return_value=True):
            passed, failures, loss = self.risk_mgr.pre_trade_risk_check(
                symbol="BTCUSDm",
                engine_magic=1001,
                order_type="BUY",
                entry_price=60000.0,
                stop_loss_price=59850.0,
                take_profit_price=60350.0,
                volume=0.01,
                quality_score=85,
                all_open_positions=[],
                equity=50.0,
                free_margin=45.0,
                candle_id="BTC_CANDLE_WEEKDAY",
                traded_candle_ids=set(),
                last_trade_time=0.0,
            )
            self.assertTrue(passed, f"Expected BTC check to pass on weekday, failed with: {failures}")

    def test_gold_not_blocked_by_crypto_weekend_filter(self):
        """Gold (XAUUSDm) should not be blocked by the crypto weekend filter."""
        with patch.object(self.risk_mgr, "is_session_allowed", return_value=True):
            passed, failures, loss = self.risk_mgr.pre_trade_risk_check(
                symbol="XAUUSDm",
                engine_magic=1001,
                order_type="BUY",
                entry_price=2500.0,
                stop_loss_price=2498.0,
                take_profit_price=2504.0,
                volume=0.01,
                quality_score=85,
                all_open_positions=[],
                equity=50.0,
                free_margin=45.0,
                candle_id="GOLD_CANDLE_001",
                traded_candle_ids=set(),
                last_trade_time=0.0,
            )
            # Gold should not have Check 19b failure
            self.assertFalse(any("Check 19b Fail" in f for f in failures))

    def test_copy_engine_blocks_btc_on_weekends_when_disabled(self):
        """Account D follower rejects BTC copy trade on weekends when disabled."""
        cfg = dict(self.config)
        cfg["risk_management"] = dict(cfg.get("risk_management", {}))
        cfg["risk_management"]["crypto_weekend_trading_enabled"] = False
        account_mgr = MultiAccountManager(cfg)
        acc_d = account_mgr.get_account("account_d")
        acc_d.connector = MockConnector("account_d")
        copy_engine = CopyTradingEngine(cfg, account_mgr)

        event = CopyEvent(
            event_id="EVT_BTC_WEEKEND_01",
            master_account_id="account_c",
            follower_account_id="account_d",
            symbol="BTCUSDm",
            direction="BUY",
            master_entry=60000.0,
            master_sl=59850.0,
            master_tp=60350.0,
            master_volume=0.01,
            master_ticket=999999,
            event_type="OPEN",
            magic=1001,
        )

        saturday = datetime.datetime(2026, 9, 5, 12, 0, 0, tzinfo=datetime.timezone.utc)
        with patch("datetime.datetime") as mock_dt:
            mock_dt.now.return_value = saturday
            mock_dt.timezone = datetime.timezone
            ok, reason = copy_engine._handle_open_event(event, acc_d)
            self.assertFalse(ok)
            self.assertIn("WEEKEND CRYPTO FILTER", reason)


if __name__ == "__main__":
    unittest.main()
