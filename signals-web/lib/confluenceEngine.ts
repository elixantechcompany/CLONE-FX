import {
  Candle,
  BiasEvaluation,
  SetupEvaluation,
  TriggerEvaluation,
  ConfluenceSignal,
  MarketDataBundle,
} from './types';

/**
 * Calculates Exponential Moving Average (EMA)
 */
export function calculateEMA(candles: Candle[], period: number): number[] {
  if (candles.length < period) return [];
  const k = 2 / (period + 1);
  const emaValues: number[] = [];

  // Start with SMA for the first value
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
    // Fallback baseline
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

  // Simple average of recent TRs
  const recentTR = trValues.slice(-period);
  const atr = recentTR.reduce((acc, val) => acc + val, 0) / recentTR.length;
  return Number(atr.toFixed(4));
}

/**
 * 4H — Macro Trend Bias Evaluator
 * Enforces: EMA 20/50 slope & alignment + Swing Market Structure (HH/HL vs LH/LL)
 */
export function evaluate4HBias(candles4h: Candle[]): BiasEvaluation {
  if (candles4h.length < 50) {
    return {
      direction: 'NO_BIAS',
      ema20: 0,
      ema50: 0,
      trendStructure: 'RANGING',
      explanation: 'Insufficient 4H candle data for EMA50 calculation',
    };
  }

  const ema20Series = calculateEMA(candles4h, 20);
  const ema50Series = calculateEMA(candles4h, 50);

  const latest20 = ema20Series[ema20Series.length - 1];
  const latest50 = ema50Series[ema50Series.length - 1];
  const lastClose = candles4h[candles4h.length - 1].close;

  // Evaluate swing points (last 20 bars)
  const window = candles4h.slice(-20);
  let higherHighs = 0;
  let lowerLows = 0;

  for (let i = 2; i < window.length - 2; i++) {
    if (window[i].high > window[i - 1].high && window[i].high > window[i + 1].high) {
      if (i > 5 && window[i].high > window[i - 4].high) higherHighs++;
    }
    if (window[i].low < window[i - 1].low && window[i].low < window[i + 1].low) {
      if (i > 5 && window[i].low < window[i - 4].low) lowerLows++;
    }
  }

  const isBullishEMAs = lastClose > latest20 && latest20 > latest50;
  const isBearishEMAs = lastClose < latest20 && latest20 < latest50;

  if (isBullishEMAs && higherHighs >= lowerLows) {
    return {
      direction: 'LONG_BIAS',
      ema20: Number(latest20.toFixed(2)),
      ema50: Number(latest50.toFixed(2)),
      trendStructure: 'HIGHER_HIGHS_LOWS',
      explanation: `4H UPTREND: Price (${lastClose.toFixed(2)}) > EMA20 (${latest20.toFixed(2)}) > EMA50 (${latest50.toFixed(2)}) with Bullish Structure`,
    };
  } else if (isBearishEMAs && lowerLows >= higherHighs) {
    return {
      direction: 'SHORT_BIAS',
      ema20: Number(latest20.toFixed(2)),
      ema50: Number(latest50.toFixed(2)),
      trendStructure: 'LOWER_HIGHS_LOWS',
      explanation: `4H DOWNTREND: Price (${lastClose.toFixed(2)}) < EMA20 (${latest20.toFixed(2)}) < EMA50 (${latest50.toFixed(2)}) with Bearish Structure`,
    };
  }

  return {
    direction: 'NO_BIAS',
    ema20: Number(latest20.toFixed(2)),
    ema50: Number(latest50.toFixed(2)),
    trendStructure: 'RANGING',
    explanation: `4H RANGING / CONSOLIDATION near EMA20 (${latest20.toFixed(2)}). Hard gate active: No trades in chop.`,
  };
}

/**
 * 1H — Setup Detection Evaluator
 * Only evaluated if 4H has a bias. Looks for price returning to a key level in the bias direction.
 */
export function evaluate1HSetup(
  candles1h: Candle[],
  bias: BiasEvaluation
): SetupEvaluation {
  if (bias.direction === 'NO_BIAS' || candles1h.length < 20) {
    return {
      status: 'NO_SETUP',
      keyLevel: 0,
      zoneType: 'SUPPORT_DEMAND',
      explanation: 'No 4H bias established or insufficient 1H candles',
    };
  }

  const recentCandles = candles1h.slice(-25);
  const currentPrice = recentCandles[recentCandles.length - 1].close;

  // Find swing highs & lows in recent 1H price action
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

  if (bias.direction === 'LONG_BIAS') {
    // Look for pullback to prior swing low (SSL sweep) or retest of key demand
    const demandLevel = swingLow !== Infinity ? swingLow : currentPrice * 0.995;
    const distanceToDemand = Math.abs(currentPrice - demandLevel);
    const maxThreshold = currentPrice * 0.006; // Within 0.6% of key demand

    if (distanceToDemand <= maxThreshold || currentPrice <= demandLevel * 1.002) {
      return {
        status: 'SETUP_FORMING',
        keyLevel: Number(demandLevel.toFixed(2)),
        zoneType: 'SUPPORT_DEMAND',
        explanation: `1H Setup Forming: Price retesting Key Demand / Prior Reaction Zone at ${demandLevel.toFixed(2)}`,
      };
    }
  } else if (bias.direction === 'SHORT_BIAS') {
    // Look for pullback to prior swing high (BSL sweep) or supply zone
    const supplyLevel = swingHigh !== -Infinity ? swingHigh : currentPrice * 1.005;
    const distanceToSupply = Math.abs(supplyLevel - currentPrice);
    const maxThreshold = currentPrice * 0.006; // Within 0.6% of key supply

    if (distanceToSupply <= maxThreshold || currentPrice >= supplyLevel * 0.998) {
      return {
        status: 'SETUP_FORMING',
        keyLevel: Number(supplyLevel.toFixed(2)),
        zoneType: 'RESISTANCE_SUPPLY',
        explanation: `1H Setup Forming: Price retesting Key Supply / Prior Resistance Zone at ${supplyLevel.toFixed(2)}`,
      };
    }
  }

  return {
    status: 'NO_SETUP',
    keyLevel: 0,
    zoneType: 'SUPPORT_DEMAND',
    explanation: '1H Price currently mid-range; not at key structural reaction zone',
  };
}

/**
 * 30M — Entry Trigger Evaluator
 * Only evaluated if 1H has a forming setup. Looks for rejection candle, momentum shift or minor break.
 */
export function evaluate30MTrigger(
  candles30m: Candle[],
  bias: BiasEvaluation,
  setup: SetupEvaluation
): TriggerEvaluation {
  if (setup.status !== 'SETUP_FORMING' || candles30m.length < 15) {
    return {
      status: 'NO_TRIGGER',
      triggerPrice: 0,
      triggerType: 'REJECTION_CANDLE',
      atr30m: 0,
      explanation: '1H setup not confirmed; trigger inspection skipped',
    };
  }

  const atr30m = calculateATR(candles30m, 14);
  const triggerBar = candles30m[candles30m.length - 1];
  const prevBar = candles30m[candles30m.length - 2];

  const totalRange = triggerBar.high - triggerBar.low;
  if (totalRange <= 0) {
    return {
      status: 'NO_TRIGGER',
      triggerPrice: triggerBar.close,
      triggerType: 'REJECTION_CANDLE',
      atr30m,
      explanation: 'Zero candle range detected on 30M',
    };
  }

  const upperWick = triggerBar.high - Math.max(triggerBar.open, triggerBar.close);
  const lowerWick = Math.min(triggerBar.open, triggerBar.close) - triggerBar.low;

  if (bias.direction === 'LONG_BIAS') {
    // Bullish Rejection: Lower wick >= 25% of total bar OR Bullish Close higher than previous high
    const isLowerWickRejection = lowerWick / totalRange >= 0.25;
    const isBullishBreak = triggerBar.close > prevBar.high && triggerBar.close > triggerBar.open;

    if (isLowerWickRejection || isBullishBreak) {
      return {
        status: 'ENTRY_CONFIRMED',
        triggerPrice: Number(triggerBar.close.toFixed(2)),
        triggerType: isLowerWickRejection ? 'REJECTION_CANDLE' : 'STRUCTURE_BREAK',
        atr30m,
        explanation: isLowerWickRejection
          ? `30M Bullish Rejection Pin-bar (${((lowerWick / totalRange) * 100).toFixed(0)}% lower wick) at demand level`
          : `30M Bullish Closed Candle Breakout above previous high (${prevBar.high.toFixed(2)})`,
      };
    }
  } else if (bias.direction === 'SHORT_BIAS') {
    // Bearish Rejection: Upper wick >= 25% of total bar OR Bearish Close lower than previous low
    const isUpperWickRejection = upperWick / totalRange >= 0.25;
    const isBearishBreak = triggerBar.close < prevBar.low && triggerBar.close < triggerBar.open;

    if (isUpperWickRejection || isBearishBreak) {
      return {
        status: 'ENTRY_CONFIRMED',
        triggerPrice: Number(triggerBar.close.toFixed(2)),
        triggerType: isUpperWickRejection ? 'REJECTION_CANDLE' : 'STRUCTURE_BREAK',
        atr30m,
        explanation: isUpperWickRejection
          ? `30M Bearish Rejection Pin-bar (${((upperWick / totalRange) * 100).toFixed(0)}% upper wick) at supply level`
          : `30M Bearish Closed Candle Breakdown below previous low (${prevBar.low.toFixed(2)})`,
      };
    }
  }

  return {
    status: 'NO_TRIGGER',
    triggerPrice: triggerBar.close,
    triggerType: 'REJECTION_CANDLE',
    atr30m,
    explanation: '30M candle did not produce confirmed rejection wick or momentum breakout',
  };
}

/**
 * Full Confluence Engine: Orchestrates 4H, 1H, and 30M alignment
 */
export function runConfluenceScan(bundle: MarketDataBundle): ConfluenceSignal | null {
  const { symbol, timeframes } = bundle;
  const candles4h = timeframes['4h'];
  const candles1h = timeframes['1h'];
  const candles30m = timeframes['30m'];

  // Step 1: 4H Bias
  const bias4h = evaluate4HBias(candles4h);
  if (bias4h.direction === 'NO_BIAS') {
    return null; // Enforce: Skip trading in ranging market to protect prop firm capital
  }

  // Step 2: 1H Setup Detection
  const setup1h = evaluate1HSetup(candles1h, bias4h);
  if (setup1h.status !== 'SETUP_FORMING') {
    return null; // No trade if price hasn't returned to a defined key level
  }

  // Step 3: 30M Entry Trigger
  const trigger30m = evaluate30MTrigger(candles30m, bias4h, setup1h);
  if (trigger30m.status !== 'ENTRY_CONFIRMED') {
    return null; // No trade without confirmation at the level
  }

  // 3/3 Alignment Confirmed!
  const direction = bias4h.direction === 'LONG_BIAS' ? 'LONG' : 'SHORT';
  const entryPrice = trigger30m.triggerPrice;
  const atr = trigger30m.atr30m;

  // Risk Parameters: 1.5x ATR on 30M entry timeframe
  const isGold = symbol === 'XAUUSD';
  const minSlDistance = isGold ? 2.50 : 150.0;
  const rawSlDistance = Math.max(atr * 1.5, minSlDistance);
  const slDistance = Number(rawSlDistance.toFixed(2));

  // Minimum 1:2.0 Risk-to-Reward Ratio
  const tpDistance1 = Number((slDistance * 2.0).toFixed(2));
  const tpDistance2 = Number((slDistance * 3.2).toFixed(2));

  const stopLoss = direction === 'LONG'
    ? Number((entryPrice - slDistance).toFixed(2))
    : Number((entryPrice + slDistance).toFixed(2));

  const takeProfit1 = direction === 'LONG'
    ? Number((entryPrice + tpDistance1).toFixed(2))
    : Number((entryPrice - tpDistance1).toFixed(2));

  const takeProfit2 = direction === 'LONG'
    ? Number((entryPrice + tpDistance2).toFixed(2))
    : Number((entryPrice - tpDistance2).toFixed(2));

  const confluences: string[] = [
    `4H Macro Bias: ${bias4h.explanation}`,
    `1H Structure: ${setup1h.explanation}`,
    `30M Trigger: ${trigger30m.explanation}`,
    `Stop Loss: 1.5x 30M ATR (${slDistance.toFixed(2)} pts)`,
    `Take Profit: 1:2.00 Risk-to-Reward Target (${tpDistance1.toFixed(2)} pts)`,
    `Prop Firm Filter: 3/3 Genuine Multi-Timeframe Alignment Confirmed`,
  ];

  return {
    symbol,
    direction,
    entryPrice,
    stopLoss,
    takeProfit1,
    takeProfit2,
    riskReward: 2.0,
    slDistance,
    tpDistance: tpDistance1,
    confluenceScore: '3/3',
    scoreNumeric: 100,
    timeframeStack: {
      '4H': bias4h.direction,
      '1H': setup1h.status,
      '30M': trigger30m.status,
    },
    confluences,
    status: 'ACTIVE',
    outcomeNotes: 'Freshly generated signal awaiting manual execution on MT5/Exness terminal.',
    createdAt: new Date().toISOString(),
  };
}
