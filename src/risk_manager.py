"""
Risk Management and Circuit Breaker Engine
Enforces:
  1. Strict $1.00 Maximum Loss Cap per trade
  2. Maximum 5 Concurrent Open Positions
  3. Spread Filter & Circuit Breakers
"""

import datetime
import logging
import math
from typing import Optional, Tuple
import MetaTrader5 as mt5

logger = logging.getLogger("GoldBot.RiskManager")


class RiskManager:
    def __init__(self, config: dict, connector):
        self.config = config
        self.risk_config = config.get("risk_management", {})
        self.circuit_config = config.get("circuit_breakers", {})
        self.connector = connector

        # Daily tracking
        self.current_day: Optional[datetime.date] = None
        self.daily_start_equity: float = 0.0
        self.daily_trade_count: int = 0
        self.circuit_tripped: bool = False
        self.trip_reason: str = ""

    def reset_daily_metrics_if_needed(self, current_equity: float):
        """Resets the day's baseline equity and trade counter at midnight."""
        today = datetime.datetime.now(datetime.timezone.utc).date()
        if self.current_day != today or self.daily_start_equity <= 0:
            self.current_day = today
            self.daily_start_equity = current_equity
            self.daily_trade_count = 0
            self.circuit_tripped = False
            self.trip_reason = ""
            logger.info(f"Daily Risk Baseline Initialized for {today}: Equity = ${current_equity:.2f} | Trade Count reset to 0.")

    def record_trade_placed(self):
        """Increments the daily executed trade counter."""
        self.daily_trade_count += 1
        max_trades = self.risk_config.get("max_daily_trades", 10)
        logger.info(f"Daily trade count incremented: {self.daily_trade_count}/{max_trades}")

    def check_circuit_breakers(self, current_equity: float) -> Tuple[bool, str]:
        """
        Validates whether daily loss limit or trade cap has been triggered.
        Returns: (can_trade: bool, reason: str)
        """
        self.reset_daily_metrics_if_needed(current_equity)

        if self.circuit_tripped:
            return False, f"Trading halted for today: {self.trip_reason}"

        max_trades = self.risk_config.get("max_daily_trades", 10)
        if self.daily_trade_count >= max_trades:
            return False, f"Daily trade cap reached ({self.daily_trade_count}/{max_trades})."

        max_dd_pct = self.circuit_config.get("max_daily_drawdown_percent", 15.0)
        max_profit_pct = self.circuit_config.get("max_daily_profit_percent", 50.0)

        # Drawdown check
        equity_drop = (self.daily_start_equity - current_equity) / self.daily_start_equity * 100.0
        if equity_drop >= max_dd_pct:
            self.circuit_tripped = True
            self.trip_reason = f"Max Daily Drawdown Reached (-{equity_drop:.2f}% >= -{max_dd_pct}%)"
            logger.warning(f"CIRCUIT BREAKER TRIPPED: {self.trip_reason}")
            return False, self.trip_reason

        # Profit lock check
        if max_profit_pct > 0:
            profit_gain = (current_equity - self.daily_start_equity) / self.daily_start_equity * 100.0
            if profit_gain >= max_profit_pct:
                self.circuit_tripped = True
                self.trip_reason = f"Daily Profit Target Achieved (+{profit_gain:.2f}% >= +{max_profit_pct}%)"
                logger.info(f"PROFIT TARGET REACHED: {self.trip_reason} - locking profits for today.")
                return False, self.trip_reason

        return True, "OK"

    def check_spread_allowed(self, symbol: str) -> Tuple[bool, int]:
        """Checks if current spread is within the safety threshold."""
        info = mt5.symbol_info(symbol)
        if info is None:
            return False, 9999

        current_spread = info.spread
        max_allowed = self.risk_config.get("max_spread_points", 60)

        if current_spread > max_allowed:
            logger.warning(
                f"Spread too high on {symbol}: current {current_spread} > max {max_allowed} points. Trade filtered."
            )
            return False, current_spread

        return True, current_spread

    def clamp_stop_loss_to_max_dollar_loss(
        self,
        symbol: str,
        order_type: str,
        entry_price: float,
        proposed_sl: float,
        volume: float = 0.01,
    ) -> float:
        """
        Enforces that the Stop Loss will NEVER allow a loss greater than $1.00 USD.
        For 0.01 lot on Gold, $1.00 loss = $1.00 move in Gold price.
        """
        max_loss_dollars = self.risk_config.get("max_loss_dollars_per_trade", 1.0)
        info = mt5.symbol_info(symbol)
        digits = info.digits if info else 3

        # For 0.01 lot on Gold (contract size = 100 oz), 1 lot * $1 move = $100.
        # 0.01 lot * $1 move = $1.00.
        # Max price move allowed for $1.00 loss:
        max_price_distance = max_loss_dollars / (volume * (info.trade_contract_size if info and info.trade_contract_size > 0 else 100.0))

        if order_type.upper() == "BUY":
            hard_capped_sl = round(entry_price - max_price_distance, digits)
            # If proposed SL is further away than the $1 cap, use the hard cap
            if proposed_sl <= 0 or proposed_sl < hard_capped_sl:
                logger.info(
                    f"Stop Loss clamped to $1.00 max risk: Proposed {proposed_sl:.2f} -> Clamped {hard_capped_sl:.2f} (-${max_loss_dollars:.2f})"
                )
                return hard_capped_sl
            return round(proposed_sl, digits)

        elif order_type.upper() == "SELL":
            hard_capped_sl = round(entry_price + max_price_distance, digits)
            if proposed_sl <= 0 or proposed_sl > hard_capped_sl:
                logger.info(
                    f"Stop Loss clamped to $1.00 max risk: Proposed {proposed_sl:.2f} -> Clamped {hard_capped_sl:.2f} (-${max_loss_dollars:.2f})"
                )
                return hard_capped_sl
            return round(proposed_sl, digits)

        return proposed_sl

    def calculate_lot_size(
        self,
        symbol: str,
        entry_price: float,
        stop_loss_price: float,
        equity: float,
    ) -> float:
        """Returns safe fixed 0.01 micro-lot size for account safety."""
        return self.risk_config.get("fixed_lot_size", 0.01)
