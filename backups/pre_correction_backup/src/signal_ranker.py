"""
Portfolio Signal Conviction Ranking & Allocation Engine
When multiple valid trade setups occur simultaneously across symbols (XAUUSD, BTCUSD)
or engines (Musumali, Scalper), ranks them by composite conviction score (0 - 100)
to ensure only highest-quality setups consume available portfolio risk capacity.
"""

import logging
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

logger = logging.getLogger("GoldBot.SignalRanker")


@dataclass
class TradeCandidate:
    symbol: str
    engine_name: str
    magic: int
    direction: str
    entry: float
    sl: float
    tp: float
    candle_id: str
    zone_id: Optional[float]
    base_quality_score: int
    setup_reason: str
    timeframe: str
    spread: int
    conviction_score: float = 0.0


class SignalRanker:
    def __init__(self, config: dict):
        self.config = config

    def rank_candidates(self, candidates: List[TradeCandidate]) -> List[TradeCandidate]:
        """
        Calculates composite conviction score for each candidate and returns sorted list.
        Factors:
          1. Base Quality Score (50% weight)
          2. R:R Potential (20% weight)
          3. Timeframe Seniority (15% weight)
          4. Spread Health (15% weight)
        """
        if not candidates:
            return []

        for cand in candidates:
            score = float(cand.base_quality_score) * 0.50

            # R:R Potential
            sl_dist = abs(cand.entry - cand.sl)
            tp_dist = abs(cand.tp - cand.entry)
            rr = (tp_dist / sl_dist) if sl_dist > 0 else 1.0
            if rr >= 2.0:
                score += 20.0
            elif rr >= 1.5:
                score += 15.0
            else:
                score += 10.0

            # Timeframe Seniority (HTF setups receive higher institutional weighting)
            if cand.timeframe in ("H1", "H4"):
                score += 15.0
            elif cand.timeframe in ("M30", "M15"):
                score += 12.0
            elif cand.timeframe == "M5":
                score += 10.0
            else:
                score += 7.0

            # Spread Quality
            is_btc = "BTC" in cand.symbol.upper()
            normal_spread = 2200 if is_btc else 280
            if cand.spread <= normal_spread:
                score += 15.0
            elif cand.spread <= (normal_spread * 1.2):
                score += 10.0
            else:
                score += 5.0

            cand.conviction_score = round(min(100.0, score), 1)

        # Sort descending by conviction score
        sorted_candidates = sorted(candidates, key=lambda c: c.conviction_score, reverse=True)

        if len(sorted_candidates) > 1:
            logger.info(
                f"[SIGNAL RANKING AUDIT] Evaluated {len(sorted_candidates)} simultaneous candidates:\n" +
                "\n".join([f"  #{i+1}: {c.symbol} ({c.engine_name} {c.direction}) -> Conviction: {c.conviction_score}/100 [Base: {c.base_quality_score}]" for i, c in enumerate(sorted_candidates)])
            )

        return sorted_candidates
