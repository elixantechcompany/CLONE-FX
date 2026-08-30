"""
Intelligent Position Management & Exit Engine (Multi-Symbol & Timeframe-Isolated)
Enforces:
  1. Fix the Large-Loss Problem: Multi-tier R-multiple profit locking & dynamic giveback guardian.
  2. Strict Timeframe-Isolated Early Invalidation Exits:
     - Scalper (Magic 1001): M1 structure + M5 momentum + EMA 7/16 + RSI deterioration.
     - Musumali (Magic 2001): M30/H1 thesis invalidation (M1 noise never affects Musumali).
  3. Peak Profit & Giveback Guardian (+2.0R trades never allowed to bleed back into losses).
  4. 6-Stage Position Lifecycle State Machine.
  5. Multi-Symbol support for XAUUSD and BTCUSD.
"""

import enum
import logging
import time
from typing import Dict, List, Optional, Tuple, Union, Any
import MetaTrader5 as mt5
import pandas as pd

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
    LOCK_BREAKEVEN = "LOCK_BREAKEVEN"
    TIGHTEN_PROTECTION = "TIGHTEN_PROTECTION"
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
        account_id: str = "account_1",
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
        self.account_id = account_id

        self.open_time = time.time()
        self.initial_risk_dist = abs(open_price - initial_sl) if initial_sl > 0 else (2.0 if "XAU" in symbol else 150.0)
        
        # Initial 1R risk in USD
        if "BTC" in symbol.upper():
            self.initial_risk_dollars = self.initial_risk_dist * volume
        else:
            self.initial_risk_dollars = self.initial_risk_dist * volume * 100.0

        self.state = PositionState.STATE_1_INITIAL
        self.peak_r = 0.0
        self.current_r = 0.0
        self.peak_profit_dollars = 0.0
        self.bars_held = 0
        self.last_bar_time: Optional[str] = None

        self.continuation_score = 50
        self.reversal_score = 50
        self.be_applied = False
        self.exit_reason: Optional[str] = None


class IntelligentExitEngine:
    def __init__(self, config: dict):
        self.config = config
        self.profit_cfg = config.get("profit_management", {})
        self.cb_cfg = config.get("circuit_breakers", {})

        # R-Multiple Thresholds
        self.r_be_trigger = self.profit_cfg.get("breakeven_trigger_r", 0.50)
        self.r_be_lock = self.profit_cfg.get("breakeven_lock_r", 0.10)
        self.r_tier1_trigger = self.profit_cfg.get("tier1_protect_trigger_r", 1.00)
        self.r_tier1_lock = self.profit_cfg.get("tier1_protect_lock_r", 0.50)
        self.r_tier2_trigger = self.profit_cfg.get("tier2_protect_trigger_r", 1.50)
        self.r_tier2_lock = self.profit_cfg.get("tier2_protect_lock_r", 1.00)
        self.r_tier3_trigger = self.profit_cfg.get("tier3_protect_trigger_r", 2.00)
        self.r_tier3_lock = self.profit_cfg.get("tier3_protect_lock_r", 1.50)
        self.r_tier4_trigger = self.profit_cfg.get("tier4_protect_trigger_r", 3.00)
        self.r_tier4_lock = self.profit_cfg.get("tier4_protect_lock_r", 2.30)

        # Reversal & Continuation Thresholds
        self.reversal_exit_threshold = self.profit_cfg.get("reversal_exit_threshold", 70)
        self.reversal_warning_threshold = self.profit_cfg.get("reversal_warning_threshold", 50)
        self.continuation_strong_threshold = self.profit_cfg.get("continuation_strong_threshold", 60)

        # Giveback Guardian Settings
        self.giveback_min_peak_r = self.profit_cfg.get("giveback_min_peak_r", 0.80)
        self.giveback_max_r_decay = self.profit_cfg.get("giveback_max_r_decay", 0.35)

        # Stale Trade Timeout Limits
        self.scalp_max_bars_timeout = self.profit_cfg.get("scalp_timeout_bars", 12)
        self.musumali_max_bars_timeout = self.profit_cfg.get("musumali_timeout_bars", 20)

        # Dollar Accumulation Step Locking
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
        account_id: str = "account_1",
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
                account_id=account_id,
            )
            logger.info(
                f"[{account_id}] [POSITION REGISTERED] Ticket #{ticket} ({symbol} {pos_type} {volume} lots @ {open_price:.2f}) | "
                f"Initial SL: {sl:.2f} (1R = ${self.records[ticket].initial_risk_dollars:.2f}) | TP: {tp:.2f}"
            )
        return self.records[ticket]

    def cleanup_closed_tickets(self, current_open_tickets: List[int]):
        """Removes records of closed positions."""
        stale = [t for t in self.records if t not in current_open_tickets]
        for t in stale:
            del self.records[t]

    def evaluate_scalper_reversal_score(
        self,
        symbol: str,
        pos_type: str,
        df_m1: Optional[pd.DataFrame],
        df_m5: Optional[pd.DataFrame],
        live_tick,
    ) -> Tuple[int, dict]:
        """
        Scalper Exit Intelligence: Evaluates M1/M5 microstructure and momentum shift.
        Strictly isolated to M1 and M5 timeframes.
        """
        breakdown = {}
        score = 0

        # Dimension 1: M1 Market Structure Break (+30 pts)
        s_m1 = 0
        if df_m1 is not None and len(df_m1) >= 5:
            last_m1 = df_m1.iloc[-2]
            if pos_type == "BUY":
                recent_low = df_m1["low"].iloc[-7:-2].min()
                if last_m1["close"] < recent_low or (live_tick and live_tick.bid < recent_low):
                    s_m1 = 30
            elif pos_type == "SELL":
                recent_high = df_m1["high"].iloc[-7:-2].max()
                if last_m1["close"] > recent_high or (live_tick and live_tick.ask > recent_high):
                    s_m1 = 30
        breakdown["m1_structure"] = s_m1
        score += s_m1

        # Dimension 2: M5 Reversal Candle / Momentum Shift (+25 pts)
        s_m5 = 0
        if df_m5 is not None and len(df_m5) >= 5:
            last_m5 = df_m5.iloc[-2]
            m5_range = last_m5["high"] - last_m5["low"]
            if pos_type == "BUY" and last_m5["close"] < last_m5["open"]:
                body = last_m5["open"] - last_m5["close"]
                s_m5 = 25 if (m5_range > 0 and body / m5_range >= 0.50) else 15
            elif pos_type == "SELL" and last_m5["close"] > last_m5["open"]:
                body = last_m5["close"] - last_m5["open"]
                s_m5 = 25 if (m5_range > 0 and body / m5_range >= 0.50) else 15
        breakdown["m5_momentum"] = s_m5
        score += s_m5

        # Dimension 3: Fast/Slow EMA Trend Cross (+25 pts)
        s_ema = 0
        if df_m1 is not None and len(df_m1) >= 20:
            df_m1 = df_m1.copy()
            df_m1["ema7"] = df_m1["close"].ewm(span=7, adjust=False).mean()
            df_m1["ema16"] = df_m1["close"].ewm(span=16, adjust=False).mean()
            last_bar = df_m1.iloc[-2]
            if pos_type == "BUY" and (last_bar["ema7"] < last_bar["ema16"] or last_bar["close"] < last_bar["ema16"]):
                s_ema = 25
            elif pos_type == "SELL" and (last_bar["ema7"] > last_bar["ema16"] or last_bar["close"] > last_bar["ema16"]):
                s_ema = 25
        breakdown["ema_trend"] = s_ema
        score += s_ema

        # Dimension 4: RSI Momentum Exhaustion (+20 pts)
        s_rsi = 0
        if df_m5 is not None and len(df_m5) >= 15:
            delta = df_m5["close"].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / (loss + 1e-9)
            rsi = 100 - (100 / (1 + rs)).iloc[-2]
            if pos_type == "BUY" and (rsi < 40.0 or rsi > 80.0):
                s_rsi = 20
            elif pos_type == "SELL" and (rsi > 60.0 or rsi < 20.0):
                s_rsi = 20
        breakdown["rsi_exhaustion"] = s_rsi
        score += s_rsi

        return min(100, score), breakdown

    def evaluate_musumali_reversal_score(
        self,
        symbol: str,
        pos_type: str,
        df_m30: Optional[pd.DataFrame],
        df_h1: Optional[pd.DataFrame],
        live_tick,
        thesis_anchor: Optional[float] = None,
    ) -> Tuple[int, dict]:
        """
        Musumali Exit Intelligence: Evaluates M30/H1 structure and thesis invalidation.
        DOES NOT USE M1 NOISE.
        """
        breakdown = {}
        score = 0

        # Dimension 1: Thesis Invalidation / Anchor Breach (+40 pts)
        s_thesis = 0
        if thesis_anchor is not None and live_tick is not None:
            buffer = 1.0 if "XAU" in symbol else 50.0
            if pos_type == "BUY" and live_tick.bid < (thesis_anchor - buffer):
                s_thesis = 40
            elif pos_type == "SELL" and live_tick.ask > (thesis_anchor + buffer):
                s_thesis = 40
        breakdown["thesis_anchor"] = s_thesis
        score += s_thesis

        # Dimension 2: M30 Structure Break (+30 pts)
        s_m30 = 0
        if df_m30 is not None and len(df_m30) >= 5:
            last_m30 = df_m30.iloc[-2]
            if pos_type == "BUY":
                m30_low = df_m30["low"].iloc[-6:-2].min()
                if last_m30["close"] < m30_low:
                    s_m30 = 30
            elif pos_type == "SELL":
                m30_high = df_m30["high"].iloc[-6:-2].max()
                if last_m30["close"] > m30_high:
                    s_m30 = 30
        breakdown["m30_structure"] = s_m30
        score += s_m30

        # Dimension 3: H1 Institutional Bias Deterioration (+30 pts)
        s_h1 = 0
        if df_h1 is not None and len(df_h1) >= 20:
            df_h1 = df_h1.copy()
            df_h1["ema20"] = df_h1["close"].ewm(span=20, adjust=False).mean()
            last_h1 = df_h1.iloc[-2]
            if pos_type == "BUY" and last_h1["close"] < last_h1["ema20"]:
                s_h1 = 30
            elif pos_type == "SELL" and last_h1["close"] > last_h1["ema20"]:
                s_h1 = 30
        breakdown["h1_bias"] = s_h1
        score += s_h1

        return min(100, score), breakdown

    def evaluate_reversal_confidence_score(
        self,
        symbol: str,
        pos_type: str,
        magic: int,
        df_m1: Optional[pd.DataFrame],
        df_m5: Optional[pd.DataFrame],
        df_m15: Optional[pd.DataFrame] = None,
        live_tick = None,
        thesis_anchor: Optional[float] = None,
    ) -> Tuple[int, dict]:
        """Backward-compatible helper delegating to timeframe-isolated reversal evaluations."""
        if magic == 1001:
            return self.evaluate_scalper_reversal_score(symbol, pos_type, df_m1, df_m5, live_tick)
        else:
            return self.evaluate_musumali_reversal_score(symbol, pos_type, df_m15, df_m15, live_tick, thesis_anchor)

    def evaluate_position_lifecycle(
        self,
        pos_dict: dict,
        df_m1: Optional[pd.DataFrame] = None,
        df_m5: Optional[pd.DataFrame] = None,
        df_m30: Optional[pd.DataFrame] = None,
        df_h1: Optional[pd.DataFrame] = None,
        live_tick = None,
        live_atr: float = 2.0,
        digits: int = 2,
        df_m15: Optional[pd.DataFrame] = None,
    ) -> Tuple[ExitDecision, Optional[float], str]:
        """
        Full tick-by-tick evaluation of an open position through the 6-stage state machine.
        Returns: (ExitDecision, target_new_sl, reason_text)
        """
        if df_m30 is None and df_m15 is not None:
            df_m30 = df_m15
        ticket = pos_dict["ticket"]
        symbol = pos_dict.get("symbol", "XAUUSDm")
        p_type = pos_dict["type"]
        vol = pos_dict["volume"]
        open_price = pos_dict["price_open"]
        curr_price = pos_dict["price_current"]
        current_sl = pos_dict.get("sl", 0.0)
        current_tp = pos_dict.get("tp", 0.0)
        profit = pos_dict.get("profit", 0.0)
        magic = pos_dict.get("magic", 1001)

        rec = self.records.get(ticket)
        if rec is None:
            rec = self.register_position(
                ticket=ticket,
                symbol=symbol,
                pos_type=p_type,
                volume=vol,
                open_price=open_price,
                sl=current_sl,
                tp=current_tp,
                magic=magic,
            )

        # Compute dynamic R-multiple progress
        risk_dist = rec.initial_risk_dist
        price_gain = (curr_price - open_price) if p_type == "BUY" else (open_price - curr_price)
        current_r = price_gain / risk_dist if risk_dist > 0 else 0.0

        rec.current_r = current_r
        rec.peak_r = max(rec.peak_r, current_r)
        rec.peak_profit_dollars = max(rec.peak_profit_dollars, profit)

        # Update bar count
        df_track = df_m1 if magic == 1001 else df_m30
        if df_track is not None and len(df_track) >= 2:
            latest_bar_str = str(df_track.iloc[-2]["time"])
            if latest_bar_str != rec.last_bar_time:
                rec.last_bar_time = latest_bar_str
                rec.bars_held += 1

        # Evaluate Timeframe-Isolated Reversal Score
        if magic == 1001:
            # Scalper: Evaluate M1/M5
            reversal_score, breakdown = self.evaluate_scalper_reversal_score(
                symbol=symbol, pos_type=p_type, df_m1=df_m1, df_m5=df_m5, live_tick=live_tick
            )
        else:
            # Musumali: Evaluate M30/H1 (Ignore M1 noise)
            reversal_score, breakdown = self.evaluate_musumali_reversal_score(
                symbol=symbol, pos_type=p_type, df_m30=df_m30, df_h1=df_h1, live_tick=live_tick, thesis_anchor=rec.thesis_anchor
            )

        rec.reversal_score = reversal_score

        # =====================================================================
        # STATE 6: EMERGENCY SAFETY SHIELD (Catastrophic Slippage Backstop)
        # =====================================================================
        hard_loss_ceiling = 50.0
        if profit <= -hard_loss_ceiling:
            rec.state = PositionState.STATE_6_EMERGENCY
            rec.exit_reason = f"EMERGENCY_SHIELD (Loss ${abs(profit):.2f} >= Cap ${hard_loss_ceiling:.2f})"
            logger.critical(f"[{rec.account_id}] Ticket #{ticket} transitioned to STATE_6_EMERGENCY -> {rec.exit_reason}")
            return ExitDecision.CLOSE_MARKET, None, rec.exit_reason

        # =====================================================================
        # STATE 5: CONFIRMED REVERSAL EXIT (Multi-Signal Agreement >= 70/100)
        # =====================================================================
        if reversal_score >= self.reversal_exit_threshold:
            rec.state = PositionState.STATE_5_CONFIRMED_REVERSAL
            rec.exit_reason = f"REVERSAL_CONFIRMED (Score {reversal_score}/100 >= {self.reversal_exit_threshold} | {breakdown})"
            logger.info(f"[{rec.account_id}] Ticket #{ticket} ({p_type}) Confirmed Reversal Exit! Current R: {current_r:+.2f}R, Peak R: {rec.peak_r:+.2f}R")
            return ExitDecision.CLOSE_MARKET, None, rec.exit_reason

        # =====================================================================
        # STATE 4: MOMENTUM WEAKENING & PROFIT GIVEBACK GUARDIAN
        # Prevent +2.0R winners from turning into full losses
        # =====================================================================
        if rec.peak_r >= self.giveback_min_peak_r:
            r_giveback = rec.peak_r - current_r
            max_allowed_decay = self.giveback_max_r_decay if reversal_score < self.reversal_warning_threshold else (self.giveback_max_r_decay * 0.70)
            if r_giveback >= max_allowed_decay:
                rec.state = PositionState.STATE_4_MOMENTUM_WEAKENING
                rec.exit_reason = f"PROFIT_GIVEBACK_GUARD (Peaked at {rec.peak_r:+.2f}R, gave back {r_giveback:.2f}R >= {max_allowed_decay:.2f}R)"
                logger.info(f"[{rec.account_id}] Ticket #{ticket} Profit Giveback Triggered -> {rec.exit_reason}")
                return ExitDecision.CLOSE_MARKET, None, rec.exit_reason

        # =====================================================================
        # STALE TRADE TIMEOUT (Failure to progress)
        # =====================================================================
        max_timeout = self.scalp_max_bars_timeout if magic == 1001 else self.musumali_max_bars_timeout
        if rec.bars_held >= max_timeout and current_r < 0.30:
            rec.state = PositionState.STATE_4_MOMENTUM_WEAKENING
            rec.exit_reason = f"TIMEOUT_MOMENTUM_FAILURE (Held {rec.bars_held} bars without progress, Current R: {current_r:+.2f}R)"
            logger.info(f"[{rec.account_id}] Ticket #{ticket} Stale Trade Timeout -> {rec.exit_reason}")
            return ExitDecision.CLOSE_MARKET, None, rec.exit_reason

        # =====================================================================
        # DOLLAR ACCUMULATION STEP LOCKING (Agile Profit Bank)
        # =====================================================================
        if self.dollar_step_lock_enabled and profit >= self.dollar_step_size:
            rec.state = PositionState.STATE_2_PROFITABLE
            steps = int(profit / self.dollar_step_size)
            locked_dollars = (steps - 1) * self.dollar_step_size + self.dollar_step_buffer
            dollar_price_dist = locked_dollars / (vol * (1.0 if "BTC" in symbol.upper() else 100.0)) if vol > 0 else 0.10
            if p_type == "BUY":
                target_sl = round(open_price + dollar_price_dist, digits)
                if target_sl > current_sl:
                    rec.be_applied = True
                    return ExitDecision.TIGHTEN_PROTECTION, target_sl, f"DOLLAR_ACCUMULATION_LOCK (+${profit:.2f} -> Step {steps} Locking +${locked_dollars:.2f} @ {target_sl:.2f})"
            elif p_type == "SELL":
                target_sl = round(open_price - dollar_price_dist, digits)
                if current_sl == 0 or target_sl < current_sl:
                    rec.be_applied = True
                    return ExitDecision.TIGHTEN_PROTECTION, target_sl, f"DOLLAR_ACCUMULATION_LOCK (+${profit:.2f} -> Step {steps} Locking +${locked_dollars:.2f} @ {target_sl:.2f})"

        # =====================================================================
        # STATE 3: STRONG WINNER (Runners above +1.50R / +2.00R / +3.00R+)
        # =====================================================================
        if current_r >= self.r_tier4_trigger:
            rec.state = PositionState.STATE_3_STRONG_WINNER
            lock_price = round(open_price + (risk_dist * self.r_tier4_lock), digits) if p_type == "BUY" else round(open_price - (risk_dist * self.r_tier4_lock), digits)
            trailing_buffer = round(max(risk_dist * 0.40, live_atr * 0.50), digits)
            trail_sl = round(curr_price - trailing_buffer, digits) if p_type == "BUY" else round(curr_price + trailing_buffer, digits)
            eff_sl = max(trail_sl, lock_price) if p_type == "BUY" else min(trail_sl, lock_price)
            if (p_type == "BUY" and eff_sl > current_sl) or (p_type == "SELL" and (current_sl == 0 or eff_sl < current_sl)):
                return ExitDecision.TRAIL_ATR, eff_sl, f"TIER4_RUNNER_TRAIL (+{current_r:.2f}R -> Locking +{self.r_tier4_lock:.2f}R @ {eff_sl:.2f})"

        elif current_r >= self.r_tier3_trigger:
            rec.state = PositionState.STATE_3_STRONG_WINNER
            lock_price = round(open_price + (risk_dist * self.r_tier3_lock), digits) if p_type == "BUY" else round(open_price - (risk_dist * self.r_tier3_lock), digits)
            trailing_buffer = round(max(risk_dist * 0.50, live_atr * 0.60), digits)
            trail_sl = round(curr_price - trailing_buffer, digits) if p_type == "BUY" else round(curr_price + trailing_buffer, digits)
            eff_sl = max(trail_sl, lock_price) if p_type == "BUY" else min(trail_sl, lock_price)
            if (p_type == "BUY" and eff_sl > current_sl) or (p_type == "SELL" and (current_sl == 0 or eff_sl < current_sl)):
                return ExitDecision.TRAIL_ATR, eff_sl, f"TIER3_INTELLIGENT_TRAIL (+{current_r:.2f}R -> Locking +{self.r_tier3_lock:.2f}R @ {eff_sl:.2f})"

        elif current_r >= self.r_tier2_trigger:
            rec.state = PositionState.STATE_3_STRONG_WINNER
            lock_price = round(open_price + (risk_dist * self.r_tier2_lock), digits) if p_type == "BUY" else round(open_price - (risk_dist * self.r_tier2_lock), digits)
            if (p_type == "BUY" and lock_price > current_sl) or (p_type == "SELL" and (current_sl == 0 or lock_price < current_sl)):
                return ExitDecision.TIGHTEN_PROTECTION, lock_price, f"PROFIT_LOCK_TIER2 (+{current_r:.2f}R -> Locking +{self.r_tier2_lock:.2f}R @ {lock_price:.2f})"

        # =====================================================================
        # STATE 2: PROFITABLE (+0.50R Breakeven Lock & +1.00R Tier 1 Protection)
        # =====================================================================
        elif current_r >= self.r_tier1_trigger:
            rec.state = PositionState.STATE_2_PROFITABLE
            lock_price = round(open_price + (risk_dist * self.r_tier1_lock), digits) if p_type == "BUY" else round(open_price - (risk_dist * self.r_tier1_lock), digits)
            if (p_type == "BUY" and lock_price > current_sl) or (p_type == "SELL" and (current_sl == 0 or lock_price < current_sl)):
                return ExitDecision.TIGHTEN_PROTECTION, lock_price, f"PROFIT_LOCK_TIER1 (+{current_r:.2f}R -> Locking +{self.r_tier1_lock:.2f}R @ {lock_price:.2f})"

        elif current_r >= self.r_be_trigger and not rec.be_applied:
            rec.state = PositionState.STATE_2_PROFITABLE
            be_price = round(open_price + (risk_dist * self.r_be_lock), digits) if p_type == "BUY" else round(open_price - (risk_dist * self.r_be_lock), digits)
            if (p_type == "BUY" and be_price > current_sl) or (p_type == "SELL" and (current_sl == 0 or be_price < current_sl)):
                rec.be_applied = True
                return ExitDecision.LOCK_BREAKEVEN, be_price, f"BREAKEVEN_LOCK (+{current_r:.2f}R -> Moving SL to {be_price:.2f} [+0.1R buffer])"

        return ExitDecision.HOLD, None, "Within normal parameters"
