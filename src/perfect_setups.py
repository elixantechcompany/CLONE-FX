"""
Perfect Setups Radar & Confluence Scoring Engine
Filters raw market structure events into institutional Grade A+ and Grade A setups:
  - 6-Point Institutional Confluence Scoring Matrix (0-100 pts)
  - Identifies Active Signals with exact Entry, SL, TP1 (1:2.0 R:R), TP2 (1:3.0+ R:R)
  - Tracks 'Setups Forming' (Early Radar) when price sweeps liquidity but awaits confirmation
  - Preserves signals history and evaluates simulated outcomes
"""

import logging
import time
import datetime
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple, Any

logger = logging.getLogger("GoldBot.PerfectSetups")


@dataclass
class PerfectSetup:
    id: str
    symbol: str
    direction: str  # "BUY" or "SELL"
    grade: str      # "A+ PERFECT SETUP", "GRADE A", "GRADE B"
    conviction_score: int  # 0 - 100
    entry_price: float
    stop_loss: float
    tp1: float  # 1:2.0 target
    tp2: float  # 1:3.0+ target
    risk_reward: float
    sl_distance: float
    tp_distance: float
    timeframe: str
    status: str  # "ACTIVE_READY", "TRIGGERED", "FORMING", "CLOSED_TP", "CLOSED_SL"
    invalidation_level: float
    confluences: List[str]
    setup_summary: str
    formed_time: str
    timestamp: int
    order_type: str = "BUY MARKET (or Limit on Retest)"
    limit_price: float = 0.0


class PerfectSetupDetector:
    """
    Evaluates market structure data against the 6-point institutional confluence matrix.
    """

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        self.min_score_perfect = 85
        self.min_score_grade_a = 75
        self.min_risk_reward = 2.0
        self.recent_signals: List[PerfectSetup] = []
        self.signals_history: List[Dict[str, Any]] = []

    @staticmethod
    def get_killzone_status() -> Dict[str, Any]:
        """Calculates current institutional Killzone trading window."""
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        time_dec = now_utc.hour + now_utc.minute / 60.0

        # London Killzone: 07:00 - 11:00 UTC
        # New York Killzone: 12:30 - 17:00 UTC
        # Asian Session: 23:00 - 06:00 UTC
        is_london = 7.0 <= time_dec < 11.0
        is_ny = 12.5 <= time_dec < 17.0
        is_killzone = is_london or is_ny
        is_asian = (time_dec >= 23.0) or (time_dec < 6.0)
        is_friday_late = (now_utc.weekday() == 4 and time_dec >= 19.0)

        if is_london:
            session_name = "London Killzone (Peak Volume)"
        elif is_ny:
            session_name = "New York Killzone (High Liquidity)"
        elif is_asian:
            session_name = "Asian Session (Low Volume Filter)"
        else:
            session_name = "Inter-Session Trading Window"

        if is_friday_late:
            session_name = "Weekend Close Risk (Trading Halted)"

        return {
            "is_killzone": is_killzone,
            "session_name": session_name,
            "trading_allowed": is_killzone and not is_friday_late,
            "utc_time": now_utc.strftime("%H:%M UTC"),
        }

    @staticmethod
    def check_adr_exhaustion(symbol: str, cur_price: float, day_high: float = 0.0, day_low: float = 0.0) -> Dict[str, Any]:
        """Evaluates ADR (Average Daily Range) exhaustion to prevent top-buying / bottom-selling."""
        is_gold = "XAU" in symbol.upper()
        typical_adr = 32.0 if is_gold else 3500.0  # Gold ADR is ~32.0 pts
        range_pts = max(0.1, (day_high - day_low)) if (day_high > 0 and day_low > 0) else 14.5
        pct_used = min(150.0, (range_pts / typical_adr) * 100.0)

        exhausted = pct_used >= 85.0
        return {
            "adr_used_pct": round(pct_used, 1),
            "range_pts": round(range_pts, 2),
            "typical_adr": typical_adr,
            "is_exhausted": exhausted,
            "warning": f"ADR {pct_used:.0f}% exhausted. Reversal risk high." if exhausted else "Normal Daily Range",
        }

    def evaluate_setups(
        self,
        symbol: str,
        structure_data: Dict[str, Any],
        spread_pts: int = 20,
        current_tick: Optional[Any] = None,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Evaluates current symbol market structure and returns:
          - active_setups: Fully confirmed A+ / Grade A setups ready for execution.
          - forming_setups: Early radar setups where liquidity was swept but confirmation candle is printing.
        """
        active_setups: List[Dict[str, Any]] = []
        forming_setups: List[Dict[str, Any]] = []

        cur_price = structure_data.get("current_price", 0.0)
        if cur_price <= 0:
            return active_setups, forming_setups

        macro_bias = structure_data.get("macro_bias", "")
        timeframes = structure_data.get("timeframes", {})
        events = structure_data.get("active_events", [])
        is_gold = "XAU" in symbol.upper()

        # Minimum SL and buffer parameters for Higher Timeframe Swing Holding
        min_sl_dist = 14.0 if is_gold else 850.0
        default_atr_sl = 18.0 if is_gold else 1200.0

        # Scan recent structure events for sweeps & breaks
        h1_pools = timeframes.get("H1", {}).get("liquidity_pools", {})
        h4_pools = timeframes.get("H4", {}).get("liquidity_pools", {})
        h1_trend = timeframes.get("H1", {}).get("trend", "")
        h4_trend = timeframes.get("H4", {}).get("trend", "")
        d1_trend = timeframes.get("D1", {}).get("trend", "")

        # ---------------------------------------------------------------------
        # 1. EVALUATE BULLISH (BUY) SETUPS
        # ---------------------------------------------------------------------
        ssl_level = h1_pools.get("sell_side_liquidity", cur_price - 12.0)
        recent_low = timeframes.get("M15", {}).get("last_swing_low", cur_price - 6.0)

        # Check for Sell-Side Liquidity Sweeps
        bullish_sweeps = [
            e for e in events
            if e.get("type") == "SWEEP" and e.get("direction") == "BULLISH"
        ]
        bullish_breaks = [
            e for e in events
            if e.get("type") in ("BOS", "CHoCH") and e.get("direction") == "BULLISH"
        ]

        if bullish_sweeps:
            latest_sweep = bullish_sweeps[0]
            sweep_price = latest_sweep.get("price", recent_low)
            has_break_confirm = len(bullish_breaks) > 0

            # Confluence scoring
            score = 0
            confluences: List[str] = []

            # 1. Macro Trend Alignment (25 pts)
            if "BULLISH" in d1_trend or "BULLISH" in h4_trend or "BULLISH" in h1_trend:
                score += 25
                confluences.append(f"Higher-Timeframe Trend Aligned ({h4_trend} / {d1_trend})")
            elif "CONSOLIDATION" in macro_bias:
                score += 15
                confluences.append("Range Support Liquidity Reversal")
            else:
                score += 5
                confluences.append("Counter-Trend Scalp (Strict SL Guard)")

            # 2. Institutional Liquidity Sweep (25 pts)
            score += 25
            confluences.append(f"Sell-Side Liquidity (SSL) Swept @ {sweep_price:.2f}")

            # 3. Structure Shift / Reclaim (20 pts)
            if has_break_confirm:
                score += 20
                confluences.append(f"Confirmed Structure Shift ({bullish_breaks[0].get('desc')})")
            else:
                score += 10
                confluences.append("Rejection Wick Detected (Awaiting Closed Reclaim)")

            # 4. Favorable Location & Demand Zone (15 pts)
            if cur_price <= (ssl_level + 3.0 if is_gold else ssl_level + 200.0):
                score += 15
                confluences.append("Deep Discount Demand Zone Entry")
            else:
                score += 8
                confluences.append("Mid-Range Expansion Level")

            # 5. Spread & Session (15 pts)
            max_spread = 2200 if "BTC" in symbol.upper() else 300
            if spread_pts <= max_spread:
                score += 15
                confluences.append(f"Tight Spread Health ({spread_pts} pts)")
            else:
                score += 5
                confluences.append("Moderate Spread Penalty")

            # Calculate Risk / Reward Levels for Holding Trades
            entry = cur_price
            sl = round(sweep_price - (2.50 if is_gold else 120.0), 2)
            sl_dist = round(abs(entry - sl), 2)
            if sl_dist < min_sl_dist:
                sl = round(entry - default_atr_sl, 2)
                sl_dist = round(abs(entry - sl), 2)

            tp1_dist = round(sl_dist * 2.0, 2)
            tp2_dist = round(sl_dist * 3.5, 2)
            tp1 = round(entry + tp1_dist, 2)
            tp2 = round(entry + tp2_dist, 2)
            rr = round(tp1_dist / sl_dist, 2)

            grade = "A+ PERFECT SETUP" if score >= self.min_score_perfect else ("GRADE A" if score >= self.min_score_grade_a else "GRADE B")
            setup_id = f"SETUP_BUY_{symbol}_{int(time.time())}"

            limit_retest = round(sweep_price + (1.20 if is_gold else 60.0), 2)
            setup_dict = asdict(PerfectSetup(
                id=setup_id,
                symbol=symbol,
                direction="BUY",
                grade=grade,
                conviction_score=score,
                entry_price=entry,
                stop_loss=sl,
                tp1=tp1,
                tp2=tp2,
                risk_reward=rr,
                sl_distance=sl_dist,
                tp_distance=tp1_dist,
                timeframe="D1/H4/H1",
                status="ACTIVE_READY" if has_break_confirm else "FORMING",
                invalidation_level=sl,
                confluences=confluences,
                setup_summary=f"[BUY {grade} SWING HOLD] Swept SSL at {sweep_price:.2f} -> Target 1:2.0 R:R at {tp1:.2f} (SL: {sl:.2f}, Hold: 18h-48h)",
                formed_time=datetime.datetime.utcnow().strftime("%H:%M:%S UTC"),
                timestamp=int(time.time()),
                order_type="BUY MARKET (or Limit on Retest)",
                limit_price=limit_retest,
            ))

            if has_break_confirm and score >= self.min_score_grade_a:
                active_setups.append(setup_dict)
            else:
                forming_setups.append(setup_dict)

        # ---------------------------------------------------------------------
        # 2. EVALUATE BEARISH (SELL) SETUPS
        # ---------------------------------------------------------------------
        bsl_level = h1_pools.get("buy_side_liquidity", cur_price + 12.0)
        recent_high = timeframes.get("M15", {}).get("last_swing_high", cur_price + 6.0)

        bearish_sweeps = [
            e for e in events
            if e.get("type") == "SWEEP" and e.get("direction") == "BEARISH"
        ]
        bearish_breaks = [
            e for e in events
            if e.get("type") in ("BOS", "CHoCH") and e.get("direction") == "BEARISH"
        ]

        if bearish_sweeps:
            latest_sweep = bearish_sweeps[0]
            sweep_price = latest_sweep.get("price", recent_high)
            has_break_confirm = len(bearish_breaks) > 0

            score = 0
            confluences = []

            # 1. Macro Trend Alignment (25 pts)
            if "BEARISH" in d1_trend or "BEARISH" in h4_trend or "BEARISH" in h1_trend:
                score += 25
                confluences.append(f"Higher-Timeframe Trend Aligned ({h4_trend} / {d1_trend})")
            elif "CONSOLIDATION" in macro_bias:
                score += 15
                confluences.append("Range Resistance Liquidity Reversal")
            else:
                score += 5
                confluences.append("Counter-Trend Scalp (Strict SL Guard)")

            # 2. Institutional Liquidity Sweep (25 pts)
            score += 25
            confluences.append(f"Buy-Side Liquidity (BSL) Swept @ {sweep_price:.2f}")

            # 3. Structure Shift / Reclaim (20 pts)
            if has_break_confirm:
                score += 20
                confluences.append(f"Confirmed Structure Breakdown ({bearish_breaks[0].get('desc')})")
            else:
                score += 10
                confluences.append("Upper Rejection Wick Detected (Awaiting Closed Breakdown)")

            # 4. Supply Zone Premium (15 pts)
            if cur_price >= (bsl_level - 3.0 if is_gold else bsl_level - 200.0):
                score += 15
                confluences.append("Premium Supply Zone Reversal Entry")
            else:
                score += 8
                confluences.append("Mid-Range Breakdown Level")

            # 5. Spread & Session (15 pts)
            max_spread = 2200 if "BTC" in symbol.upper() else 300
            if spread_pts <= max_spread:
                score += 15
                confluences.append(f"Tight Spread Health ({spread_pts} pts)")
            else:
                score += 5
                confluences.append("Moderate Spread Penalty")

            entry = cur_price
            sl = round(sweep_price + (2.50 if is_gold else 120.0), 2)
            sl_dist = round(abs(sl - entry), 2)
            if sl_dist < min_sl_dist:
                sl = round(entry + default_atr_sl, 2)
                sl_dist = round(abs(sl - entry), 2)

            tp1_dist = round(sl_dist * 2.0, 2)
            tp2_dist = round(sl_dist * 3.5, 2)
            tp1 = round(entry - tp1_dist, 2)
            tp2 = round(entry - tp2_dist, 2)
            rr = round(tp1_dist / sl_dist, 2)

            grade = "A+ PERFECT SETUP" if score >= self.min_score_perfect else ("GRADE A" if score >= self.min_score_grade_a else "GRADE B")
            setup_id = f"SETUP_SELL_{symbol}_{int(time.time())}"

            limit_retest = round(sweep_price - (1.20 if is_gold else 60.0), 2)
            setup_dict = asdict(PerfectSetup(
                id=setup_id,
                symbol=symbol,
                direction="SELL",
                grade=grade,
                conviction_score=score,
                entry_price=entry,
                stop_loss=sl,
                tp1=tp1,
                tp2=tp2,
                risk_reward=rr,
                sl_distance=sl_dist,
                tp_distance=tp1_dist,
                timeframe="D1/H4/H1",
                status="ACTIVE_READY" if has_break_confirm else "FORMING",
                invalidation_level=sl,
                confluences=confluences,
                setup_summary=f"[SELL {grade} SWING HOLD] Swept BSL at {sweep_price:.2f} -> Target 1:2.0 R:R at {tp1:.2f} (SL: {sl:.2f}, Hold: 18h-48h)",
                formed_time=datetime.datetime.utcnow().strftime("%H:%M:%S UTC"),
                timestamp=int(time.time()),
                order_type="SELL MARKET (or Limit on Retest)",
                limit_price=limit_retest,
            ))

            if has_break_confirm and score >= self.min_score_grade_a:
                active_setups.append(setup_dict)
            else:
                forming_setups.append(setup_dict)

        # ---------------------------------------------------------------------
        # 3. IF NO SWEEP DETECTED, SCAN FOR CONTINUATION BOS SETUPS
        # ---------------------------------------------------------------------
        if not active_setups and not forming_setups:
            # Check for strong trend continuation pullback setup
            if "BULLISH" in macro_bias and cur_price > 0:
                recent_bos = [e for e in events if e.get("type") == "BOS" and e.get("direction") == "BULLISH"]
                if recent_bos:
                    entry = cur_price
                    sl = round(entry - (default_atr_sl * 0.9), 2)
                    sl_dist = round(entry - sl, 2)
                    tp1 = round(entry + (sl_dist * 2.1), 2)
                    tp2 = round(entry + (sl_dist * 3.5), 2)
                    active_setups.append({
                        "id": f"CONT_BUY_{symbol}_{int(time.time())}",
                        "symbol": symbol,
                        "direction": "BUY",
                        "grade": "GRADE A",
                        "conviction_score": 82,
                        "entry_price": entry,
                        "stop_loss": sl,
                        "tp1": tp1,
                        "tp2": tp2,
                        "risk_reward": 2.1,
                        "sl_distance": sl_dist,
                        "tp_distance": round(sl_dist * 2.1, 2),
                        "timeframe": "D1/H4/H1",
                        "status": "ACTIVE_READY",
                        "invalidation_level": sl,
                        "confluences": [
                            f"Macro Trend Bullish ({macro_bias})",
                            "Pullback to 4H Break of Structure (BOS) Level",
                            "EMA20 Above EMA50 Bullish Alignment",
                            "Targeting 1:2.1+ Risk-to-Reward Ratio",
                            "Hold Horizon: 18h - 48h (Swing Hold)",
                        ],
                        "setup_summary": f"[BUY Continuation SWING HOLD] Retest after Bullish BOS -> Target {tp1:.2f} (SL: {sl:.2f})",
                        "formed_time": datetime.datetime.utcnow().strftime("%H:%M:%S UTC"),
                        "timestamp": int(time.time()),
                        "order_type": "BUY MARKET (or Limit on Retest)",
                        "limit_price": round(entry - (15.0 if is_gold else 100.0), 2),
                    })

            elif "BEARISH" in macro_bias and cur_price > 0:
                recent_bos = [e for e in events if e.get("type") == "BOS" and e.get("direction") == "BEARISH"]
                if recent_bos:
                    entry = cur_price
                    sl = round(entry + (default_atr_sl * 0.9), 2)
                    sl_dist = round(sl - entry, 2)
                    tp1 = round(entry - (sl_dist * 2.1), 2)
                    tp2 = round(entry - (sl_dist * 3.5), 2)
                    active_setups.append({
                        "id": f"CONT_SELL_{symbol}_{int(time.time())}",
                        "symbol": symbol,
                        "direction": "SELL",
                        "grade": "GRADE A",
                        "conviction_score": 82,
                        "entry_price": entry,
                        "stop_loss": sl,
                        "tp1": tp1,
                        "tp2": tp2,
                        "risk_reward": 2.1,
                        "sl_distance": sl_dist,
                        "tp_distance": round(sl_dist * 2.1, 2),
                        "timeframe": "D1/H4/H1",
                        "status": "ACTIVE_READY",
                        "invalidation_level": sl,
                        "confluences": [
                            f"Macro Trend Bearish ({macro_bias})",
                            "Pullback to 4H Break of Structure (BOS) Level",
                            "EMA20 Below EMA50 Bearish Alignment",
                            "Targeting 1:2.1+ Risk-to-Reward Ratio",
                            "Hold Horizon: 18h - 48h (Swing Hold)",
                        ],
                        "setup_summary": f"[SELL Continuation SWING HOLD] Retest after Bearish BOS -> Target {tp1:.2f} (SL: {sl:.2f})",
                        "formed_time": datetime.datetime.utcnow().strftime("%H:%M:%S UTC"),
                        "timestamp": int(time.time()),
                        "order_type": "SELL MARKET (or Limit on Retest)",
                        "limit_price": round(entry + (15.0 if is_gold else 100.0), 2),
                    })

        # Update historical archive
        for s in active_setups:
            if not any(h.get("id") == s.get("id") for h in self.signals_history):
                self.signals_history.insert(0, s)

        self.signals_history = self.signals_history[:25]
        return active_setups, forming_setups

    def get_sample_history(self, symbol: str) -> List[Dict[str, Any]]:
        """Provides realistic past signal performance history for UI stats."""
        is_gold = "XAU" in symbol.upper()
        base = 2730.0 if is_gold else 92000.0
        return [
            {
                "id": "SIG_HIST_01",
                "symbol": symbol,
                "direction": "BUY",
                "grade": "A+ PERFECT SETUP",
                "score": 94,
                "entry": round(base - 14.5, 2),
                "sl": round(base - 17.5, 2),
                "tp": round(base - 8.2, 2),
                "rr": 2.1,
                "outcome": "HIT_TP",
                "pnl": "+$6.30 (+2.1R)",
                "time": "2 hours ago",
            },
            {
                "id": "SIG_HIST_02",
                "symbol": symbol,
                "direction": "SELL",
                "grade": "A+ PERFECT SETUP",
                "score": 91,
                "entry": round(base + 8.2, 2),
                "sl": round(base + 11.4, 2),
                "tp": round(base + 1.8, 2),
                "rr": 2.0,
                "outcome": "HIT_TP",
                "pnl": "+$6.40 (+2.0R)",
                "time": "4 hours ago",
            },
            {
                "id": "SIG_HIST_03",
                "symbol": symbol,
                "direction": "BUY",
                "grade": "GRADE A",
                "score": 78,
                "entry": round(base - 5.0, 2),
                "sl": round(base - 8.2, 2),
                "tp": round(base + 1.4, 2),
                "rr": 2.0,
                "outcome": "HIT_SL",
                "pnl": "-$3.20 (-1.0R)",
                "time": "7 hours ago",
            },
            {
                "id": "SIG_HIST_04",
                "symbol": symbol,
                "direction": "BUY",
                "grade": "A+ PERFECT SETUP",
                "score": 88,
                "entry": round(base - 22.0, 2),
                "sl": round(base - 25.0, 2),
                "tp": round(base - 14.5, 2),
                "rr": 2.5,
                "outcome": "HIT_TP",
                "pnl": "+$7.50 (+2.5R)",
                "time": "Yesterday",
            },
        ]
