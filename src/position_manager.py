"""
Intelligent Position Management & Exit Engine
Implements:
1. 6-Stage Position State Machine (INITIAL -> PROFITABLE -> STRONG_WINNER -> MOMENTUM_WEAKENING -> CONFIRMED_REVERSAL -> EMERGENCY).
2. Multi-Signal Continuation vs. Reversal Confidence Scoring (0 - 100).
3. Dynamic R-Multiple Profit Protection (+0.5R, +0.8R, +1.0R, +1.5R, +2.0R).
4. Volatility-Aware Dynamic Giveback & Peak R Decay Guardian.
5. Stale Trade Timeout (Time-based Trade Failure Detection).
6. Thesis Invalidation Detector.
7. Engine-Specific Exit Profiles (Musumali HTF vs. Micro-Scalper M1/M5).
"""

import enum
import logging
import time
from typing import Dict, List, Optional, Tuple, Union
import pandas as pd
import MetaTrader5 as mt5

logger = logging.getLogger("GoldBot.PositionManager")


class PositionState(enum.Enum):
    STATE_1_INITIAL = "INITIAL"
    STATE_2_PROFITABLE = "PROFITABLE"
    STATE_3_STRONG_WINNER = "STRONG_WINNER"
    STATE_4_MOMENTUM_WEAKENING = "MOMENTUM_WEAKENING"
    STATE_5_CONFIRMED_REVERSAL = "CONFIRMED_REVERSAL"
    STATE_6_EMERGENCY = "EMERGENCY"


class ExitDecision(enum.Enum):
    HOLD = "HOLD"
    TIGHTEN_PROTECTION = "TIGHTEN_PROTECTION"
    LOCK_BREAKEVEN = "LOCK_BREAKEVEN"
    TRAIL_ATR = "TRAIL_ATR"
    CLOSE_MARKET = "CLOSE_MARKET"
    PARTIAL_CLOSE = "PARTIAL_CLOSE"


class PositionRecord:
    """Tracks stateful analytics for a single active trade ticket."""
    def __init__(
        self,
        ticket: int,
        symbol: str,
        pos_type: str,
        volume: float,
        open_price: float,
        initial_sl: float,
        initial_tp: float,
        magic: int,
        thesis_anchor: Optional[float] = None,
    ):
        self.ticket = ticket
        self.symbol = symbol
        self.pos_type = pos_type
        self.volume = volume
        self.open_price = open_price
        self.initial_sl = initial_sl
        self.initial_tp = initial_tp
        self.magic = magic
        self.thesis_anchor = thesis_anchor

        self.open_time = time.time()
        self.initial_risk_dist = abs(open_price - initial_sl) if initial_sl > 0 else 2.0
        self.initial_risk_dollars = self.initial_risk_dist * volume * 100.0  # 1R in USD (XAUUSD standard)

        self.state = PositionState.STATE_1_INITIAL
        self.peak_r = 0.0
        self.current_r = 0.0
        self.peak_profit_dollars = 0.0
        self.bars_held = 0
        self.last_bar_time: Optional[str] = None
        
        self.continuation_score = 50
        self.reversal_score = 50
        self.be_applied = False
        self.partial_closed = False
        self.exit_reason: Optional[str] = None


class IntelligentExitEngine:
    def __init__(self, config: dict):
        self.config = config
        self.profit_cfg = config.get("profit_management", {})
        self.cb_cfg = config.get("circuit_breakers", {})

        # R-Multiple Thresholds
        self.r_be_trigger = self.profit_cfg.get("breakeven_trigger_r", 0.30)
        self.r_be_lock = self.profit_cfg.get("breakeven_lock_r", 0.10)
        self.r_tier1_protect_trigger = self.profit_cfg.get("tier1_protect_trigger_r", 0.55)
        self.r_tier1_protect_lock = self.profit_cfg.get("tier1_protect_lock_r", 0.30)
        self.r_tier2_protect_trigger = self.profit_cfg.get("tier2_protect_trigger_r", 0.85)
        self.r_tier2_protect_lock = self.profit_cfg.get("tier2_protect_lock_r", 0.55)
        self.r_tier3_protect_trigger = self.profit_cfg.get("tier3_protect_trigger_r", 1.10)
        self.r_tier3_protect_lock = self.profit_cfg.get("tier3_protect_lock_r", 0.80)

        # Reversal & Continuation Thresholds
        self.reversal_exit_threshold = self.profit_cfg.get("reversal_exit_threshold", 70)
        self.reversal_warning_threshold = self.profit_cfg.get("reversal_warning_threshold", 50)
        self.continuation_strong_threshold = self.profit_cfg.get("continuation_strong_threshold", 60)

        # Stale Trade Timeout Limits
        self.scalp_max_bars_timeout = self.profit_cfg.get("scalp_timeout_bars", 10)  # 10 M1 bars = 10 mins
        self.musumali_max_bars_timeout = self.profit_cfg.get("musumali_timeout_bars", 20)  # 20 M15/M30 bars

        # Dynamic Giveback Settings
        self.giveback_min_peak_r = self.profit_cfg.get("giveback_min_peak_r", 0.50)
        self.giveback_max_r_decay = self.profit_cfg.get("giveback_max_r_decay", 0.25)

        # Direct Agile Dollar Accumulation Step Locking ($0.50 Accumulation Ratchet)
        self.dollar_step_lock_enabled = self.profit_cfg.get("dollar_step_lock_enabled", True)
        self.dollar_step_size = float(self.profit_cfg.get("dollar_step_size", 0.50))
        self.dollar_step_buffer = float(self.profit_cfg.get("dollar_step_buffer", 0.20))

        # Active trade records map: ticket -> PositionRecord
        self.records: Dict[int, PositionRecord] = {}

    def register_position(
        self,
        ticket: int,
        symbol: str,
        pos_type: str,
        volume: float,
        open_price: float,
        sl: float,
        tp: float,
        magic: int,
        thesis_anchor: Optional[float] = None,
    ) -> PositionRecord:
        """Registers a newly opened position for stateful tracking."""
        if ticket not in self.records:
            self.records[ticket] = PositionRecord(
                ticket=ticket,
                symbol=symbol,
                pos_type=pos_type,
                volume=volume,
                open_price=open_price,
                initial_sl=sl,
                initial_tp=tp,
                magic=magic,
                thesis_anchor=thesis_anchor,
            )
            logger.info(
                f"[POSITION REGISTERED] Ticket #{ticket} ({pos_type} {volume} lots @ {open_price:.2f}) | "
                f"Initial SL: {sl:.2f} (1R = ${self.records[ticket].initial_risk_dollars:.2f}) | Initial TP: {tp:.2f}"
            )
        return self.records[ticket]

    def cleanup_closed_tickets(self, current_open_tickets: List[int]):
        """Removes records of positions that have closed."""
        stale_tickets = [t for t in self.records if t not in current_open_tickets]
        for t in stale_tickets:
            del self.records[t]

    def evaluate_reversal_confidence_score(
        self,
        symbol: str,
        pos_type: str,
        magic: int,
        df_m1: Optional[pd.DataFrame],
        df_m5: Optional[pd.DataFrame],
        df_m15: Optional[pd.DataFrame],
        live_tick,
        thesis_anchor: Optional[float] = None,
    ) -> Tuple[int, dict]:
        """
        Computes composite Reversal Confidence Score (0 - 100) across independent technical dimensions.
        """
        breakdown = {}
        score = 0

        # Dimension 1: M1 Market Structure Break (+25 pts)
        s_m1 = 0
        if df_m1 is not None and len(df_m1) >= 5:
            last_m1 = df_m1.iloc[-2]
            prev_m1 = df_m1.iloc[-3]
            if pos_type == "BUY":
                # Bearish structure break: closed below recent M1 swing low
                recent_low = df_m1["low"].iloc[-7:-2].min()
                if last_m1["close"] < recent_low or (live_tick and live_tick.bid < recent_low):
                    s_m1 = 25
                elif last_m1["close"] < prev_m1["low"]:
                    s_m1 = 15
            elif pos_type == "SELL":
                # Bullish structure break: closed above recent M1 swing high
                recent_high = df_m1["high"].iloc[-7:-2].max()
                if last_m1["close"] > recent_high or (live_tick and live_tick.ask > recent_high):
                    s_m1 = 25
                elif last_m1["close"] > prev_m1["high"]:
                    s_m1 = 15
        breakdown["m1_structure"] = s_m1
        score += s_m1

        # Dimension 2: M5 Momentum Shift / Reversal Candle (+20 pts)
        s_m5 = 0
        if df_m5 is not None and len(df_m5) >= 5:
            last_m5 = df_m5.iloc[-2]
            if pos_type == "BUY":
                if last_m5["close"] < last_m5["open"]:  # Strong red body on M5
                    m5_range = last_m5["high"] - last_m5["low"]
                    body = last_m5["open"] - last_m5["close"]
                    s_m5 = 20 if (m5_range > 0 and body / m5_range >= 0.50) else 10
            elif pos_type == "SELL":
                if last_m5["close"] > last_m5["open"]:  # Strong green body on M5
                    m5_range = last_m5["high"] - last_m5["low"]
                    body = last_m5["close"] - last_m5["open"]
                    s_m5 = 20 if (m5_range > 0 and body / m5_range >= 0.50) else 10
        breakdown["m5_momentum"] = s_m5
        score += s_m5

        # Dimension 3: Fast / Slow EMA Trend Dynamics (+15 pts)
        s_ema = 0
        df_target = df_m1 if magic == 1001 else df_m5
        if df_target is not None and len(df_target) >= 20:
            df_target = df_target.copy()
            df_target["ema_fast"] = df_target["close"].ewm(span=9, adjust=False).mean()
            df_target["ema_slow"] = df_target["close"].ewm(span=21, adjust=False).mean()
            last_bar = df_target.iloc[-2]
            if pos_type == "BUY" and (last_bar["ema_fast"] < last_bar["ema_slow"] or last_bar["close"] < last_bar["ema_slow"]):
                s_ema = 15
            elif pos_type == "SELL" and (last_bar["ema_fast"] > last_bar["ema_slow"] or last_bar["close"] > last_bar["ema_slow"]):
                s_ema = 15
        breakdown["ema_trend"] = s_ema
        score += s_ema

        # Dimension 4: RSI Momentum Exhaustion / Deterioration (+10 pts)
        s_rsi = 0
        if df_m5 is not None and len(df_m5) >= 15:
            delta = df_m5["close"].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / (loss + 1e-9)
            rsi = 100 - (100 / (1 + rs)).iloc[-2]
            if pos_type == "BUY" and (rsi < 42.0 or rsi > 78.0):
                s_rsi = 10
            elif pos_type == "SELL" and (rsi > 58.0 or rsi < 22.0):
                s_rsi = 10
        breakdown["rsi_exhaustion"] = s_rsi
        score += s_rsi

        # Dimension 5: Rejection / Opposing Pinbar Formation (+10 pts)
        s_rejection = 0
        if df_m1 is not None and len(df_m1) >= 3:
            last_bar = df_m1.iloc[-2]
            b_range = last_bar["high"] - last_bar["low"]
            if b_range > 0:
                if pos_type == "BUY":
                    upper_wick = last_bar["high"] - max(last_bar["open"], last_bar["close"])
                    if (upper_wick / b_range) >= 0.45:  # Shooting star / topping tail
                        s_rejection = 10
                elif pos_type == "SELL":
                    lower_wick = min(last_bar["open"], last_bar["close"]) - last_bar["low"]
                    if (lower_wick / b_range) >= 0.45:  # Hammer / bottoming tail
                        s_rejection = 10
        breakdown["rejection_pinbar"] = s_rejection
        score += s_rejection

        # Dimension 6: M15 Trend Slope Deterioration (+10 pts)
        s_m15 = 0
        if df_m15 is not None and len(df_m15) >= 25:
            df_m15 = df_m15.copy()
            df_m15["ema20"] = df_m15["close"].ewm(span=20, adjust=False).mean()
            slope = df_m15["ema20"].iloc[-2] - df_m15["ema20"].iloc[-5]
            if pos_type == "BUY" and slope < -0.10:
                s_m15 = 10
            elif pos_type == "SELL" and slope > 0.10:
                s_m15 = 10
        breakdown["m15_slope"] = s_m15
        score += s_m15

        # Dimension 7: Thesis Invalidation / Anchor Breach (+10 pts)
        s_thesis = 0
        if thesis_anchor is not None and live_tick is not None:
            if pos_type == "BUY" and live_tick.bid < (thesis_anchor - 0.50):
                s_thesis = 10
            elif pos_type == "SELL" and live_tick.ask > (thesis_anchor + 0.50):
                s_thesis = 10
        breakdown["thesis_anchor"] = s_thesis
        score += s_thesis

        total_reversal_score = min(100, score)
        return total_reversal_score, breakdown

    def evaluate_continuation_confidence_score(
        self,
        symbol: str,
        pos_type: str,
        df_m1: Optional[pd.DataFrame],
        df_m5: Optional[pd.DataFrame],
        live_tick,
        current_r: float,
    ) -> int:
        """
        Evaluates forward continuation momentum (0 to 100).
        Measures whether the trade is actively pushing into profit vs stagnating.
        """
        score = 0
        
        # 1. Price relative to Fast EMA (+25 pts)
        if df_m1 is not None and len(df_m1) >= 10:
            ema9 = df_m1["close"].ewm(span=9, adjust=False).mean().iloc[-2]
            last_c = df_m1["close"].iloc[-2]
            if pos_type == "BUY" and last_c > ema9:
                score += 25
            elif pos_type == "SELL" and last_c < ema9:
                score += 25

        # 2. Recent Candle Push / Color (+25 pts)
        if df_m1 is not None and len(df_m1) >= 5:
            last_bar = df_m1.iloc[-2]
            if pos_type == "BUY" and last_bar["close"] > last_bar["open"]:
                score += 25
            elif pos_type == "SELL" and last_bar["close"] < last_bar["open"]:
                score += 25

        # 3. Positive R Progress (+25 pts)
        if current_r >= 0.30:
            score += 25
        elif current_r > 0.0:
            score += 10

        # 4. M5 Momentum Alignment (+25 pts)
        if df_m5 is not None and len(df_m5) >= 5:
            last_m5 = df_m5.iloc[-2]
            if pos_type == "BUY" and last_m5["close"] > last_m5["open"]:
                score += 25
            elif pos_type == "SELL" and last_m5["close"] < last_m5["open"]:
                score += 25

        return min(100, score)

    def evaluate_position_lifecycle(
        self,
        pos_dict: dict,
        df_m1: Optional[pd.DataFrame],
        df_m5: Optional[pd.DataFrame],
        df_m15: Optional[pd.DataFrame],
        live_tick,
        live_atr: float = 2.0,
        digits: int = 3,
    ) -> Tuple[ExitDecision, Optional[float], str]:
        """
        Full tick-by-tick evaluation of an open position through the 6-stage state machine.
        Returns: (ExitDecision, target_new_sl, reason_text)
        """
        ticket = pos_dict["ticket"]
        p_type = pos_dict["type"]
        vol = pos_dict["volume"]
        open_price = pos_dict["price_open"]
        curr_price = pos_dict["price_current"]
        current_sl = pos_dict.get("sl", 0.0)
        current_tp = pos_dict.get("tp", 0.0)
        profit = pos_dict.get("profit", 0.0)
        magic = pos_dict.get("magic", 1001)

        # Get or register state record
        rec = self.records.get(ticket)
        if rec is None:
            rec = self.register_position(
                ticket=ticket,
                symbol=pos_dict.get("symbol", "XAUUSDm"),
                pos_type=p_type,
                volume=vol,
                open_price=open_price,
                sl=current_sl,
                tp=current_tp,
                magic=magic,
            )

        # Recalculate R and peak metrics
        risk_dist = rec.initial_risk_dollars / (vol * 100.0) if rec.initial_risk_dollars > 0 else max(abs(open_price - current_sl), 1.0)
        if risk_dist <= 0:
            risk_dist = 1.0
        price_gain = (curr_price - open_price) if p_type == "BUY" else (open_price - curr_price)
        current_r = price_gain / risk_dist

        rec.current_r = current_r
        rec.peak_r = max(rec.peak_r, current_r)
        rec.peak_profit_dollars = max(rec.peak_profit_dollars, profit)

        # Update bar count held
        if df_m1 is not None and len(df_m1) >= 2:
            latest_bar_str = str(df_m1.iloc[-2]["time"])
            if latest_bar_str != rec.last_bar_time:
                rec.last_bar_time = latest_bar_str
                rec.bars_held += 1

        # Evaluate Reversal & Continuation Confidence Scores (0 - 100)
        pos_symbol = pos_dict.get("symbol", getattr(rec, "symbol", "XAUUSDm"))
        reversal_score, breakdown = self.evaluate_reversal_confidence_score(
            symbol=pos_symbol,
            pos_type=p_type,
            magic=magic,
            df_m1=df_m1,
            df_m5=df_m5,
            df_m15=df_m15,
            live_tick=live_tick,
            thesis_anchor=rec.thesis_anchor,
        )
        continuation_score = self.evaluate_continuation_confidence_score(
            symbol=pos_symbol,
            pos_type=p_type,
            df_m1=df_m1,
            df_m5=df_m5,
            live_tick=live_tick,
            current_r=current_r,
        )
        rec.reversal_score = reversal_score
        rec.continuation_score = continuation_score

        # =====================================================================
        # STATE 6: EMERGENCY SAFETY SHIELD (Catastrophic Slippage / Gap Backstop)
        # =====================================================================
        hard_loss_dollars = self.cb_cfg.get("hard_max_loss_per_trade_dollars", 5.00)
        catastrophic_ceiling = max(rec.initial_risk_dollars * 1.35, hard_loss_dollars, 4.50)
        if profit <= -catastrophic_ceiling:
            rec.state = PositionState.STATE_6_EMERGENCY
            rec.exit_reason = f"EMERGENCY_SHIELD (Loss ${abs(profit):.2f} >= Cap ${catastrophic_ceiling:.2f})"
            logger.critical(f"[POSITION STATE] Ticket #{ticket} transitioned to STATE_6_EMERGENCY -> {rec.exit_reason}")
            return ExitDecision.CLOSE_MARKET, None, rec.exit_reason

        # =====================================================================
        # STATE 5: CONFIRMED REVERSAL EXIT (Multi-Signal Agreement >= 70/100)
        # =====================================================================
        if reversal_score >= self.reversal_exit_threshold:
            # If trade has reached meaningful profit (+0.4R+), protect gains decisively
            # If trade is still early, close if reversal confirmed across M1+M5+EMA
            rec.state = PositionState.STATE_5_CONFIRMED_REVERSAL
            rec.exit_reason = (
                f"REVERSAL_CONFIRMED (Score {reversal_score}/100 >= {self.reversal_exit_threshold} | "
                f"M1: {breakdown['m1_structure']}, M5: {breakdown['m5_momentum']}, EMA: {breakdown['ema_trend']}, "
                f"RSI: {breakdown['rsi_exhaustion']}, Pin: {breakdown['rejection_pinbar']})"
            )
            logger.info(
                f"[POSITION STATE FIX 33 UPGRADE] Ticket #{ticket} ({p_type}) Confirmed Reversal Exit! "
                f"Current R: {current_r:+.2f}R, Peak R: {rec.peak_r:+.2f}R -> Closing at market ({rec.exit_reason})"
            )
            return ExitDecision.CLOSE_MARKET, None, rec.exit_reason

        # =====================================================================
        # STATE 4: MOMENTUM WEAKENING & PROFIT DECAY (Reversal 50-69 or Peak Giveback)
        # =====================================================================
        if rec.peak_r >= self.giveback_min_peak_r:
            r_giveback = rec.peak_r - current_r
            # Dynamic Giveback Buffer based on momentum health
            max_allowed_decay = self.giveback_max_r_decay if reversal_score < self.reversal_warning_threshold else (self.giveback_max_r_decay * 0.70)
            
            if r_giveback >= max_allowed_decay:
                rec.state = PositionState.STATE_4_MOMENTUM_WEAKENING
                rec.exit_reason = (
                    f"PROFIT_GIVEBACK (Peaked at {rec.peak_r:+.2f}R, gave back {r_giveback:.2f}R >= {max_allowed_decay:.2f}R | "
                    f"Reversal Score: {reversal_score}/100)"
                )
                logger.info(f"[POSITION STATE] Ticket #{ticket} Profit Decay Triggered -> {rec.exit_reason}")
                return ExitDecision.CLOSE_MARKET, None, rec.exit_reason

        # =====================================================================
        # STALE TRADE TIMEOUT (Time-Based Trade Failure Detection - Directive 8)
        # =====================================================================
        max_timeout_bars = self.scalp_max_bars_timeout if magic == 1001 else self.musumali_max_bars_timeout
        if rec.bars_held >= max_timeout_bars and current_r < 0.30 and continuation_score < 60:
            rec.state = PositionState.STATE_4_MOMENTUM_WEAKENING
            rec.exit_reason = (
                f"TIMEOUT_MOMENTUM_FAILURE (Held {rec.bars_held} bars without progress, "
                f"Current R: {current_r:+.2f}R, Continuation Score: {continuation_score}/100)"
            )
            logger.info(f"[POSITION STATE] Ticket #{ticket} Stale Trade Timeout -> {rec.exit_reason}")
            return ExitDecision.CLOSE_MARKET, None, rec.exit_reason

        # =====================================================================
        # STATE 3: STRONG WINNER (Runners above +1.5R with strong continuation)
        # =====================================================================
        if current_r >= self.r_tier3_protect_trigger and continuation_score >= self.continuation_strong_threshold:
            rec.state = PositionState.STATE_3_STRONG_WINNER
            # Volatility-Aware Trailing Stop (ATR Buffer)
            trailing_buffer = round(max(risk_dist * 0.50, live_atr * 0.65, 1.20), digits)
            if p_type == "BUY":
                trail_sl = round(curr_price - trailing_buffer, digits)
                lock_price = round(open_price + (risk_dist * self.r_tier3_protect_lock), digits)
                eff_sl = max(trail_sl, lock_price)
                if eff_sl > current_sl:
                    reason = f"STRONG_WINNER_TRAIL (+{current_r:.2f}R, Moving SL to {eff_sl:.2f} [+1.0R+ locked])"
                    return ExitDecision.TRAIL_ATR, eff_sl, reason
            elif p_type == "SELL":
                trail_sl = round(curr_price + trailing_buffer, digits)
                lock_price = round(open_price - (risk_dist * self.r_tier3_protect_lock), digits)
                eff_sl = min(trail_sl, lock_price)
                if current_sl == 0 or eff_sl < current_sl:
                    reason = f"STRONG_WINNER_TRAIL (+{current_r:.2f}R, Moving SL to {eff_sl:.2f} [+1.0R+ locked])"
                    return ExitDecision.TRAIL_ATR, eff_sl, reason

        # =====================================================================
        # STATE 2: PROFITABLE (Agile $0.50 Accumulation Ratchet & R-Tier Locking)
        # =====================================================================
        # 1. Direct Agile Dollar Accumulation Step Locking ($0.50 Increments)
        if self.dollar_step_lock_enabled and profit >= self.dollar_step_size:
            rec.state = PositionState.STATE_2_PROFITABLE
            steps = int(profit / self.dollar_step_size)
            locked_dollars = (steps - 1) * self.dollar_step_size + self.dollar_step_buffer
            dollar_price_dist = locked_dollars / (vol * 100.0) if vol > 0 else 0.10
            
            if p_type == "BUY":
                target_sl = round(open_price + dollar_price_dist, digits)
                if target_sl > current_sl:
                    rec.be_applied = True
                    reason = f"DOLLAR_ACCUMULATION_LOCK (+${profit:.2f} -> Step {steps} Locking +${locked_dollars:.2f} @ {target_sl:.2f})"
                    logger.info(f"[POSITION STATE] Ticket #{ticket} {reason}")
                    return ExitDecision.TIGHTEN_PROTECTION, target_sl, reason
            elif p_type == "SELL":
                target_sl = round(open_price - dollar_price_dist, digits)
                if current_sl == 0 or target_sl < current_sl:
                    rec.be_applied = True
                    reason = f"DOLLAR_ACCUMULATION_LOCK (+${profit:.2f} -> Step {steps} Locking +${locked_dollars:.2f} @ {target_sl:.2f})"
                    logger.info(f"[POSITION STATE] Ticket #{ticket} {reason}")
                    return ExitDecision.TIGHTEN_PROTECTION, target_sl, reason

        # 2. Progressive R-Tier Profit Locking
        if current_r >= self.r_tier2_protect_trigger:
            rec.state = PositionState.STATE_2_PROFITABLE
            # Lock +0.55R
            lock_price = round(open_price + (risk_dist * self.r_tier2_protect_lock), digits) if p_type == "BUY" else round(open_price - (risk_dist * self.r_tier2_protect_lock), digits)
            if (p_type == "BUY" and lock_price > current_sl) or (p_type == "SELL" and (current_sl == 0 or lock_price < current_sl)):
                reason = f"PROFIT_LOCK_TIER2 (+{current_r:.2f}R -> Locking +{self.r_tier2_protect_lock:.1f}R @ {lock_price:.2f})"
                return ExitDecision.TIGHTEN_PROTECTION, lock_price, reason

        elif current_r >= self.r_tier1_protect_trigger:
            rec.state = PositionState.STATE_2_PROFITABLE
            # Lock +0.30R
            lock_price = round(open_price + (risk_dist * self.r_tier1_protect_lock), digits) if p_type == "BUY" else round(open_price - (risk_dist * self.r_tier1_protect_lock), digits)
            if (p_type == "BUY" and lock_price > current_sl) or (p_type == "SELL" and (current_sl == 0 or lock_price < current_sl)):
                reason = f"PROFIT_LOCK_TIER1 (+{current_r:.2f}R -> Locking +{self.r_tier1_protect_lock:.1f}R @ {lock_price:.2f})"
                return ExitDecision.TIGHTEN_PROTECTION, lock_price, reason

        elif current_r >= self.r_be_trigger and not rec.be_applied:
            rec.state = PositionState.STATE_2_PROFITABLE
            # Lock Breakeven + 0.1R guaranteed green
            be_price = round(open_price + (risk_dist * self.r_be_lock), digits) if p_type == "BUY" else round(open_price - (risk_dist * self.r_be_lock), digits)
            if (p_type == "BUY" and be_price > current_sl) or (p_type == "SELL" and (current_sl == 0 or be_price < current_sl)):
                rec.be_applied = True
                reason = f"BREAKEVEN_LOCK (+{current_r:.2f}R -> Moving SL to {be_price:.2f} [+0.1R Guaranteed Green])"
                return ExitDecision.LOCK_BREAKEVEN, be_price, reason

        # Otherwise continue holding under normal state
        return ExitDecision.HOLD, None, "Position within normal parameters"
