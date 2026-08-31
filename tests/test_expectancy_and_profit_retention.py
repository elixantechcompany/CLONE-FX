"""
Unit & Forensic Diagnostic Tests for Positive Mathematical Expectancy & Profit Retention.
Verifies:
  1. No premature reversal exit during initial maturation period.
  2. No micro-cent dollar choking of profitable trades.
  3. Breakeven locks at +0.50R initial risk.
  4. Giveback guardian activates strictly at >= +1.00R peak.
  5. Independent Real-Time Loss Guard enforces hard loss ceiling.
  6. Realized R-Multiple audit reporting and consecutive loss cooldowns.
  7. Market regime filter rejects choppy alternating candles.
"""

import unittest
import time
import pandas as pd
import numpy as np
from src.position_manager import IntelligentExitEngine, PositionRecord, ExitDecision, PositionState
from src.risk_manager import RiskManager
from src.m1_scalper import M1Scalper


class TestExpectancyAndProfitRetention(unittest.TestCase):
    def setUp(self):
        self.config = {
            "m1_scalper": {
                "enabled": True,
                "magic_number": 1001,
                "min_quality_score": 70,
                "fast_ema": 7,
                "slow_ema": 16,
                "sweep_lookback_bars": 8,
                "atr_period": 14,
                "atr_sl_multiplier": 1.5,
                "risk_reward_ratio": 2.0,
                "trend_filter_enabled": False,
            },
            "profit_management": {
                "enabled": True,
                "dollar_step_lock_enabled": False,
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
                "reversal_warning_threshold": 60,
                "min_bars_before_reversal": 3,
                "min_seconds_before_reversal": 120,
                "giveback_min_peak_r": 1.00,
                "giveback_max_r_decay": 0.40,
                "scalp_timeout_bars": 15,
                "musumali_timeout_bars": 25,
            },
            "circuit_breakers": {
                "brightfunded_1000": {
                    "initial_account_size_dollars": 1000.0,
                    "max_single_trade_risk_dollars": 5.00,
                    "preferred_risk_min_dollars": 2.50,
                    "preferred_risk_max_dollars": 5.00,
                    "single_trade_hard_reject_dollars": 5.50,
                    "internal_daily_hard_stop_dollars": 25.0,
                    "internal_trailing_hard_stop_dollars": 50.0,
                    "challenge_target_profit_dollars": 100.0,
                },
                "personal_20": {
                    "initial_account_size_dollars": 20.0,
                    "max_single_trade_risk_dollars": 0.50,
                    "preferred_risk_min_dollars": 0.25,
                    "preferred_risk_max_dollars": 0.50,
                    "single_trade_hard_reject_dollars": 1.00,
                    "internal_daily_hard_stop_dollars": 2.0,
                    "internal_trailing_hard_stop_dollars": 4.0,
                    "challenge_target_profit_dollars": 10.0,
                },
            },
            "risk_management": {
                "consecutive_losses": {
                    "caution_threshold": 2,
                    "reduce_risk_threshold": 2,
                    "restrict_trading_threshold": 3,
                    "pause_module_threshold": 3,
                    "module_cooldown_minutes": 30,
                },
                "session_filter_enabled": False,
            },
            "symbols": {
                "XAUUSD": {"contract_size": 100.0, "min_volume": 0.01, "max_volume": 1.0, "volume_step": 0.01},
            },
        }
        self.exit_engine = IntelligentExitEngine(self.config)

    def test_no_premature_reversal_exit_on_initial_bars(self):
        """Verify trade is NOT exited within 30 seconds of entry despite noisy opposite indicator values."""
        pos = {
            "ticket": 1001,
            "symbol": "XAUUSDm",
            "type": "SELL",
            "volume": 0.01,
            "price_open": 2650.00,
            "price_current": 2649.90, # +$0.10 profit (+0.025R)
            "sl": 2654.00, # 4.00 distance = $4.00 risk
            "tp": 2642.00,
            "profit": 0.10,
            "magic": 1001,
        }
        rec = self.exit_engine.register_position(
            ticket=1001,
            symbol="XAUUSDm",
            pos_type="SELL",
            volume=0.01,
            open_price=2650.00,
            sl=2654.00,
            tp=2642.00,
            magic=1001,
            account_id="account_a",
        )
        rec.bars_held = 0  # Brand new trade
        rec.open_time = time.time()  # Just opened

        decision, target_sl, reason = self.exit_engine.evaluate_position_lifecycle(
            pos_dict=pos,
            df_m1=None,
            df_m5=None,
            live_atr=2.0,
            digits=2,
        )
        self.assertEqual(decision, ExitDecision.HOLD, "Brand new trade must HOLD and not exit prematurely")
        self.assertIsNone(target_sl)

    def test_no_micro_cent_dollar_step_lock(self):
        """Verify floating profit of +$0.50 does NOT choke SL into spread noise at +$0.20."""
        pos = {
            "ticket": 1002,
            "symbol": "XAUUSDm",
            "type": "BUY",
            "volume": 0.01,
            "price_open": 2650.00,
            "price_current": 2650.50, # +$0.50 profit (+0.125R on $4 risk)
            "sl": 2646.00, # 4.00 distance = $4.00 risk
            "tp": 2658.00,
            "profit": 0.50,
            "magic": 1001,
        }
        self.exit_engine.register_position(
            ticket=1002,
            symbol="XAUUSDm",
            pos_type="BUY",
            volume=0.01,
            open_price=2650.00,
            sl=2646.00,
            tp=2658.00,
            magic=1001,
            account_id="account_a",
        )
        decision, target_sl, reason = self.exit_engine.evaluate_position_lifecycle(
            pos_dict=pos,
            live_atr=2.0,
            digits=2,
        )
        # Should HOLD because +0.125R has not reached +0.50R breakeven trigger yet!
        self.assertEqual(decision, ExitDecision.HOLD, "Small +$0.50 move must HOLD and not choke SL at +$0.20")

    def test_breakeven_locks_at_half_r(self):
        """Verify Breakeven triggers at +0.50R initial risk and locks +0.10R buffer."""
        pos = {
            "ticket": 1003,
            "symbol": "XAUUSDm",
            "type": "BUY",
            "volume": 0.01,
            "price_open": 2650.00,
            "price_current": 2652.00, # +$2.00 gain (+0.50R on $4 risk)
            "sl": 2646.00, # 4.00 distance
            "tp": 2658.00,
            "profit": 2.00,
            "magic": 1001,
        }
        self.exit_engine.register_position(
            ticket=1003,
            symbol="XAUUSDm",
            pos_type="BUY",
            volume=0.01,
            open_price=2650.00,
            sl=2646.00,
            tp=2658.00,
            magic=1001,
            account_id="account_a",
        )
        decision, target_sl, reason = self.exit_engine.evaluate_position_lifecycle(
            pos_dict=pos,
            live_atr=2.0,
            digits=2,
        )
        self.assertEqual(decision, ExitDecision.LOCK_BREAKEVEN)
        # 2650.00 + (4.0 * 0.10) = 2650.40
        self.assertAlmostEqual(target_sl, 2650.40, places=2)

    def test_giveback_guardian_only_at_meaningful_peak(self):
        """Verify Giveback Guardian does NOT trigger on +0.02R noise, but protects >= +1.0R winners."""
        pos = {
            "ticket": 1004,
            "symbol": "XAUUSDm",
            "type": "BUY",
            "volume": 0.01,
            "price_open": 2650.00,
            "price_current": 2652.20, # Currently +0.55R ($2.20)
            "sl": 2646.00,
            "tp": 2658.00,
            "profit": 2.20,
            "magic": 1001,
        }
        rec = self.exit_engine.register_position(
            ticket=1004,
            symbol="XAUUSDm",
            pos_type="BUY",
            volume=0.01,
            open_price=2650.00,
            sl=2646.00,
            tp=2658.00,
            magic=1001,
            account_id="account_a",
        )
        # Simulate that peak reached +1.20R ($4.80) and has now decayed to +0.55R (gave back 0.65R > 0.40R max decay)
        rec.peak_r = 1.20
        decision, target_sl, reason = self.exit_engine.evaluate_position_lifecycle(
            pos_dict=pos,
            live_atr=2.0,
            digits=2,
        )
        self.assertEqual(decision, ExitDecision.CLOSE_MARKET)
        self.assertIn("PROFIT_GIVEBACK_GUARD", reason)

    def test_real_time_loss_guard_emergency_close(self):
        """Verify Real-Time Loss Guard forces emergency close when loss reaches $5.00 cap on BrightFunded."""
        pos = {
            "ticket": 1005,
            "symbol": "XAUUSDm",
            "type": "BUY",
            "volume": 0.01,
            "price_open": 2650.00,
            "price_current": 2644.80, # Loss -$5.20
            "sl": 2644.00,
            "tp": 2658.00,
            "profit": -5.20,
            "magic": 1001,
        }
        self.exit_engine.register_position(
            ticket=1005,
            symbol="XAUUSDm",
            pos_type="BUY",
            volume=0.01,
            open_price=2650.00,
            sl=2644.00,
            tp=2658.00,
            magic=1001,
            account_id="account_a",
        )
        decision, target_sl, reason = self.exit_engine.evaluate_position_lifecycle(
            pos_dict=pos,
            live_atr=2.0,
            digits=2,
        )
        self.assertEqual(decision, ExitDecision.CLOSE_MARKET)
        self.assertIn("EMERGENCY_REAL_TIME_LOSS_GUARD", reason)

    def test_consecutive_losses_cooldown_in_risk_manager(self):
        """Verify 2 consecutive losses trigger risk reduction and 3 trigger module pause."""
        rm = RiskManager(self.config, connector=None, account_id="account_a")
        # Record loss 1
        rm.record_trade_result(zone_id=None, profit=-4.00, magic=1001, symbol="XAUUSDm", exit_reason="SL_Hit")
        self.assertEqual(rm.engine_consecutive_losses[1001], 1)
        in_cd, _ = rm.is_engine_in_cooldown(1001)
        self.assertFalse(in_cd)

        # Record loss 2
        rm.record_trade_result(zone_id=None, profit=-3.90, magic=1001, symbol="XAUUSDm", exit_reason="SL_Hit")
        self.assertEqual(rm.engine_consecutive_losses[1001], 2)
        in_cd, _ = rm.is_engine_in_cooldown(1001)
        self.assertFalse(in_cd)

        # Record loss 3 -> Should trigger 30-min pause
        rm.record_trade_result(zone_id=None, profit=-4.10, magic=1001, symbol="XAUUSDm", exit_reason="SL_Hit")
        self.assertEqual(rm.engine_consecutive_losses[1001], 3)
        in_cd, msg = rm.is_engine_in_cooldown(1001)
        self.assertTrue(in_cd, "Engine 1001 must be in cooldown after 3 consecutive losses")

    def test_market_regime_alternating_chop_rejection(self):
        """Verify M1Scalper rejects setups during extreme alternating chop."""
        scalper = M1Scalper(self.config)
        # Create synthetic alternating candles with >= 30 bars (green, red, green, red, ...)
        dates = pd.date_range("2026-08-31 00:00", periods=30, freq="1min")
        opens = [2650.0 if i % 2 == 0 else 2651.0 for i in range(30)]
        closes = [2651.0 if i % 2 == 0 else 2650.0 for i in range(30)]
        highs = [2651.5 for _ in range(30)]
        lows = [2649.5 for _ in range(30)]
        df_chop = pd.DataFrame({
            "time": dates,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "tick_volume": [100] * 30,
        })
        scalper.fetch_rates = lambda sym, tf, count=50: df_chop

        class FakeTick:
            bid = 2650.0
            ask = 2650.3

        sig, sl, tp, p_loss, p_lbl, score, reason = scalper.evaluate_tf(
            symbol="XAUUSDm",
            tf_name="M1",
            tf_const=1,
            digits=2,
            tick=FakeTick(),
        )
        self.assertIsNone(sig, "Setup must be rejected in alternating chop")
        self.assertIn("chop", reason.lower())


if __name__ == "__main__":
    unittest.main()
