"""
Unit Tests for Intelligent Position Management & Reversal Engine
Tests:
  1. Reversal & Continuation Scoring (0 - 100)
  2. 6-State Position Lifecycle State Machine
  3. Dynamic R-Multiple Profit Locking (+0.5R, +0.8R, +1.0R, +1.5R)
  4. Volatility-Aware Trailing & Peak R Decay Protection
  5. Stale Trade Timeout & Thesis Invalidation
  6. 4-Tier Institutional Drawdown Ladder
"""

import unittest
import pandas as pd
import numpy as np

from src.position_manager import (
    IntelligentExitEngine,
    PositionState,
    ExitDecision,
    PositionRecord,
)
from src.risk_manager import RiskManager


class MockTick:
    def __init__(self, bid: float, ask: float):
        self.bid = bid
        self.ask = ask


class MockConnector:
    def get_account_summary(self):
        return {"balance": 100.0, "equity": 100.0}


def create_dummy_df(num_bars=30, start_price=2650.0, trend="bullish"):
    times = pd.date_range("2026-08-28 12:00:00", periods=num_bars, freq="1min")
    data = []
    curr = start_price
    for i in range(num_bars):
        if trend == "bullish":
            open_p = curr
            close_p = curr + 0.5
            high_p = close_p + 0.3
            low_p = open_p - 0.2
            curr = close_p
        elif trend == "bearish":
            open_p = curr
            close_p = curr - 0.5
            high_p = open_p + 0.2
            low_p = close_p - 0.3
            curr = close_p
        else: # chop
            open_p = curr
            close_p = curr + (0.2 if i % 2 == 0 else -0.2)
            high_p = max(open_p, close_p) + 0.1
            low_p = min(open_p, close_p) - 0.1
            curr = close_p

        data.append({
            "time": int(times[i].timestamp()),
            "open": open_p,
            "high": high_p,
            "low": low_p,
            "close": close_p,
            "tick_volume": 100,
        })
    return pd.DataFrame(data)


class TestIntelligentExitEngine(unittest.TestCase):
    def setUp(self):
        self.config = {
            "profit_management": {
                "enabled": True,
                "breakeven_trigger_r": 0.50,
                "breakeven_lock_r": 0.10,
                "tier1_protect_trigger_r": 0.80,
                "tier1_protect_lock_r": 0.30,
                "tier2_protect_trigger_r": 1.00,
                "tier2_protect_lock_r": 0.50,
                "tier3_protect_trigger_r": 1.50,
                "tier3_protect_lock_r": 1.00,
                "reversal_exit_threshold": 70,
                "reversal_warning_threshold": 50,
                "continuation_strong_threshold": 60,
                "giveback_min_peak_r": 0.80,
                "giveback_max_r_decay": 0.40,
                "scalp_timeout_bars": 12,
                "trailing_enabled": True,
                "trailing_trigger_r": 1.2,
            },
            "circuit_breakers": {
                "drawdown_warning_pct": 1.0,
                "drawdown_risk_reduction_pct": 2.0,
                "drawdown_pause_pct": 3.0,
                "max_daily_drawdown_percent": 5.0,
            }
        }
        self.engine = IntelligentExitEngine(self.config)

    def test_reversal_confidence_scoring(self):
        """Tests that a strong bearish multi-timeframe structure generates high reversal score for a BUY."""
        df_m1_bear = create_dummy_df(30, start_price=2660.0, trend="bearish")
        df_m5_bear = create_dummy_df(30, start_price=2660.0, trend="bearish")
        df_m15_bear = create_dummy_df(35, start_price=2660.0, trend="bearish")
        live_tick = MockTick(bid=2645.0, ask=2645.3)

        rev_score, breakdown = self.engine.evaluate_reversal_confidence_score(
            symbol="XAUUSDm",
            pos_type="BUY",
            magic=1001,
            df_m1=df_m1_bear,
            df_m5=df_m5_bear,
            df_m15=df_m15_bear,
            live_tick=live_tick,
            thesis_anchor=2658.0,
        )
        self.assertGreaterEqual(rev_score, 60, "Bearish conditions should produce high reversal score against BUY")

    def test_position_registration_and_initial_risk(self):
        """Tests that ticket registration accurately calculates $1R initial risk."""
        self.engine.register_position(
            ticket=1001,
            symbol="XAUUSDm",
            pos_type="BUY",
            volume=0.01,
            open_price=2650.00,
            sl=2648.00,
            tp=2656.00,
            magic=1001,
        )
        rec = self.engine.records.get(1001)
        self.assertIsNotNone(rec)
        self.assertAlmostEqual(rec.initial_risk_dollars, 2.00, places=2)
        self.assertEqual(rec.state, PositionState.STATE_1_INITIAL)

    def test_breakeven_lock_at_half_r(self):
        """Tests that moving into +0.5R profit transitions to STATE_2_PROFITABLE and locks breakeven."""
        self.engine.register_position(
            ticket=1002,
            symbol="XAUUSDm",
            pos_type="BUY",
            volume=0.01,
            open_price=2650.00,
            sl=2648.00,
            tp=2656.00,
            magic=1001,
        )
        pos_dict = {
            "ticket": 1002,
            "symbol": "XAUUSDm",
            "type": "BUY",
            "volume": 0.01,
            "price_open": 2650.00,
            "price_current": 2651.10, # +$1.10 = +0.55R
            "sl": 2648.00,
            "tp": 2656.00,
            "profit": 1.10,
            "magic": 1001,
        }
        df_m1 = create_dummy_df(30, 2650.0, "bullish")
        df_m5 = create_dummy_df(30, 2650.0, "bullish")
        live_tick = MockTick(bid=2651.10, ask=2651.36)

        decision, new_sl, reason = self.engine.evaluate_position_lifecycle(
            pos_dict=pos_dict,
            df_m1=df_m1,
            df_m5=df_m5,
            df_m15=None,
            live_tick=live_tick,
            live_atr=2.0,
            digits=2,
        )
        self.assertIn(decision, [ExitDecision.LOCK_BREAKEVEN, ExitDecision.TIGHTEN_PROTECTION])
        self.assertGreater(new_sl, 2650.00, "New SL should lock in positive green profit")
        rec = self.engine.records[1002]
        self.assertEqual(rec.state, PositionState.STATE_2_PROFITABLE)

    def test_dollar_accumulation_step_locking(self):
        """Tests that reaching $0.50 profit immediately switches SL to lock in gain."""
        self.engine.register_position(
            ticket=1008,
            symbol="XAUUSDm",
            pos_type="BUY",
            volume=0.01,
            open_price=2650.00,
            sl=2648.00,
            tp=2656.00,
            magic=1001,
        )
        pos_dict = {
            "ticket": 1008,
            "symbol": "XAUUSDm",
            "type": "BUY",
            "volume": 0.01,
            "price_open": 2650.00,
            "price_current": 2650.50, # Reached +$0.50
            "sl": 2648.00,
            "tp": 2656.00,
            "profit": 0.50,
            "magic": 1001,
        }
        df_m1 = create_dummy_df(30, 2650.0, "bullish")
        df_m5 = create_dummy_df(30, 2650.0, "bullish")
        live_tick = MockTick(bid=2650.50, ask=2650.76)

        decision, new_sl, reason = self.engine.evaluate_position_lifecycle(
            pos_dict=pos_dict,
            df_m1=df_m1,
            df_m5=df_m5,
            df_m15=None,
            live_tick=live_tick,
            live_atr=2.0,
            digits=2,
        )
        self.assertEqual(decision, ExitDecision.TIGHTEN_PROTECTION)
        self.assertGreater(new_sl, 2650.00, "SL must switch immediately to green at $0.50 profit")
        self.assertIn("DOLLAR_ACCUMULATION_LOCK", reason)

    def test_confirmed_reversal_exit(self):
        """Tests that high reversal score (>=70) triggers immediate market close."""
        self.engine.register_position(
            ticket=1003,
            symbol="XAUUSDm",
            pos_type="BUY",
            volume=0.01,
            open_price=2650.00,
            sl=2648.00,
            tp=2656.00,
            magic=1001,
        )
        pos_dict = {
            "ticket": 1003,
            "symbol": "XAUUSDm",
            "type": "BUY",
            "volume": 0.01,
            "price_open": 2650.00,
            "price_current": 2649.50,
            "sl": 2648.00,
            "tp": 2656.00,
            "profit": -0.50,
            "magic": 1001,
        }
        df_m1_bear = create_dummy_df(30, 2660.0, "bearish")
        df_m5_bear = create_dummy_df(30, 2660.0, "bearish")
        df_m15_bear = create_dummy_df(35, 2660.0, "bearish")
        live_tick = MockTick(bid=2649.50, ask=2649.76)

        decision, _, reason = self.engine.evaluate_position_lifecycle(
            pos_dict=pos_dict,
            df_m1=df_m1_bear,
            df_m5=df_m5_bear,
            df_m15=df_m15_bear,
            live_tick=live_tick,
            live_atr=2.0,
            digits=2,
        )
        self.assertEqual(decision, ExitDecision.CLOSE_MARKET)
        self.assertIn("REVERSAL_CONFIRMED", reason)

    def test_stale_trade_timeout(self):
        """Tests that stagnating micro-scalps exceeding timeout bars trigger graceful exit."""
        self.engine.register_position(
            ticket=1004,
            symbol="XAUUSDm",
            pos_type="BUY",
            volume=0.01,
            open_price=2650.00,
            sl=2648.00,
            tp=2656.00,
            magic=1001,
        )
        # Advance bars held to 15
        rec = self.engine.records[1004]
        rec.bars_held = 15
        pos_dict = {
            "ticket": 1004,
            "symbol": "XAUUSDm",
            "type": "BUY",
            "volume": 0.01,
            "price_open": 2650.00,
            "price_current": 2650.10, # +0.05R stagnation
            "sl": 2648.00,
            "tp": 2656.00,
            "profit": 0.10,
            "magic": 1001,
        }
        df_m1_chop = create_dummy_df(30, 2650.0, "chop")
        # Ensure stalling candle
        df_m1_chop.loc[df_m1_chop.index[-2], 'close'] = 2649.95
        df_m1_chop.loc[df_m1_chop.index[-2], 'open'] = 2650.05
        live_tick = MockTick(bid=2650.10, ask=2650.36)

        decision, _, reason = self.engine.evaluate_position_lifecycle(
            pos_dict=pos_dict,
            df_m1=df_m1_chop,
            df_m5=None,
            df_m15=None,
            live_tick=live_tick,
            live_atr=2.0,
            digits=2,
        )
        self.assertEqual(decision, ExitDecision.CLOSE_MARKET)
        self.assertIn("TIMEOUT_MOMENTUM_FAILURE", reason)


class TestInstitutionalRiskLadder(unittest.TestCase):
    def setUp(self):
        self.config = {
            "circuit_breakers": {
                "daily_loss_states": {
                    "normal_max_loss_dollars": 15.0,
                    "caution_max_loss_dollars": 30.0,
                    "reduced_risk_max_loss_dollars": 40.0,
                    "critical_max_loss_dollars": 50.0,
                    "emergency_max_loss_dollars": 58.0,
                    "hard_stop_loss_dollars": 60.0,
                },
                "daily_profit_states": {
                    "protection_trigger_dollars": 60.0,
                    "high_selectivity_dollars": 70.0,
                    "daily_target_stop_dollars": 80.0,
                },
            },
            "risk_management": {
                "risk_per_trade_percent": 1.5,
                "consecutive_losses": {
                    "caution_threshold": 2,
                    "reduce_risk_threshold": 3,
                    "restrict_trading_threshold": 4,
                    "pause_module_threshold": 5,
                }
            }
        }
        self.connector = MockConnector()
        self.rm = RiskManager(self.config, self.connector)
        self.rm.reset_daily_metrics_if_needed(current_equity=1000.0)

    def test_drawdown_risk_reduction_and_pause(self):
        """Tests that realized losses progressively activate risk reduction and trading halts."""
        # 0. Normal trading
        can_trade, reason = self.rm.check_circuit_breakers(current_equity=1000.0)
        self.assertTrue(can_trade)
        self.assertEqual(self.rm.risk_reduction_multiplier, 1.0)

        # 1. Simulate -$35 loss on $1000 baseline -> REDUCED_RISK (0.5x)
        self.rm.record_trade_result(zone_id=None, profit=-35.0, magic=1001, exit_reason="SL_HIT")
        can_trade, reason = self.rm.check_circuit_breakers(current_equity=965.0)
        self.assertTrue(can_trade)
        self.assertEqual(self.rm.risk_reduction_multiplier, 0.50, "Risk sizing multiplier should be halved in REDUCED_RISK")

        # 2. Simulate further loss reaching -$60 total loss -> HARD_STOP
        self.rm.record_trade_result(zone_id=None, profit=-25.0, magic=1001, exit_reason="SL_HIT")
        can_trade, reason = self.rm.check_circuit_breakers(current_equity=940.0)
        self.assertFalse(can_trade, "Trading should halt at -$60 daily loss")
        self.assertEqual(self.rm.trading_state, "HARD_STOP")


if __name__ == "__main__":
    unittest.main()
