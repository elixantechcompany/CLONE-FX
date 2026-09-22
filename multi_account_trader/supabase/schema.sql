-- Multi-Account Trading Platform Database Schema
-- Designed for FREE TIER Supabase deployment

-- Enable necessary extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Trading Accounts Table
CREATE TABLE trading_accounts (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    account_number TEXT NOT NULL,
    broker_name TEXT NOT NULL,
    mt5_server TEXT NOT NULL,
    encrypted_password TEXT NOT NULL, -- Encrypted using pgcrypto
    risk_percentage DECIMAL(5,2) DEFAULT 1.0, -- Default 1% risk
    is_active BOOLEAN DEFAULT true,
    connection_status TEXT DEFAULT 'disconnected', -- 'connected', 'disconnected', 'error'
    balance DECIMAL(18,2) DEFAULT 0.0,
    equity DECIMAL(18,2) DEFAULT 0.0,
    daily_profit_loss DECIMAL(18,2) DEFAULT 0.0,
    last_sync TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Ensure unique account number per user
    CONSTRAINT unique_account_per_user UNIQUE (user_id, account_number)
);

-- Index for performance
CREATE INDEX idx_trading_accounts_user_id ON trading_accounts(user_id);
CREATE INDEX idx_trading_accounts_is_active ON trading_accounts(is_active);
CREATE INDEX idx_trading_accounts_connection_status ON trading_accounts(connection_status);

-- Function to enforce 5-account limit per user
CREATE OR REPLACE FUNCTION check_account_limit()
RETURNS TRIGGER AS $$
BEGIN
    DECLARE
        account_count INTEGER;
    BEGIN
        -- Count existing active accounts for this user
        SELECT COUNT(*) INTO account_count
        FROM trading_accounts
        WHERE user_id = NEW.user_id;
        
        -- Enforce 5-account limit
        IF account_count >= 5 THEN
            RAISE EXCEPTION 'Maximum 5 trading accounts allowed per user';
        END IF;
        
        RETURN NEW;
    END;
END;
$$ LANGUAGE plpgsql;

-- Trigger to enforce account limit on INSERT
CREATE TRIGGER enforce_account_limit
    BEFORE INSERT ON trading_accounts
    FOR EACH ROW
    EXECUTE FUNCTION check_account_limit();

-- Function to automatically update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to auto-update updated_at
CREATE TRIGGER update_trading_accounts_updated_at
    BEFORE UPDATE ON trading_accounts
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Row Level Security (RLS) Policies
ALTER TABLE trading_accounts ENABLE ROW LEVEL SECURITY;

-- Policy: Users can only see their own accounts
CREATE POLICY "Users can view own trading accounts"
    ON trading_accounts FOR SELECT
    USING (auth.uid() = user_id);

-- Policy: Users can insert their own accounts (subject to limit)
CREATE POLICY "Users can insert own trading accounts"
    ON trading_accounts FOR INSERT
    WITH CHECK (auth.uid() = user_id);

-- Policy: Users can update their own accounts
CREATE POLICY "Users can update own trading accounts"
    ON trading_accounts FOR UPDATE
    USING (auth.uid() = user_id);

-- Policy: Users can delete their own accounts
CREATE POLICY "Users can delete own trading accounts"
    ON trading_accounts FOR DELETE
    USING (auth.uid() = user_id);

-- Trading Signals Table (for manual trading signals)
CREATE TABLE trading_signals (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    symbol TEXT NOT NULL DEFAULT 'XAUUSD',
    direction TEXT NOT NULL, -- 'BUY' or 'SELL'
    entry_price DECIMAL(10,2) NOT NULL,
    stop_loss DECIMAL(10,2) NOT NULL,
    take_profit DECIMAL(10,2) NOT NULL,
    risk_reward_ratio DECIMAL(3,2) NOT NULL,
    signal_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE DEFAULT (NOW() + INTERVAL '5 minutes'),
    h4_ema50 DECIMAL(10,2),
    h1_ema50 DECIMAL(10,2),
    h4_price_above_ema BOOLEAN,
    h1_price_above_ema BOOLEAN,
    atr_value DECIMAL(10,2),
    is_valid BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index for signal queries
CREATE INDEX idx_trading_signals_symbol ON trading_signals(symbol);
CREATE INDEX idx_trading_signals_is_valid ON trading_signals(is_valid);
CREATE INDEX idx_trading_signals_created_at ON trading_signals(created_at DESC);

-- RLS for signals (public read access for authenticated users)
ALTER TABLE trading_signals ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Authenticated users can view signals"
    ON trading_signals FOR SELECT
    USING (auth.role() = 'authenticated');

-- Emergency Kill Switch Table
CREATE TABLE emergency_commands (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    command_type TEXT NOT NULL, -- 'KILL_ALL', 'PAUSE_ALL', 'RESUME_ALL'
    status TEXT DEFAULT 'pending', -- 'pending', 'executed', 'failed'
    executed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    CONSTRAINT valid_command_type CHECK (command_type IN ('KILL_ALL', 'PAUSE_ALL', 'RESUME_ALL'))
);

CREATE INDEX idx_emergency_commands_user_id ON emergency_commands(user_id);
CREATE INDEX idx_emergency_commands_status ON emergency_commands(status);

ALTER TABLE emergency_commands ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage own emergency commands"
    ON emergency_commands FOR ALL
    USING (auth.uid() = user_id);

-- Function to clean up expired signals
CREATE OR REPLACE FUNCTION cleanup_expired_signals()
RETURNS void AS $$
BEGIN
    UPDATE trading_signals
    SET is_valid = false
    WHERE is_valid = true 
    AND expires_at < NOW();
END;
$$ LANGUAGE plpgsql;

-- Useful views for dashboard
CREATE VIEW active_accounts_summary AS
SELECT 
    user_id,
    COUNT(*) as total_accounts,
    COUNT(*) FILTER (WHERE is_active = true) as active_accounts,
    SUM(balance) as total_balance,
    SUM(equity) as total_equity,
    SUM(daily_profit_loss) as total_daily_pnl
FROM trading_accounts
GROUP BY user_id;

CREATE VIEW latest_signals AS
SELECT *
FROM trading_signals
WHERE is_valid = true
ORDER BY created_at DESC
LIMIT 10;