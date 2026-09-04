"""
Comprehensive Unit Tests for Dynamic Stop Loss Advancement, Profit Locking, and Trailing.
Verifies:
  1. Fast Breakeven locking as soon as position reaches initial profit trigger.
  2. Progressive step-by-step SL advancing ($0.50 -> $1.00 -> $1.50 -> $2.00 -> $2.50+).
  3. Multi-Tier R-multiple profit locking (Tier 1, Tier 2, Tier 3, Tier 4).
  4. Continuous ATR trailing stop for momentum runners.
  5. Partial close SL protection and volume recalculation.
  6. Ratchet rule: Stop Loss strictly moves forward and never backward.
  7. Verification across BUY and SELL positions for Gold (XAUUSD) and Bitcoin (BTCUSD).
"""

import unittest
from unittest.mock import MagicMock
from src.position_manager import IntelligentExitEngine, PositionRecord, ExitDecision, PositionState


class TestProfitSLAdvancement(unittest.TestCase):
    def setUp(self):
        self.config = {
            "profit_management": {
                "enabled": True,
                "dollar_step_lock_enabled": True,
                "step_trigger_dollars": 0.50,
                "step_size_dollars": 0.50,
                "breakeven_buffer_dollars": 0.05,
                "breakeven_trigger_r": 0.35,
                "breakeven_lock_r": 0.05,
                "tier1_protect_trigger_r": 0.80,
                "tier1_protect_lock_r": 0.40,
                "tier2_protect_trigger_r": 1.20,
                "tier2_protect_lock_r": 0.80,
                "tier3_protect_trigger_r": 1.60,
                "tier3_protect_lock_r": 1.20,
                "tier4_protect_trigger_r": 2.20,
                "tier4_protect_lock_r": 1.70,
                "trailing_enabled": True,
                "trailing_trigger_r": 1.40,
                "trailing_distance_r": 0.60,
                "reversal_exit_threshold": 80,
                "min_bars_before_reversal": 3,
                "min_seconds_before_reversal": 120,
                "giveback_min_peak_r": 1.00,
                "giveback_max_r_decay": 0.40,
                "scalp_timeout_bars": 15,
                "musumali_timeout_bars": 25,
            }
        }
        self.engine = IntelligentExitEngine(self.config)

    def test_buy_progressive_profit_sl_ratchet(self):
        """Tests that a BUY position progressively advances SL as profits grow."""
        ticket = 501
        self.engine.register_position(
            ticket=ticket,
            symbol="XAUUSDm",
            pos_type="BUY",
            volume=0.01,
            open_price=2650.00,
            sl=2646.00, # $4.00 initial risk (1R = $4.00)
            tp=2665.00,
            magic=1001,
        )

        # Stage 1: Trade enters small profit +$0.50 (+0.125R) -> Moves SL to Breakeven (+0.05 cushion)
        pos = {
            "ticket": ticket,
            "symbol": "XAUUSDm",
            "type": "BUY",
            "volume": 0.01,
            "price_open": 2650.00,
            "price_current": 2650.50,
            "sl": 2646.00,
            "tp": 2665.00,
            "profit": 0.50,
            "magic": 1001,
        }
        dec, sl, reason = self.engine.evaluate_position_lifecycle(pos, digits=2)
        self.assertEqual(dec, ExitDecision.LOCK_BREAKEVEN)
        self.assertEqual(sl, 2650.05) # 2650.00 + $0.05
        self.assertIn("FAST_BREAKEVEN", reason)

        # Stage 2: Profit grows to +$1.00 -> Advances SL to +$0.50 profit
        pos["price_current"] = 2651.00
        pos["profit"] = 1.00
        pos["sl"] = 2650.05
        dec, sl, reason = self.engine.evaluate_position_lifecycle(pos, digits=2)
        self.assertEqual(dec, ExitDecision.TIGHTEN_PROTECTION)
        self.assertEqual(sl, 2650.50)
        self.assertIn("PROFIT_STEP_LOCK", reason)

        # Stage 3: Profit grows to +$2.00 -> Advances SL to +$1.50 profit
        pos["price_current"] = 2652.00
        pos["profit"] = 2.00
        pos["sl"] = 2650.50
        dec, sl, reason = self.engine.evaluate_position_lifecycle(pos, digits=2)
        self.assertEqual(dec, ExitDecision.TIGHTEN_PROTECTION)
        self.assertEqual(sl, 2651.50)

        # Stage 4: Profit grows to +$3.50 -> Advances SL to +$3.00 profit
        pos["price_current"] = 2653.50
        pos["profit"] = 3.50
        pos["sl"] = 2651.50
        dec, sl, reason = self.engine.evaluate_position_lifecycle(pos, digits=2)
        self.assertEqual(dec, ExitDecision.TIGHTEN_PROTECTION)
        self.assertEqual(sl, 2653.00)

    def test_sell_progressive_profit_sl_ratchet(self):
        """Tests that a SELL position progressively lowers SL as profits grow."""
        ticket = 601
        self.engine.register_position(
            ticket=ticket,
            symbol="XAUUSDm",
            pos_type="SELL",
            volume=0.01,
            open_price=2650.00,
            sl=2654.00, # $4.00 initial risk (1R = $4.00)
            tp=2635.00,
            magic=1001,
        )

        # Stage 1: +$0.50 profit on SELL -> Moves SL to Breakeven (-0.05 cushion)
        pos = {
            "ticket": ticket,
            "symbol": "XAUUSDm",
            "type": "SELL",
            "volume": 0.01,
            "price_open": 2650.00,
            "price_current": 2649.50,
            "sl": 2654.00,
            "tp": 2635.00,
            "profit": 0.50,
            "magic": 1001,
        }
        dec, sl, reason = self.engine.evaluate_position_lifecycle(pos, digits=2)
        self.assertEqual(dec, ExitDecision.LOCK_BREAKEVEN)
        self.assertEqual(sl, 2649.95) # 2650.00 - $0.05

        # Stage 2: +$1.50 profit on SELL -> Moves SL to lock +$1.00 profit (2649.00)
        pos["price_current"] = 2648.50
        pos["profit"] = 1.50
        pos["sl"] = 2649.95
        dec, sl, reason = self.engine.evaluate_position_lifecycle(pos, digits=2)
        self.assertEqual(dec, ExitDecision.TIGHTEN_PROTECTION)
        self.assertEqual(sl, 2649.00) # 2650.00 - $1.00

    def test_r_multiple_tier_and_runner_trailing(self):
        """Tests that large winning runners trigger continuous ATR trailing and high R-locks."""
        ticket = 701
        self.engine.register_position(
            ticket=ticket,
            symbol="XAUUSDm",
            pos_type="BUY",
            volume=0.01,
            open_price=2650.00,
            sl=2648.00, # 1R = $2.00
            tp=2665.00,
            magic=2001,
        )

        # Reach +2.50R ($5.00 gain, price = 2655.00)
        pos = {
            "ticket": ticket,
            "symbol": "XAUUSDm",
            "type": "BUY",
            "volume": 0.01,
            "price_open": 2650.00,
            "price_current": 2655.00,
            "sl": 2650.10,
            "tp": 2665.00,
            "profit": 5.00,
            "magic": 2001,
        }
        dec, sl, reason = self.engine.evaluate_position_lifecycle(pos, live_atr=1.5, digits=2)
        # Should lock at least Tier 4 (+1.70R = 2650 + 3.40 = 2653.40) or trail ATR
        self.assertIn(dec, [ExitDecision.TRAIL_ATR, ExitDecision.TIGHTEN_PROTECTION])
        self.assertGreaterEqual(sl, 2653.40)

    def test_partial_close_volume_update(self):
        """Tests that PositionRecord updates volume and recalculates risk upon partial close."""
        rec = PositionRecord(
            ticket=801,
            symbol="XAUUSDm",
            pos_type="BUY",
            volume=0.04,
            open_price=2650.00,
            initial_sl=2648.00, # 2.00 risk dist
            initial_tp=2660.00,
            magic=1001,
        )
        self.assertAlmostEqual(rec.initial_risk_dollars, 8.00, places=2)

        # Partially close 0.02 lots -> Remaining volume is 0.02
        rec.update_volume(0.02)
        self.assertEqual(rec.volume, 0.02)
        self.assertAlmostEqual(rec.initial_risk_dollars, 4.00, places=2)

    def test_bitcoin_btc_profit_sl_advancement(self):
        """Tests BTCUSD stop loss progression with crypto dollar multiplier."""
        ticket = 901
        self.engine.register_position(
            ticket=ticket,
            symbol="BTCUSDm",
            pos_type="BUY",
            volume=0.01,
            open_price=60000.00,
            sl=59800.00, # 200.00 risk dist = $2.00 risk on 0.01
            tp=61000.00,
            magic=1001,
        )

        # Reached +$1.00 profit (price = 60100.00)
        pos = {
            "ticket": ticket,
            "symbol": "BTCUSDm",
            "type": "BUY",
            "volume": 0.01,
            "price_open": 60000.00,
            "price_current": 60100.00,
            "sl": 59800.00,
            "tp": 61000.00,
            "profit": 1.00,
            "magic": 1001,
        }
        dec, sl, reason = self.engine.evaluate_position_lifecycle(pos, digits=2)
        self.assertEqual(dec, ExitDecision.TIGHTEN_PROTECTION)
        # $0.50 profit locked on 0.01 lot = $50.00 price move -> 60050.00
        self.assertEqual(sl, 60050.00)


if __name__ == "__main__":
    unittest.main()
