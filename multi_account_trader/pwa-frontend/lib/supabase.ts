import { createClient } from '@supabase/supabase-js';

// Supabase configuration
const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || '';
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || '';

export const supabase = createClient(supabaseUrl, supabaseAnonKey);

// Types for database queries
export type Database = {
  public: {
    Tables: {
      trading_accounts: {
        Row: {
          id: string;
          user_id: string;
          account_number: string;
          broker_name: string;
          mt5_server: string;
          encrypted_password: string;
          risk_percentage: number;
          is_active: boolean;
          connection_status: string;
          balance: number;
          equity: number;
          daily_profit_loss: number;
          last_sync: string;
          created_at: string;
          updated_at: string;
        };
        Insert: {
          id?: string;
          user_id: string;
          account_number: string;
          broker_name: string;
          mt5_server: string;
          encrypted_password: string;
          risk_percentage?: number;
          is_active?: boolean;
          connection_status?: string;
          balance?: number;
          equity?: number;
          daily_profit_loss?: number;
          last_sync?: string;
          created_at?: string;
          updated_at?: string;
        };
        Update: {
          id?: string;
          user_id?: string;
          account_number?: string;
          broker_name?: string;
          mt5_server?: string;
          encrypted_password?: string;
          risk_percentage?: number;
          is_active?: boolean;
          connection_status?: string;
          balance?: number;
          equity?: number;
          daily_profit_loss?: number;
          last_sync?: string;
          created_at?: string;
          updated_at?: string;
        };
      };
      trading_signals: {
        Row: {
          id: string;
          symbol: string;
          direction: string;
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
        };
        Insert: {
          id?: string;
          symbol?: string;
          direction: string;
          entry_price: number;
          stop_loss: number;
          take_profit: number;
          risk_reward_ratio: number;
          signal_time?: string;
          expires_at?: string;
          h4_ema50?: number;
          h1_ema50?: number;
          h4_price_above_ema?: boolean;
          h1_price_above_ema?: boolean;
          atr_value?: number;
          is_valid?: boolean;
          created_at?: string;
        };
        Update: {
          id?: string;
          symbol?: string;
          direction?: string;
          entry_price?: number;
          stop_loss?: number;
          take_profit?: number;
          risk_reward_ratio?: number;
          signal_time?: string;
          expires_at?: string;
          h4_ema50?: number;
          h1_ema50?: number;
          h4_price_above_ema?: boolean;
          h1_price_above_ema?: boolean;
          atr_value?: number;
          is_valid?: boolean;
          created_at?: string;
        };
      };
      emergency_commands: {
        Row: {
          id: string;
          user_id: string;
          command_type: string;
          status: string;
          executed_at: string | null;
          created_at: string;
        };
        Insert: {
          id?: string;
          user_id: string;
          command_type: string;
          status?: string;
          executed_at?: string | null;
          created_at?: string;
        };
        Update: {
          id?: string;
          user_id?: string;
          command_type?: string;
          status?: string;
          executed_at?: string | null;
          created_at?: string;
        };
      };
    };
  };
};