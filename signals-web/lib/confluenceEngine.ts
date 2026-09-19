import {
  Candle,
  BiasEvaluation,
  SetupEvaluation,
  TriggerEvaluation,
  ConfluenceSignal,
  MarketDataBundle,
  MT5OrderType,
} from './types';

/**
 * Institutional Confluence & Swing Holding Engine
 * Designed specifically for Higher Timeframes (D1, 4H, 1H) holding trades:
 * - Tier 1: Daily (D1) Macro Directional Bias & Institutional Trend
 * - Tier 2: 4-Hour (4H) Intermediate Swing Structure & Key Reaction Zone
 * - Tier 3: 1-Hour (1H) Structural Shift, Reclaim & Execution Trigger
 *
 * Risk Architecture:
 * - Wide, structural invalidation stop losses that give holding positions room to breathe.
 * - Multi-session profit targets: TP1 (1:2.0 - 1:2.5) and TP2 (1:3.5 - 1:5.0+).
 */

/**
 * Calculates Exponential Moving Average (EMA)
 */
export function calculateEMA(candles: Candle[], period: number): number[] {
  if (candles.length < period) return [];
  const k = 2 / (period + 1);
  const emaValues: number[] = [];

  let sum = 0;
  for (let i = 0; i < period; i++) {
    sum += candles[i].close;
  }
  let prevEMA = sum / period;
  emaValues.push(prevEMA);

  for (let i = period; i < candles.length; i++) {
    const currentClose = candles[i].close;
    const currentEMA = currentClose * k + prevEMA * (1 - k);
    emaValues.push(currentEMA);
    prevEMA = currentEMA;
  }

  return emaValues;
}

/**
 * Calculates Average True Range (ATR)
 */
export function calculateATR(candles: Candle[], period: number = 14): number {
  if (candles.length < period + 1) {
    const last = candles[candles.length - 1];
    return Math.max(last.high - last.low, 2.0);
  }

  const trValues: number[] = [];
  for (let i = 1; i < candles.length; i++) {
    const current = candles[i];
    const prev = candles[i - 1];
    const tr = Math.max(
      current.high - current.low,
      Math.abs(current.high - prev.close),
      Math.abs(current.low - prev.close)
    );
    trValues.push(tr);
  }

  const recentTR = trValues.slice(-period);
  const atr = recentTR.reduce((acc, val) => acc + val, 0) / recentTR.length;
  return Number(atr.toFixed(4));
}

/**
 * Tier 1: Daily (D1) Macro Trend Bias Evaluator
 * Enforces: Daily EMA20/50 alignment & multi-day swing structure
 */
export function evaluateD1Bias(candlesD1: Candle[]): BiasEvaluation {
  if (candlesD1.length < 20) {
    return {
      direction: 'NO_BIAS',
      ema20: 0,
      ema50: 0,
      trendStructure: 'RANGING',
      explanation: 'Insufficient D1 candle data for Macro Bias calculation',
    };
  }

  const ema20Series = calculateEMA(candlesD1, Math.min(20, Math.floor(candlesD1.length / 2)));
  const ema50Series = calculateEMA(candlesD1, Math.min(50, candlesD1.length - 1));

  const latest20 = ema20Series.length > 0 ? ema20Series[ema20Series.length - 1] : candlesD1[candlesD1.length - 1].close;
  const latest50 = ema50Series.length > 0 ? ema50Series[ema50Series.length - 1] : latest20;
  const lastClose = candlesD1[candlesD1.length - 1].close;

  // Evaluate multi-day swing points
  const window = candlesD1.slice(-20);
  let higherHighs = 0;
  let lowerLows = 0;

  for (let i = 2; i < window.length - 2; i++) {
    if (window[i].high > window[i - 1].high && window[i].high > window[i + 1].high) {
      if (i > 4 && window[i].high > window[i - 3].high) higherHighs++;
    }
    if (window[i].low < window[i - 1].low && window[i].low < window[i + 1].low) {
      if (i > 4 && window[i].low < window[i - 3].low) lowerLows++;
    }
  }

  const isBullish = lastClose >= latest20 && latest20 >= latest50;
  const isBearish = lastClose <= latest20 && latest20 <= latest50;

  if (isBullish && higherHighs >= lowerLows) {
    return {
      direction: 'LONG_BIAS',
      ema20: Number(latest20.toFixed(2)),
      ema50: Number(latest50.toFixed(2)),
      trendStructure: 'HIGHER_HIGHS_LOWS',
      explanation: `D1 MACRO BULLISH: Price (${lastClose.toFixed(2)}) > EMA20 (${latest20.toFixed(2)}) > EMA50 (${latest50.toFixed(2)}) with Bullish Expansion`,
    };
  } else if (isBearish && lowerLows >= higherHighs) {
    return {
      direction: 'SHORT_BIAS',
      ema20: Number(latest20.toFixed(2)),
      ema50: Number(latest50.toFixed(2)),
      trendStructure: 'LOWER_HIGHS_LOWS',
      explanation: `D1 MACRO BEARISH: Price (${lastClose.toFixed(2)}) < EMA20 (${latest20.toFixed(2)}) < EMA50 (${latest50.toFixed(2)}) with Bearish Expansion`,
    };
  }

  // If EMAs and swings are mixed, check direction relative to EMA20
  if (lastClose > latest20) {
    return {
      direction: 'LONG_BIAS',
      ema20: Number(latest20.toFixed(2)),
      ema50: Number(latest50.toFixed(2)),
      trendStructure: 'RANGING',
      explanation: `D1 Range Support: Price held above Daily EMA20 (${latest20.toFixed(2)}). Bullish Reversal Bias active.`,
    };
  } else {
    return {
      direction: 'SHORT_BIAS',
      ema20: Number(latest20.toFixed(2)),
      ema50: Number(latest50.toFixed(2)),
      trendStructure: 'RANGING',
      explanation: `D1 Range Resistance: Price below Daily EMA20 (${latest20.toFixed(2)}). Bearish Reversal Bias active.`,
    };
  }
}

/**
 * Tier 2: 4-Hour (4H) Intermediate Swing Structure & Setup Detection
 * Looks for price returning to key 4H swing levels, order blocks, or liquidity pools.
 */
export function evaluate4HSetup(
  candles4h: Candle[],
  biasD1: BiasEvaluation
): SetupEvaluation {
  if (biasD1.direction === 'NO_BIAS' || candles4h.length < 20) {
    return {
      status: 'NO_SETUP',
      keyLevel: 0,
      zoneType: 'SUPPORT_DEMAND',
      explanation: 'No D1 macro bias established or insufficient 4H candles',
    };
  }

  const recentCandles = candles4h.slice(-30);
  const currentPrice = recentCandles[recentCandles.length - 1].close;

  let swingHigh = -Infinity;
  let swingLow = Infinity;

  for (let i = 2; i < recentCandles.length - 2; i++) {
    const bar = recentCandles[i];
    if (bar.high > recentCandles[i - 1].high && bar.high > recentCandles[i + 1].high) {
      if (bar.high > swingHigh) swingHigh = bar.high;
    }
    if (bar.low < recentCandles[i - 1].low && bar.low < recentCandles[i + 1].low) {
      if (bar.low < swingLow) swingLow = bar.low;
    }
  }

  if (biasD1.direction === 'LONG_BIAS') {
    const demandLevel = swingLow !== Infinity ? swingLow : currentPrice * 0.992;
    const distanceToDemand = Math.abs(currentPrice - demandLevel);
    const maxThreshold = currentPrice * 0.015; // Within 1.5% for 4H swing holding

    if (distanceToDemand <= maxThreshold || currentPrice <= demandLevel * 1.008) {
      return {
        status: 'SETUP_FORMING',
        keyLevel: Number(demandLevel.toFixed(2)),
        zoneType: 'SUPPORT_DEMAND',
        explanation: `4H Swing Setup: Price retesting 4H Major Demand / Swing Low Pool at ${demandLevel.toFixed(2)}`,
      };
    }
  } else if (biasD1.direction === 'SHORT_BIAS') {
    const supplyLevel = swingHigh !== -Infinity ? swingHigh : currentPrice * 1.008;
    const distanceToSupply = Math.abs(supplyLevel - currentPrice);
    const maxThreshold = currentPrice * 0.015;

    if (distanceToSupply <= maxThreshold || currentPrice >= supplyLevel * 0.992) {
      return {
        status: 'SETUP_FORMING',
        keyLevel: Number(supplyLevel.toFixed(2)),
        zoneType: 'RESISTANCE_SUPPLY',
        explanation: `4H Swing Setup: Price retesting 4H Major Supply / Swing High Pool at ${supplyLevel.toFixed(2)}`,
      };
    }
  }

  return {
    status: 'NO_SETUP',
    keyLevel: 0,
    zoneType: 'SUPPORT_DEMAND',
    explanation: '4H Price currently mid-range; awaiting pullback to structural swing boundaries',
  };
}

/**
 * Tier 3: 1-Hour (1H) Structural Confirmation & Execution Trigger
 * Confirms rejection wick, liquidity sweep reclaim, or momentum close on the 1H chart.
 */
export function evaluate1HTrigger(
  candles1h: Candle[],
  biasD1: BiasEvaluation,
  setup4h: SetupEvaluation
): TriggerEvaluation {
  if (setup4h.status !== 'SETUP_FORMING' || candles1h.length < 15) {
    return {
      status: 'NO_TRIGGER',
      triggerPrice: 0,
      triggerType: 'REJECTION_CANDLE',
      atr30m: 0,
      explanation: '4H setup not confirmed; 1H trigger inspection skipped',
    };
  }

  const atr1h = calculateATR(candles1h, 14);
  const triggerBar = candles1h[candles1h.length - 1];
  const prevBar = candles1h[candles1h.length - 2];

  const totalRange = triggerBar.high - triggerBar.low;
  if (totalRange <= 0) {
    return {
      status: 'NO_TRIGGER',
      triggerPrice: triggerBar.close,
      triggerType: 'REJECTION_CANDLE',
      atr30m: atr1h,
      explanation: 'Zero candle range detected on 1H',
    };
  }

  const upperWick = triggerBar.high - Math.max(triggerBar.open, triggerBar.close);
  const lowerWick = Math.min(triggerBar.open, triggerBar.close) - triggerBar.low;

  if (biasD1.direction === 'LONG_BIAS') {
    const isLowerWickRejection = lowerWick / totalRange >= 0.20;
    const isBullishBreak = triggerBar.close > prevBar.high || triggerBar.close > triggerBar.open;

    if (isLowerWickRejection || isBullishBreak) {
      return {
        status: 'ENTRY_CONFIRMED',
        triggerPrice: Number(triggerBar.close.toFixed(2)),
        triggerType: isLowerWickRejection ? 'REJECTION_CANDLE' : 'STRUCTURE_BREAK',
        atr30m: atr1h,
        explanation: isLowerWickRejection
          ? `1H Institutional Bullish Rejection Pin-bar (${((lowerWick / totalRange) * 100).toFixed(0)}% lower wick) reclaiming demand level`
          : `1H Bullish Closed Candle Reclaim above prior structural level (${prevBar.high.toFixed(2)})`,
      };
    }
  } else if (biasD1.direction === 'SHORT_BIAS') {
    const isUpperWickRejection = upperWick / totalRange >= 0.20;
    const isBearishBreak = triggerBar.close < prevBar.low || triggerBar.close < triggerBar.open;

    if (isUpperWickRejection || isBearishBreak) {
      return {
        status: 'ENTRY_CONFIRMED',
        triggerPrice: Number(triggerBar.close.toFixed(2)),
        triggerType: isUpperWickRejection ? 'REJECTION_CANDLE' : 'STRUCTURE_BREAK',
        atr30m: atr1h,
        explanation: isUpperWickRejection
          ? `1H Institutional Bearish Rejection Pin-bar (${((upperWick / totalRange) * 100).toFixed(0)}% upper wick) rejecting supply level`
          : `1H Bearish Closed Candle Breakdown below prior structural level (${prevBar.low.toFixed(2)})`,
      };
    }
  }

  return {
    status: 'NO_TRIGGER',
    triggerPrice: triggerBar.close,
    triggerType: 'REJECTION_CANDLE',
    atr30m: atr1h,
    explanation: '1H candle awaiting confirmed rejection wick or momentum breakout',
  };
}

/**
 * Full Confluence Engine: Orchestrates D1, 4H, and 1H alignment for Holding/Swing Trades
 */
export function runConfluenceScan(bundle: MarketDataBundle): ConfluenceSignal | null {
  const { symbol, timeframes } = bundle;
  const candlesD1 = timeframes['1d'] || timeframes['4h'];
  const candles4h = timeframes['4h'];
  const candles1h = timeframes['1h'];

  // Step 1: D1 Macro Bias
  const biasD1 = evaluateD1Bias(candlesD1);
  if (biasD1.direction === 'NO_BIAS') {
    return null;
  }

  // Step 2: 4H Setup Detection
  const setup4h = evaluate4HSetup(candles4h, biasD1);
  if (setup4h.status !== 'SETUP_FORMING') {
    return null;
  }

  // Step 3: 1H Entry Trigger
  const trigger1h = evaluate1HTrigger(candles1h, biasD1, setup4h);
  if (trigger1h.status !== 'ENTRY_CONFIRMED') {
    return null;
  }

  // Confirmed 3-Timeframe Alignment
  const direction = biasD1.direction === 'LONG_BIAS' ? 'BUY' : 'SELL';
  const entryPrice = trigger1h.triggerPrice;
  const atr = trigger1h.atr30m; // 1H ATR

  // Holding Trade Risk Parameters:
  // Stops are placed with wide structural invalidation buffer (NOT tight scalp stops)
  const isGold = symbol === 'XAUUSD';
  const minSlDistance = isGold ? 14.00 : 850.0;
  const rawSlDistance = Math.max(atr * 2.2, minSlDistance);
  const slDistance = Number(rawSlDistance.toFixed(2));

  // Minimum 1:2.0 Risk-to-Reward Ratio for TP1, and 1:3.5 for multi-day holding TP2
  const tpDistance1 = Number((slDistance * 2.0).toFixed(2));
  const tpDistance2 = Number((slDistance * 3.5).toFixed(2));

  const stopLoss = direction === 'BUY'
    ? Number((entryPrice - slDistance).toFixed(2))
    : Number((entryPrice + slDistance).toFixed(2));

  const takeProfit1 = direction === 'BUY'
    ? Number((entryPrice + tpDistance1).toFixed(2))
    : Number((entryPrice - tpDistance1).toFixed(2));

  const takeProfit2 = direction === 'BUY'
    ? Number((entryPrice + tpDistance2).toFixed(2))
    : Number((entryPrice - tpDistance2).toFixed(2));

  const limitPrice = direction === 'BUY'
    ? Number((entryPrice - slDistance * 0.20).toFixed(2))
    : Number((entryPrice + slDistance * 0.20).toFixed(2));

  const confluences: string[] = [
    `D1 Macro Bias: ${biasD1.explanation}`,
    `4H Swing Structure: ${setup4h.explanation}`,
    `1H Confirmation Trigger: ${trigger1h.explanation}`,
    `Holding Stop Loss: Structural Invalidation Buffer (${slDistance.toFixed(2)} pts)`,
    `Multi-Session Target 1: 1:2.00 Risk-to-Reward (${tpDistance1.toFixed(2)} pts)`,
    `Multi-Session Target 2: 1:3.50 Macro Extension (${tpDistance2.toFixed(2)} pts)`,
    `Hold Horizon: 18h - 48h (Institutional Swing Position)`,
  ];

  return {
    symbol,
    direction,
    orderType: `${direction} MARKET (or Limit on Retest)` as MT5OrderType,
    entryPrice,
    limitPrice,
    stopLoss,
    takeProfit1,
    takeProfit2,
    riskReward: 2.0,
    slDistance,
    tpDistance: tpDistance1,
    confluenceScore: '3/3',
    scoreNumeric: 100,
    tradeStyle: 'SWING_HOLD',
    holdDuration: '18h - 48h (Swing Hold)',
    htfConfluence: {
      dailyBias: biasD1.explanation,
      h4Structure: setup4h.explanation,
      h1Trigger: trigger1h.explanation,
    },
    timeframeStack: {
      'D1': biasD1.direction,
      '4H': setup4h.status,
      '1H': trigger1h.status,
    },
    confluences,
    status: 'ACTIVE',
    outcomeNotes: 'Institutional Swing Holding Signal. Calculated on D1/4H/1H structure for multi-session hold.',
    createdAt: new Date().toISOString(),
  };
}
