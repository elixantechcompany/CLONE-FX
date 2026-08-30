"""
BrightFunded Free $1K Challenge Risk Management & Circuit Breaker Engine
Enforces:
  1. Challenge Objective: Pass $100 Profit Target ($1,100 Total Equity) without breaching firm limits.
  2. BrightFunded Firm Limits:
     - Daily Drawdown Limit: 3% = $30.00
     - Trailing Maximum Drawdown Limit: 6% = $60.00 (Dynamic from Lifetime High-Water Mark)
  3. Internal Multi-Tier Safety Buffers (Well below firm limits):
     - Daily Loss: Warning at -$15.00, Reduced-Risk at -$20.00, Internal Hard Stop at -$25.00 (~$5 safety buffer).
     - Trailing Max Drawdown: Warning at $30.00 from HWM, Reduced-Risk at $40.00 from HWM, Internal Hard Stop at $50.00 from HWM ($10 safety buffer).
  4. Individual Trade Risk:
     - Strictly DYNAMIC position sizing (Never fixed lots).
     - Normal maximum risk: ~$5.00.
     - Preferred risk range: $2.50 - $5.00 depending on quality score and account state.
     - Separate calculations for XAUUSD and BTCUSD with exact symbol specs (contract size, tick size, tick value, spread, slippage).
  5. Profit Management Lifecycle:
     - +$30.00: Activate profit protection (tighten stops, lock gains).
     - +$40.00: High selectivity mode (Score >= 80 only).
     - +$50.00: Daily target stop (protect the day's gains, stop opening new trades).
     - +$100.00: Challenge passed state lock.
  6. Zero Martingale / Zero Revenge Trading.
"""

import datetime
import logging
import os
import json
import time
from typing import Dict, List, Optional, Tuple, Any
import MetaTrader5 as mt5

logger = logging.getLogger("GoldBot.RiskManager")


class RiskManager:
    def __init__(self, config: dict, connector, account_id: str = "account_1"):
        self.config = config
        self.account_id = account_id
        self.connector = connector
        self.funded_cfg = config.get("funded_account", {})
        self.risk_config = config.get("risk_management", {})
        self.circuit_config = config.get("circuit_breakers", {})
        self.zone_config = config.get("zone_management", {})
        self.symbols_cfg = config.get("symbols", {})

        # BrightFunded $1K Challenge Specifications
        self.initial_account_size = float(self.funded_cfg.get("initial_account_size_dollars", 1000.0))
        self.challenge_target_profit = float(self.funded_cfg.get("challenge_target_profit_dollars", 100.0))
        self.firm_daily_limit = float(self.funded_cfg.get("firm_daily_drawdown_limit_dollars", 30.0))
        self.firm_trailing_limit = float(self.funded_cfg.get("firm_trailing_max_drawdown_dollars", 60.0))

        # Internal Multi-Tier Daily Loss Thresholds ($5 buffer below $30 limit)
        self.daily_warning_loss = float(self.funded_cfg.get("internal_daily_warning_dollars", 15.0))
        self.daily_reduced_risk_loss = float(self.funded_cfg.get("internal_daily_reduced_risk_dollars", 20.0))
        self.daily_hard_stop_loss = float(self.funded_cfg.get("internal_daily_hard_stop_dollars", 25.0))

        # Internal Multi-Tier Trailing Drawdown Thresholds ($10 buffer below $60 trailing limit)
        self.trailing_warning_drawdown = float(self.funded_cfg.get("internal_trailing_warning_dollars", 30.0))
        self.trailing_reduced_risk_drawdown = float(self.funded_cfg.get("internal_trailing_reduced_risk_dollars", 40.0))
        self.trailing_hard_stop_drawdown = float(self.funded_cfg.get("internal_trailing_hard_stop_dollars", 50.0))

        # Individual Trade Risk Bounds
        self.max_single_trade_risk = float(self.funded_cfg.get("max_single_trade_risk_dollars", 5.00))
        self.preferred_risk_min = float(self.funded_cfg.get("preferred_risk_min_dollars", 2.50))
        self.preferred_risk_max = float(self.funded_cfg.get("preferred_risk_max_dollars", 5.00))
        self.single_trade_hard_reject = float(self.funded_cfg.get("single_trade_hard_reject_dollars", 5.50))

        # Profit Management & Daily Objectives ($30 -> $40 -> $50 Lifecycle)
        self.profit_protect_trigger = float(self.funded_cfg.get("daily_profit_objective_min", 30.0))
        self.profit_high_selectivity_trigger = float(self.funded_cfg.get("daily_profit_objective_selective", 40.0))
        self.profit_target_stop = float(self.funded_cfg.get("daily_profit_objective_max", 50.0))

        # High-Water Mark Giveback Protection
        hwm_cfg = self.circuit_config.get("high_water_giveback_protection", {})
        self.hwm_protection_enabled = hwm_cfg.get("enabled", True)
        self.hwm_arm_profit = float(hwm_cfg.get("min_profit_to_arm_dollars", 25.0))
        self.hwm_max_giveback_pct = float(hwm_cfg.get("max_giveback_pct_of_peak", 35.0))

        # Daily baseline and state
        self.current_day: Optional[datetime.date] = None
        self.daily_start_equity: float = 0.0
        self.daily_high_water_equity: float = 0.0
        self.lifetime_high_water_equity: float = 1000.0
        self.daily_trade_count: int = 0
        self.circuit_tripped: bool = False
        self.trip_reason: str = ""
        self.trading_state: str = "NORMAL" # NORMAL, WARNING, REDUCED_RISK, DAILY_HARD_STOP, TRAILING_HARD_STOP, PROFIT_PROTECTION, HIGH_SELECTIVITY, TARGET_REACHED, CHALLENGE_PASSED
        self.risk_reduction_multiplier: float = 1.0

        # Persistence for Lifetime High-Water Mark
        self.hwm_file = f"data/hwm_{self.account_id}.json"
        self._load_lifetime_hwm()

        # Magic Numbers
        self.magic_scalper = config.get("m1_scalper", {}).get("magic_number", 1001)
        self.magic_musumali = config.get("musumali_strategy", {}).get("magic_number", 2001)

        # Multi-Dimensional Performance Tracking
        self.daily_pnl_by_engine: Dict[int, float] = {self.magic_scalper: 0.0, self.magic_musumali: 0.0}
        self.daily_trades_by_engine: Dict[int, int] = {self.magic_scalper: 0, self.magic_musumali: 0}
        self.daily_wins_by_engine: Dict[int, int] = {self.magic_scalper: 0, self.magic_musumali: 0}
        self.daily_pnl_by_symbol: Dict[str, float] = {}

        # Consecutive Losses Tracked by: Account, Engine, Symbol
        self.account_consecutive_losses: int = 0
        self.engine_consecutive_losses: Dict[int, int] = {self.magic_scalper: 0, self.magic_musumali: 0}
        self.symbol_consecutive_losses: Dict[str, int] = {}
        self.engine_cooldown_until: Dict[int, float] = {self.magic_scalper: 0.0, self.magic_musumali: 0.0}
        self.symbol_cooldown_until: Dict[str, float] = {}

        # Consecutive loss rules
        cl_cfg = self.risk_config.get("consecutive_losses", {})
        self.cl_caution_threshold = cl_cfg.get("caution_threshold", 2)
        self.cl_reduce_risk_threshold = cl_cfg.get("reduce_risk_threshold", 3)
        self.cl_restrict_threshold = cl_cfg.get("restrict_trading_threshold", 4)
        self.cl_pause_threshold = cl_cfg.get("pause_module_threshold", 5)
        self.cl_cooldown_seconds = cl_cfg.get("module_cooldown_minutes", 30) * 60.0

        # Liquidity Zone Failure Memory
        self.zone_failures: Dict[float, int] = {}
        self.zone_cooldown_until: Dict[float, float] = {}
        self.max_zone_failures = self.zone_config.get("max_zone_failures", 2)
        self.zone_cooldown_minutes = self.zone_config.get("zone_cooldown_minutes", 10)

        # Profit Analytics
        self.total_peak_r: float = 0.0
        self.total_captured_r: float = 0.0
        self.exit_reason_stats: Dict[str, dict] = {}

    def _load_lifetime_hwm(self):
        """Loads historical lifetime high-water mark for accurate trailing drawdown tracking."""
        try:
            if os.path.exists(self.hwm_file):
                with open(self.hwm_file, "r") as f:
                    data = json.load(f)
                    self.lifetime_high_water_equity = max(self.initial_account_size, float(data.get("lifetime_hwm", 1000.0)))
        except Exception:
            self.lifetime_high_water_equity = self.initial_account_size

    def _save_lifetime_hwm(self):
        """Persists lifetime high-water mark."""
        try:
            os.makedirs("data", exist_ok=True)
            with open(self.hwm_file, "w") as f:
                json.dump({"lifetime_hwm": self.lifetime_high_water_equity}, f)
        except Exception:
            pass

    def reset_daily_metrics_if_needed(self, current_equity: float):
        """Resets daily starting equity and daily metrics at 00:00 UTC."""
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        today = now_utc.date()

        if self.current_day != today or self.daily_start_equity <= 0:
            self.current_day = today
            self.daily_start_equity = current_equity if current_equity > 0 else self.initial_account_size
            self.daily_high_water_equity = self.daily_start_equity
            self.lifetime_high_water_equity = max(self.lifetime_high_water_equity, current_equity)
            self._save_lifetime_hwm()
            self.daily_trade_count = 0
            self.circuit_tripped = False
            self.trip_reason = ""
            self.trading_state = "NORMAL"
            self.risk_reduction_multiplier = 1.0

            self.account_consecutive_losses = 0
            self.engine_consecutive_losses = {self.magic_scalper: 0, self.magic_musumali: 0}
            self.symbol_consecutive_losses.clear()
            self.engine_cooldown_until = {self.magic_scalper: 0.0, self.magic_musumali: 0.0}
            self.symbol_cooldown_until.clear()

            self.daily_pnl_by_engine = {self.magic_scalper: 0.0, self.magic_musumali: 0.0}
            self.daily_trades_by_engine = {self.magic_scalper: 0, self.magic_musumali: 0}
            self.daily_wins_by_engine = {self.magic_scalper: 0, self.magic_musumali: 0}
            self.daily_pnl_by_symbol.clear()
            self.zone_failures.clear()
            self.zone_cooldown_until.clear()

            logger.info(
                f"[{self.account_id}] [DAILY RESET] Baseline Equity: ${self.daily_start_equity:.2f} | "
                f"Daily Stop: -${self.daily_hard_stop_loss:.2f} (Buffer: ${self.firm_daily_limit - self.daily_hard_stop_loss:.2f}) | "
                f"Lifetime HWM: ${self.lifetime_high_water_equity:.2f} | Challenge Target: +${self.challenge_target_profit:.2f}"
            )

    def record_trade_placed(self, magic: Optional[int] = None, symbol: Optional[str] = None):
        """Increments daily executed trade counter."""
        self.daily_trade_count += 1
        max_trades = self.risk_config.get("max_daily_trades", 12)
        logger.info(f"[{self.account_id}] Trade placed: Daily Count = {self.daily_trade_count}/{max_trades}")

    def record_trade_result(
        self,
        zone_id: Optional[float],
        profit: float,
        magic: Optional[int] = None,
        symbol: Optional[str] = None,
        exit_reason: str = "SL_TP_HIT",
        peak_r: float = 0.0,
        captured_r: float = 0.0,
    ):
        """Updates multi-dimensional metrics upon trade close."""
        now = time.time()
        m_key = self.magic_scalper if magic in (self.magic_scalper, 1001) else (
            self.magic_musumali if magic in (self.magic_musumali, 2001) else (magic or 0)
        )
        sym_key = symbol or "UNKNOWN"

        if m_key in self.daily_pnl_by_engine:
            self.daily_pnl_by_engine[m_key] += profit
            self.daily_trades_by_engine[m_key] += 1
            if profit > 0:
                self.daily_wins_by_engine[m_key] += 1

        self.daily_pnl_by_symbol[sym_key] = self.daily_pnl_by_symbol.get(sym_key, 0.0) + profit

        if peak_r > 0:
            self.total_peak_r += peak_r
            self.total_captured_r += max(0.0, captured_r)

        clean_reason = exit_reason.split()[0] if exit_reason else "UNKNOWN"
        if clean_reason not in self.exit_reason_stats:
            self.exit_reason_stats[clean_reason] = {"count": 0, "profit": 0.0, "captured_r": 0.0}
        self.exit_reason_stats[clean_reason]["count"] += 1
        self.exit_reason_stats[clean_reason]["profit"] += profit
        self.exit_reason_stats[clean_reason]["captured_r"] += captured_r

        if profit < -0.25:
            # Loss recorded
            self.account_consecutive_losses += 1
            self.engine_consecutive_losses[m_key] = self.engine_consecutive_losses.get(m_key, 0) + 1
            self.symbol_consecutive_losses[sym_key] = self.symbol_consecutive_losses.get(sym_key, 0) + 1

            logger.warning(
                f"[{self.account_id}] Trade Loss: ${profit:.2f} ({sym_key}, Magic #{m_key}) | "
                f"Consecutive Losses -> Account: {self.account_consecutive_losses}, "
                f"Engine: {self.engine_consecutive_losses[m_key]}, Symbol: {self.symbol_consecutive_losses[sym_key]}"
            )

            if zone_id is not None:
                self.zone_failures[zone_id] = self.zone_failures.get(zone_id, 0) + 1
                self.zone_cooldown_until[zone_id] = now + (self.zone_cooldown_minutes * 60)

            if self.engine_consecutive_losses[m_key] >= self.cl_pause_threshold:
                expiry = now + self.cl_cooldown_seconds
                self.engine_cooldown_until[m_key] = expiry
                logger.warning(f"[{self.account_id}] Engine #{m_key} paused for {self.cl_cooldown_seconds/60:.0f}m cooldown.")

            if self.symbol_consecutive_losses[sym_key] >= self.cl_pause_threshold:
                expiry = now + self.cl_cooldown_seconds
                self.symbol_cooldown_until[sym_key] = expiry
                logger.warning(f"[{self.account_id}] Symbol {sym_key} paused for {self.cl_cooldown_seconds/60:.0f}m cooldown.")

        elif profit > 0.10:
            # Win recorded
            self.account_consecutive_losses = 0
            self.engine_consecutive_losses[m_key] = 0
            self.symbol_consecutive_losses[sym_key] = 0
            if zone_id is not None and zone_id in self.zone_failures:
                self.zone_failures[zone_id] = max(0, self.zone_failures[zone_id] - 1)
            logger.info(f"[{self.account_id}] Trade Win: +${profit:.2f} ({sym_key}, Magic #{m_key}) -> Consecutive losses reset.")

    def is_engine_in_cooldown(self, magic: int) -> Tuple[bool, str]:
        expiry = self.engine_cooldown_until.get(magic, 0.0)
        now = time.time()
        m_name = "Scalp" if magic == self.magic_scalper else ("Musumali" if magic == self.magic_musumali else f"Module_{magic}")
        if now < expiry:
            rem = int(expiry - now)
            return True, f"Engine {m_name} in cooldown ({rem}s remaining)"
        return False, "ACTIVE"

    def is_symbol_in_cooldown(self, symbol: str) -> Tuple[bool, str]:
        expiry = self.symbol_cooldown_until.get(symbol, 0.0)
        now = time.time()
        if now < expiry:
            rem = int(expiry - now)
            return True, f"Symbol {symbol} in cooldown ({rem}s remaining)"
        return False, "ACTIVE"

    def is_zone_allowed(self, zone_id: Optional[float]) -> Tuple[bool, str]:
        if zone_id is None:
            return True, "OK"
        now = time.time()
        cooldown_until = self.zone_cooldown_until.get(zone_id, 0.0)
        failures = self.zone_failures.get(zone_id, 0)
        if now < cooldown_until and failures >= self.max_zone_failures:
            rem = int(cooldown_until - now)
            return False, f"Zone {zone_id:.1f} in cooldown ({failures} failures, {rem}s remaining)"
        return True, "OK"

    def calculate_monetary_loss(
        self,
        symbol: str,
        entry_price: float,
        stop_loss_price: float,
        volume: float,
    ) -> float:
        """
        Dynamically calculates the exact monetary loss ($) if Stop Loss is hit.
        Uses MT5 contract size, point size, and spread buffer.
        """
        spec = self.connector.get_symbol_specs(symbol) if self.connector else None
        sl_distance = abs(entry_price - stop_loss_price)
        if sl_distance <= 0:
            sl_distance = 1.0

        if spec and isinstance(getattr(spec, "contract_size", None), (int, float)) and spec.contract_size > 0:
            contract_size = float(spec.contract_size)
            point = float(spec.point) if getattr(spec, "point", None) and spec.point > 0 else 0.01
            spread = float(spec.spread) if getattr(spec, "spread", None) is not None else 20.0
            
            raw_loss = sl_distance * contract_size * volume
            spread_cost = spread * point * contract_size * volume
            estimated_slippage_cost = 5.0 * point * contract_size * volume
            total_expected_loss = raw_loss + spread_cost + estimated_slippage_cost
            return round(total_expected_loss, 2)
        else:
            if "BTC" in symbol.upper():
                return round(sl_distance * 1.0 * volume, 2)
            else:
                return round(sl_distance * 100.0 * volume, 2)

    def calculate_lot_size(
        self,
        symbol: str,
        entry_price: float,
        stop_loss_price: float,
        equity: float,
        quality_score: int = 50,
        open_trades_count: int = 0,
    ) -> float:
        """
        STRICT DYNAMIC SIZING FOR BRIGHTFUNDED FREE $1K CHALLENGE:
        - Never fixed lot sizes.
        - Calculates target risk ($2.50 to $5.00) based on Quality Score (0-100) and Account State.
        - Strictly bounds potential loss to remaining daily & trailing drawdown buffers.
        - Downscales lot size if simulated loss exceeds $5.00 max risk.
        - Rejects trade (returns 0.0) if 0.01 lot loss exceeds $5.50 hard reject limit.
        """
        spec = self.connector.get_symbol_specs(symbol) if self.connector else None
        min_vol = float(spec.volume_min) if (spec and isinstance(getattr(spec, "volume_min", None), (int, float))) else 0.01
        max_vol = float(spec.volume_max) if (spec and isinstance(getattr(spec, "volume_max", None), (int, float))) else 10.0
        vol_step = float(spec.volume_step) if (spec and isinstance(getattr(spec, "volume_step", None), (int, float))) else 0.01
        contract_size = float(spec.contract_size) if (spec and isinstance(getattr(spec, "contract_size", None), (int, float)) and spec.contract_size > 0) else 100.0

        # 1. Base Monetary Risk Allocation from Quality Score
        if quality_score >= 80:
            base_dollar_risk = 4.75 # High conviction A+ setup
        elif quality_score >= 65:
            base_dollar_risk = 3.75 # Strong conviction setup
        elif quality_score >= 50:
            base_dollar_risk = 2.75 # Standard baseline setup
        else:
            base_dollar_risk = 2.00 # Lower conviction

        # 2. Modulate by Account State & Multiplier
        allocated_dollar_risk = base_dollar_risk * self.risk_reduction_multiplier

        # 3. Buffer Constraints (Never allow single trade to consume >40% of remaining buffer to internal stop)
        net_daily_pnl = equity - self.daily_start_equity
        daily_loss = abs(min(0.0, net_daily_pnl))
        remaining_daily_internal_buffer = max(0.50, self.daily_hard_stop_loss - daily_loss)

        trailing_drawdown = self.lifetime_high_water_equity - equity
        remaining_trailing_internal_buffer = max(0.50, self.trailing_hard_stop_drawdown - trailing_drawdown)

        max_risk_allowed_by_daily = remaining_daily_internal_buffer * 0.40
        max_risk_allowed_by_trailing = remaining_trailing_internal_buffer * 0.25

        target_dollar_risk = min(
            allocated_dollar_risk,
            self.max_single_trade_risk,
            max_risk_allowed_by_daily,
            max_risk_allowed_by_trailing
        )
        target_dollar_risk = max(1.50, target_dollar_risk)

        sl_distance = abs(entry_price - stop_loss_price)
        if sl_distance <= 0:
            sl_distance = 1.0

        # 4. Sizing Math by Symbol
        if "BTC" in symbol.upper():
            raw_lots = target_dollar_risk / (sl_distance * max(contract_size, 1.0))
        else:
            raw_lots = target_dollar_risk / (sl_distance * contract_size)

        # 5. Quantize to Step
        stepped_lots = round(raw_lots / vol_step) * vol_step
        final_lots = round(max(min_vol, min(stepped_lots, max_vol)), 2)

        # 6. Post-Sizing Simulation & Safety Verification
        expected_loss = self.calculate_monetary_loss(symbol, entry_price, stop_loss_price, final_lots)

        # If simulated loss exceeds $5.00 limit due to step rounding, downscale
        while expected_loss > self.max_single_trade_risk and final_lots > min_vol:
            final_lots = round(final_lots - vol_step, 2)
            expected_loss = self.calculate_monetary_loss(symbol, entry_price, stop_loss_price, final_lots)

        # Hard rejection check if minimum lot still exceeds hard limit ($5.50)
        if expected_loss > self.single_trade_hard_reject:
            logger.warning(
                f"[{self.account_id}] [LOT SIZING REJECTED] {symbol} minimum lot {final_lots} results in ${expected_loss:.2f} loss "
                f"(SL distance ${sl_distance:.2f} too wide for $5.00 max risk limit)."
            )
            return 0.0

        logger.info(
            f"[{self.account_id}] [DYNAMIC LOT SIZE] {symbol}: {final_lots} lots | "
            f"Target Risk: ${target_dollar_risk:.2f} | Simulated SL Loss: ${expected_loss:.2f} | Quality: {quality_score}/100"
        )
        return final_lots

    def check_circuit_breakers(self, current_equity: float) -> Tuple[bool, str]:
        """
        BrightFunded Free $1K Challenge Circuit Breaker & Safety Engine:
          1. Challenge Target: +$100 ($1,100 Goal) -> CHALLENGE PASSED LOCK.
          2. Daily Profit Lifecycle: +$30 (Protection) -> +$40 (High Selectivity) -> +$50 (Target Stop).
          3. Daily Loss Ladder (Firm: -$30 | Internal Stop: -$25):
             - Normal: $0 to -$15
             - Warning: -$15 to -$20
             - Reduced Risk: -$20 to -$25 (0.4x sizing)
             - Internal Hard Stop: -$25 (NO NEW TRADES, ~$5 buffer preserved).
          4. Trailing Max Drawdown Ladder (Firm: $60 Trailing | Internal Stop: $50):
             - Normal Trailing: $0 to $30 draw from HWM
             - Warning Trailing: $30 to $40 draw from HWM
             - Reduced Risk Trailing: $40 to $50 draw from HWM (0.4x sizing)
             - Trailing Hard Stop: $50 drop from HWM (NO NEW TRADES, $10 buffer preserved).
        """
        self.reset_daily_metrics_if_needed(current_equity)
        self.daily_high_water_equity = max(self.daily_high_water_equity, current_equity)
        if current_equity > self.lifetime_high_water_equity:
            self.lifetime_high_water_equity = current_equity
            self._save_lifetime_hwm()

        if self.circuit_tripped:
            return False, f"Trading halted: {self.trip_reason}"

        net_daily_pnl = current_equity - self.daily_start_equity
        challenge_pnl = current_equity - self.initial_account_size
        trailing_drawdown = self.lifetime_high_water_equity - current_equity

        # =====================================================================
        # 1. CHALLENGE PASSED GOAL CHECK (+$100.00)
        # =====================================================================
        if challenge_pnl >= self.challenge_target_profit:
            self.circuit_tripped = True
            self.trading_state = "CHALLENGE_PASSED"
            self.trip_reason = (
                f"🎉 BRIGHTFUNDED $1K CHALLENGE PASSED! Total Profit = +${challenge_pnl:.2f} >= +${self.challenge_target_profit:.2f}. "
                f"Trading LOCKED to protect funded challenge achievement."
            )
            logger.info(f"[{self.account_id}] {self.trip_reason}")
            return False, self.trip_reason

        # =====================================================================
        # 2. DAILY PROFIT TARGET LIFECYCLE ($30 -> $40 -> $50)
        # =====================================================================
        if net_daily_pnl >= self.profit_target_stop:
            self.circuit_tripped = True
            self.trading_state = "TARGET_REACHED"
            self.trip_reason = f"Daily Target Achieved (+${net_daily_pnl:.2f} >= +${self.profit_target_stop:.2f})! Day gains locked."
            logger.info(f"[{self.account_id}] {self.trip_reason}")
            return False, self.trip_reason
        elif net_daily_pnl >= self.profit_high_selectivity_trigger:
            self.trading_state = "HIGH_SELECTIVITY"
            self.risk_reduction_multiplier = 0.50
        elif net_daily_pnl >= self.profit_protect_trigger:
            self.trading_state = "PROFIT_PROTECTION"
            self.risk_reduction_multiplier = 0.70

        # =====================================================================
        # 3. HIGH-WATER MARK GIVEBACK PROTECTION
        # =====================================================================
        if self.hwm_protection_enabled:
            daily_peak_profit = self.daily_high_water_equity - self.daily_start_equity
            if daily_peak_profit >= self.hwm_arm_profit:
                profit_giveback = self.daily_high_water_equity - current_equity
                giveback_pct = (profit_giveback / daily_peak_profit) * 100.0 if daily_peak_profit > 0 else 0.0
                if giveback_pct >= self.hwm_max_giveback_pct:
                    self.circuit_tripped = True
                    self.trading_state = "PROFIT_PROTECTION_HALT"
                    self.trip_reason = (
                        f"Giveback Protection Triggered! Peak +${daily_peak_profit:.2f}, giveback ${profit_giveback:.2f} ({giveback_pct:.1f}%). "
                        f"Trading paused for today to bank daily profits."
                    )
                    logger.warning(f"[{self.account_id}] {self.trip_reason}")
                    return False, self.trip_reason

        # =====================================================================
        # 4. INTERNAL DAILY LOSS LADDER (Firm Limit: $30 | Internal Stop: $25)
        # =====================================================================
        if net_daily_pnl < 0:
            daily_loss = abs(net_daily_pnl)

            if daily_loss >= self.daily_hard_stop_loss:
                self.circuit_tripped = True
                self.trading_state = "DAILY_HARD_STOP"
                self.trip_reason = (
                    f"INTERNAL DAILY HARD STOP (-${daily_loss:.2f} >= -${self.daily_hard_stop_loss:.2f})! "
                    f"Halted with ~${self.firm_daily_limit - daily_loss:.2f} buffer before BrightFunded $30 firm limit."
                )
                logger.critical(f"[{self.account_id}] {self.trip_reason}")
                return False, self.trip_reason

            elif daily_loss >= self.daily_reduced_risk_loss:
                self.trading_state = "REDUCED_RISK"
                self.risk_reduction_multiplier = 0.40
                logger.warning(f"[{self.account_id}] Daily Loss State: REDUCED_RISK (-${daily_loss:.2f}) -> 0.4x sizing.")

            elif daily_loss >= self.daily_warning_loss:
                self.trading_state = "WARNING"
                self.risk_reduction_multiplier = 0.70
                logger.info(f"[{self.account_id}] Daily Loss State: WARNING (-${daily_loss:.2f}) -> 0.7x sizing.")

            else:
                self.trading_state = "NORMAL"
                self.risk_reduction_multiplier = 1.0

        # =====================================================================
        # 5. DYNAMIC TRAILING MAXIMUM DRAWDOWN LADDER (Firm: $60 | Internal Stop: $50)
        # =====================================================================
        if trailing_drawdown >= self.trailing_hard_stop_drawdown:
            self.circuit_tripped = True
            self.trading_state = "TRAILING_HARD_STOP"
            self.trip_reason = (
                f"INTERNAL TRAILING HARD STOP (${trailing_drawdown:.2f} >= ${self.trailing_hard_stop_drawdown:.2f} from HWM ${self.lifetime_high_water_equity:.2f})! "
                f"Halted with ~${self.firm_trailing_limit - trailing_drawdown:.2f} buffer before BrightFunded $60 trailing firm limit."
            )
            logger.critical(f"[{self.account_id}] {self.trip_reason}")
            return False, self.trip_reason

        elif trailing_drawdown >= self.trailing_reduced_risk_drawdown:
            self.trading_state = "REDUCED_RISK_TRAILING"
            self.risk_reduction_multiplier = min(self.risk_reduction_multiplier, 0.40)
            logger.warning(f"[{self.account_id}] Trailing Drawdown State: REDUCED_RISK (${trailing_drawdown:.2f} from HWM).")

        elif trailing_drawdown >= self.trailing_warning_drawdown:
            self.trading_state = "WARNING_TRAILING"
            self.risk_reduction_multiplier = min(self.risk_reduction_multiplier, 0.70)
            logger.info(f"[{self.account_id}] Trailing Drawdown State: WARNING (${trailing_drawdown:.2f} from HWM).")

        # Consecutive Losses Modulation
        if self.account_consecutive_losses >= self.cl_reduce_risk_threshold:
            self.risk_reduction_multiplier = min(self.risk_reduction_multiplier, 0.50)

        return True, "OK"

    def pre_trade_risk_check(
        self,
        symbol: str,
        engine_magic: int,
        order_type: str,
        entry_price: float,
        stop_loss_price: float,
        take_profit_price: float,
        volume: float,
        quality_score: int,
        all_open_positions: List[dict],
        equity: float,
        free_margin: float,
        candle_id: str,
        traded_candle_ids: set,
        last_trade_time: float,
    ) -> Tuple[bool, List[str], float]:
        """
        Executes Mandatory 20-Point Pre-Trade Safety Verification for BrightFunded 1K Challenge.
        Strictly rejects trades if expected loss >= $5.50 or if risk exceeds remaining drawdown buffers.
        """
        failures = []
        expected_monetary_loss = 0.0

        if volume <= 0.0:
            failures.append("Check 0 Fail: Calculated volume is 0.0 (SL width or risk cap rejection)")
            return False, failures, 0.0

        # 1. Connection check
        if not self.connector or not self.connector.is_connected():
            failures.append("Check 1 Fail: Account connection not active")

        # 2. Symbol check
        spec = self.connector.get_symbol_specs(symbol) if self.connector else None
        if spec is None:
            failures.append(f"Check 2 Fail: Symbol {symbol} specs not available")

        # 3. Engine check
        if engine_magic not in (self.magic_scalper, self.magic_musumali):
            failures.append(f"Check 3 Fail: Engine Magic #{engine_magic} invalid")

        # 4. Order direction check
        if order_type not in ("BUY", "SELL"):
            failures.append(f"Check 4 Fail: Order direction {order_type} invalid")

        # 5. Quality Score Threshold check
        min_q = 50
        if self.trading_state in ("REDUCED_RISK", "REDUCED_RISK_TRAILING"):
            min_q = 70
        elif self.trading_state == "HIGH_SELECTIVITY":
            min_q = 80
        if quality_score < min_q:
            failures.append(f"Check 5 Fail: Quality score {quality_score}/100 below required {min_q} for state {self.trading_state}")

        # 6. Timeframe Identifier check
        if engine_magic == self.magic_scalper and "SCALP" not in candle_id:
            failures.append("Check 6 Fail: Scalper setup missing scalp timeframe identifier")
        elif engine_magic == self.magic_musumali and "SWEEP" not in candle_id:
            failures.append("Check 6 Fail: Musumali setup missing sweep timeframe identifier")

        # 7. Spread Check
        spread_ok, current_spread, spread_msg = self.check_spread_allowed(symbol)
        if not spread_ok:
            failures.append(f"Check 7 Fail: Spread too high ({spread_msg})")

        # 8. Volatility SL Distance Check
        sl_dist = abs(entry_price - stop_loss_price)
        if sl_dist <= 0:
            failures.append("Check 8 Fail: SL distance zero or negative")

        # 9. Macro News Check
        in_news, news_msg = self.is_in_news_blackout()
        if in_news:
            failures.append(f"Check 9 Fail: News blackout active ({news_msg})")

        # 10. Margin Check
        required_margin = (entry_price * volume * (spec.contract_size if spec else 100.0)) / max(self.connector.get_account_summary().get("leverage", 100), 1) if self.connector else 50.0
        if free_margin < (required_margin * 2.0):
            failures.append(f"Check 10 Fail: Insufficient free margin (Free: ${free_margin:.2f}, Req: ${required_margin:.2f})")

        # 11. Concurrency Check (Max 2 positions per account, max 1 per symbol, max 1 per engine)
        max_total = self.config.get("harmony_rules", {}).get("total_max_open_positions", 2)
        if len(all_open_positions) >= max_total:
            failures.append(f"Check 11 Fail: Max total open positions reached ({len(all_open_positions)}/{max_total})")

        symbol_pos = [p for p in all_open_positions if p.get("symbol") == symbol]
        if len(symbol_pos) >= 1:
            failures.append(f"Check 11 Fail: Max 1 position per symbol reached for {symbol}")

        engine_pos = [p for p in all_open_positions if p.get("magic") == engine_magic]
        if len(engine_pos) >= 1:
            failures.append(f"Check 11 Fail: Max 1 position for engine #{engine_magic} reached")

        # 12. Circuit Breaker State Check
        can_trade, dd_reason = self.check_circuit_breakers(equity)
        if not can_trade:
            failures.append(f"Check 12 Fail: Circuit breaker active ({dd_reason})")

        # 13 & 14. Stop Loss Geometry Check
        if (order_type == "BUY" and stop_loss_price >= entry_price) or (order_type == "SELL" and stop_loss_price <= entry_price):
            failures.append(f"Check 14 Fail: Stop Loss {stop_loss_price:.2f} invalid relative to entry {entry_price:.2f}")

        # 15 & 16. Strict Monetary Risk Checks ($5.00 max risk cap)
        expected_monetary_loss = self.calculate_monetary_loss(symbol, entry_price, stop_loss_price, volume)
        if expected_monetary_loss > self.single_trade_hard_reject:
            failures.append(
                f"Check 16 Fail: Calculated Loss ${expected_monetary_loss:.2f} exceeds strict $5.50 hard reject limit"
            )

        # Buffer Preservation Checks (Trade loss must not breach internal stops)
        net_daily_pnl = equity - self.daily_start_equity
        projected_daily_loss = abs(min(0.0, net_daily_pnl)) + expected_monetary_loss
        if projected_daily_loss >= self.daily_hard_stop_loss:
            failures.append(
                f"Check 16 Fail: Projected daily loss ${projected_daily_loss:.2f} exceeds internal daily stop ${self.daily_hard_stop_loss:.2f}"
            )

        trailing_drawdown = self.lifetime_high_water_equity - equity
        projected_trailing_drawdown = trailing_drawdown + expected_monetary_loss
        if projected_trailing_drawdown >= self.trailing_hard_stop_drawdown:
            failures.append(
                f"Check 16 Fail: Projected trailing drawdown ${projected_trailing_drawdown:.2f} exceeds internal trailing stop ${self.trailing_hard_stop_drawdown:.2f}"
            )

        # 17. Engine & Symbol Cooldown Checks
        in_e_cd, e_cd_msg = self.is_engine_in_cooldown(engine_magic)
        if in_e_cd:
            failures.append(f"Check 17 Fail: {e_cd_msg}")

        in_s_cd, s_cd_msg = self.is_symbol_in_cooldown(symbol)
        if in_s_cd:
            failures.append(f"Check 17 Fail: {s_cd_msg}")

        # 18. Duplicate Setup Check
        if candle_id in traded_candle_ids:
            failures.append(f"Check 18 Fail: Candle setup {candle_id} already executed")

        is_dup_type = any(p.get("magic") == engine_magic and p.get("symbol") == symbol and p.get("type") == order_type for p in all_open_positions)
        if is_dup_type:
            failures.append(f"Check 18 Fail: Duplicate {order_type} position already active on {symbol} for engine #{engine_magic}")

        # 19. Cooldown Seconds Check
        cooldown_sec = self.config.get("harmony_rules", {}).get("cooldown_seconds_per_trade", 30)
        if (time.time() - last_trade_time) < cooldown_sec:
            rem_cd = int(cooldown_sec - (time.time() - last_trade_time))
            failures.append(f"Check 19 Fail: In trade cooldown ({rem_cd}s remaining)")

        # 20. Broker Volume Bounds Check
        if spec:
            if volume < spec.volume_min or volume > spec.volume_max:
                failures.append(f"Check 20 Fail: Volume {volume} outside broker bounds [{spec.volume_min}, {spec.volume_max}]")

        passed = len(failures) == 0
        if not passed:
            logger.warning(f"[{self.account_id}] [PRE-TRADE CHECK FAILED]:\n - " + "\n - ".join(failures))
        else:
            logger.info(
                f"[{self.account_id}] [PRE-TRADE 20-POINT CHECK PASSED] {symbol} {order_type} {volume} lots | "
                f"Entry: {entry_price:.2f} | SL: {stop_loss_price:.2f} | Expected Loss: ${expected_monetary_loss:.2f} (<= $5.00) | Quality: {quality_score}/100"
            )

        return passed, failures, expected_monetary_loss

    def check_spread_allowed(self, symbol: str) -> Tuple[bool, int, str]:
        info = mt5.symbol_info(symbol) if self.connector else None
        if info is None:
            return False, 9999, "No symbol info"

        current_spread = info.spread
        sym_settings = self.symbols_cfg.get("symbol_settings", {}).get(symbol.replace("m", "").replace("_i", "").replace("z", ""), {})
        max_allowed = sym_settings.get("max_spread_points", 320 if "XAU" in symbol else 2500)

        session_name = self.get_current_trading_session()
        st_cfg = self.risk_config.get("session_tuning", {}).get("sessions", {}).get(session_name, {})
        if "XAU" in symbol:
            max_allowed = st_cfg.get("max_spread_points_xau", max_allowed)
        elif "BTC" in symbol:
            max_allowed = st_cfg.get("max_spread_points_btc", max_allowed)

        if current_spread > max_allowed:
            return False, current_spread, f"Spread [{current_spread} pts] > max [{max_allowed} pts] for {symbol} ({session_name})"

        return True, current_spread, "OK"

    def is_in_news_blackout(self) -> Tuple[bool, str]:
        if not self.risk_config.get("news_blackout_enabled", True):
            return False, "Disabled"

        now_utc = datetime.datetime.now(datetime.timezone.utc)
        before_min = self.risk_config.get("blackout_before_minutes", 10)
        after_min = self.risk_config.get("blackout_after_minutes", 15)

        if now_utc.weekday() <= 4:
            current_minute_of_day = now_utc.hour * 60 + now_utc.minute
            macro_windows = [
                (750, "US Macro CPI/NFP/GDP @ 12:30 UTC"),
                (840, "US ISM/PMI @ 14:00 UTC"),
                (1080, "US FOMC Rate Decision @ 18:00 UTC"),
            ]
            for event_min, event_name in macro_windows:
                window_start = event_min - before_min
                window_end = event_min + after_min
                if window_start <= current_minute_of_day <= window_end:
                    rem = window_end - current_minute_of_day
                    return True, f"{event_name} ({rem}m remaining)"

        return False, "Clear"

    def get_current_trading_session(self) -> str:
        hour = datetime.datetime.now(datetime.timezone.utc).hour
        if 0 <= hour < 7:
            return "Asian"
        elif 7 <= hour < 12:
            return "London"
        elif 12 <= hour < 16:
            return "London/NY Overlap"
        elif 16 <= hour < 21:
            return "New York"
        else:
            return "Late Asian/Off-Hours"

    def is_session_allowed(self) -> Tuple[bool, str, str]:
        session_name = self.get_current_trading_session()
        if not self.risk_config.get("session_filter_enabled", True):
            return True, session_name, "Disabled"
        allowed = self.risk_config.get("allowed_sessions", ["London", "London/NY Overlap", "New York", "Asian"])
        if session_name not in allowed:
            return False, session_name, f"Session '{session_name}' not in {allowed}"
        return True, session_name, "OK"

    def get_module_performance_summary(self) -> dict:
        scalp_pnl = self.daily_pnl_by_engine.get(self.magic_scalper, 0.0)
        musu_pnl = self.daily_pnl_by_engine.get(self.magic_musumali, 0.0)
        return {
            "scalp_pnl": round(scalp_pnl, 2),
            "scalp_trades": self.daily_trades_by_engine.get(self.magic_scalper, 0),
            "scalp_wins": self.daily_wins_by_engine.get(self.magic_scalper, 0),
            "musumali_pnl": round(musu_pnl, 2),
            "musumali_trades": self.daily_trades_by_engine.get(self.magic_musumali, 0),
            "musumali_wins": self.daily_wins_by_engine.get(self.magic_musumali, 0),
            "symbol_pnl": {k: round(v, 2) for k, v in self.daily_pnl_by_symbol.items()},
            "total_day_pnl": round(scalp_pnl + musu_pnl, 2),
            "trading_state": self.trading_state,
        }

    def get_circuit_breaker_status(self, current_equity: Optional[float] = None) -> str:
        eq = current_equity if current_equity is not None else self.daily_start_equity
        net_day = eq - self.daily_start_equity
        challenge_pnl = eq - self.initial_account_size
        trailing_dd = self.lifetime_high_water_equity - eq

        rem_daily_buf = max(0.0, self.daily_hard_stop_loss - abs(min(0.0, net_day)))
        rem_trailing_buf = max(0.0, self.trailing_hard_stop_drawdown - trailing_dd)

        return (
            f"State: {self.trading_state} | Challenge P&L: ${challenge_pnl:+.2f}/+$100 | "
            f"Day P&L: ${net_day:+.2f} (Daily Buf: ${rem_daily_buf:.2f}) | "
            f"HWM: ${self.lifetime_high_water_equity:.2f} (Trailing Buf: ${rem_trailing_buf:.2f})"
        )
