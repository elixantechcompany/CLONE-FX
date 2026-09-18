const fs = require('fs');
const path = require('path');

const ACCESS_TOKEN = process.env.SUPABASE_ACCESS_TOKEN || '';
const PROJECT_REF = process.env.SUPABASE_PROJECT_REF || 'xeckbeavsvyoporldjzm';

const sqlQueries = `
-- 1. Ensure enum types
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'signal_status') THEN
    CREATE TYPE signal_status AS ENUM ('ACTIVE', 'EXPIRED', 'HIT_TP', 'HIT_SL', 'NOT_TAKEN');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'signal_direction') THEN
    CREATE TYPE signal_direction AS ENUM ('LONG', 'SHORT');
  END IF;
END $$;

-- 2. Create signals table
CREATE TABLE IF NOT EXISTS signals (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  symbol VARCHAR(20) NOT NULL,
  direction signal_direction NOT NULL,
  entry_price NUMERIC(14, 4) NOT NULL,
  stop_loss NUMERIC(14, 4) NOT NULL,
  take_profit_1 NUMERIC(14, 4) NOT NULL,
  take_profit_2 NUMERIC(14, 4),
  risk_reward NUMERIC(6, 2) NOT NULL,
  sl_distance NUMERIC(14, 4) NOT NULL,
  tp_distance NUMERIC(14, 4) NOT NULL,
  confluence_score VARCHAR(10) NOT NULL,
  score_numeric INT NOT NULL DEFAULT 100,
  timeframe_stack JSONB NOT NULL,
  confluences TEXT[] NOT NULL,
  status signal_status NOT NULL DEFAULT 'ACTIVE',
  outcome_notes TEXT DEFAULT '',
  closed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3. Create price cache table
CREATE TABLE IF NOT EXISTS price_cache (
  symbol VARCHAR(20) NOT NULL,
  timeframe VARCHAR(10) NOT NULL,
  candles JSONB NOT NULL,
  last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (symbol, timeframe)
);

-- 4. Create accounts_overview table
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

-- 5. Create trade_executions table
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

-- 6. Create bot_alerts table
CREATE TABLE IF NOT EXISTS bot_alerts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_type VARCHAR(50) NOT NULL,
  severity VARCHAR(20) NOT NULL DEFAULT 'INFO',
  symbol VARCHAR(20),
  message TEXT NOT NULL,
  metadata JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 7. Performance Indexes
CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals (symbol);
CREATE INDEX IF NOT EXISTS idx_signals_status ON signals (status);
CREATE INDEX IF NOT EXISTS idx_signals_confluence ON signals (confluence_score);
CREATE INDEX IF NOT EXISTS idx_signals_created_at ON signals (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_trade_symbol ON trade_executions (symbol);
CREATE INDEX IF NOT EXISTS idx_trade_status ON trade_executions (status);

-- 8. Enable Row Level Security (RLS)
ALTER TABLE signals ENABLE ROW LEVEL SECURITY;
ALTER TABLE price_cache ENABLE ROW LEVEL SECURITY;
ALTER TABLE accounts_overview ENABLE ROW LEVEL SECURITY;
ALTER TABLE trade_executions ENABLE ROW LEVEL SECURITY;
ALTER TABLE bot_alerts ENABLE ROW LEVEL SECURITY;

-- 9. RLS Policies
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Public signals read') THEN
    CREATE POLICY "Public signals read" ON signals FOR SELECT USING (true);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Service role full access signals') THEN
    CREATE POLICY "Service role full access signals" ON signals FOR ALL USING (true) WITH CHECK (true);
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Public price_cache read') THEN
    CREATE POLICY "Public price_cache read" ON price_cache FOR SELECT USING (true);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Service role full access price_cache') THEN
    CREATE POLICY "Service role full access price_cache" ON price_cache FOR ALL USING (true) WITH CHECK (true);
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Public accounts read') THEN
    CREATE POLICY "Public accounts read" ON accounts_overview FOR SELECT USING (true);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Service role full access accounts') THEN
    CREATE POLICY "Service role full access accounts" ON accounts_overview FOR ALL USING (true) WITH CHECK (true);
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Public trade read') THEN
    CREATE POLICY "Public trade read" ON trade_executions FOR SELECT USING (true);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Service role full access trade') THEN
    CREATE POLICY "Service role full access trade" ON trade_executions FOR ALL USING (true) WITH CHECK (true);
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Public alerts read') THEN
    CREATE POLICY "Public alerts read" ON bot_alerts FOR SELECT USING (true);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Service role full access alerts') THEN
    CREATE POLICY "Service role full access alerts" ON bot_alerts FOR ALL USING (true) WITH CHECK (true);
  END IF;
END $$;

-- 10. Seed Accounts Data
INSERT INTO accounts_overview (account_id, name, balance, equity, daily_pnl, max_dd_limit, status)
VALUES 
  ('account_a', 'Exness Primary ($100)', 100.0, 100.0, 0.0, 15.0, 'ACTIVE'),
  ('account_b', 'BrightFunded Challenge ($1,000)', 1000.0, 1000.0, 0.0, 50.0, 'ACTIVE'),
  ('account_c', 'HF Markets Personal ($20)', 20.0, 20.0, 0.0, 4.0, 'ACTIVE'),
  ('account_d', 'FBS Markets ($20)', 20.0, 20.0, 0.0, 4.0, 'ACTIVE')
ON CONFLICT (account_id) DO NOTHING;
`;

async function run() {
  console.log('Sending comprehensive SQL DDL to Supabase Management API...');
  const res = await fetch(`https://api.supabase.com/v1/projects/${PROJECT_REF}/database/query`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${ACCESS_TOKEN}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ query: sqlQueries }),
  });

  const status = res.status;
  const data = await res.text();
  console.log('HTTP Status:', status);
  console.log('Response:', data);

  if (status === 200 || status === 201) {
    console.log('[✓] ALL TABLES CREATED AND ACTIVE IN SUPABASE!');
  } else {
    console.error('[!] Failed to execute DDL');
  }
}

run().catch(console.error);
