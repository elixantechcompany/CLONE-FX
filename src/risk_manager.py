"""
Risk Management and Circuit Breaker Engine
Enforces:
  1. Priority 3: Liquidity Zone Failure Memory & 15-Minute Cooldown.
  2. Priority 4: Daily Max-Loss Hard Circuit Breaker & Consecutive Loss Protector.
  3. Spread Filter & Safe Micro-Lot Position Sizing.
"""

import datetime
import logging
import time
from typing import Dict, Optional, Tuple
import MetaTrader5 as mt5

logger = logging.getLogger("GoldBot.RiskManager")


class RiskManager:
    def __init__(self, config: dict, connector):
        self.config = config
        self.risk_config = config.get("risk_management", {})
        self.circuit_config = config.get("circuit_breakers", {})
        self.zone_config = config.get("zone_management", {})
        self.connector = connector

        # Priority 4: Daily tracking & Circuit Breakers
        self.current_day: Optional[datetime.date] = None
        self.daily_start_equity: float = 0.0
        self.daily_trade_count: int = 0
        self.circuit_tripped: bool = False
        self.trip_reason: str = ""
        self.max_daily_dd_pct = self.circuit_config.get("max_daily_drawdown_percent", 20.0)
        self.max_daily_profit_pct = self.circuit_config.get("max_daily_profit_percent", 50.0)

        # Consecutive Loss Cooling
        self.consecutive_losses: int = 0
        self.max_consecutive_losses = self.circuit_config.get("max_consecutive_losses", 3)
        self.consecutive_loss_cooldown_minutes = self.circuit_config.get("consecutive_loss_cooldown_minutes", 60)
        self.consecutive_loss_cooldown_until: float = 0.0

        # Priority 3: Liquidity Zone Failure Memory & Cooldown
        self.zone_failures: Dict[float, int] = {}
        self.zone_cooldown_until: Dict[float, float] = {}
        self.max_zone_failures = self.zone_config.get("max_zone_failures", 2)
        self.zone_cooldown_minutes = self.zone_config.get("zone_cooldown_minutes", 15)

        # Fix 10 & 13: Magic Numbers & Independent Daily Performance Tracking per Module
        self.magic_scalper = config.get("m1_scalper", {}).get("magic_number", 1001)
        self.magic_musumali = config.get("musumali_strategy", {}).get("magic_number", 2001)
        self.daily_pnl_scalp: float = 0.0
        self.daily_pnl_musumali: float = 0.0
        self.daily_trades_scalp: int = 0
        self.daily_trades_musumali: int = 0
        self.daily_wins_scalp: int = 0
        self.daily_wins_musumali: int = 0

        # Fix 17: Per-Module Consecutive-Loss Circuit Breakers
        self.consecutive_loss_threshold = self.circuit_config.get("max_consecutive_losses", 3)
        self.consecutive_loss_window_seconds = self.circuit_config.get("consecutive_loss_window_minutes", 30) * 60.0
        self.circuit_breaker_cooldown_seconds = self.circuit_config.get("circuit_breaker_cooldown_minutes", 20) * 60.0
        self.module_consecutive_losses: Dict[int, int] = {
            self.magic_scalper: 0,
            self.magic_musumali: 0,
        }
        self.module_loss_timestamps: Dict[int, List[float]] = {
            self.magic_scalper: [],
            self.magic_musumali: [],
        }
        self.module_cooldown_until: Dict[int, float] = {
            self.magic_scalper: 0.0,
            self.magic_musumali: 0.0,
        }

    def reset_daily_metrics_if_needed(self, current_equity: float):
        """Resets the day's baseline equity and counters at midnight UTC."""
        today = datetime.datetime.now(datetime.timezone.utc).date()
        if self.current_day != today or self.daily_start_equity <= 0:
            self.current_day = today
            self.daily_start_equity = current_equity
            self.daily_trade_count = 0
            self.circuit_tripped = False
            self.trip_reason = ""
            self.consecutive_losses = 0
            self.consecutive_loss_cooldown_until = 0.0
            self.zone_failures.clear()
            self.zone_cooldown_until.clear()
            self.daily_pnl_scalp = 0.0
            self.daily_pnl_musumali = 0.0
            self.daily_trades_scalp = 0
            self.daily_trades_musumali = 0
            self.daily_wins_scalp = 0
            self.daily_wins_musumali = 0
            self.module_consecutive_losses = {self.magic_scalper: 0, self.magic_musumali: 0}
            self.module_loss_timestamps = {self.magic_scalper: [], self.magic_musumali: []}
            self.module_cooldown_until = {self.magic_scalper: 0.0, self.magic_musumali: 0.0}
            logger.info(
                f"Daily Risk Baseline Initialized for {today}: Baseline Equity = ${current_equity:.2f} | "
                f"Max Daily DD Limit: -{self.max_daily_dd_pct}% (-${current_equity * (self.max_daily_dd_pct/100.0):.2f})"
            )

    def record_trade_placed(self, magic: Optional[int] = None):
        """Increments the daily executed trade counter."""
        self.daily_trade_count += 1
        max_trades = self.risk_config.get("max_daily_trades", 15)
        logger.info(f"Daily trade count incremented: {self.daily_trade_count}/{max_trades}")

    def record_trade_result(self, zone_id: Optional[float], profit: float, magic: Optional[int] = None):
        """
        Priority 3, 4, Fix 13 & Fix 17: Updates zone failure memory, per-module consecutive losses, and performance.
        """
        now = time.time()

        # Fix 13: Independent Per-Module Performance Tracking
        m_key = self.magic_scalper if magic in (self.magic_scalper, 1001, 888777) else (
            self.magic_musumali if magic in (self.magic_musumali, 2001, 999888) else (magic or 0)
        )
        m_name = "Scalp" if m_key == self.magic_scalper else ("Musumali" if m_key == self.magic_musumali else f"Module_{m_key}")

        if m_key == self.magic_scalper:
            self.daily_pnl_scalp += profit
            self.daily_trades_scalp += 1
            if profit > 0.0:
                self.daily_wins_scalp += 1
        elif m_key == self.magic_musumali:
            self.daily_pnl_musumali += profit
            self.daily_trades_musumali += 1
            if profit > 0.0:
                self.daily_wins_musumali += 1

        logger.info(
            f"[DAILY MODULE P&L AUDIT FIX 13] Scalp P&L Today: ${self.daily_pnl_scalp:+.2f} ({self.daily_trades_scalp} trades, {self.daily_wins_scalp}W) | "
            f"Musumali P&L Today: ${self.daily_pnl_musumali:+.2f} ({self.daily_trades_musumali} trades, {self.daily_wins_musumali}W) | "
            f"Total Day P&L: ${(self.daily_pnl_scalp + self.daily_pnl_musumali):+.2f}"
        )

        if profit < -0.05:
            # Global & Per-Module Loss Recording
            self.consecutive_losses += 1
            logger.warning(f"Trade closed with loss: ${profit:.2f} | Consecutive Losses: {self.consecutive_losses}")

            if zone_id is not None:
                self.zone_failures[zone_id] = self.zone_failures.get(zone_id, 0) + 1
                cooldown_expiry = now + (self.zone_cooldown_minutes * 60)
                self.zone_cooldown_until[zone_id] = cooldown_expiry
                logger.warning(
                    f"[ZONE COOLDOWN] Zone {zone_id:.1f} hit failure #{self.zone_failures[zone_id]}. "
                    f"Locked for {self.zone_cooldown_minutes} minutes."
                )

            # Fix 17: Per-Module Clustered Consecutive Loss Circuit Breaker
            if m_key not in self.module_loss_timestamps:
                self.module_loss_timestamps[m_key] = []
            self.module_loss_timestamps[m_key].append(now)
            # Prune losses outside window
            self.module_loss_timestamps[m_key] = [
                t for t in self.module_loss_timestamps[m_key] if now - t <= self.consecutive_loss_window_seconds
            ]
            self.module_consecutive_losses[m_key] = self.module_consecutive_losses.get(m_key, 0) + 1

            if (
                self.module_consecutive_losses[m_key] >= self.consecutive_loss_threshold
                and len(self.module_loss_timestamps[m_key]) >= self.consecutive_loss_threshold
            ):
                expiry = now + self.circuit_breaker_cooldown_seconds
                self.module_cooldown_until[m_key] = expiry
                expiry_str = datetime.datetime.fromtimestamp(expiry, tz=datetime.timezone.utc).strftime("%H:%M:%S UTC")
                logger.warning(
                    f"[CIRCUIT BREAKER FIX 17] {m_name} module (Magic #{m_key}) paused — "
                    f"{self.module_consecutive_losses[m_key]} consecutive losses within {self.consecutive_loss_window_seconds/60:.0f}m. "
                    f"Cooldown active until {expiry_str} ({self.circuit_breaker_cooldown_seconds/60:.0f}m cooldown)."
                )

            if self.consecutive_losses >= self.max_consecutive_losses:
                self.consecutive_loss_cooldown_until = now + (self.consecutive_loss_cooldown_minutes * 60)
                logger.warning(
                    f"[CONSECUTIVE LOSS PAUSE] {self.consecutive_losses} losses in a row across account! "
                    f"Trading paused for {self.consecutive_loss_cooldown_minutes} minutes."
                )
        elif profit > 0.05:
            # Win recorded -> Reset consecutive losses for this module
            self.consecutive_losses = 0
            self.module_consecutive_losses[m_key] = 0
            self.module_loss_timestamps[m_key] = []
            if zone_id is not None and zone_id in self.zone_failures:
                self.zone_failures[zone_id] = max(0, self.zone_failures[zone_id] - 1)
                logger.info(f"Trade closed with profit: +${profit:.2f} | Zone {zone_id:.1f} failure count decremented.")

    def is_module_in_cooldown(self, magic: int) -> Tuple[bool, str]:
        """
        Fix 17 & Fix 18: Checks whether a specific module is currently locked in circuit breaker cooldown.
        Emits explicit re-arm log the moment cooldown expires.
        """
        if not hasattr(self, "module_was_in_cooldown"):
            self.module_was_in_cooldown = {}

        expiry = self.module_cooldown_until.get(magic, 0.0)
        now = time.time()
        m_name = "Scalp" if magic == self.magic_scalper else ("Musumali" if magic == self.magic_musumali else f"Module_{magic}")

        if now < expiry:
            self.module_was_in_cooldown[magic] = True
            rem_s = expiry - now
            expiry_str = datetime.datetime.fromtimestamp(expiry, tz=datetime.timezone.utc).strftime("%H:%M:%S UTC")
            return True, f"PAUSED ({m_name} in cooldown until {expiry_str}, {rem_s:.0f}s remaining)"
        else:
            # Check if module just transitioned from in-cooldown to active (Fix 18)
            if self.module_was_in_cooldown.get(magic, False):
                self.module_was_in_cooldown[magic] = False
                self.module_consecutive_losses[magic] = 0
                self.module_loss_timestamps[magic] = []
                logger.info(
                    f"[CIRCUIT BREAKER RE-ARMED FIX 18] Circuit breaker cooldown expired for {m_name} (Magic #{magic}) — "
                    f"Module re-armed for live trading!"
                )
            return False, "ACTIVE"

    def get_circuit_breaker_status(self) -> str:
        """Fix 18: Returns human-readable status of both module circuit breakers."""
        scalp_in_cd, scalp_msg = self.is_module_in_cooldown(self.magic_scalper)
        musumali_in_cd, musumali_msg = self.is_module_in_cooldown(self.magic_musumali)
        s_status = scalp_msg if scalp_in_cd else "ACTIVE (0 losses)"
        m_status = musumali_msg if musumali_in_cd else "ACTIVE (0 losses)"
        return f"Scalp #1001: {s_status} | Musumali #2001: {m_status}"

    def get_module_performance_summary(self) -> dict:
        """Fix 13: Returns dictionary snapshot of per-module daily performance metrics."""
        return {
            "scalp_pnl": self.daily_pnl_scalp,
            "scalp_trades": self.daily_trades_scalp,
            "scalp_wins": self.daily_wins_scalp,
            "musumali_pnl": self.daily_pnl_musumali,
            "musumali_trades": self.daily_trades_musumali,
            "musumali_wins": self.daily_wins_musumali,
            "total_day_pnl": self.daily_pnl_scalp + self.daily_pnl_musumali,
        }

    def is_zone_allowed(self, zone_id: Optional[float]) -> Tuple[bool, str]:
        """
        Priority 3: Checks if a liquidity price zone is currently in cooldown due to previous failures.
        """
        if zone_id is None:
            return True, "OK"

        now = time.time()
        cooldown_until = self.zone_cooldown_until.get(zone_id, 0.0)
        failures = self.zone_failures.get(zone_id, 0)

        if now < cooldown_until and failures >= self.max_zone_failures:
            rem_sec = int(cooldown_until - now)
            reason = f"Zone {zone_id:.1f} in cooldown ({failures} failures, {rem_sec}s remaining)"
            return False, reason

        return True, "OK"

    def check_circuit_breakers(self, current_equity: float) -> Tuple[bool, str]:
        """
        Priority 4: Validates daily loss circuit breaker, consecutive loss cooldown, and trade caps.
        Returns: (can_trade: bool, reason: str)
        """
        self.reset_daily_metrics_if_needed(current_equity)
        now = time.time()

        # Check hard daily trip
        if self.circuit_tripped:
            return False, f"Trading halted for today: {self.trip_reason}"

        # Check consecutive loss cooldown
        if now < self.consecutive_loss_cooldown_until:
            rem_min = int((self.consecutive_loss_cooldown_until - now) / 60)
            return False, f"Consecutive loss cooling active ({rem_min} mins remaining)"

        # Check daily trade cap
        max_trades = self.risk_config.get("max_daily_trades", 15)
        if self.daily_trade_count >= max_trades:
            return False, f"Daily trade cap reached ({self.daily_trade_count}/{max_trades})"

        # Check daily drawdown circuit breaker based on realized closed trade losses
        realized_pnl = self.daily_pnl_scalp + self.daily_pnl_musumali
        ref_balance = max(self.daily_start_equity, current_equity, 10.0)
        if realized_pnl < 0:
            realized_loss = abs(realized_pnl)
            daily_loss_pct = (realized_loss / ref_balance) * 100.0
            if daily_loss_pct >= self.max_daily_dd_pct:
                self.circuit_tripped = True
                self.trip_reason = (
                    f"Daily Max-Loss Circuit Breaker Tripped! Realized Daily Loss: -${realized_loss:.2f} "
                    f"(-{daily_loss_pct:.1f}% >= -{self.max_daily_dd_pct}%)"
                )
                logger.critical(f"================================================================")
                logger.critical(f" [CIRCUIT BREAKER] {self.trip_reason}")
                logger.critical(f" Trading HALTED for remainder of day to protect capital.")
                logger.critical(f"================================================================")
                return False, self.trip_reason

        # Profit lock check based on realized closed trade P&L
        if self.max_daily_profit_pct > 0 and realized_pnl > 0:
            profit_gain_pct = (realized_pnl / ref_balance) * 100.0
            if profit_gain_pct >= self.max_daily_profit_pct:
                self.circuit_tripped = True
                self.trip_reason = f"Daily Profit Target Achieved (Realized PnL: +${realized_pnl:.2f}, +{profit_gain_pct:.2f}%). Profits locked for today."
                logger.info(f"PROFIT TARGET REACHED: {self.trip_reason}")
                return False, self.trip_reason

        return True, "OK"

    def check_spread_allowed(self, symbol: str) -> Tuple[bool, int]:
        """Checks if current spread is within the safety threshold."""
        info = mt5.symbol_info(symbol)
        if info is None:
            return False, 9999

        current_spread = info.spread
        max_allowed = self.risk_config.get("max_spread_points", 350)

        if current_spread > max_allowed:
            logger.warning(
                f"Spread too high on {symbol}: current {current_spread} > max {max_allowed} points. Trade filtered."
            )
            return False, current_spread

        return True, current_spread

    def calculate_lot_size(
        self,
        symbol: str,
        entry_price: float,
        stop_loss_price: float,
        equity: float,
        open_trades_count: int = 0,
    ) -> float:
        """
        Fix 7 & Fix 12: Risk-Based Position Sizing with Shared Account Risk Pool Awareness.
        Calculates lot size based on a fixed risk percentage of equity divided by the stop loss distance.
        Ensures total simultaneous portfolio risk across both modules stays within max_total_account_risk_percent.
        """
        info = mt5.symbol_info(symbol)
        min_vol = info.volume_min if info else 0.01
        max_vol = info.volume_max if info else 200.0
        vol_step = info.volume_step if info else 0.01
        contract_size = info.trade_contract_size if info else 100.0

        mode = self.risk_config.get("lot_mode", "risk_percent")
        if mode == "fixed":
            fixed_lot = self.risk_config.get("fixed_lot_size", 0.01)
            return max(min_vol, min(round(fixed_lot / vol_step) * vol_step, max_vol))

        base_risk_pct = self.risk_config.get("risk_per_trade_percent", 1.5)
        max_account_risk_pct = self.risk_config.get("max_total_account_risk_percent", 6.0)

        # Shared Risk Budget Allocation across both active modules (Fix 12)
        committed_risk = open_trades_count * base_risk_pct
        remaining_risk = max(0.5, max_account_risk_pct - committed_risk)
        effective_risk_pct = min(base_risk_pct, remaining_risk)

        dollar_risk = max(equity * (effective_risk_pct / 100.0), 0.20)

        sl_distance = abs(entry_price - stop_loss_price)
        if sl_distance <= 0:
            sl_distance = 1.0

        # Dollar move on Gold = sl_distance * contract_size per 1.00 lot
        raw_lots = dollar_risk / (sl_distance * contract_size)
        step_lots = round(raw_lots / vol_step) * vol_step
        final_lots = round(max(min_vol, min(step_lots, max_vol)), 2)

        logger.info(
            f"[POSITION SIZING FIX 7 & 12] Equity: ${equity:.2f} | Effective Risk: {effective_risk_pct:.2f}% (${dollar_risk:.2f}) "
            f"(Open: {open_trades_count}, Pool Cap: {max_account_risk_pct}%) | SL Dist: ${sl_distance:.2f} -> Sized: {final_lots} lots"
        )
        return final_lots
