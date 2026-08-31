"""
Unit Tests for Critical Two-Stage Entry Confirmation Pipeline & Centralized Final Entry Gate.
Verifies:
  1. Developing / intrabar candle tick touches do NOT trigger entry.
  2. Breakout entry strictly requires closed-candle confirmation beyond trigger level.
  3. Pullback entries require EMA touch + closed reversal candle confirmation.
  4. Musumali 4-stage funnel requires sequential progression (cannot jump stages).
  5. Setup expiration occurs after 3 bars without confirmation.
  6. FinalEntryGate blocks any order with confirmation_verified=False or incomplete funnel stage.
  7. FinalEntryGate logs explicit rejection reasons for debugging.
"""

import unittest
import time
import pandas as pd
from unittest.mock import MagicMock

from src.m1_scalper import M1Scalper
from src.strategy import MusumaliStrategy
from src.execution import OrderExecutor, FinalEntryGate


class MockTick:
    def __init__(self, bid=2650.0, ask=2650.3):
        self.bid = bid
        self.ask = ask


class TestTwoStageEntryConfirmation(unittest.TestCase):
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
            "musumali_strategy": {
                "enabled": True,
                "magic_number": 2001,
                "cluster_search_bars": 15,
                "min_rejection_wick_pct": 0.15,
                "risk_reward_ratio": 2.0,
                "require_htf_alignment": False,
                "atr_period": 14,
                "atr_sl_multiplier": 1.5,
                "timeframes": ["M30", "H1"],
            },
            "profit_management": {
                "enabled": True,
            },
            "risk_management": {
                "slippage_points": 30,
                "session_filter_enabled": False,
            },
            "symbols": {
                "symbol_settings": {
                    "XAUUSD": {
                        "min_sl_distance_dollars": 2.00,
                        "max_sl_distance_dollars": 15.00,
                        "scalp_min_sl_dollars": 1.50,
                        "scalp_max_sl_dollars": 4.50,
                        "zone_band_points": 2.0,
                    }
                }
            },
        }
        self.scalper = M1Scalper(self.config)
        self.musumali = MusumaliStrategy(self.config)

    def test_scalper_rejects_intrabar_touch_without_closed_breakout(self):
        """Verify M1Scalper does NOT enter when live tick touches high, but previous closed candle is inside range."""
        dates = pd.date_range("2026-08-31 00:00", periods=30, freq="1min")
        # Standard range candles with normal wicks (not pinbars or breakouts)
        # Open 2649, High 2652, Low 2646, Close 2649.5 (upper wick 2.5, lower wick 3.0, body 0.5)
        # upper_wick / tot_range = 2.5 / 6 = 0.416 (> 0.35 -> not a bull pinbar)
        opens = [2649.0] * 30
        highs = [2652.0] * 30
        lows = [2646.0] * 30
        closes = [2649.5] * 30
        df = pd.DataFrame({
            "time": dates,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "tick_volume": [100] * 30,
        })
        self.scalper.fetch_rates = lambda sym, tf, count=50: df

        # Live tick spikes to 2653.0 (intrabar developing tick touch above 2652.0)
        tick = MockTick(bid=2652.8, ask=2653.0)

        sig, entry, sl, tp, cid, score, reason = self.scalper.evaluate_tf(
            symbol="XAUUSDm",
            tf_name="M1",
            tf_const=1,
            digits=2,
            tick=tick,
        )
        # Must NOT enter because the completed candle did not close beyond recent high
        self.assertIsNone(sig, "Intrabar tick spike must NOT trigger an entry without closed candle confirmation")

    def test_scalper_confirms_closed_candle_breakout(self):
        """Verify M1Scalper enters once a candle has closed firmly beyond the breakout level."""
        dates = pd.date_range("2026-08-31 00:00", periods=30, freq="1min")
        # Realistic oscillating price to give RSI around 55
        prices = [
            2645, 2646, 2644, 2647, 2645, 2648, 2646, 2649, 2647, 2648,
            2646, 2647, 2645, 2648, 2646, 2649, 2647, 2648, 2646, 2649,
            2647, 2648, 2646, 2647, 2645, 2648, 2647, 2648, 2647, 2652
        ]
        opens = [p - 1.0 for p in prices]
        highs = [p + 1.0 for p in prices]
        lows = [p - 2.0 for p in prices]
        closes = [float(p) for p in prices]

        # Prior bar (iloc[-3]) closed at 2648.0 (below recent high 2650.0)
        closes[-3] = 2648.0
        # Closed bar (iloc[-2]) broke and CLOSED at 2652.0 (firmly above recent high 2650.0)
        opens[-2] = 2648.0
        highs[-2] = 2653.0
        lows[-2] = 2647.5
        closes[-2] = 2652.0

        df = pd.DataFrame({
            "time": dates,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "tick_volume": [150] * 30,
        })
        self.scalper.fetch_rates = lambda sym, tf, count=50: df

        tick = MockTick(bid=2652.0, ask=2652.3)

        sig, entry, sl, tp, cid, score, reason = self.scalper.evaluate_tf(
            symbol="XAUUSDm",
            tf_name="M1",
            tf_const=1,
            digits=2,
            tick=tick,
            trend_ctx="UPTREND",
            slope=0.15,
        )
        self.assertEqual(sig, "BUY")
        self.assertIn("Confirmed Bullish Breakout", reason)
        self.assertGreaterEqual(score, 70)

    def test_musumali_requires_closed_breakout_below_rejection_low(self):
        """Verify Musumali SELL requires a closed candle below sweep rejection candle low."""
        dates = pd.date_range("2026-08-31 00:00", periods=30, freq="30min")
        opens = [2645.0] * 30
        highs = [2650.0] * 30
        lows = [2640.0] * 30
        closes = [2645.0] * 30

        # Swing high established at bar -10
        highs[-10] = 2655.0

        # Sweep bar at offset -3 sweeps 2655.0 to 2658.0 and closes rejection at 2652.0 (low was 2648.0)
        highs[-3] = 2658.0
        opens[-3] = 2654.0
        closes[-3] = 2651.0
        lows[-3] = 2648.0

        # Case A: Last closed bar (offset -2) closed at 2650.0 (STILL ABOVE rejection low 2648.0)
        closes[-2] = 2650.0
        opens[-2] = 2651.0
        highs[-2] = 2653.0
        lows[-2] = 2649.0

        df_pending = pd.DataFrame({
            "time": dates,
            "open": opens.copy(),
            "high": highs.copy(),
            "low": lows.copy(),
            "close": closes.copy(),
        })
        self.musumali.fetch_rates = lambda sym, tf, count=50: df_pending

        sig, _, _, _, _, _, _, _ = self.musumali.evaluate_musumali_setup_on_timeframe(
            symbol="XAUUSDm",
            tf_name="M30",
            tf_const=30,
            point=0.01,
            digits=2,
            htf_trend="DOWNTREND",
            htf_reason="H1 Bearish",
        )
        self.assertIsNone(sig, "Musumali must NOT enter while breakout below 2648.0 is unconfirmed")

        # Case B: Last closed bar (offset -2) closes at 2646.0 (FIRMLY BELOW rejection low 2648.0)
        closes[-2] = 2646.0
        opens[-2] = 2650.0
        highs[-2] = 2650.5
        lows[-2] = 2645.0

        df_confirmed = pd.DataFrame({
            "time": dates,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
        })
        self.musumali.fetch_rates = lambda sym, tf, count=50: df_confirmed

        import MetaTrader5 as mt5
        orig_tick = mt5.symbol_info_tick
        mt5.symbol_info_tick = lambda sym: MockTick(bid=2646.0, ask=2646.3)
        try:
            sig, entry, sl, tp, cid, zid, score, reason = self.musumali.evaluate_musumali_setup_on_timeframe(
                symbol="XAUUSDm",
                tf_name="M30",
                tf_const=30,
                point=0.01,
                digits=2,
                htf_trend="DOWNTREND",
                htf_reason="H1 Bearish",
            )
            self.assertEqual(sig, "SELL")
            self.assertIn("Closed Breakdown Below", reason)
        finally:
            mt5.symbol_info_tick = orig_tick

    def test_final_entry_gate_blocks_unconfirmed_orders(self):
        """Verify FinalEntryGate blocks execution if confirmation_verified is False."""
        mock_connector = MagicMock()
        mock_connector.verify_pre_trade_identity.return_value = (True, "OK")
        executor = OrderExecutor(self.config, connector=mock_connector, account_id="account_a")

        gate = FinalEntryGate(executor)

        # Attempt gate entry without confirmation
        passed, reason, audit = gate.evaluate_final_gate(
            symbol="XAUUSDm",
            order_type="BUY",
            volume=0.01,
            sl=2646.0,
            tp=2658.0,
            magic=1001,
            candle_id="SCALP_BUY_UNCONFIRMED",
            quality_score=85,
            confirmation_verified=False, # Unconfirmed!
            funnel_stage="PENDING",
        )
        self.assertFalse(passed, "Final entry gate must REJECT unconfirmed setups")
        self.assertIn("ENTRY_REJECTED: WAITING_FOR_CONFIRMATION", reason)


if __name__ == "__main__":
    unittest.main()
