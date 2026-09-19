export interface Candle {
  time: number; // Unix timestamp in seconds
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

export type Timeframe = '1d' | '4h' | '1h' | '30m';

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

export type SignalDirection = 'BUY' | 'SELL' | 'LONG' | 'SHORT';
export type OrderAction = 'BUY' | 'SELL';
export type MT5OrderType = 'BUY MARKET' | 'BUY LIMIT' | 'BUY STOP' | 'SELL MARKET' | 'SELL LIMIT' | 'SELL STOP' | 'BUY MARKET (or Limit on Retest)' | 'SELL MARKET (or Limit on Retest)' | string;
export type ConfluenceScore = '3/3' | '2/3' | 'A+ PERFECT SETUP' | 'GRADE B' | 'GRADE C';
export type TradeOutcome = 'WIN' | 'LOSS' | 'BREAKEVEN' | 'OPEN';

export interface ConfluenceSignal {
  id?: string;
  symbol: string;
  direction: SignalDirection; // 'BUY' or 'SELL'
  orderType?: MT5OrderType;
  limitPrice?: number;
  entryPrice: number;
  stopLoss: number;
  takeProfit1: number;
  takeProfit2?: number;
  riskReward: number;
  slDistance: number;
  tpDistance: number;
  confluenceScore: string;
  scoreNumeric?: number;
  tradeStyle?: 'SWING_HOLD' | 'INTRADAY';
  holdDuration?: string; // e.g. "12h - 48h (Swing)"
  htfConfluence?: {
    dailyBias: string;
    h4Structure: string;
    h1Trigger: string;
  };
  timeframeStack?: {
    'D1'?: string;
    '4H': string;
    '1H': string;
    '30M'?: string;
  };
  confluences: string[];
  status: 'ACTIVE' | 'EXPIRED' | 'HIT_TP' | 'HIT_SL' | 'NOT_TAKEN' | 'ACTIVE_READY' | 'FORMING';
  outcomeNotes?: string;
  setup_summary?: string;
  reason?: string;
  createdAt?: string;
  formed_time?: string;
  timestamp?: number;
}

export interface JournalEntry {
  id: string;
  user_email?: string;
  symbol: string;
  order_action: OrderAction;
  order_type: MT5OrderType;
  entry_price: number;
  exit_price?: number;
  stop_loss: number;
  take_profit: number;
  lot_size: number;
  profit_usd: number;
  rr_ratio: number;
  outcome: TradeOutcome;
  session: string; // 'London', 'New York', 'Asian', 'Overlap'
  setup_type: string; // 'Liquidity Sweep', 'Break of Structure (BOS)', 'FVG Tap', 'Trend Continuation', 'Manual Scalp'
  emotions?: string; // 'Disciplined & Calm', 'Patient Entry', 'FOMO / Chased', 'Rushed Close'
  notes?: string;
  created_at: string;
  closed_at?: string;
}

export interface UserProfile {
  id?: string;
  name: string;
  email: string;
  accountType: 'PERSONAL' | 'PROP_FIRM' | 'CENT_ACCOUNT' | 'PRO_INSTITUTIONAL' | 'STANDARD_USD' | 'CENT_USC' | 'RAW_SPREAD' | 'DEMO' | string;
  isLoggedIn: boolean;
  avatarUrl?: string;
  token?: string;
}

export interface MarketSchedule {
  symbol: string;
  is_open: boolean;
  status: 'OPEN' | 'CLOSED';
  status_text: string;
  seconds_to_change?: number;
  asset_type?: string;
  current_time_utc?: string;
}

export interface EarlyWarning {
  id: string;
  symbol: string;
  type: string;
  severity: 'WARNING' | 'CRITICAL' | 'INFO';
  message: string;
  action: 'MOVE_SL_TO_BE' | 'LOCK_PARTIAL_70_PCT' | 'TIGHTEN_STOP_LOSS' | 'ALERT_ONLY';
  peak_pnl?: number;
  current_pnl?: number;
  giveback_pct?: number;
  timestamp: number;
  formatted_time: string;
}

export interface LivePosition {
  ticket: number;
  account_id: string;
  account_name: string;
  symbol: string;
  type: 'BUY' | 'SELL';
  volume: number;
  open_price: number;
  current_price: number;
  sl: number;
  tp: number;
  profit: number;
  swap?: number;
  comment?: string;
  open_time?: string;
}

export interface FleetAccount {
  id: string;
  name: string;
  type: string;
  balance: number;
  equity: number;
  margin: number;
  free_margin: number;
  profit: number;
  drawdown_pct: number;
  status: string;
  execution_mode: string;
}

export interface DashboardApiResponse {
  last_updated?: string;
  timestamp?: number;
  market_schedules?: Record<string, MarketSchedule>;
  accounts?: FleetAccount[];
  positions?: LivePosition[];
  perfect_setups?: ConfluenceSignal[];
  forming_setups?: ConfluenceSignal[];
  signals_history?: ConfluenceSignal[];
  early_warnings?: EarlyWarning[];
  account?: {
    balance: number;
    equity: number;
    margin_free: number;
  };
  master_switch?: {
    primary_switch?: string;
    algo_trading_active?: boolean;
  };
}

export type MT5AccountType = 'REAL' | 'DEMO' | string;

export interface MarketDataBundle {
  symbol: 'XAUUSD' | 'BTCUSD';
  timeframes: {
    '1d'?: Candle[];
    '4h': Candle[];
    '1h': Candle[];
    '30m'?: Candle[];
  };
}
