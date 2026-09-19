"""
Institutional Early Warning & Profit Defense Engine
Monitors live market structure, active confluence signals, and open trade positions
to detect lower-timeframe Change of Character (CHoCH), momentum exhaustion,
and deep retracements (>50% giveback) ahead of human reaction time.
"""

from typing import Dict, List, Any, Optional
import datetime
import logging

logger = logging.getLogger("GoldBot.EarlyWarning")


class EarlyWarningDetector:
    """
    Early Warning System that stays ahead of the chart:
    1. Detects M1/M5 Change of Character (CHoCH) before HTF confirms reversal.
    2. Flags deep retracements (>50% peak giveback) to defend open profits.
    3. Identifies volume climax and rejection wicks.
    """

    @staticmethod
    def analyze_signal_warnings(
        signal: Dict[str, Any],
        current_price: float,
        m5_candles: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Evaluates an active signal or position against current chart action.
        Returns a list of structured early warning alerts.
        """
        warnings = []
        direction = signal.get("direction", "BUY").upper()
        entry = float(signal.get("entry_price", current_price))
        sl = float(signal.get("stop_loss", entry - 5.0))
        tp1 = float(signal.get("tp1", signal.get("take_profit_1", entry + 10.0)))
        risk_dist = abs(entry - sl) if abs(entry - sl) > 0 else 1.0

        now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M:%S UTC")

        # 1. RETRACEMENT DEFENSE (Has profit been given back by >50%?)
        if direction in ("BUY", "LONG"):
            peak_price = float(signal.get("peak_price", max(entry, current_price)))
            max_gain = peak_price - entry
            current_gain = current_price - entry

            # If we achieved >= 1.0R gain, check retracement from peak
            if max_gain >= (0.8 * risk_dist):
                retracement = peak_price - current_price
                retrace_pct = (retracement / max_gain) * 100.0 if max_gain > 0 else 0.0

                if retrace_pct >= 50.0:
                    severity = "CRITICAL" if retrace_pct >= 65.0 else "HIGH"
                    warnings.append({
                        "type": "PROFIT_DEFENSE_RETRACEMENT",
                        "severity": severity,
                        "title": f"⚠️ Deep Retracement Alert ({retrace_pct:.0f}% Giveback)",
                        "message": (
                            f"Price reached peak high of {peak_price:.2f} and has retraced {retrace_pct:.1f}% "
                            f"down to {current_price:.2f}. Profits at risk."
                        ),
                        "recommended_action": "TRAIL_SL_TO_BREAKEVEN" if retrace_pct < 65 else "LOCK_PARTIAL_70_PCT",
                        "action_label": "Move SL to Breakeven (+0.2R) or Lock 70% Profit Now",
                        "threshold": f">{50}% of peak move",
                        "timestamp": now_str,
                    })

        elif direction in ("SELL", "SHORT"):
            peak_price = float(signal.get("peak_price", min(entry, current_price)))
            max_gain = entry - peak_price
            current_gain = entry - current_price

            if max_gain >= (0.8 * risk_dist):
                retracement = current_price - peak_price
                retrace_pct = (retracement / max_gain) * 100.0 if max_gain > 0 else 0.0

                if retrace_pct >= 50.0:
                    severity = "CRITICAL" if retrace_pct >= 65.0 else "HIGH"
                    warnings.append({
                        "type": "PROFIT_DEFENSE_RETRACEMENT",
                        "severity": severity,
                        "title": f"⚠️ Deep Retracement Alert ({retrace_pct:.0f}% Giveback)",
                        "message": (
                            f"Price reached peak low of {peak_price:.2f} and has retraced {retrace_pct:.1f}% "
                            f"up to {current_price:.2f}. Profits at risk."
                        ),
                        "recommended_action": "TRAIL_SL_TO_BREAKEVEN" if retrace_pct < 65 else "LOCK_PARTIAL_70_PCT",
                        "action_label": "Move SL to Breakeven (+0.2R) or Lock 70% Profit Now",
                        "threshold": f">{50}% of peak move",
                        "timestamp": now_str,
                    })

        # 2. LOWER-TIMEFRAME CHoCH (Change of Character) from M5 Candles
        if m5_candles and len(m5_candles) >= 5:
            recent_5 = m5_candles[-5:]
            c_curr = recent_5[-1]
            c_prev = recent_5[-2]

            if direction in ("BUY", "LONG"):
                # Bullish trade: Warning if recent candle breaks prior swing low with strong body
                prior_low = min(c["low"] for c in recent_5[:-1])
                if c_curr["close"] < prior_low and c_curr["close"] < c_curr["open"]:
                    warnings.append({
                        "type": "EARLY_M5_CHoCH_BEARISH",
                        "severity": "HIGH",
                        "title": "⚡ Early M5 Bearish CHoCH Detected",
                        "message": (
                            f"M5 Candle closed below recent swing low ({prior_low:.2f}) at {c_curr['close']:.2f}. "
                            "Early structure shift against bullish trade."
                        ),
                        "recommended_action": "TIGHTEN_STOP_LOSS",
                        "action_label": f"Tighten SL above {c_curr['high']:.2f} or secure partial TP1",
                        "threshold": "M5 Swing Low Breakdown",
                        "timestamp": now_str,
                    })

                # Rejection wick exhaustion at top
                c_range = c_curr["high"] - c_curr["low"]
                upper_wick = c_curr["high"] - max(c_curr["open"], c_curr["close"])
                if c_range > 0 and (upper_wick / c_range) >= 0.45 and c_curr["high"] >= entry:
                    warnings.append({
                        "type": "EXHAUSTION_UPPER_WICK",
                        "severity": "MEDIUM",
                        "title": "🔍 Upper Rejection Wick (Buyer Exhaustion)",
                        "message": f"M5 candle rejected higher prices with {upper_wick/c_range*100:.0f}% upper wick at {c_curr['high']:.2f}.",
                        "recommended_action": "WATCH_MOMENTUM",
                        "action_label": "Watch for reversal; do not add new long size",
                        "threshold": ">45% upper wick",
                        "timestamp": now_str,
                    })

            elif direction in ("SELL", "SHORT"):
                # Bearish trade: Warning if recent candle breaks prior swing high
                prior_high = max(c["high"] for c in recent_5[:-1])
                if c_curr["close"] > prior_high and c_curr["close"] > c_curr["open"]:
                    warnings.append({
                        "type": "EARLY_M5_CHoCH_BULLISH",
                        "severity": "HIGH",
                        "title": "⚡ Early M5 Bullish CHoCH Detected",
                        "message": (
                            f"M5 Candle closed above recent swing high ({prior_high:.2f}) at {c_curr['close']:.2f}. "
                            "Early structure shift against short trade."
                        ),
                        "recommended_action": "TIGHTEN_STOP_LOSS",
                        "action_label": f"Tighten SL below {c_curr['low']:.2f} or secure partial TP1",
                        "threshold": "M5 Swing High Breakout",
                        "timestamp": now_str,
                    })

                # Rejection wick exhaustion at bottom
                c_range = c_curr["high"] - c_curr["low"]
                lower_wick = min(c_curr["open"], c_curr["close"]) - c_curr["low"]
                if c_range > 0 and (lower_wick / c_range) >= 0.45 and c_curr["low"] <= entry:
                    warnings.append({
                        "type": "EXHAUSTION_LOWER_WICK",
                        "severity": "MEDIUM",
                        "title": "🔍 Lower Rejection Wick (Seller Exhaustion)",
                        "message": f"M5 candle rejected lower prices with {lower_wick/c_range*100:.0f}% lower wick at {c_curr['low']:.2f}.",
                        "recommended_action": "WATCH_MOMENTUM",
                        "action_label": "Watch for reversal; do not add new short size",
                        "threshold": ">45% lower wick",
                        "timestamp": now_str,
                    })

        return warnings

    @classmethod
    def evaluate_all_open_positions(
        cls,
        positions: List[Dict[str, Any]],
        m5_candles_by_symbol: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    ) -> List[Dict[str, Any]]:
        """Evaluates every open position across accounts and attaches early warning alerts."""
        alerts = []
        candles_map = m5_candles_by_symbol or {}

        for pos in positions:
            sym = pos.get("symbol", "XAUUSD")
            clean_sym = sym.replace("m", "").replace("_i", "").replace("z", "").upper()
            curr_p = float(pos.get("current_price", pos.get("price_current", 0.0)))
            candles = candles_map.get(clean_sym) or candles_map.get(sym)

            warns = cls.analyze_signal_warnings(pos, curr_p, candles)
            if warns:
                for w in warns:
                    alerts.append({
                        **w,
                        "ticket": pos.get("ticket"),
                        "account_id": pos.get("account_id"),
                        "symbol": clean_sym,
                        "type_dir": pos.get("type"),
                        "volume": pos.get("volume"),
                        "pnl": pos.get("profit"),
                    })

        return alerts
