-- ==============================================================================
-- Supabase Schema for XAUUSD / BTCUSD Multi-Timeframe Signal Interface
-- ==============================================================================

-- 1. Create enum for signal status & outcomes
CREATE TYPE signal_status AS ENUM (
  'ACTIVE',
  'EXPIRED',
  'HIT_TP',
  'HIT_SL',
  'NOT_TAKEN'
);

CREATE TYPE signal_direction AS ENUM (
  'LONG',
  'SHORT'
);

-- 2. Create signals table
CREATE TABLE IF NOT EXISTS signals (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  symbol VARCHAR(20) NOT NULL,            -- 'XAUUSD' or 'BTCUSD'
  direction signal_direction NOT NULL,    -- 'LONG' or 'SHORT'
  entry_price NUMERIC(14, 4) NOT NULL,    -- Trigger candle close or retest level
  stop_loss NUMERIC(14, 4) NOT NULL,      -- 1.5x ATR baseline on 30M
  take_profit_1 NUMERIC(14, 4) NOT NULL,  -- Min 1:2.0 R:R target
  take_profit_2 NUMERIC(14, 4),           -- Extended 1:3.0+ target (optional)
  risk_reward NUMERIC(6, 2) NOT NULL,     -- e.g. 2.00, 2.50
  sl_distance NUMERIC(14, 4) NOT NULL,    -- Stop loss distance in price points
  tp_distance NUMERIC(14, 4) NOT NULL,    -- Take profit distance in price points
  confluence_score VARCHAR(10) NOT NULL,  -- '3/3' (Funded Prop Ready) or '2/3' (Caution)
  score_numeric INT NOT NULL DEFAULT 100, -- 100 for 3/3, 70 for 2/3
  timeframe_stack JSONB NOT NULL,         -- Breakdown of 4H, 1H, 30M alignment states
  confluences TEXT[] NOT NULL,            -- Array of verified confluence bullets
  status signal_status NOT NULL DEFAULT 'ACTIVE',
  outcome_notes TEXT DEFAULT '',          -- Notes from manual trade journal review
  closed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3. Create price cache table for multi-timeframe candle optimization
CREATE TABLE IF NOT EXISTS price_cache (
  symbol VARCHAR(20) NOT NULL,
  timeframe VARCHAR(10) NOT NULL,         -- '30m', '1h', '4h'
  candles JSONB NOT NULL,                 -- Array of { time, open, high, low, close, volume }
  last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (symbol, timeframe)
);

-- 4. Create accounts overview table (Multi-Account tracking)
CREATE TABLE IF NOT EXISTS accounts_overview (
  account_id VARCHAR(50) PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  balance NUMERIC(14, 2) NOT NULL DEFAULT 0.0,
  equity NUMERIC(14, 2) NOT NULL DEFAULT 0.0,
  daily_pnl NUMERIC(14, 2) NOT NULL DEFAULT 0.0,
  daily_dd_pct NUMERIC(6, 2) NOT NULL DEFAULT 0.0,
  max_dd_limit NUMERIC(14, 2) NOT NULL DEFAULT 0.0,
  status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
  last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 5. Create trade executions table (Live Tickets & Outcomes)
CREATE TABLE IF NOT EXISTS trade_executions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  ticket BIGINT,
  account_id VARCHAR(50),
  symbol VARCHAR(20) NOT NULL,
  order_type VARCHAR(20) NOT NULL,
  lot_size NUMERIC(10, 2) NOT NULL,
  open_price NUMERIC(14, 4) NOT NULL,
  stop_loss NUMERIC(14, 4),
  take_profit NUMERIC(14, 4),
  close_price NUMERIC(14, 4),
  profit_usd NUMERIC(14, 2) DEFAULT 0.0,
  pips_gain NUMERIC(10, 2) DEFAULT 0.0,
  strategy_tag VARCHAR(50) DEFAULT 'MANUAL_CONFLUENCE',
  status VARCHAR(20) NOT NULL DEFAULT 'OPEN',
  opened_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  closed_at TIMESTAMPTZ
);

-- 6. Create bot alerts table (Events & Notifications)
CREATE TABLE IF NOT EXISTS bot_alerts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_type VARCHAR(50) NOT NULL,
  severity VARCHAR(20) NOT NULL DEFAULT 'INFO',
  symbol VARCHAR(20),
  message TEXT NOT NULL,
  metadata JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 4. Create performance indexes
CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals (symbol);
CREATE INDEX IF NOT EXISTS idx_signals_status ON signals (status);
CREATE INDEX IF NOT EXISTS idx_signals_confluence ON signals (confluence_score);
CREATE INDEX IF NOT EXISTS idx_signals_created_at ON signals (created_at DESC);

-- 5. Row Level Security (RLS)
ALTER TABLE signals ENABLE ROW LEVEL SECURITY;
ALTER TABLE price_cache ENABLE ROW LEVEL SECURITY;

-- Allow public read access to signals for the dashboard
CREATE POLICY "Public signals read" ON signals
  FOR SELECT USING (true);

-- Allow authenticated or service role write/update
CREATE POLICY "Service role full access signals" ON signals
  FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY "Service role full access price_cache" ON price_cache
  FOR ALL USING (true) WITH CHECK (true);

-- 6. Updated_at auto-trigger
CREATE OR REPLACE FUNCTION update_modified_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE 'plpgsql';

CREATE OR REPLACE TRIGGER update_signals_modtime
  BEFORE UPDATE ON signals
  FOR EACH ROW
  EXECUTE FUNCTION update_modified_column();

-- ==============================================================================
-- Sample Seed Data (For Testing Dashboard UI)
-- ==============================================================================
INSERT INTO signals (
  symbol, direction, entry_price, stop_loss, take_profit_1, take_profit_2,
  risk_reward, sl_distance, tp_distance, confluence_score, score_numeric,
  timeframe_stack, confluences, status, outcome_notes, created_at
) VALUES 
(
  'XAUUSD',
  'LONG',
  2735.20,
  2729.80,
  2746.00,
  2752.50,
  2.00,
  5.40,
  10.80,
  '3/3',
  100,
  '{"4H": "LONG_BIAS (EMA20 > EMA50, HH+HL)", "1H": "SETUP_FORMING (Demand Zone Retest @ 2734.50)", "30M": "ENTRY_CONFIRMED (Rejection Pin-bar 38% wick)"}',
  ARRAY[
    '4H Macro Trend: Strong Bullish (Price > 20 EMA > 50 EMA)',
    '1H Structure: Retest of Key Demand & Prior Resistance Turned Support',
    '30M Trigger: Bullish Rejection Pin-bar closed firmly back inside range',
    'Risk/Reward: 1:2.00 hard floor verified',
    'Prop Firm Condition: 3/3 Full Confluence Aligned'
  ],
  'ACTIVE',
  'Awaiting manual entry on MT5 terminal. 0.25% risk lot size calculated.',
  NOW() - INTERVAL '1 hour'
),
(
  'BTCUSD',
  'SHORT',
  92850.00,
  93450.00,
  91650.00,
  90800.00,
  2.00,
  600.00,
  1200.00,
  '3/3',
  100,
  '{"4H": "SHORT_BIAS (EMA20 < EMA50, LH+LL)", "1H": "SETUP_FORMING (Buy-Side Liquidity Sweep @ 93000)", "30M": "ENTRY_CONFIRMED (Bearish Engulfing Breakdown)"}',
  ARRAY[
    '4H Macro Trend: Bearish Structural Shift (Lower Highs & Lower Lows)',
    '1H Structure: Sweep of Asian Session High Buy-Side Liquidity',
    '30M Trigger: Confirmed Bearish Closed Breakdown Below 92,900',
    'Risk/Reward: 1:2.00 Target achieved at 91,650'
  ],
  'HIT_TP',
  'Hit TP1 at 91,650 for +2.0R gain. Target achieved in 3 hours.',
  NOW() - INTERVAL '1 day'
),
(
  'XAUUSD',
  'LONG',
  2718.50,
  2713.00,
  2729.50,
  2735.00,
  2.00,
  5.50,
  11.00,
  '3/3',
  100,
  '{"4H": "LONG_BIAS", "1H": "SETUP_FORMING", "30M": "ENTRY_CONFIRMED"}',
  ARRAY[
    '4H Bullish EMA Expansion',
    '1H Liquidity Sweep of Prior Low',
    '30M Strong Bullish Candle Close'
  ],
  'HIT_TP',
  'Full TP reached smoothly at London open.',
  NOW() - INTERVAL '2 days'
),
(
  'BTCUSD',
  'LONG',
  91200.00,
  90600.00,
  92400.00,
  93000.00,
  2.00,
  600.00,
  1200.00,
  '2/3',
  70,
  '{"4H": "NO_BIAS (Consolidation)", "1H": "SETUP_FORMING", "30M": "ENTRY_CONFIRMED"}',
  ARRAY[
    '4H Ranging - Caution flag for funded accounts',
    '1H Support Bounce',
    '30M Pin-bar Confirmation'
  ],
  'NOT_TAKEN',
  'Skipped on funded account due to 2/3 score (4H ranging). Good rule enforcement.',
  NOW() - INTERVAL '3 days'
);
