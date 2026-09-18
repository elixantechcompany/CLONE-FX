export interface Candle {
  time: number; // Unix timestamp in seconds
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

export type Timeframe = '30m' | '1h' | '4h';

export type BiasDirection = 'LONG_BIAS' | 'SHORT_BIAS' | 'NO_BIAS';

export interface BiasEvaluation {
  direction: BiasDirection;
  ema20: number;
  ema50: number;
  trendStructure: 'HIGHER_HIGHS_LOWS' | 'LOWER_HIGHS_LOWS' | 'RANGING';
  explanation: string;
}

export type SetupStatus = 'SETUP_FORMING' | 'NO_SETUP';

export interface SetupEvaluation {
  status: SetupStatus;
  keyLevel: number;
  zoneType: 'SUPPORT_DEMAND' | 'RESISTANCE_SUPPLY' | 'LIQUIDITY_SWEEP';
  explanation: string;
}

export type TriggerStatus = 'ENTRY_CONFIRMED' | 'NO_TRIGGER';

export interface TriggerEvaluation {
  status: TriggerStatus;
  triggerPrice: number;
  triggerType: 'REJECTION_CANDLE' | 'MOMENTUM_SHIFT' | 'STRUCTURE_BREAK';
  atr30m: number;
  explanation: string;
}

export type SignalDirection = 'LONG' | 'SHORT';
export type ConfluenceScore = '3/3' | '2/3';

export interface ConfluenceSignal {
  id?: string;
  symbol: 'XAUUSD' | 'BTCUSD';
  direction: SignalDirection;
  entryPrice: number;
  stopLoss: number;
  takeProfit1: number;
  takeProfit2?: number;
  riskReward: number;
  slDistance: number;
  tpDistance: number;
  confluenceScore: ConfluenceScore;
  scoreNumeric: number;
  timeframeStack: {
    '4H': string;
    '1H': string;
    '30M': string;
  };
  confluences: string[];
  status: 'ACTIVE' | 'EXPIRED' | 'HIT_TP' | 'HIT_SL' | 'NOT_TAKEN';
  outcomeNotes?: string;
  createdAt?: string;
}

export interface MarketDataBundle {
  symbol: 'XAUUSD' | 'BTCUSD';
  timeframes: {
    '4h': Candle[];
    '1h': Candle[];
    '30m': Candle[];
  };
}
