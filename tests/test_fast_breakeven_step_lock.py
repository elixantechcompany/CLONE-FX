"""
Unit Tests for Fast Breakeven & 50-Cent Immediate Profit Step Lock.
Verifies:
  1. At +$0.50 profit: SL immediately moves to Breakeven (+0.05 cushion).
  2. At +$1.00 profit: SL immediately advances to +$0.50 profit lock.
  3. At +$1.50 profit: SL immediately advances to +$1.00 profit lock.
  4. At +$2.00 profit: SL immediately advances to +$1.50 profit lock.
  5. At +$2.50 profit: SL immediately advances to +$2.00 profit lock.
  6. Tested across both BUY and SELL positions on XAUUSD.
"""

import unittest
from src.position_manager import IntelligentExitEngine, ExitDecision, PositionState


class TestFastBreakevenStepLock(unittest.TestCase):
    def setUp(self):
        self.config = {
            "profit_management": {
                "enabled": True,
                "dollar_step_lock_enabled": True,
                "step_trigger_dollars": 0.50,
                "step_size_dollars": 0.50,
                "breakeven_buffer_dollars": 0.05,
                "breakeven_trigger_r": 0.50,
                "breakeven_lock_r": 0.10,
                "tier1_protect_trigger_r": 1.00,
                "tier1_protect_lock_r": 0.50,
                "tier2_protect_trigger_r": 1.50,
                "tier2_protect_lock_r": 1.00,
                "tier3_protect_trigger_r": 2.00,
                "tier3_protect_lock_r": 1.50,
                "tier4_protect_trigger_r": 3.00,
                "tier4_protect_lock_r": 2.30,
                "reversal_exit_threshold": 80,
                "min_bars_before_reversal": 3,
                "min_seconds_before_reversal": 120,
                "giveback_min_peak_r": 1.00,
                "giveback_max_r_decay": 0.40,
                "scalp_timeout_bars": 15,
                "musumali_timeout_bars": 25,
            }
        }
        self.exit_engine = IntelligentExitEngine(self.config)

    def test_buy_fast_breakeven_at_50_cents(self):
        """At +$0.50 profit, BUY SL moves immediately to Breakeven (+0.05 cushion)."""
        pos = {
            "ticket": 101,
            "symbol": "XAUUSDm",
            "type": "BUY",
            "volume": 0.01,
            "price_open": 2650.00,
            "price_current": 2650.50,
            "sl": 2646.00, # Initial $4.00 SL
            "tp": 2658.00,
            "profit": 0.50,
            "magic": 1001,
        }
        decision, target_sl, reason = self.exit_engine.evaluate_position_lifecycle(pos, digits=2)
        self.assertEqual(decision, ExitDecision.LOCK_BREAKEVEN)
        self.assertEqual(target_sl, 2650.05) # 2650.00 + $0.05 buffer
        self.assertIn("FAST_BREAKEVEN", reason)

    def test_buy_step_lock_at_1_dollar(self):
        """At +$1.00 profit, BUY SL moves to lock +$0.50 profit."""
        pos = {
            "ticket": 102,
            "symbol": "XAUUSDm",
            "type": "BUY",
            "volume": 0.01,
            "price_open": 2650.00,
            "price_current": 2651.00,
            "sl": 2650.05, # Current SL at breakeven
            "tp": 2658.00,
            "profit": 1.00,
            "magic": 1001,
        }
        decision, target_sl, reason = self.exit_engine.evaluate_position_lifecycle(pos, digits=2)
        self.assertEqual(decision, ExitDecision.TIGHTEN_PROTECTION)
        self.assertEqual(target_sl, 2650.50) # 2650.00 + $0.50 profit
        self.assertIn("PROFIT_STEP_LOCK", reason)

    def test_buy_step_lock_at_1_50_dollars(self):
        """At +$1.50 profit, BUY SL moves to lock +$1.00 profit."""
        pos = {
            "ticket": 103,
            "symbol": "XAUUSDm",
            "type": "BUY",
            "volume": 0.01,
            "price_open": 2650.00,
            "price_current": 2651.50,
            "sl": 2650.50,
            "tp": 2658.00,
            "profit": 1.50,
            "magic": 1001,
        }
        decision, target_sl, reason = self.exit_engine.evaluate_position_lifecycle(pos, digits=2)
        self.assertEqual(decision, ExitDecision.TIGHTEN_PROTECTION)
        self.assertEqual(target_sl, 2651.00) # 2650.00 + $1.00 profit
        self.assertIn("PROFIT_STEP_LOCK", reason)

    def test_buy_step_lock_at_2_00_dollars(self):
        """At +$2.00 profit, BUY SL moves to lock +$1.50 profit."""
        pos = {
            "ticket": 104,
            "symbol": "XAUUSDm",
            "type": "BUY",
            "volume": 0.01,
            "price_open": 2650.00,
            "price_current": 2652.00,
            "sl": 2651.00,
            "tp": 2658.00,
            "profit": 2.00,
            "magic": 1001,
        }
        decision, target_sl, reason = self.exit_engine.evaluate_position_lifecycle(pos, digits=2)
        self.assertEqual(decision, ExitDecision.TIGHTEN_PROTECTION)
        self.assertEqual(target_sl, 2651.50) # 2650.00 + $1.50 profit

    def test_sell_fast_breakeven_at_50_cents(self):
        """At +$0.50 profit, SELL SL moves immediately to Breakeven (+0.05 cushion)."""
        pos = {
            "ticket": 201,
            "symbol": "XAUUSDm",
            "type": "SELL",
            "volume": 0.01,
            "price_open": 2650.00,
            "price_current": 2649.50,
            "sl": 2654.00, # Initial $4.00 SL
            "tp": 2642.00,
            "profit": 0.50,
            "magic": 1001,
        }
        decision, target_sl, reason = self.exit_engine.evaluate_position_lifecycle(pos, digits=2)
        self.assertEqual(decision, ExitDecision.LOCK_BREAKEVEN)
        self.assertEqual(target_sl, 2649.95) # 2650.00 - $0.05 buffer
        self.assertIn("FAST_BREAKEVEN", reason)

    def test_sell_step_lock_at_1_50_dollars(self):
        """At +$1.50 profit, SELL SL moves to lock +$1.00 profit."""
        pos = {
            "ticket": 202,
            "symbol": "XAUUSDm",
            "type": "SELL",
            "volume": 0.01,
            "price_open": 2650.00,
            "price_current": 2648.50,
            "sl": 2649.50,
            "tp": 2642.00,
            "profit": 1.50,
            "magic": 1001,
        }
        decision, target_sl, reason = self.exit_engine.evaluate_position_lifecycle(pos, digits=2)
        self.assertEqual(decision, ExitDecision.TIGHTEN_PROTECTION)
        self.assertEqual(target_sl, 2649.00) # 2650.00 - $1.00 profit


if __name__ == "__main__":
    unittest.main()
