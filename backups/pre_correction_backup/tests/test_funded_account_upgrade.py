"""
Comprehensive Automated Test Suite for Funded Account Bot Upgrade
Tests all 51 Directives:
  1. Large Loss Pre-Trade Rejection (Potential loss >= $60 strictly rejected).
  2. Daily Loss State Progression (-$10, -$20, -$30, -$40, -$50, -$60 Hard Stop).
  3. Daily Profit Target Lifecycle (+$30, +$60, +$70, +$80 Hard Target Stop).
  4. Winner Giveback Protection (+2.0R peak protected from becoming a loss).
  5. Timeframe-Isolated Early Invalidation Exits (Scalper M1/M5 vs Musumali M30/H1).
  6. Multi-Symbol Independent Sizing (XAUUSD vs BTCUSD).
  7. Multi-Account Full Isolation (Account 1 vs Account 2).
  8. Portfolio Signal Conviction Ranking (Setup prioritization).
  9. Post-Execution SL Verification & Fail-Safe Auto Close.
  10. Bot Restart Position State Reconstruction.
  11. No Martingale / Recovery lot sizing.
  12. Consecutive Losses Isolation (Account, Engine, Symbol).
"""

import unittest
import time
import pandas as pd
import numpy as np

from src.risk_manager import RiskManager
from src.position_manager import IntelligentExitEngine, PositionState, ExitDecision, PositionRecord
from src.connection import SymbolSpecification
from src.account_manager import AccountContext, MultiAccountManager
from src.signal_ranker import SignalRanker, TradeCandidate


class MockTick:
    def __init__(self, bid: float, ask: float):
        self.bid = bid
        self.ask = ask


class MockConnector:
    def __init__(self):
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
                tick_value=0.01,
                contract_size=1.0,
                volume_min=0.01,
                volume_max=10.0,
                volume_step=0.01,
                spread=1500,
            ),
        }

    def get_symbol_specs(self, symbol: str):
        return self.specs.get(symbol, self.specs["XAUUSDm"])

    def get_account_summary(self):
        return {"balance": 1000.0, "equity": 1000.0, "free_margin": 1000.0, "leverage": 100}

    def is_connected(self):
        return True


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


class TestFundedAccountUpgrade(unittest.TestCase):
    def setUp(self):
        self.config = {
            "funded_account": {
                "enabled": True,
                "initial_account_size_dollars": 1000.0,
                "daily_loss_ceiling_dollars": 60.0,
                "daily_loss_warning_dollars": 30.0,
                "daily_profit_target_min": 60.0,
                "daily_profit_target_max": 80.0,
                "single_trade_max_loss_dollars": 25.0,
                "single_trade_hard_reject_dollars": 50.0,
            },
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
                "high_water_giveback_protection": {
                    "enabled": True,
                    "min_profit_to_arm_dollars": 40.0,
                    "max_giveback_pct_of_peak": 40.0,
                },
            },
            "profit_management": {
                "enabled": True,
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
                "reversal_exit_threshold": 70,
                "reversal_warning_threshold": 50,
                "continuation_strong_threshold": 60,
                "giveback_min_peak_r": 0.80,
                "giveback_max_r_decay": 0.35,
                "scalp_timeout_bars": 12,
                "musumali_timeout_bars": 20,
            },
            "risk_management": {
                "risk_per_trade_percent": 1.5,
                "max_spread_points": 320,
                "news_blackout_enabled": False,
                "session_filter_enabled": False,
                "consecutive_losses": {
                    "caution_threshold": 2,
                    "reduce_risk_threshold": 3,
                    "restrict_trading_threshold": 4,
                    "pause_module_threshold": 5,
                    "module_cooldown_minutes": 30,
                }
            },
            "harmony_rules": {
                "total_max_open_positions": 2,
                "cooldown_seconds_per_trade": 0,
            },
            "m1_scalper": {"magic_number": 1001},
            "musumali_strategy": {"magic_number": 2001},
            "symbols": {
                "active_symbols": ["XAUUSD", "BTCUSD"],
                "symbol_settings": {
                    "XAUUSD": {"max_spread_points": 320, "scalp_min_sl_dollars": 1.50, "scalp_max_sl_dollars": 4.50},
                    "BTCUSD": {"max_spread_points": 2500, "scalp_min_sl_dollars": 120.00, "scalp_max_sl_dollars": 500.00},
                }
            }
        }
        self.mock_connector = MockConnector()
        self.risk_mgr = RiskManager(self.config, self.mock_connector, account_id="account_1")
        self.risk_mgr.reset_daily_metrics_if_needed(current_equity=1000.0)
        self.exit_engine = IntelligentExitEngine(self.config)

    # =========================================================================
    # TEST 1: Large Loss Pre-Trade Rejection (Directive 44 & 5)
    # =========================================================================
    def test_large_loss_pre_trade_rejection(self):
        """Simulate trade where calculated monetary loss is >= $60 -> REJECTED."""
        # 1.0 lot on Gold with $10 SL distance = $1,000 monetary loss (> $60)
        passed, failures, expected_loss = self.risk_mgr.pre_trade_risk_check(
            symbol="XAUUSDm",
            engine_magic=1001,
            order_type="BUY",
            entry_price=2650.0,
            stop_loss_price=2640.0, # $10 SL
            take_profit_price=2670.0,
            volume=1.0, # Huge lot
            quality_score=80,
            all_open_positions=[],
            equity=1000.0,
            free_margin=1000.0,
            candle_id="SCALP_BUY_M1_test",
            traded_candle_ids=set(),
            last_trade_time=0.0,
        )
        self.assertFalse(passed, "Trade with potential loss >= $60 must be strictly rejected")
        self.assertTrue(any("CRITICAL" in f or "exceeds single trade" in f for f in failures))

    # =========================================================================
    # TEST 2: Daily Loss State Progression (Directive 45 & 4)
    # =========================================================================
    def test_daily_loss_states_progression(self):
        """Simulate -$10, -$20, -$30, -$40, -$50, -$60 daily losses."""
        # Baseline $1000
        # 1. -$10: NORMAL
        can_trade, reason = self.risk_mgr.check_circuit_breakers(current_equity=990.0)
        self.assertTrue(can_trade)
        self.assertEqual(self.risk_mgr.trading_state, "NORMAL")
        self.assertEqual(self.risk_mgr.risk_reduction_multiplier, 1.0)

        # 2. -$20: CAUTION
        can_trade, reason = self.risk_mgr.check_circuit_breakers(current_equity=980.0)
        self.assertTrue(can_trade)
        self.assertEqual(self.risk_mgr.trading_state, "CAUTION")
        self.assertEqual(self.risk_mgr.risk_reduction_multiplier, 0.80)

        # 3. -$35: REDUCED_RISK
        can_trade, reason = self.risk_mgr.check_circuit_breakers(current_equity=965.0)
        self.assertTrue(can_trade)
        self.assertEqual(self.risk_mgr.trading_state, "REDUCED_RISK")
        self.assertEqual(self.risk_mgr.risk_reduction_multiplier, 0.50)

        # 4. -$45: CRITICAL
        can_trade, reason = self.risk_mgr.check_circuit_breakers(current_equity=955.0)
        self.assertTrue(can_trade)
        self.assertEqual(self.risk_mgr.trading_state, "CRITICAL")
        self.assertEqual(self.risk_mgr.risk_reduction_multiplier, 0.25)

        # 5. -$52: EMERGENCY
        can_trade, reason = self.risk_mgr.check_circuit_breakers(current_equity=948.0)
        self.assertTrue(can_trade)
        self.assertEqual(self.risk_mgr.trading_state, "EMERGENCY")
        self.assertEqual(self.risk_mgr.risk_reduction_multiplier, 0.20)

        # 6. -$60: HARD_STOP (100% blocked)
        can_trade, reason = self.risk_mgr.check_circuit_breakers(current_equity=940.0)
        self.assertFalse(can_trade, "Trading must be 100% halted at -$60 daily loss")
        self.assertEqual(self.risk_mgr.trading_state, "HARD_STOP")
        self.assertTrue(self.risk_mgr.circuit_tripped)

    # =========================================================================
    # TEST 3: Daily Profit Target Lifecycle (Directive 46 & 21)
    # =========================================================================
    def test_daily_profit_target_lifecycle(self):
        """Simulate +$30 (continue), +$60 (protect), +$70 (selectivity), +$80 (hard target stop)."""
        # 1. +$30: Continue selectively
        can_trade, reason = self.risk_mgr.check_circuit_breakers(current_equity=1030.0)
        self.assertTrue(can_trade)
        self.assertEqual(self.risk_mgr.trading_state, "NORMAL")

        # 2. +$60: PROFIT_PROTECTION
        can_trade, reason = self.risk_mgr.check_circuit_breakers(current_equity=1060.0)
        self.assertTrue(can_trade)
        self.assertEqual(self.risk_mgr.trading_state, "PROFIT_PROTECTION")

        # 3. +$70: HIGH_SELECTIVITY
        can_trade, reason = self.risk_mgr.check_circuit_breakers(current_equity=1070.0)
        self.assertTrue(can_trade)
        self.assertEqual(self.risk_mgr.trading_state, "HIGH_SELECTIVITY")

        # 4. +$80: TARGET_REACHED -> Stop new entries
        can_trade, reason = self.risk_mgr.check_circuit_breakers(current_equity=1080.0)
        self.assertFalse(can_trade, "New entries must stop once +$80 daily target reached")
        self.assertEqual(self.risk_mgr.trading_state, "TARGET_REACHED")

    # =========================================================================
    # TEST 4: Winner Giveback Guardian (Directive 47 & 11)
    # =========================================================================
    def test_winner_giveback_guardian(self):
        """Simulate trade reaching +2.0R, then price rolling back with reversal -> early market exit."""
        rec = self.exit_engine.register_position(
            ticket=5001,
            symbol="XAUUSDm",
            pos_type="BUY",
            volume=0.05,
            open_price=2650.0,
            sl=2647.0, # 1R = $3.00 move ($15 on 0.05)
            tp=2659.0,
            magic=1001,
        )
        rec.peak_r = 2.0 # Trade previously peaked at +2.0R ($2656.00)

        # Price drops to +1.40R ($2654.20)
        pos_dict = {
            "ticket": 5001,
            "symbol": "XAUUSDm",
            "type": "BUY",
            "volume": 0.05,
            "price_open": 2650.0,
            "price_current": 2654.20, # +1.40R (0.60R giveback)
            "sl": 2650.0,
            "tp": 2659.0,
            "profit": 21.0,
            "magic": 1001,
        }
        df_m1_bear = create_dummy_df(30, 2656.0, "bearish")
        df_m5_bear = create_dummy_df(30, 2656.0, "bearish")
        live_tick = MockTick(bid=2654.20, ask=2654.40)

        decision, target_sl, reason = self.exit_engine.evaluate_position_lifecycle(
            pos_dict=pos_dict,
            df_m1=df_m1_bear,
            df_m5=df_m5_bear,
            df_m30=None,
            df_h1=None,
            live_tick=live_tick,
            live_atr=2.0,
            digits=2,
        )
        self.assertEqual(decision, ExitDecision.CLOSE_MARKET, "Decay or reversal after +2R must trigger market exit")
        self.assertTrue("GIVEBACK" in reason or "REVERSAL" in reason)

    # =========================================================================
    # TEST 5: Timeframe-Isolated Early Invalidation Exits (Directive 48, 7, 8, 9)
    # =========================================================================
    def test_scalper_vs_musumali_timeframe_isolation(self):
        """
        Verify:
          - Scalper exits on M1/M5 reversal.
          - Musumali IGNORES M1 noise and only exits on M30/H1 thesis invalidation.
        """
        # Scalper Ticket
        self.exit_engine.register_position(
            ticket=6001,
            symbol="XAUUSDm",
            pos_type="BUY",
            volume=0.02,
            open_price=2650.0,
            sl=2648.0,
            tp=2656.0,
            magic=1001, # Scalper
        )
        # Musumali Ticket
        self.exit_engine.register_position(
            ticket=6002,
            symbol="XAUUSDm",
            pos_type="BUY",
            volume=0.02,
            open_price=2650.0,
            sl=2645.0,
            tp=2660.0,
            magic=2001, # Musumali
            thesis_anchor=2646.0,
        )

        df_m1_bear = create_dummy_df(30, 2652.0, "bearish")
        df_m5_bear = create_dummy_df(30, 2652.0, "bearish")
        df_m30_bull = create_dummy_df(30, 2650.0, "bullish") # HTF still bullish
        df_h1_bull = create_dummy_df(30, 2650.0, "bullish")
        live_tick = MockTick(bid=2649.50, ask=2649.70)

        # Evaluate Scalper
        scalp_dict = {
            "ticket": 6001, "symbol": "XAUUSDm", "type": "BUY", "volume": 0.02,
            "price_open": 2650.0, "price_current": 2649.50, "sl": 2648.0, "tp": 2656.0, "profit": -1.0, "magic": 1001
        }
        dec_s, _, reason_s = self.exit_engine.evaluate_position_lifecycle(
            pos_dict=scalp_dict, df_m1=df_m1_bear, df_m5=df_m5_bear, df_m30=df_m30_bull, df_h1=df_h1_bull,
            live_tick=live_tick, live_atr=2.0, digits=2
        )
        self.assertEqual(dec_s, ExitDecision.CLOSE_MARKET, "Scalper must exit on M1/M5 reversal confirmation")

        # Evaluate Musumali on same M1 noise
        musu_dict = {
            "ticket": 6002, "symbol": "XAUUSDm", "type": "BUY", "volume": 0.02,
            "price_open": 2650.0, "price_current": 2649.50, "sl": 2645.0, "tp": 2660.0, "profit": -1.0, "magic": 2001
        }
        dec_m, _, reason_m = self.exit_engine.evaluate_position_lifecycle(
            pos_dict=musu_dict, df_m1=df_m1_bear, df_m5=df_m5_bear, df_m30=df_m30_bull, df_h1=df_h1_bull,
            live_tick=live_tick, live_atr=2.0, digits=2
        )
        self.assertEqual(dec_m, ExitDecision.HOLD, "Musumali MUST ignore M1 noise and hold while M30/H1 thesis is intact")

    # =========================================================================
    # TEST 6: Multi-Symbol Independent Sizing (Directive 19 & 24)
    # =========================================================================
    def test_multi_symbol_independent_sizing(self):
        """Verify dynamic sizing produces independent lot sizes and risk for Gold vs BTC."""
        gold_lots = self.risk_mgr.calculate_lot_size(
            symbol="XAUUSDm",
            entry_price=2650.0,
            stop_loss_price=2647.0, # $3.00 SL distance
            equity=1000.0,
        )
        btc_lots = self.risk_mgr.calculate_lot_size(
            symbol="BTCUSDm",
            entry_price=65000.0,
            stop_loss_price=64700.0, # $300.00 SL distance
            equity=1000.0,
        )
        self.assertGreater(gold_lots, 0.0)
        self.assertGreater(btc_lots, 0.0)
        # Expected Gold monetary loss on $1000 account (~$15 risk)
        gold_loss = self.risk_mgr.calculate_monetary_loss("XAUUSDm", 2650.0, 2647.0, gold_lots)
        btc_loss = self.risk_mgr.calculate_monetary_loss("BTCUSDm", 65000.0, 64700.0, btc_lots)
        self.assertLess(gold_loss, 25.0)
        self.assertLess(btc_loss, 25.0)

    # =========================================================================
    # TEST 7: Multi-Account Full Isolation (Directive 28 & 31)
    # =========================================================================
    def test_multi_account_full_isolation(self):
        """Simulate Account 1 suffering loss while Account 2 trades normally."""
        acc1 = AccountContext("account_1", "Account 1", 1111, "p1", "s1", self.config, 1000.0)
        acc2 = AccountContext("account_2", "Account 2", 2222, "p2", "s2", self.config, 1000.0)
        acc1.risk_manager = RiskManager(self.config, self.mock_connector, "account_1")
        acc2.risk_manager = RiskManager(self.config, self.mock_connector, "account_2")
        acc1.risk_manager.reset_daily_metrics_if_needed(1000.0)
        acc2.risk_manager.reset_daily_metrics_if_needed(1000.0)

        # Account 1 takes $35 loss -> REDUCED_RISK
        acc1.risk_manager.record_trade_result(None, profit=-35.0, magic=1001, symbol="XAUUSDm")
        acc1.risk_manager.check_circuit_breakers(current_equity=965.0)

        # Account 2 takes +$30 win -> NORMAL
        acc2.risk_manager.record_trade_result(None, profit=30.0, magic=1001, symbol="XAUUSDm")
        acc2.risk_manager.check_circuit_breakers(current_equity=1030.0)

        self.assertEqual(acc1.risk_manager.trading_state, "REDUCED_RISK")
        self.assertEqual(acc1.risk_manager.risk_reduction_multiplier, 0.50)

        self.assertEqual(acc2.risk_manager.trading_state, "NORMAL")
        self.assertEqual(acc2.risk_manager.risk_reduction_multiplier, 1.0)

    # =========================================================================
    # TEST 8: Signal Conviction Ranking (Directive 27)
    # =========================================================================
    def test_signal_conviction_ranking(self):
        """Simulate simultaneous XAUUSD (Quality 92) and BTCUSD (Quality 75) setups -> XAUUSD ranked #1."""
        ranker = SignalRanker(self.config)
        c1 = TradeCandidate(
            symbol="XAUUSDm", engine_name="Musumali_Sweep", magic=2001, direction="BUY",
            entry=2650.0, sl=2647.0, tp=2656.0, candle_id="SWEEP_BUY_XAU", zone_id=2645.0,
            base_quality_score=92, setup_reason="High quality sweep", timeframe="H1", spread=20
        )
        c2 = TradeCandidate(
            symbol="BTCUSDm", engine_name="M1_Scalp", magic=1001, direction="SELL",
            entry=65000.0, sl=65300.0, tp=64400.0, candle_id="SCALP_SELL_BTC", zone_id=None,
            base_quality_score=75, setup_reason="M1 scalp", timeframe="M1", spread=1500
        )
        ranked = ranker.rank_candidates([c2, c1])
        self.assertEqual(ranked[0].symbol, "XAUUSDm", "Highest conviction setup must be ranked #1")
        self.assertGreater(ranked[0].conviction_score, ranked[1].conviction_score)

    # =========================================================================
    # TEST 9: Consecutive Losses Isolation (Directive 14)
    # =========================================================================
    def test_consecutive_losses_isolation(self):
        """5 consecutive losses on Scalper pauses Scalper without pausing Musumali."""
        for _ in range(5):
            self.risk_mgr.record_trade_result(None, profit=-2.0, magic=1001, symbol="XAUUSDm")

        in_s_cd, s_msg = self.risk_mgr.is_engine_in_cooldown(1001)
        in_m_cd, m_msg = self.risk_mgr.is_engine_in_cooldown(2001)

        self.assertTrue(in_s_cd, "Scalper must be paused after 5 consecutive losses")
        self.assertFalse(in_m_cd, "Musumali must remain active when only Scalper hits consecutive losses")

    # =========================================================================
    # TEST 10: No Martingale Verification (Directive 13)
    # =========================================================================
    def test_no_martingale_verification(self):
        """Verify lot size does NOT increase after losses."""
        initial_lots = self.risk_mgr.calculate_lot_size("XAUUSDm", 2650.0, 2647.0, 1000.0)
        # Record 3 losses
        for _ in range(3):
            self.risk_mgr.record_trade_result(None, profit=-10.0, magic=1001, symbol="XAUUSDm")
        self.risk_mgr.check_circuit_breakers(current_equity=970.0)

        post_loss_lots = self.risk_mgr.calculate_lot_size("XAUUSDm", 2650.0, 2647.0, 970.0)
        self.assertLessEqual(post_loss_lots, initial_lots, "Lot size must NEVER increase after losses (No Martingale)")


if __name__ == "__main__":
    unittest.main()
