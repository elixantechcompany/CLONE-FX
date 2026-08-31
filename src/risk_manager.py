"""
BrightFunded & Personal Multi-Account Risk Management & Circuit Breaker Engine
Supports:
  1. Profile-Aware Risk Management:
     - BRIGHTFUNDED ($1,000 Accounts A & B):
       - Challenge Objective: Pass $100 Profit Target ($1,100 Total Equity) without breaching firm limits.
       - Official Limits: Daily Drawdown 3% ($30), Trailing Drawdown 6% ($60 from HWM).
       - Internal Multi-Tier Buffers: -$15 warning, -$20 reduced risk, -$25 hard stop (~$5 safety buffer).
       - Trailing Buffers: $30 warning, $40 reduced risk, $50 hard stop ($10 safety buffer).
       - Individual Trade Risk: Strictly dynamic $2.50 - $5.00 (Hard reject at $5.50).
       - Profit Lifecycle: +$30 protection -> +$40 selectivity -> +$50 day target stop -> +$100 challenge passed.
     - PERSONAL ($20 Accounts C & D):
       - Baseline: $20.00.
       - Daily Drawdown Stop: -$3.00 (15%).
       - Individual Trade Risk: $0.25 - $0.50 (Hard reject at $1.00).
       - Daily Target: +$2.00.
  2. Full Account Isolation: Independent Drawdown, HWM, Daily P&L, Consecutive Losses, and Cooldowns.
  3. Zero Martingale / Zero Revenge Trading.
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
    def __init__(self, config: dict, connector, account_id: str = "account_a", account_type: Optional[str] = None):
        self.config = config
        self.account_id = account_id.lower()
        self.connector = connector
        
        # Determine account type & initial balance
        acc_list = config.get("accounts", {}).get("account_list", [])
        matched = [a for a in acc_list if str(a.get("id", "")).lower() == self.account_id]
        if matched:
            self.account_type = account_type.upper() if account_type else matched[0].get("type", "BRIGHTFUNDED").upper()
            configured_balance = float(matched[0].get("balance", 0.0))
        else:
            self.account_type = account_type.upper() if account_type else "BRIGHTFUNDED"
            configured_balance = 0.0

        self.funded_cfg = config.get("funded_account", {})
        self.personal_cfg = config.get("personal_account", {})
        self.risk_config = config.get("risk_management", {})
        self.circuit_config = config.get("circuit_breakers", {})
        self.zone_config = config.get("zone_management", {})
        self.symbols_cfg = config.get("symbols", {})

        if self.account_type == "PERSONAL":
            # Personal Micro Profile
            default_size = configured_balance if configured_balance > 0 else float(self.personal_cfg.get("initial_account_size_dollars", 20.0))
            self.initial_account_size = default_size
            self.challenge_target_profit = float(self.personal_cfg.get("daily_profit_objective_dollars", 30.0))
            self.firm_daily_limit = float(self.personal_cfg.get("daily_drawdown_limit_dollars", 6.0))
            self.firm_trailing_limit = float(self.personal_cfg.get("daily_drawdown_limit_dollars", 8.0))

            self.daily_warning_loss = 3.00
            self.daily_reduced_risk_loss = 4.50
            self.daily_hard_stop_loss = float(self.personal_cfg.get("daily_drawdown_limit_dollars", 6.00))

            self.trailing_warning_drawdown = 4.00
            self.trailing_reduced_risk_drawdown = 6.00
            self.trailing_hard_stop_drawdown = 8.00

            self.max_single_trade_risk = float(self.personal_cfg.get("max_single_trade_risk_dollars", 2.50))
            self.preferred_risk_min = float(self.personal_cfg.get("preferred_risk_min_dollars", 1.50))
            self.preferred_risk_max = float(self.personal_cfg.get("preferred_risk_max_dollars", 2.50))
            self.single_trade_hard_reject = float(self.personal_cfg.get("single_trade_hard_reject_dollars", 3.50))

            self.profit_protect_trigger = 10.00
            self.profit_high_selectivity_trigger = 20.00
            self.profit_target_stop = float(self.personal_cfg.get("daily_profit_objective_dollars", 30.00))
        else:
            # BrightFunded $1,000 Profile
            self.initial_account_size = float(self.funded_cfg.get("initial_account_size_dollars", 1000.0))
            self.challenge_target_profit = float(self.funded_cfg.get("challenge_target_profit_dollars", 100.0))
            self.firm_daily_limit = float(self.funded_cfg.get("firm_daily_drawdown_limit_dollars", 30.0))
            self.firm_trailing_limit = float(self.funded_cfg.get("firm_trailing_max_drawdown_dollars", 60.0))

            self.daily_warning_loss = float(self.funded_cfg.get("internal_daily_warning_dollars", 15.0))
            self.daily_reduced_risk_loss = float(self.funded_cfg.get("internal_daily_reduced_risk_dollars", 20.0))
            self.daily_hard_stop_loss = float(self.funded_cfg.get("internal_daily_hard_stop_dollars", 25.0))

            self.trailing_warning_drawdown = float(self.funded_cfg.get("internal_trailing_warning_dollars", 30.0))
            self.trailing_reduced_risk_drawdown = float(self.funded_cfg.get("internal_trailing_reduced_risk_dollars", 40.0))
            self.trailing_hard_stop_drawdown = float(self.funded_cfg.get("internal_trailing_hard_stop_dollars", 50.0))

            self.max_single_trade_risk = float(self.funded_cfg.get("max_single_trade_risk_dollars", 3.00))
            self.preferred_risk_min = float(self.funded_cfg.get("preferred_risk_min_dollars", 2.00))
            self.preferred_risk_max = float(self.funded_cfg.get("preferred_risk_max_dollars", 3.00))
            self.single_trade_hard_reject = float(self.funded_cfg.get("single_trade_hard_reject_dollars", 3.50))

            self.profit_protect_trigger = float(self.funded_cfg.get("daily_profit_objective_min", 30.0))
            self.profit_high_selectivity_trigger = float(self.funded_cfg.get("daily_profit_objective_selective", 40.0))
            self.profit_target_stop = float(self.funded_cfg.get("daily_profit_objective_max", 50.0))

        # High-Water Mark Giveback Protection
        hwm_cfg = self.circuit_config.get("high_water_giveback_protection", {})
        self.hwm_protection_enabled = hwm_cfg.get("enabled", True)
        self.hwm_arm_profit = float(hwm_cfg.get("min_profit_to_arm_dollars", 8.0 if self.account_type == "BRIGHTFUNDED" else 1.50))
        self.hwm_max_giveback_pct = float(hwm_cfg.get("max_giveback_pct_of_peak", 25.0))

        # Daily baseline and state
        self.current_day: Optional[datetime.date] = None
        self.daily_start_equity: float = 0.0
        self.daily_high_water_equity: float = 0.0
        self.lifetime_high_water_equity: float = self.initial_account_size
        self.daily_trade_count: int = 0
        self.circuit_tripped: bool = False
        self.trip_reason: str = ""
        self.trading_state: str = "NORMAL"
        self.risk_reduction_multiplier: float = 1.0

        # Persistence for Lifetime High-Water Mark
        self.hwm_file = f"data/hwm_{self.account_id}.json"
        self._load_lifetime_hwm()

        # Magic Numbers
        self.magic_scalper = config.get("m1_scalper", {}).get("magic_number", 1001)
        self.magic_musumali = config.get("musumali_strategy", {}).get("magic_number", 2001)

        # Performance Tracking
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
        self.cl_caution_threshold = int(cl_cfg.get("caution_threshold", 2))
        self.cl_reduce_risk_threshold = int(cl_cfg.get("reduce_risk_threshold", 2))
        self.cl_restrict_threshold = int(cl_cfg.get("restrict_trading_threshold", 3))
        self.cl_pause_threshold = int(cl_cfg.get("pause_module_threshold", 3))
        self.cl_cooldown_seconds = float(cl_cfg.get("module_cooldown_minutes", 30)) * 60.0

        # Liquidity Zone Failure Memory
        self.zone_failures: Dict[float, int] = {}
        self.zone_cooldown_until: Dict[float, float] = {}
        self.max_zone_failures = self.zone_config.get("max_zone_failures", 2)
        self.zone_cooldown_minutes = self.zone_config.get("zone_cooldown_minutes", 10)

        # Profit & Session Expectancy Analytics
        self.total_peak_r: float = 0.0
        self.total_captured_r: float = 0.0
        self.exit_reason_stats: Dict[str, dict] = {}
        self.session_performance: Dict[str, dict] = {
            "Asian": {"wins": 0, "losses": 0, "win_pnl": 0.0, "loss_pnl": 0.0},
            "London": {"wins": 0, "losses": 0, "win_pnl": 0.0, "loss_pnl": 0.0},
            "London/NY Overlap": {"wins": 0, "losses": 0, "win_pnl": 0.0, "loss_pnl": 0.0},
            "New York": {"wins": 0, "losses": 0, "win_pnl": 0.0, "loss_pnl": 0.0},
            "Late Asian/Off-Hours": {"wins": 0, "losses": 0, "win_pnl": 0.0, "loss_pnl": 0.0},
        }

    @property
    def is_personal(self) -> bool:
        return self.account_type == "PERSONAL"


    def _load_lifetime_hwm(self):
        """Loads historical lifetime high-water mark for accurate trailing drawdown tracking."""
        try:
            if os.path.exists(self.hwm_file):
                with open(self.hwm_file, "r") as f:
                    data = json.load(f)
                    self.lifetime_high_water_equity = max(self.initial_account_size, float(data.get("lifetime_hwm", self.initial_account_size)))
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
                f"[{self.account_id.upper()}] [DAILY RESET] Profile: {self.account_type} | Baseline Equity: ${self.daily_start_equity:.2f} | "
                f"Daily Stop: -${self.daily_hard_stop_loss:.2f} | Lifetime HWM: ${self.lifetime_high_water_equity:.2f}"
            )

    def record_trade_placed(self, magic: Optional[int] = None, symbol: Optional[str] = None):
        """Increments daily executed trade counter."""
        self.daily_trade_count += 1
        max_trades = self.risk_config.get("max_daily_trades", 12)
        logger.info(f"[{self.account_id.upper()}] Trade placed: Daily Count = {self.daily_trade_count}/{max_trades}")

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

        loss_threshold = -0.25 if self.account_type == "BRIGHTFUNDED" else -0.05
        win_threshold = 0.10 if self.account_type == "BRIGHTFUNDED" else 0.05

        if profit < loss_threshold:
            # Loss recorded
            self.last_trade_was_loss = True
            self.last_loss_time = now
            self.account_consecutive_losses += 1
            self.engine_consecutive_losses[m_key] = self.engine_consecutive_losses.get(m_key, 0) + 1
            self.symbol_consecutive_losses[sym_key] = self.symbol_consecutive_losses.get(sym_key, 0) + 1

            logger.warning(
                f"[{self.account_id.upper()}] Trade Loss: ${profit:.2f} ({sym_key}, Magic #{m_key}) | "
                f"Consecutive Losses -> Account: {self.account_consecutive_losses}, "
                f"Engine: {self.engine_consecutive_losses[m_key]}, Symbol: {self.symbol_consecutive_losses[sym_key]}"
            )

            if zone_id is not None:
                self.zone_failures[zone_id] = self.zone_failures.get(zone_id, 0) + 1
                self.zone_cooldown_until[zone_id] = now + (self.zone_cooldown_minutes * 60)

            if self.engine_consecutive_losses[m_key] >= self.cl_pause_threshold:
                expiry = now + self.cl_cooldown_seconds
                self.engine_cooldown_until[m_key] = expiry
                logger.warning(f"[{self.account_id.upper()}] Engine #{m_key} paused for {self.cl_cooldown_seconds/60:.0f}m cooldown.")

            if self.symbol_consecutive_losses[sym_key] >= self.cl_pause_threshold:
                expiry = now + self.cl_cooldown_seconds
                self.symbol_cooldown_until[sym_key] = expiry
                logger.warning(f"[{self.account_id.upper()}] Symbol {sym_key} paused for {self.cl_cooldown_seconds/60:.0f}m cooldown.")

        elif profit > win_threshold:
            # Win recorded
            self.last_trade_was_loss = False
            self.account_consecutive_losses = 0
            self.engine_consecutive_losses[m_key] = 0
            self.symbol_consecutive_losses[sym_key] = 0
            if zone_id is not None and zone_id in self.zone_failures:
                self.zone_failures[zone_id] = max(0, self.zone_failures[zone_id] - 1)
            logger.info(f"[{self.account_id.upper()}] Trade Win: +${profit:.2f} ({sym_key}, Magic #{m_key}) -> Consecutive losses reset.")

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
        DYNAMIC SIZING BOUNDED BY PROFILE RISK LIMITS:
        - Never fixed lot sizes.
        - Calculates target risk based on Quality Score (0-100), Profile, and Account State.
        - Strictly bounds potential loss to remaining daily & trailing drawdown buffers.
        - Rejects trade (returns 0.0) if minimum lot loss exceeds profile single_trade_hard_reject limit.
        """
        spec = self.connector.get_symbol_specs(symbol) if self.connector else None
        min_vol = float(spec.volume_min) if (spec and isinstance(getattr(spec, "volume_min", None), (int, float))) else 0.01
        max_vol = float(spec.volume_max) if (spec and isinstance(getattr(spec, "volume_max", None), (int, float))) else 10.0
        vol_step = float(spec.volume_step) if (spec and isinstance(getattr(spec, "volume_step", None), (int, float))) else 0.01
        contract_size = float(spec.contract_size) if (spec and isinstance(getattr(spec, "contract_size", None), (int, float)) and spec.contract_size > 0) else 100.0

        if self.account_type == "PERSONAL":
            # Personal $20 Profile
            if quality_score >= 80:
                base_dollar_risk = 0.45
            elif quality_score >= 65:
                base_dollar_risk = 0.35
            elif quality_score >= 50:
                base_dollar_risk = 0.25
            else:
                base_dollar_risk = 0.18
        else:
            # BrightFunded $1,000 Profile
            if quality_score >= 80:
                base_dollar_risk = 3.00
            elif quality_score >= 65:
                base_dollar_risk = 2.50
            elif quality_score >= 50:
                base_dollar_risk = 2.00
            else:
                base_dollar_risk = 1.50

        allocated_dollar_risk = base_dollar_risk * self.risk_reduction_multiplier

        # Buffer Constraints
        net_daily_pnl = equity - self.daily_start_equity
        daily_loss = abs(min(0.0, net_daily_pnl))
        remaining_daily_internal_buffer = max(0.10, self.daily_hard_stop_loss - daily_loss)

        trailing_drawdown = self.lifetime_high_water_equity - equity
        remaining_trailing_internal_buffer = max(0.10, self.trailing_hard_stop_drawdown - trailing_drawdown)

        max_risk_allowed_by_daily = remaining_daily_internal_buffer * 0.40
        max_risk_allowed_by_trailing = remaining_trailing_internal_buffer * 0.25

        target_dollar_risk = min(
            allocated_dollar_risk,
            self.max_single_trade_risk,
            max_risk_allowed_by_daily,
            max_risk_allowed_by_trailing
        )
        target_dollar_risk = max(0.15 if self.account_type == "PERSONAL" else 1.50, target_dollar_risk)

        sl_distance = abs(entry_price - stop_loss_price)
        if sl_distance <= 0:
            sl_distance = 1.0

        if "BTC" in symbol.upper():
            raw_lots = target_dollar_risk / (sl_distance * max(contract_size, 1.0))
        else:
            raw_lots = target_dollar_risk / (sl_distance * contract_size)

        stepped_lots = round(raw_lots / vol_step) * vol_step
        final_lots = round(max(min_vol, min(stepped_lots, max_vol)), 2)

        # Post-Sizing Simulation & Safety Verification
        expected_loss = self.calculate_monetary_loss(symbol, entry_price, stop_loss_price, final_lots)

        while expected_loss > self.max_single_trade_risk and final_lots > min_vol:
            final_lots = round(final_lots - vol_step, 2)
            expected_loss = self.calculate_monetary_loss(symbol, entry_price, stop_loss_price, final_lots)

        # Hard rejection check if minimum lot still exceeds hard limit
        if expected_loss > self.single_trade_hard_reject:
            logger.warning(
                f"[{self.account_id.upper()}] [LOT SIZING REJECTED] {symbol} min lot {final_lots} results in ${expected_loss:.2f} loss "
                f"(SL distance ${sl_distance:.2f} too wide for ${self.single_trade_hard_reject:.2f} max risk limit)."
            )
            return 0.0

        logger.info(
            f"[{self.account_id.upper()}] [DYNAMIC LOT SIZE] {symbol}: {final_lots} lots | "
            f"Target Risk: ${target_dollar_risk:.2f} | Simulated SL Loss: ${expected_loss:.2f} | Quality: {quality_score}/100"
        )
        return final_lots

    def check_circuit_breakers(self, current_equity: float) -> Tuple[bool, str]:
        """
        Circuit Breaker & Safety Engine (Profile-Aware):
          1. Challenge / Target Profit Goal.
          2. Daily Profit Lifecycle.
          3. Internal Daily Loss Ladder (Hard Stop leaves buffer before firm limit).
          4. Dynamic Trailing Maximum Drawdown Ladder (Hard Stop leaves buffer before firm limit).
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

        # 1. CHALLENGE / TARGET PASSED GOAL CHECK (Prop Firm Accounts Only)
        if self.account_type == "BRIGHTFUNDED" and challenge_pnl >= self.challenge_target_profit:
            self.circuit_tripped = True
            self.trading_state = "CHALLENGE_PASSED"
            self.trip_reason = (
                f"[TARGET ACHIEVED] Total Profit = +${challenge_pnl:.2f} >= +${self.challenge_target_profit:.2f}. "
                f"Trading LOCKED to protect achievement."
            )
            logger.info(f"[{self.account_id.upper()}] {self.trip_reason}")
            return False, self.trip_reason

        # 2. DAILY PROFIT TARGET LIFECYCLE
        if net_daily_pnl >= self.profit_target_stop:
            self.circuit_tripped = True
            self.trading_state = "TARGET_REACHED"
            self.trip_reason = f"Daily Target Achieved (+${net_daily_pnl:.2f} >= +${self.profit_target_stop:.2f})! Day gains locked."
            logger.info(f"[{self.account_id.upper()}] {self.trip_reason}")
            return False, self.trip_reason
        elif net_daily_pnl >= self.profit_high_selectivity_trigger:
            self.trading_state = "HIGH_SELECTIVITY"
            self.risk_reduction_multiplier = 0.50
        elif net_daily_pnl >= self.profit_protect_trigger:
            self.trading_state = "PROFIT_PROTECTION"
            self.risk_reduction_multiplier = 0.70

        # 3. HIGH-WATER MARK GIVEBACK PROTECTION
        if self.hwm_protection_enabled:
            daily_peak_profit = self.daily_high_water_equity - self.daily_start_equity
            if daily_peak_profit >= self.hwm_arm_profit:
                profit_giveback = self.daily_high_water_equity - current_equity
                giveback_pct = (profit_giveback / daily_peak_profit) * 100.0 if daily_peak_profit > 0 else 0.0
                if giveback_pct >= self.hwm_max_giveback_pct or (daily_peak_profit >= 12.0 and profit_giveback >= 3.50):
                    self.circuit_tripped = True
                    self.trading_state = "PROFIT_PROTECTION_HALT"
                    self.trip_reason = (
                        f"Giveback Protection Triggered! Peak +${daily_peak_profit:.2f}, giveback ${profit_giveback:.2f} ({giveback_pct:.1f}%). "
                        f"Trading paused for today to bank ${current_equity - self.daily_start_equity:+.2f} daily profits."
                    )
                    logger.warning(f"[{self.account_id.upper()}] {self.trip_reason}")
                    return False, self.trip_reason

        # 4. INTERNAL DAILY LOSS LADDER
        if net_daily_pnl < 0:
            daily_loss = abs(net_daily_pnl)

            if daily_loss >= self.daily_hard_stop_loss:
                self.circuit_tripped = True
                self.trading_state = "DAILY_HARD_STOP"
                self.trip_reason = (
                    f"INTERNAL DAILY HARD STOP (-${daily_loss:.2f} >= -${self.daily_hard_stop_loss:.2f})! "
                    f"Halted with ~${self.firm_daily_limit - daily_loss:.2f} buffer before firm limit."
                )
                logger.critical(f"[{self.account_id.upper()}] {self.trip_reason}")
                return False, self.trip_reason

            elif daily_loss >= self.daily_reduced_risk_loss:
                self.trading_state = "REDUCED_RISK"
                self.risk_reduction_multiplier = 0.40
                logger.warning(f"[{self.account_id.upper()}] Daily Loss State: REDUCED_RISK (-${daily_loss:.2f}) -> 0.4x sizing.")

            elif daily_loss >= self.daily_warning_loss:
                self.trading_state = "WARNING"
                self.risk_reduction_multiplier = 0.70
                logger.info(f"[{self.account_id.upper()}] Daily Loss State: WARNING (-${daily_loss:.2f}) -> 0.7x sizing.")

            else:
                self.trading_state = "NORMAL"
                self.risk_reduction_multiplier = 1.0

        # 5. DYNAMIC TRAILING MAXIMUM DRAWDOWN LADDER
        if trailing_drawdown >= self.trailing_hard_stop_drawdown:
            self.circuit_tripped = True
            self.trading_state = "TRAILING_HARD_STOP"
            self.trip_reason = (
                f"INTERNAL TRAILING HARD STOP (${trailing_drawdown:.2f} >= ${self.trailing_hard_stop_drawdown:.2f} from HWM ${self.lifetime_high_water_equity:.2f})! "
                f"Halted with ~${self.firm_trailing_limit - trailing_drawdown:.2f} buffer before firm limit."
            )
            logger.critical(f"[{self.account_id.upper()}] {self.trip_reason}")
            return False, self.trip_reason

        elif trailing_drawdown >= self.trailing_reduced_risk_drawdown:
            self.trading_state = "REDUCED_RISK_TRAILING"
            self.risk_reduction_multiplier = min(self.risk_reduction_multiplier, 0.40)
            logger.warning(f"[{self.account_id.upper()}] Trailing Drawdown State: REDUCED_RISK (${trailing_drawdown:.2f} from HWM).")

        elif trailing_drawdown >= self.trailing_warning_drawdown:
            self.trading_state = "WARNING_TRAILING"
            self.risk_reduction_multiplier = min(self.risk_reduction_multiplier, 0.70)
            logger.info(f"[{self.account_id.upper()}] Trailing Drawdown State: WARNING (${trailing_drawdown:.2f} from HWM).")

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
        Executes Mandatory 20-Point Pre-Trade Safety Verification.
        Strictly rejects trades if expected loss >= single_trade_hard_reject limit.
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

        # 6. Global circuit breaker check
        can_trade, reason = self.check_circuit_breakers(equity)
        if not can_trade:
            failures.append(f"Check 6 Fail: Circuit breaker active ({reason})")

        # 7. Engine cooldown check
        in_cd, cd_reason = self.is_engine_in_cooldown(engine_magic)
        if in_cd:
            failures.append(f"Check 7 Fail: {cd_reason}")

        # 8. Symbol cooldown check
        s_in_cd, s_cd_reason = self.is_symbol_in_cooldown(symbol)
        if s_in_cd:
            failures.append(f"Check 8 Fail: {s_cd_reason}")

        # 9. Concurrency: Total open positions cap (Max 2)
        total_open = len(all_open_positions)
        if total_open >= 2:
            failures.append(f"Check 9 Fail: Max total open positions reached ({total_open}/2)")

        # 10. Concurrency: Engine positions cap (Max 1 per engine)
        engine_open = [p for p in all_open_positions if p.get("magic") == engine_magic]
        if len(engine_open) >= 1:
            failures.append(f"Check 10 Fail: Engine Magic #{engine_magic} already has active trade (#{engine_open[0]['ticket']})")

        # 11. Concurrency: Symbol positions cap (Max 1 per symbol)
        sym_open = [p for p in all_open_positions if p.get("symbol") == symbol]
        if len(sym_open) >= 1:
            failures.append(f"Check 11 Fail: Symbol {symbol} already has active trade (#{sym_open[0]['ticket']})")

        # 12. Opposing direction hedge check
        for p in sym_open:
            p_dir = p.get("type", "").upper()
            if (order_type == "BUY" and p_dir == "SELL") or (order_type == "SELL" and p_dir == "BUY"):
                failures.append(f"Check 12 Fail: Opposing hedge on {symbol} strictly forbidden (Existing #{p['ticket']} is {p_dir})")

        # 13. Trade spacing cooldown & Post-Loss Cooldown
        spacing_cd = self.config.get("harmony_rules", {}).get("cooldown_seconds_per_trade", 90)
        if getattr(self, "last_trade_was_loss", False):
            spacing_cd = max(spacing_cd, 180)
        time_since_last = time.time() - last_trade_time
        if time_since_last < spacing_cd:
            failures.append(f"Check 13 Fail: Trade spacing cooldown active ({spacing_cd - time_since_last:.1f}s remaining)")

        # 14. Duplicate candle ID check
        if candle_id and candle_id in traded_candle_ids:
            failures.append(f"Check 14 Fail: Duplicate setup execution prevented (Candle ID {candle_id} already traded)")

        # 15. SL / TP Sanity & Minimum Distance
        sl_dist = abs(entry_price - stop_loss_price)
        if "BTC" in symbol.upper():
            min_sl = 20.0 if self.is_personal else 50.0
        else:
            min_sl = 0.40 if self.is_personal else 1.00
        if sl_dist < min_sl:
            failures.append(f"Check 15 Fail: SL distance ${sl_dist:.2f} below volatility floor ${min_sl:.2f}")


        # 16. Spread check
        if spec:
            max_spread = self.symbols_cfg.get("symbol_settings", {}).get(symbol, {}).get("max_spread_points", 320)
            if spec.spread > max_spread:
                failures.append(f"Check 16 Fail: Current spread {spec.spread} exceeds limit {max_spread}")

        # 17. Free Margin check
        min_margin = 2.0 if self.account_type == "PERSONAL" else 10.0
        if free_margin < min_margin:
            failures.append(f"Check 17 Fail: Free margin ${free_margin:.2f} insufficient (< ${min_margin:.2f})")

        # 18. Daily Trade Cap check
        max_daily = self.risk_config.get("max_daily_trades", 12)
        if self.daily_trade_count >= max_daily:
            failures.append(f"Check 18 Fail: Daily trade cap reached ({self.daily_trade_count}/{max_daily})")

        # 19. Session filter check
        session_allowed = self.is_session_allowed()
        if not session_allowed:
            failures.append(f"Check 19 Fail: Current session not in allowed trading sessions list")

        # 20. Exact Monetary Risk & Hard Reject Ceiling
        expected_monetary_loss = self.calculate_monetary_loss(symbol, entry_price, stop_loss_price, volume)
        if expected_monetary_loss > self.single_trade_hard_reject:
            failures.append(
                f"Check 20 Fail: Expected SL loss ${expected_monetary_loss:.2f} exceeds hard reject limit "
                f"${self.single_trade_hard_reject:.2f}"
            )

        passed = len(failures) == 0
        if not passed:
            logger.warning(f"[{self.account_id.upper()}] [PRE-TRADE REJECTED] {symbol} {order_type}: {failures[0]} (Total {len(failures)} failures)")
        else:
            logger.info(f"[{self.account_id.upper()}] [PRE-TRADE PASSED] 20/20 checks verified! Expected Risk: ${expected_monetary_loss:.2f}")

        return passed, failures, expected_monetary_loss

    def is_session_allowed(self) -> bool:
        """Checks if current time falls within configured allowed trading sessions."""
        if not self.risk_config.get("session_filter_enabled", True):
            return True
        session = self.get_current_trading_session()
        allowed = self.risk_config.get("allowed_sessions", ["London", "London/NY Overlap", "New York", "Asian", "Late Asian/Off-Hours"])
        return session in allowed

    def get_current_trading_session(self) -> str:
        """Determines active forex/crypto trading session by UTC hour."""
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        hour = now_utc.hour

        if 13 <= hour < 17:
            return "London/NY Overlap"
        elif 8 <= hour < 17:
            return "London"
        elif 13 <= hour < 22:
            return "New York"
        elif 0 <= hour < 8:
            return "Asian"
        else:
            return "Late Asian/Off-Hours"

    def get_circuit_breaker_status(self, equity: float) -> str:
        """Returns diagnostic status string."""
        net_pnl = equity - self.daily_start_equity
        trailing_dd = self.lifetime_high_water_equity - equity
        return (
            f"Profile: {self.account_type} | State: {self.trading_state} | Daily P&L: ${net_pnl:+.2f} | "
            f"Trailing DD: ${trailing_dd:.2f} (HWM: ${self.lifetime_high_water_equity:.2f}) | Mult: {self.risk_reduction_multiplier:.2f}x"
        )

    def get_module_performance_summary(self) -> dict:
        """Returns engine breakdown metrics."""
        scalp_pnl = self.daily_pnl_by_engine.get(self.magic_scalper, 0.0)
        musumali_pnl = self.daily_pnl_by_engine.get(self.magic_musumali, 0.0)
        return {
            "total_day_pnl": scalp_pnl + musumali_pnl,
            "scalp_pnl": scalp_pnl,
            "scalp_trades": self.daily_trades_by_engine.get(self.magic_scalper, 0),
            "scalp_wins": self.daily_wins_by_engine.get(self.magic_scalper, 0),
            "musumali_pnl": musumali_pnl,
            "musumali_trades": self.daily_trades_by_engine.get(self.magic_musumali, 0),
            "musumali_wins": self.daily_wins_by_engine.get(self.magic_musumali, 0),
        }

    def get_session_tuning_params(self, session: Optional[str] = None) -> dict:
        """Returns session-specific tuning configuration."""
        cur_session = session or self.get_current_trading_session()
        tuning_cfg = self.risk_config.get("session_tuning", {}).get("sessions", {})
        session_data = tuning_cfg.get(cur_session, {
            "quality_score_threshold": 50,
            "max_spread_points_xau": 320,
            "max_spread_points_btc": 2500,
        })
        return {
            "session": cur_session,
            "quality_score_threshold": session_data.get("quality_score_threshold", 50),
            "max_spread_points": session_data.get("max_spread_points_xau", 320),
            "max_spread_points_xau": session_data.get("max_spread_points_xau", 320),
            "max_spread_points_btc": session_data.get("max_spread_points_btc", 2500),
        }

