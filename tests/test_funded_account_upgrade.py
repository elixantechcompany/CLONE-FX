"""
Comprehensive Automated Test Suite for Funded Account Bot Upgrade
Tests all Directives:
  1. Large Loss Pre-Trade Rejection (Potential loss >= $5.50 strictly rejected).
  2. Daily Loss State Progression (-$15 Warning, -$20 Reduced Risk, -$25 Hard Stop).
  3. Daily Profit Target Lifecycle (+$30 Protection, +$40 High Selectivity, +$50 Target Stop).
  4. Winner Giveback Protection (+2.0R peak protected from becoming a loss).
  5. Timeframe-Isolated Early Invalidation Exits (Scalper M1/M5 vs Musumali M30/H1).
  6. Multi-Symbol Independent Sizing (XAUUSD vs BTCUSD).
  7. Multi-Account Full Isolation (Account A vs Account B).
  8. Portfolio Signal Conviction Ranking (Setup prioritization).
  9. Consecutive Losses Isolation (Account, Engine, Symbol).
  10. No Martingale / Recovery lot sizing.
"""

import unittest
import time
import os
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
                spread=100,
            ),
        }

    def is_connected(self) -> bool:
        return True

    def get_symbol_specs(self, symbol: str):
        return self.specs.get(symbol, self.specs["XAUUSDm"])


def create_dummy_df(num_bars=30, start_price=2650.0, trend="bullish") -> pd.DataFrame:
    records = []
    curr = start_price
    t0 = 1700000000
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
        else:
            open_p = curr
            close_p = curr + (0.2 if i % 2 == 0 else -0.2)
            high_p = max(open_p, close_p) + 0.1
            low_p = min(open_p, close_p) - 0.1
            curr = close_p

        records.append({
            "time": t0 + i * 60,
            "open": open_p,
            "high": high_p,
            "low": low_p,
            "close": close_p,
            "tick_volume": 100,
        })
    df = pd.DataFrame(records)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df


class TestFundedAccountUpgrade(unittest.TestCase):
    def setUp(self):
        # Remove any cached HWM files for account_1
        hwm_file = "data/hwm_account_1.json"
        if os.path.exists(hwm_file):
            try:
                os.remove(hwm_file)
            except Exception:
                pass

        self.config = {
            "funded_account": {
                "initial_account_size_dollars": 1000.0,
                "firm_daily_drawdown_limit_dollars": 30.0,
                "firm_trailing_max_drawdown_dollars": 60.0,
                "challenge_target_profit_dollars": 100.0,
                "internal_daily_warning_dollars": 15.0,
                "internal_daily_reduced_risk_dollars": 20.0,
                "internal_daily_hard_stop_dollars": 25.0,
                "internal_trailing_warning_dollars": 30.0,
                "internal_trailing_reduced_risk_dollars": 40.0,
                "internal_trailing_hard_stop_dollars": 50.0,
                "max_single_trade_risk_dollars": 5.00,
                "preferred_risk_min_dollars": 2.50,
                "preferred_risk_max_dollars": 5.00,
                "single_trade_hard_reject_dollars": 5.50,
                "daily_profit_objective_min": 30.0,
                "daily_profit_objective_selective": 40.0,
                "daily_profit_objective_max": 50.0,
            },
            "personal_account": {
                "initial_account_size_dollars": 20.0,
                "max_single_trade_risk_dollars": 0.50,
                "single_trade_hard_reject_dollars": 1.00,
                "daily_drawdown_limit_dollars": 3.00,
                "daily_profit_objective_dollars": 2.00,
            },
            "profit_management": {
                "breakeven_trigger_r": 0.50,
                "breakeven_lock_r": 0.10,
                "tier1_protect_trigger_r": 1.00,
                "tier1_protect_lock_r": 0.50,
                "tier2_protect_trigger_r": 1.50,
                "tier2_protect_lock_r": 1.00,
                "tier3_protect_trigger_r": 2.00,
                "tier3_protect_lock_r": 1.50,
                "reversal_exit_threshold": 70,
                "giveback_min_peak_r": 0.80,
                "giveback_max_r_decay": 0.35,
                "scalp_timeout_bars": 12,
                "musumali_timeout_bars": 20,
            },
            "risk_management": {
                "risk_per_trade_percent": 0.40,
                "max_daily_trades": 12,
                "slippage_points": 30,
                "session_filter_enabled": False,
                "consecutive_losses": {
                    "caution_threshold": 2,
                    "reduce_risk_threshold": 3,
                    "restrict_trading_threshold": 4,
                    "pause_module_threshold": 5,
                    "module_cooldown_minutes": 30,
                }
            },
            "circuit_breakers": {
                "high_water_giveback_protection": {
                    "enabled": True,
                    "min_profit_to_arm_dollars": 25.0,
                    "max_giveback_pct_of_peak": 35.0,
                }
            },
            "harmony_rules": {
                "cooldown_seconds_per_trade": 0,
            },
            "symbols": {
                "active_symbols": ["XAUUSD", "BTCUSD"],
                "symbol_settings": {
                    "XAUUSDm": {"max_spread_points": 320},
                    "BTCUSDm": {"max_spread_points": 2500},
                }
            },
            "m1_scalper": {"magic_number": 1001},
            "musumali_strategy": {"magic_number": 2001},
        }

        self.mock_connector = MockConnector()
        self.risk_mgr = RiskManager(self.config, self.mock_connector, "account_1")
        self.exit_engine = IntelligentExitEngine(self.config)
        self.risk_mgr.reset_daily_metrics_if_needed(1000.0)

    # TEST 1: Large Loss Pre-Trade Rejection
    def test_large_loss_pre_trade_rejection(self):
        self.risk_mgr.reset_daily_metrics_if_needed(1000.0)
        passed, failures, expected_loss = self.risk_mgr.pre_trade_risk_check(
            symbol="XAUUSDm",
            engine_magic=1001,
            order_type="BUY",
            entry_price=2650.0,
            stop_loss_price=2640.0,
            take_profit_price=2670.0,
            volume=1.0,
            quality_score=80,
            all_open_positions=[],
            equity=1000.0,
            free_margin=1000.0,
            candle_id="SCALP_BUY_M1_test",
            traded_candle_ids=set(),
            last_trade_time=0.0,
        )
        self.assertFalse(passed, "Trade with potential loss >= $5.50 must be strictly rejected")
        self.assertTrue(any("exceeds hard reject limit" in f or "Check 20" in f for f in failures))

    # TEST 2: Daily Loss State Progression
    def test_daily_loss_states_progression(self):
        self.risk_mgr.reset_daily_metrics_if_needed(1000.0)
        self.risk_mgr.lifetime_high_water_equity = 1000.0

        # 1. -$10: NORMAL
        can_trade, reason = self.risk_mgr.check_circuit_breakers(current_equity=990.0)
        self.assertTrue(can_trade)
        self.assertEqual(self.risk_mgr.trading_state, "NORMAL")
        self.assertEqual(self.risk_mgr.risk_reduction_multiplier, 1.0)

        # 2. -$16: WARNING
        can_trade, reason = self.risk_mgr.check_circuit_breakers(current_equity=984.0)
        self.assertTrue(can_trade)
        self.assertEqual(self.risk_mgr.trading_state, "WARNING")
        self.assertEqual(self.risk_mgr.risk_reduction_multiplier, 0.70)

        # 3. -$21: REDUCED_RISK
        can_trade, reason = self.risk_mgr.check_circuit_breakers(current_equity=979.0)
        self.assertTrue(can_trade)
        self.assertEqual(self.risk_mgr.trading_state, "REDUCED_RISK")
        self.assertEqual(self.risk_mgr.risk_reduction_multiplier, 0.40)

        # 4. -$26: DAILY_HARD_STOP
        can_trade, reason = self.risk_mgr.check_circuit_breakers(current_equity=974.0)
        self.assertFalse(can_trade, "Trading must be halted at -$26 daily loss")
        self.assertEqual(self.risk_mgr.trading_state, "DAILY_HARD_STOP")
        self.assertTrue(self.risk_mgr.circuit_tripped)

    # TEST 3: Daily Profit Target Lifecycle
    def test_daily_profit_target_lifecycle(self):
        self.risk_mgr.reset_daily_metrics_if_needed(1000.0)
        self.risk_mgr.lifetime_high_water_equity = 1000.0

        # 1. +$20: NORMAL
        can_trade, reason = self.risk_mgr.check_circuit_breakers(current_equity=1020.0)
        self.assertTrue(can_trade)
        self.assertEqual(self.risk_mgr.trading_state, "NORMAL")

        # 2. +$30: PROFIT_PROTECTION
        can_trade, reason = self.risk_mgr.check_circuit_breakers(current_equity=1030.0)
        self.assertTrue(can_trade)
        self.assertEqual(self.risk_mgr.trading_state, "PROFIT_PROTECTION")

        # 3. +$40: HIGH_SELECTIVITY
        can_trade, reason = self.risk_mgr.check_circuit_breakers(current_equity=1040.0)
        self.assertTrue(can_trade)
        self.assertEqual(self.risk_mgr.trading_state, "HIGH_SELECTIVITY")

        # 4. +$50: TARGET_REACHED
        can_trade, reason = self.risk_mgr.check_circuit_breakers(current_equity=1050.0)
        self.assertFalse(can_trade, "New entries must stop once +$50 daily target reached")
        self.assertEqual(self.risk_mgr.trading_state, "TARGET_REACHED")

    # TEST 4: Winner Giveback Guardian
    def test_winner_giveback_guardian(self):
        rec = self.exit_engine.register_position(
            ticket=5001,
            symbol="XAUUSDm",
            pos_type="BUY",
            volume=0.05,
            open_price=2650.0,
            sl=2647.0,
            tp=2659.0,
            magic=1001,
        )
        rec.peak_r = 2.0

        pos_dict = {
            "ticket": 5001,
            "symbol": "XAUUSDm",
            "type": "BUY",
            "volume": 0.05,
            "price_open": 2650.0,
            "price_current": 2654.20,
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
        self.assertEqual(decision, ExitDecision.CLOSE_MARKET)
        self.assertTrue("GIVEBACK" in reason or "REVERSAL" in reason)

    # TEST 5: Timeframe Isolation
    def test_scalper_vs_musumali_timeframe_isolation(self):
        self.exit_engine.register_position(
            ticket=6001, symbol="XAUUSDm", pos_type="BUY", volume=0.02,
            open_price=2650.0, sl=2648.0, tp=2656.0, magic=1001
        )
        self.exit_engine.records[6001].bars_held = 3  # Mature position
        self.exit_engine.register_position(
            ticket=6002, symbol="XAUUSDm", pos_type="BUY", volume=0.02,
            open_price=2650.0, sl=2645.0, tp=2660.0, magic=2001,
            thesis_anchor=2646.0,
        )

        df_m1_bear = create_dummy_df(30, start_price=2660.0, trend="bearish")
        df_m5_bear = create_dummy_df(30, start_price=2660.0, trend="bearish")
        df_m30_bull = create_dummy_df(30, start_price=2650.0, trend="bullish")
        df_h1_bull = create_dummy_df(30, start_price=2650.0, trend="bullish")
        live_tick = MockTick(bid=2645.0, ask=2645.3)

        scalp_dict = {
            "ticket": 6001, "symbol": "XAUUSDm", "type": "BUY", "volume": 0.02,
            "price_open": 2650.0, "price_current": 2649.50, "sl": 2648.0, "tp": 2656.0, "profit": -1.0, "magic": 1001
        }
        dec_s, _, _ = self.exit_engine.evaluate_position_lifecycle(
            pos_dict=scalp_dict, df_m1=df_m1_bear, df_m5=df_m5_bear, df_m30=df_m30_bull, df_h1=df_h1_bull,
            live_tick=live_tick, live_atr=2.0, digits=2
        )
        self.assertEqual(dec_s, ExitDecision.CLOSE_MARKET)

        musu_dict = {
            "ticket": 6002, "symbol": "XAUUSDm", "type": "BUY", "volume": 0.02,
            "price_open": 2650.0, "price_current": 2649.50, "sl": 2645.0, "tp": 2660.0, "profit": -1.0, "magic": 2001
        }
        dec_m, _, _ = self.exit_engine.evaluate_position_lifecycle(
            pos_dict=musu_dict, df_m1=df_m1_bear, df_m5=df_m5_bear, df_m30=df_m30_bull, df_h1=df_h1_bull,
            live_tick=live_tick, live_atr=2.0, digits=2
        )
        self.assertEqual(dec_m, ExitDecision.HOLD)

    # TEST 6: Multi-Symbol Independent Sizing
    def test_multi_symbol_independent_sizing(self):
        gold_lots = self.risk_mgr.calculate_lot_size(
            symbol="XAUUSDm",
            entry_price=2650.0,
            stop_loss_price=2647.0,
            equity=1000.0,
        )
        btc_lots = self.risk_mgr.calculate_lot_size(
            symbol="BTCUSDm",
            entry_price=65000.0,
            stop_loss_price=64700.0,
            equity=1000.0,
        )
        self.assertGreater(gold_lots, 0.0)
        self.assertGreater(btc_lots, 0.0)
        gold_loss = self.risk_mgr.calculate_monetary_loss("XAUUSDm", 2650.0, 2647.0, gold_lots)
        btc_loss = self.risk_mgr.calculate_monetary_loss("BTCUSDm", 65000.0, 64700.0, btc_lots)
        self.assertLessEqual(gold_loss, 5.50)
        self.assertLessEqual(btc_loss, 5.50)

    # TEST 7: Multi-Account Full Isolation
    def test_multi_account_full_isolation(self):
        acc1 = AccountContext("account_a", "Account A", 1111, "p1", "s1", self.config, 1000.0)
        acc2 = AccountContext("account_b", "Account B", 2222, "p2", "s2", self.config, 1000.0)
        acc1.risk_manager = RiskManager(self.config, self.mock_connector, "account_a")
        acc2.risk_manager = RiskManager(self.config, self.mock_connector, "account_b")
        acc1.risk_manager.reset_daily_metrics_if_needed(1000.0)
        acc2.risk_manager.reset_daily_metrics_if_needed(1000.0)

        # Account 1 takes $21 loss -> REDUCED_RISK
        acc1.risk_manager.record_trade_result(None, profit=-21.0, magic=1001, symbol="XAUUSDm")
        acc1.risk_manager.check_circuit_breakers(current_equity=979.0)

        # Account 2 takes +$20 win -> NORMAL
        acc2.risk_manager.record_trade_result(None, profit=20.0, magic=1001, symbol="XAUUSDm")
        acc2.risk_manager.check_circuit_breakers(current_equity=1020.0)

        self.assertEqual(acc1.risk_manager.trading_state, "REDUCED_RISK")
        self.assertEqual(acc1.risk_manager.risk_reduction_multiplier, 0.40)

        self.assertEqual(acc2.risk_manager.trading_state, "NORMAL")
        self.assertEqual(acc2.risk_manager.risk_reduction_multiplier, 1.0)

    # TEST 8: Signal Conviction Ranking
    def test_signal_conviction_ranking(self):
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
        self.assertEqual(ranked[0].symbol, "XAUUSDm")
        self.assertGreater(ranked[0].conviction_score, ranked[1].conviction_score)

    # TEST 9: Consecutive Losses Isolation
    def test_consecutive_losses_isolation(self):
        for _ in range(5):
            self.risk_mgr.record_trade_result(None, profit=-2.0, magic=1001, symbol="XAUUSDm")

        in_s_cd, _ = self.risk_mgr.is_engine_in_cooldown(1001)
        in_m_cd, _ = self.risk_mgr.is_engine_in_cooldown(2001)

        self.assertTrue(in_s_cd)
        self.assertFalse(in_m_cd)

    # TEST 10: No Martingale Verification
    def test_no_martingale_verification(self):
        initial_lots = self.risk_mgr.calculate_lot_size("XAUUSDm", 2650.0, 2647.0, 1000.0)
        for _ in range(3):
            self.risk_mgr.record_trade_result(None, profit=-10.0, magic=1001, symbol="XAUUSDm")
        self.risk_mgr.check_circuit_breakers(current_equity=970.0)

        post_loss_lots = self.risk_mgr.calculate_lot_size("XAUUSDm", 2650.0, 2647.0, 970.0)
        self.assertLessEqual(post_loss_lots, initial_lots)


if __name__ == "__main__":
    unittest.main()
