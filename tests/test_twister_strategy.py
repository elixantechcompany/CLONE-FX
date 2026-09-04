"""
Unit Test Suite for TwisterPro M15 Scalper Strategy Engine
Verifies:
  1. Layer 1: Momentum & Trend alignment (EMA 9/21/50 + RSI 14).
  2. Layer 2: Micro-Structure Swing Breakout & Rejection.
  3. Layer 3: Dynamic Volatility & ATR Scaling.
  4. Layer 4: High-Liquidity Session Window Gate.
  5. Layer 5: Real-time Spread Gate.
  6. Quality scoring threshold gating.
  7. Mode 1 vs Mode 2 SL and TP calculations.
  8. Traded candle deduplication.
"""

import unittest
import datetime
import pandas as pd
import numpy as np

from src.twister_strategy import TwisterProStrategy


def create_synthetic_m15_df(trend="BULLISH", count=60, atr_val=2.0, rsi_val=60.0):
    """Generates synthetic M15 dataframe with predictable technical indicator values."""
    dates = pd.date_range(end=datetime.datetime(2026, 9, 4, 14, 0, 0), periods=count, freq="15min")
    
    if trend == "BULLISH":
        # Steadily rising prices to ensure EMA 9 > EMA 21 > EMA 50
        base = np.linspace(2500.0, 2600.0, count)
        highs = base + (atr_val * 0.6)
        lows = base - (atr_val * 0.4)
        opens = base - 0.5
        closes = base + 0.5
    elif trend == "BEARISH":
        # Steadily falling prices to ensure EMA 9 < EMA 21 < EMA 50
        base = np.linspace(2600.0, 2500.0, count)
        highs = base + (atr_val * 0.4)
        lows = base - (atr_val * 0.6)
        opens = base + 0.5
        closes = base - 0.5
    else:
        # Flat / chop
        base = np.full(count, 2550.0)
        highs = base + 0.5
        lows = base - 0.5
        opens = base
        closes = base

    df = pd.DataFrame({
        "time": dates,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "tick_volume": 500,
    })
    return df


class TestTwisterProStrategy(unittest.TestCase):
    def setUp(self):
        self.config = {
            "twister_strategy": {
                "enabled": True,
                "magic_number": 2001,
                "mode": "MODE_1",
                "timeframe": "M15",
                "min_quality_score": 80,
                "fast_ema": 9,
                "mid_ema": 21,
                "slow_ema": 50,
                "rsi_period": 14,
                "rsi_buy_min": 50.0,
                "rsi_buy_max": 70.0,
                "rsi_sell_min": 30.0,
                "rsi_sell_max": 50.0,
                "swing_lookback_bars": 20,
                "min_rejection_wick_pct": 0.15,
                "atr_period": 14,
                "atr_min_points": 1.0,
                "max_candle_atr_ratio": 2.5,
                "atr_sl_multiplier": 1.5,
                "atr_tp_multiplier": 2.5,
                "atr_sl_multiplier_mode2": 1.0,
                "atr_tp_multiplier_mode2": 1.5,
                "session_filter_enabled": True,
                "session_start_hour_utc": 7,
                "session_end_hour_utc": 20,
                "max_spread_points": 35,
            }
        }
        self.strategy = TwisterProStrategy(self.config)

    def test_layer_1_momentum_bullish_pass(self):
        """Layer 1: Bullish trend EMA 9 > 21 > 50 and RSI in 50-70 band."""
        df = create_synthetic_m15_df(trend="BULLISH", count=60)
        df = self.strategy.calculate_indicators(df)
        # Ensure last closed candle has RSI in 50-70
        df.loc[df.index[-2], "rsi"] = 60.0

        direction, score, msg = self.strategy.validate_layer_1_momentum(df)
        self.assertEqual(direction, "BUY")
        self.assertEqual(score, 20)
        self.assertIn("Layer 1 Pass", msg)

    def test_layer_1_momentum_bearish_pass(self):
        """Layer 1: Bearish trend EMA 9 < 21 < 50 and RSI in 30-50 band."""
        df = create_synthetic_m15_df(trend="BEARISH", count=60)
        df = self.strategy.calculate_indicators(df)
        df.loc[df.index[-2], "rsi"] = 40.0

        direction, score, msg = self.strategy.validate_layer_1_momentum(df)
        self.assertEqual(direction, "SELL")
        self.assertEqual(score, 20)
        self.assertIn("Layer 1 Pass", msg)

    def test_layer_1_overbought_rejected(self):
        """Layer 1: Overbought RSI > 70 is rejected for BUY."""
        df = create_synthetic_m15_df(trend="BULLISH", count=60)
        df = self.strategy.calculate_indicators(df)
        df.loc[df.index[-2], "rsi"] = 78.0

        direction, score, msg = self.strategy.validate_layer_1_momentum(df)
        self.assertIsNone(direction)
        self.assertEqual(score, 0)
        self.assertIn("overbought", msg)

    def test_layer_2_micro_structure_breakout(self):
        """Layer 2: Candle close breaking out above 20-bar swing high."""
        df = create_synthetic_m15_df(trend="BULLISH", count=60)
        # Set swing high across the full lookback window to 2580.0
        lookback_start = -(self.strategy.swing_lookback_bars + 2)
        df.iloc[lookback_start:-2, df.columns.get_loc("high")] = 2580.0
        # Set entry candle close above swing high
        df.iloc[-2, df.columns.get_loc("close")] = 2585.0
        df.iloc[-2, df.columns.get_loc("high")] = 2586.0
        df.iloc[-2, df.columns.get_loc("low")] = 2584.0

        passed, score, msg = self.strategy.validate_layer_2_micro_structure(df, "BUY")
        self.assertTrue(passed)
        self.assertEqual(score, 20)
        self.assertIn("Closed breakout", msg)

    def test_layer_3_volatility_and_atr(self):
        """Layer 3: Verifies normal ATR passes, while dead market or news spike rejects."""
        df = create_synthetic_m15_df(trend="BULLISH", count=60)
        df = self.strategy.calculate_indicators(df)

        # Normal volatility: ATR = 2.0, candle range = 2.5
        df.loc[df.index[-2], "atr"] = 2.0
        df.loc[df.index[-2], "high"] = 2552.0
        df.loc[df.index[-2], "low"] = 2550.0
        passed, atr_val, score, msg = self.strategy.validate_layer_3_volatility(df)
        self.assertTrue(passed)
        self.assertEqual(score, 20)

        # Abnormally low volatility (dead market)
        df.loc[df.index[-2], "atr"] = 0.4
        passed_low, _, score_low, msg_low = self.strategy.validate_layer_3_volatility(df)
        self.assertFalse(passed_low)
        self.assertEqual(score_low, 0)
        self.assertIn("Volatility too low", msg_low)

        # News spike (> 2.5x ATR)
        df.loc[df.index[-2], "atr"] = 2.0
        df.loc[df.index[-2], "high"] = 2560.0
        df.loc[df.index[-2], "low"] = 2550.0 # Range 10.0 > 2.5 * 2.0
        passed_spike, _, score_spike, msg_spike = self.strategy.validate_layer_3_volatility(df)
        self.assertFalse(passed_spike)
        self.assertEqual(score_spike, 0)
        self.assertIn("news spike", msg_spike)

    def test_layer_4_session_gate(self):
        """Layer 4: London/NY active window (07-20 UTC) passes, Asian rollover rejects."""
        # 14:00 UTC (NY Session)
        t_active = datetime.datetime(2026, 9, 4, 14, 30, 0, tzinfo=datetime.timezone.utc)
        passed_act, score_act, _ = self.strategy.validate_layer_4_session(t_active)
        self.assertTrue(passed_act)
        self.assertEqual(score_act, 20)

        # 23:00 UTC (Rollover / Dead zone)
        t_dead = datetime.datetime(2026, 9, 4, 23, 15, 0, tzinfo=datetime.timezone.utc)
        passed_dead, score_dead, msg_dead = self.strategy.validate_layer_4_session(t_dead)
        self.assertFalse(passed_dead)
        self.assertEqual(score_dead, 0)
        self.assertIn("Low-liquidity window", msg_dead)

    def test_layer_5_spread_gate(self):
        """Layer 5: Spread <= 35 points passes, wider spread rejects."""
        passed_ok, score_ok, _ = self.strategy.validate_layer_5_spread(22)
        self.assertTrue(passed_ok)
        self.assertEqual(score_ok, 20)

        passed_wide, score_wide, msg_wide = self.strategy.validate_layer_5_spread(45)
        self.assertFalse(passed_wide)
        self.assertEqual(score_wide, 0)
        self.assertIn("exceeds scalping limit", msg_wide)

    def test_mode_1_vs_mode_2_multipliers(self):
        """Verifies Mode 1 (1.5x SL, 2.5x TP) vs Mode 2 (1.0x SL, 1.5x TP) scaling."""
        strat_mode1 = TwisterProStrategy(self.config)
        self.assertEqual(strat_mode1.atr_sl_multiplier, 1.5)
        self.assertEqual(strat_mode1.atr_tp_multiplier, 2.5)

        cfg_mode2 = dict(self.config)
        cfg_mode2["twister_strategy"] = dict(self.config["twister_strategy"])
        cfg_mode2["twister_strategy"]["mode"] = "MODE_2"
        strat_mode2 = TwisterProStrategy(cfg_mode2)
        self.assertEqual(strat_mode2.atr_sl_multiplier, 1.0)
        self.assertEqual(strat_mode2.atr_tp_multiplier, 1.5)

    def test_generate_signal_end_to_end(self):
        """End-to-end signal generation for valid high-conviction BUY setup."""
        df = create_synthetic_m15_df(trend="BULLISH", count=60)
        df = self.strategy.calculate_indicators(df)
        df.loc[df.index[-2], "rsi"] = 62.0
        df.loc[df.index[-2], "atr"] = 2.0
        # Swing high breakout across full lookback window
        lookback_start = -(self.strategy.swing_lookback_bars + 2)
        df.iloc[lookback_start:-2, df.columns.get_loc("high")] = 2570.0
        df.iloc[-2, df.columns.get_loc("close")] = 2575.0
        df.iloc[-2, df.columns.get_loc("high")] = 2576.0
        df.iloc[-2, df.columns.get_loc("low")] = 2574.0

        # Mock fetch_rates
        self.strategy.fetch_rates = lambda sym, tf, count=100: df

        # Session time at 15:00 UTC
        now_utc = datetime.datetime(2026, 9, 4, 15, 0, 0, tzinfo=datetime.timezone.utc)
        sig, entry, sl, tp, cid, zid, score, reason = self.strategy.generate_signal(
            "XAUUSDm", current_spread=25, now_utc=now_utc
        )

        self.assertEqual(sig, "BUY")
        self.assertEqual(score, 100) # All 5 layers passed (20 * 5)
        self.assertEqual(entry, 2575.0)
        # Scalp bounds clamp Gold SL between $1.00 and $2.20
        self.assertEqual(sl, 2575.0 - 2.20)
        # TP calculated from clamped SL distance and ratio
        self.assertAlmostEqual(tp, 2575.0 + (2.20 * (2.5 / 1.5)), places=2)
        self.assertTrue(cid.startswith("TWISTER_XAUUSDm_M15_"))

    def test_traded_candle_deduplication(self):
        """Ensures candle ID is rejected if already in traded_candle_ids."""
        df = create_synthetic_m15_df(trend="BULLISH", count=60)
        df = self.strategy.calculate_indicators(df)
        curr_time = df.iloc[-2]["time"]
        c_time_str = curr_time.strftime("%Y%m%d_%H%M")
        expected_cid = f"TWISTER_XAUUSDm_M15_{c_time_str}"

        self.strategy.fetch_rates = lambda sym, tf, count=100: df
        traded_ids = {expected_cid}

        sig, _, _, _, _, _, _, reason = self.strategy.generate_signal(
            "XAUUSDm", traded_candle_ids=traded_ids, current_spread=20
        )
        self.assertIsNone(sig)
        self.assertIn("already executed", reason)


if __name__ == "__main__":
    unittest.main()
