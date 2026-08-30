"""
Unit and Integration Tests for Advanced Bot Features:
1. Auto-Compounding Tiered Sizing
2. Session-Specific Dynamic Tuning
3. Dashboard JSON Exporter
4. Interactive Telegram Command Parser
"""

import unittest
import os
import json
import yaml
from unittest.mock import MagicMock

from src.risk_manager import RiskManager
from src.dashboard import DashboardExporter
from src.notifier import Notifier


class TestAdvancedFeatures(unittest.TestCase):
    def setUp(self):
        with open("config/config.yaml", "r") as f:
            self.config = yaml.safe_load(f)
        self.mock_connector = MagicMock()
        self.risk_manager = RiskManager(self.config, self.mock_connector)

    def test_auto_compounding_tiers(self):
        """Validates that lot sizes scale accurately across equity tiers."""
        # Tier 1: $0 - $60 -> 0.01 lots
        lots_40 = self.risk_manager.calculate_lot_size("XAUUSDm", 4550.0, 4545.0, equity=40.0)
        self.assertEqual(lots_40, 0.01)

        # Tier 2: $60 - $120 -> 0.02 lots
        lots_80 = self.risk_manager.calculate_lot_size("XAUUSDm", 4550.0, 4545.0, equity=80.0)
        self.assertEqual(lots_80, 0.02)

        # Tier 3: $120 - $250 -> 0.03 lots
        lots_180 = self.risk_manager.calculate_lot_size("XAUUSDm", 4550.0, 4545.0, equity=180.0)
        self.assertEqual(lots_180, 0.03)

        # Tier 4: $250 - $500 -> 0.05 lots
        lots_350 = self.risk_manager.calculate_lot_size("XAUUSDm", 4550.0, 4545.0, equity=350.0)
        self.assertEqual(lots_350, 0.05)

        # Tier 5: $500+ -> 0.10 lots
        lots_800 = self.risk_manager.calculate_lot_size("XAUUSDm", 4550.0, 4545.0, equity=800.0)
        self.assertEqual(lots_800, 0.10)

    def test_session_tuning_params(self):
        """Validates session-specific dynamic tuning."""
        params = self.risk_manager.get_session_tuning_params()
        self.assertIn("session", params)
        self.assertIn("quality_score_threshold", params)
        self.assertIn("max_spread_points", params)
        self.assertGreaterEqual(params["quality_score_threshold"], 40)
        self.assertLessEqual(params["quality_score_threshold"], 80)

    def test_dashboard_export(self):
        """Validates dashboard JSON data file generation."""
        exporter = DashboardExporter(self.config, output_dir="dashboard")
        mock_acc = {"balance": 100.0, "equity": 105.0, "margin_free": 100.0, "margin_level": 500.0}
        mock_perf = {
            "total_day_pnl": 5.0,
            "scalp_pnl": 3.0,
            "scalp_trades": 2,
            "scalp_wins": 2,
            "musumali_pnl": 2.0,
            "musumali_trades": 1,
            "musumali_wins": 1,
        }
        mock_positions = [{
            "ticket": 999999,
            "type": "BUY",
            "volume": 0.01,
            "price_open": 4550.0,
            "price_current": 4555.0,
            "sl": 4545.0,
            "tp": 4565.0,
            "profit": 5.0,
            "magic": 1001,
        }]

        exporter.last_export_time = 0.0  # Force immediate export
        exporter.export_data(
            symbol="XAUUSDm",
            account_summary=mock_acc,
            all_positions=mock_positions,
            daily_perf=mock_perf,
            circuit_status="ACTIVE",
            active_session="London/NY Overlap",
            daily_trend="UPTREND",
            trend_reason="H1 UPTREND",
        )

        data_file = "dashboard/data.json"
        self.assertTrue(os.path.exists(data_file))
        with open(data_file, "r") as f:
            data = json.load(f)
            self.assertEqual(data["account"]["equity"], 105.0)
            self.assertEqual(data["performance"]["total_day_pnl"], 5.0)
            self.assertEqual(len(data["positions"]), 1)
            self.assertEqual(data["positions"][0]["ticket"], 999999)

    def test_telegram_command_handler(self):
        """Validates interactive command execution logic."""
        notifier = Notifier(self.config)
        mock_bot = MagicMock()
        mock_bot.connector.get_account_summary.return_value = {"balance": 50.0, "equity": 55.0}
        mock_bot.executor.get_open_positions.return_value = []
        mock_bot.risk_manager.get_circuit_breaker_status.return_value = "ACTIVE"
        mock_bot.risk_manager.get_current_trading_session.return_value = "London"
        mock_bot.risk_manager.get_module_performance_summary.return_value = {
            "total_day_pnl": 5.0,
            "scalp_pnl": 5.0,
            "scalp_trades": 1,
            "scalp_wins": 1,
            "musumali_pnl": 0.0,
            "musumali_trades": 0,
            "musumali_wins": 0,
        }

        notifier.bot_instance = mock_bot
        notifier.send_telegram = MagicMock(return_value=True)

        # Test /status
        notifier._handle_command("/status")
        self.assertTrue(notifier.send_telegram.called)

        # Test /pause
        notifier._handle_command("/pause")
        self.assertTrue(mock_bot.is_manually_paused)

        # Test /resume
        notifier._handle_command("/resume")
        self.assertFalse(mock_bot.is_manually_paused)


if __name__ == "__main__":
    unittest.main()
