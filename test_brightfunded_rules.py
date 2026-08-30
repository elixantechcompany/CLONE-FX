"""
Verification test suite for BrightFunded Free $1K Challenge Risk Engine
"""

import sys
import yaml
from unittest.mock import MagicMock
from src.risk_manager import RiskManager


def run_tests():
    print("==================================================================")
    print(" RUNNING BRIGHTFUNDED FREE $1K CHALLENGE RISK SUITE VERIFICATION")
    print("==================================================================")

    with open("config/config.yaml", "r") as f:
        config = yaml.safe_load(f)

    # Setup mock connector
    mock_connector = MagicMock()
    mock_connector.is_connected.return_value = True
    mock_connector.get_account_summary.return_value = {
        "balance": 1000.0,
        "equity": 1000.0,
        "free_margin": 1000.0,
        "leverage": 100,
    }

    # Gold specs
    gold_spec = MagicMock()
    gold_spec.volume_min = 0.01
    gold_spec.volume_max = 10.0
    gold_spec.volume_step = 0.01
    gold_spec.contract_size = 100.0
    gold_spec.tick_size = 0.01
    gold_spec.tick_value = 1.0
    gold_spec.point = 0.01
    gold_spec.spread = 20

    # BTC specs
    btc_spec = MagicMock()
    btc_spec.volume_min = 0.01
    btc_spec.volume_max = 10.0
    btc_spec.volume_step = 0.01
    btc_spec.contract_size = 1.0
    btc_spec.tick_size = 0.01
    btc_spec.tick_value = 1.0
    btc_spec.point = 0.01
    btc_spec.spread = 50

    def get_specs(sym):
        return btc_spec if "BTC" in sym else gold_spec

    mock_connector.get_symbol_specs.side_effect = get_specs

    rm = RiskManager(config, mock_connector, account_id="test_account")
    rm.reset_daily_metrics_if_needed(1000.0)

    # Test 1: Dynamic Lot Sizing on XAUUSD
    # Gold SL = $3.00 distance (e.g. entry 2500, SL 2497)
    lot_gold_85 = rm.calculate_lot_size("XAUUSD", 2500.0, 2497.0, 1000.0, quality_score=85)
    loss_gold_85 = rm.calculate_monetary_loss("XAUUSD", 2500.0, 2497.0, lot_gold_85)
    print(f"[TEST 1A] Gold (Score 85, SL $3): Lots = {lot_gold_85}, Expected Loss = ${loss_gold_85:.2f}")
    assert lot_gold_85 > 0.0, "Gold lot size must be > 0"
    assert loss_gold_85 <= 5.05, f"Gold loss must not exceed $5.00 max risk, got ${loss_gold_85:.2f}"

    lot_gold_55 = rm.calculate_lot_size("XAUUSD", 2500.0, 2497.0, 1000.0, quality_score=55)
    loss_gold_55 = rm.calculate_monetary_loss("XAUUSD", 2500.0, 2497.0, lot_gold_55)
    print(f"[TEST 1B] Gold (Score 55, SL $3): Lots = {lot_gold_55}, Expected Loss = ${loss_gold_55:.2f}")
    assert loss_gold_55 <= loss_gold_85, "Lower quality score must risk less or equal monetary risk"

    # Test 2: Dynamic Lot Sizing on BTCUSD
    # BTC SL = $250 distance (e.g. entry 65000, SL 64750)
    lot_btc_85 = rm.calculate_lot_size("BTCUSD", 65000.0, 64750.0, 1000.0, quality_score=85)
    loss_btc_85 = rm.calculate_monetary_loss("BTCUSD", 65000.0, 64750.0, lot_btc_85)
    print(f"[TEST 2A] BTC (Score 85, SL $250): Lots = {lot_btc_85}, Expected Loss = ${loss_btc_85:.2f}")
    assert lot_btc_85 > 0.0, "BTC lot size must be > 0"
    assert loss_btc_85 <= 5.05, f"BTC loss must not exceed $5.00 max risk, got ${loss_btc_85:.2f}"

    # Test 3: Excessive SL distance rejection
    # If SL on Gold is $20.00, 0.01 lot loss = $20.00 > $5.50 -> Must reject!
    lot_excess = rm.calculate_lot_size("XAUUSD", 2500.0, 2480.0, 1000.0, quality_score=90)
    print(f"[TEST 3] Excessive SL distance (SL $20): Lot result = {lot_excess}")
    assert lot_excess == 0.0, "Must return 0.0 lots for excessive SL width exceeding $5.50 ceiling"

    # Test 4: Daily Loss Circuit Breaker Ladder
    # Baseline: $1000
    # At $984 (-$16 loss) -> WARNING
    can_trade, reason = rm.check_circuit_breakers(984.0)
    print(f"[TEST 4A] Equity $984 (-$16): State = {rm.trading_state}, Can Trade = {can_trade}")
    assert rm.trading_state == "WARNING"
    assert can_trade is True

    # At $979 (-$21 loss) -> REDUCED_RISK
    can_trade, reason = rm.check_circuit_breakers(979.0)
    print(f"[TEST 4B] Equity $979 (-$21): State = {rm.trading_state}, Multiplier = {rm.risk_reduction_multiplier}")
    assert rm.trading_state == "REDUCED_RISK"
    assert rm.risk_reduction_multiplier <= 0.50

    # At $974 (-$26 loss) -> DAILY_HARD_STOP ($5 buffer preserved before $30 firm limit)
    can_trade, reason = rm.check_circuit_breakers(974.0)
    print(f"[TEST 4C] Equity $974 (-$26): State = {rm.trading_state}, Can Trade = {can_trade}")
    assert rm.trading_state == "DAILY_HARD_STOP"
    assert can_trade is False

    # Test 5: Trailing Maximum Drawdown Ladder (Firm: $60 | Internal: $50)
    rm2 = RiskManager(config, mock_connector, account_id="test_account_2")
    rm2.reset_daily_metrics_if_needed(1000.0)
    # Simulate equity peaked at $1040 (HWM = 1040)
    rm2.check_circuit_breakers(1040.0)
    assert rm2.lifetime_high_water_equity == 1040.0

    # Reset day starting at $1040
    rm2.current_day = None
    rm2.reset_daily_metrics_if_needed(1040.0)

    # Next day: drops to $1005 (Daily loss = -$35, Trailing drawdown from HWM = $35) -> Trailing Warning / Reduced
    can_trade, reason = rm2.check_circuit_breakers(1005.0)
    print(f"[TEST 5A] HWM $1040 -> Equity $1005 (DD $35): State = {rm2.trading_state}")

    # Drops to $985 (Trailing drawdown from HWM = $55 >= $50 internal stop) -> TRAILING_HARD_STOP
    can_trade, reason = rm2.check_circuit_breakers(985.0)
    print(f"[TEST 5B] HWM $1040 -> Equity $985 (DD $55): State = {rm2.trading_state}, Can Trade = {can_trade}")
    assert can_trade is False

    # Test 6: Challenge Goal Completion (+ $100)
    rm3 = RiskManager(config, mock_connector, account_id="test_account_3")
    rm3.reset_daily_metrics_if_needed(1000.0)
    can_trade, reason = rm3.check_circuit_breakers(1105.0)
    print(f"[TEST 6] Equity $1105 (+ $105): State = {rm3.trading_state}, Can Trade = {can_trade}")
    assert rm3.trading_state == "CHALLENGE_PASSED"
    assert can_trade is False

    print("==================================================================")
    print(" ALL BRIGHTFUNDED FREE $1K CHALLENGE TESTS PASSED PERFECTLY! [SUCCESS]")
    print("==================================================================")


if __name__ == "__main__":
    run_tests()
