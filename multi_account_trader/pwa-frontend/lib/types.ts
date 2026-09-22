// TypeScript type definitions for Multi-Account Trading Platform

export interface TradingAccount {
  id: string;
  user_id: string;
  account_number: string;
  broker_name: string;
  mt5_server: string;
  encrypted_password: string;
  risk_percentage: number;
  is_active: boolean;
  connection_status: 'connected' | 'disconnected' | 'error';
  balance: number;
  equity: number;
  daily_profit_loss: number;
  last_sync: string;
  created_at: string;
  updated_at: string;
}

export interface TradingSignal {
  id: string;
  symbol: string;
  direction: 'BUY' | 'SELL';
  entry_price: number;
  stop_loss: number;
  take_profit: number;
  risk_reward_ratio: number;
  signal_time: string;
  expires_at: string;
  h4_ema50: number;
  h1_ema50: number;
  h4_price_above_ema: boolean;
  h1_price_above_ema: boolean;
  atr_value: number;
  is_valid: boolean;
  created_at: string;
}

export interface EmergencyCommand {
  id: string;
  user_id: string;
  command_type: 'KILL_ALL' | 'PAUSE_ALL' | 'RESUME_ALL';
  status: 'pending' | 'executed' | 'failed';
  executed_at: string | null;
  created_at: string;
}

export interface AccountSummary {
  user_id: string;
  total_accounts: number;
  active_accounts: number;
  total_balance: number;
  total_equity: number;
  total_daily_pnl: number;
}

export interface SignalFreshness {
  is_fresh: boolean;
  age_seconds: number;
  age_text: string;
  opacity: number;
}

export interface DashboardStats {
  total_accounts: number;
  active_accounts: number;
  total_balance: number;
  total_equity: number;
  daily_pnl: number;
  online_accounts: number;
}