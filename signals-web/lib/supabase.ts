import { createClient, SupabaseClient } from '@supabase/supabase-js';
import { ConfluenceSignal } from './types';

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL || '';
const SUPABASE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || '';

// Singleton Supabase client
let supabaseInstance: SupabaseClient | null = null;

export function getSupabase(): SupabaseClient | null {
  if (!SUPABASE_URL || !SUPABASE_KEY) {
    return null;
  }
  if (!supabaseInstance) {
    supabaseInstance = createClient(SUPABASE_URL, SUPABASE_KEY, {
      auth: { persistSession: false },
    });
  }
  return supabaseInstance;
}

// In-Memory fallback store for offline/local demonstration
let inMemorySignals: ConfluenceSignal[] = [
  {
    id: 'sample-xau-01',
    symbol: 'XAUUSD',
    direction: 'LONG',
    entryPrice: 2735.20,
    stopLoss: 2729.80,
    takeProfit1: 2746.00,
    takeProfit2: 2752.50,
    riskReward: 2.0,
    slDistance: 5.40,
    tpDistance: 10.80,
    confluenceScore: '3/3',
    scoreNumeric: 100,
    timeframeStack: {
      '4H': 'LONG_BIAS (EMA20 > EMA50, HH+HL)',
      '1H': 'SETUP_FORMING (Demand Zone Retest @ 2734.50)',
      '30M': 'ENTRY_CONFIRMED (Bullish Pin-bar 38% wick)',
    },
    confluences: [
      '4H Macro Trend: Strong Bullish (Price > 20 EMA > 50 EMA)',
      '1H Structure: Retest of Key Demand & Prior Resistance Turned Support',
      '30M Trigger: Bullish Rejection Pin-bar closed firmly back inside range',
      'Risk/Reward: 1:2.00 hard floor verified',
      'Prop Firm Condition: 3/3 Full Confluence Aligned',
    ],
    status: 'ACTIVE',
    outcomeNotes: 'Freshly generated signal awaiting manual review and execution on MT5.',
    createdAt: new Date(Date.now() - 3600000).toISOString(),
  },
  {
    id: 'sample-btc-02',
    symbol: 'BTCUSD',
    direction: 'SHORT',
    entryPrice: 92850.00,
    stopLoss: 93450.00,
    takeProfit1: 91650.00,
    takeProfit2: 90800.00,
    riskReward: 2.0,
    slDistance: 600.00,
    tpDistance: 1200.00,
    confluenceScore: '3/3',
    scoreNumeric: 100,
    timeframeStack: {
      '4H': 'SHORT_BIAS (EMA20 < EMA50, LH+LL)',
      '1H': 'SETUP_FORMING (BSL Sweep @ 93,000)',
      '30M': 'ENTRY_CONFIRMED (Bearish Breakdown)',
    },
    confluences: [
      '4H Macro Trend: Bearish Structural Shift (Lower Highs & Lower Lows)',
      '1H Structure: Sweep of Asian Session High Buy-Side Liquidity',
      '30M Trigger: Confirmed Bearish Closed Breakdown Below 92,900',
      'Risk/Reward: 1:2.00 Target achieved at 91,650',
    ],
    status: 'HIT_TP',
    outcomeNotes: 'Hit TP1 at 91,650 for +2.0R gain. Target achieved in 3 hours.',
    createdAt: new Date(Date.now() - 86400000).toISOString(),
  },
  {
    id: 'sample-xau-03',
    symbol: 'XAUUSD',
    direction: 'LONG',
    entryPrice: 2718.50,
    stopLoss: 2713.00,
    takeProfit1: 2729.50,
    takeProfit2: 2735.00,
    riskReward: 2.0,
    slDistance: 5.50,
    tpDistance: 11.00,
    confluenceScore: '3/3',
    scoreNumeric: 100,
    timeframeStack: {
      '4H': 'LONG_BIAS',
      '1H': 'SETUP_FORMING',
      '30M': 'ENTRY_CONFIRMED',
    },
    confluences: [
      '4H Bullish EMA Expansion',
      '1H Liquidity Sweep of Prior Low',
      '30M Strong Bullish Candle Close',
    ],
    status: 'HIT_TP',
    outcomeNotes: 'Full TP reached smoothly at London open.',
    createdAt: new Date(Date.now() - 172800000).toISOString(),
  },
  {
    id: 'sample-btc-04',
    symbol: 'BTCUSD',
    direction: 'LONG',
    entryPrice: 91200.00,
    stopLoss: 90600.00,
    takeProfit1: 92400.00,
    takeProfit2: 93000.00,
    riskReward: 2.0,
    slDistance: 600.00,
    tpDistance: 1200.00,
    confluenceScore: '2/3',
    scoreNumeric: 70,
    timeframeStack: {
      '4H': 'NO_BIAS (Consolidation)',
      '1H': 'SETUP_FORMING',
      '30M': 'ENTRY_CONFIRMED',
    },
    confluences: [
      '4H Ranging - Caution flag for funded accounts',
      '1H Support Bounce',
      '30M Pin-bar Confirmation',
    ],
    status: 'NOT_TAKEN',
    outcomeNotes: 'Skipped on funded account due to 2/3 score (4H ranging). Good rule enforcement.',
    createdAt: new Date(Date.now() - 259200000).toISOString(),
  },
];

/**
 * Saves a newly confirmed signal
 */
export async function saveSignal(signal: ConfluenceSignal): Promise<ConfluenceSignal> {
  const supabase = getSupabase();
  const newSignal = {
    ...signal,
    id: signal.id || `sig-${Date.now()}`,
    createdAt: new Date().toISOString(),
  };

  if (supabase) {
    try {
      const { data, error } = await supabase
        .from('signals')
        .insert({
          symbol: newSignal.symbol,
          direction: newSignal.direction,
          entry_price: newSignal.entryPrice,
          stop_loss: newSignal.stopLoss,
          take_profit_1: newSignal.takeProfit1,
          take_profit_2: newSignal.takeProfit2,
          risk_reward: newSignal.riskReward,
          sl_distance: newSignal.slDistance,
          tp_distance: newSignal.tpDistance,
          confluence_score: newSignal.confluenceScore,
          score_numeric: newSignal.scoreNumeric,
          timeframe_stack: newSignal.timeframeStack,
          confluences: newSignal.confluences,
          status: newSignal.status,
          outcome_notes: newSignal.outcomeNotes,
        })
        .select()
        .single();

      if (!error && data) {
        return {
          id: data.id,
          symbol: data.symbol,
          direction: data.direction,
          entryPrice: parseFloat(data.entry_price),
          stopLoss: parseFloat(data.stop_loss),
          takeProfit1: parseFloat(data.take_profit_1),
          takeProfit2: data.take_profit_2 ? parseFloat(data.take_profit_2) : undefined,
          riskReward: parseFloat(data.risk_reward),
          slDistance: parseFloat(data.sl_distance),
          tpDistance: parseFloat(data.tp_distance),
          confluenceScore: data.confluence_score,
          scoreNumeric: data.score_numeric,
          timeframeStack: data.timeframe_stack,
          confluences: data.confluences,
          status: data.status,
          outcomeNotes: data.outcome_notes,
          createdAt: data.created_at,
        };
      }
    } catch (e) {
      console.warn('[Supabase] Insert error, falling back to memory store:', e);
    }
  }

  // Fallback in-memory
  inMemorySignals.unshift(newSignal);
  return newSignal;
}

/**
 * Gets all signals (newest first)
 */
export async function getSignals(): Promise<ConfluenceSignal[]> {
  const supabase = getSupabase();
  if (supabase) {
    try {
      const { data, error } = await supabase
        .from('signals')
        .select('*')
        .order('created_at', { ascending: false });

      if (!error && data && data.length > 0) {
        return data.map((d: any) => ({
          id: d.id,
          symbol: d.symbol,
          direction: d.direction,
          entryPrice: parseFloat(d.entry_price),
          stopLoss: parseFloat(d.stop_loss),
          takeProfit1: parseFloat(d.take_profit_1),
          takeProfit2: d.take_profit_2 ? parseFloat(d.take_profit_2) : undefined,
          riskReward: parseFloat(d.risk_reward),
          slDistance: parseFloat(d.sl_distance),
          tpDistance: parseFloat(d.tp_distance),
          confluenceScore: d.confluence_score,
          scoreNumeric: d.score_numeric,
          timeframeStack: d.timeframe_stack,
          confluences: d.confluences,
          status: d.status,
          outcomeNotes: d.outcome_notes,
          createdAt: d.created_at,
        }));
      }
    } catch (e) {
      console.warn('[Supabase] Fetch error, falling back to memory store:', e);
    }
  }

  return inMemorySignals;
}

/**
 * Updates outcome of a signal (Hit TP, Hit SL, Not Taken)
 */
export async function updateSignalStatus(
  id: string,
  status: 'ACTIVE' | 'HIT_TP' | 'HIT_SL' | 'NOT_TAKEN',
  outcomeNotes?: string
): Promise<boolean> {
  const supabase = getSupabase();
  if (supabase) {
    try {
      const updatePayload: any = { status };
      if (outcomeNotes !== undefined) updatePayload.outcome_notes = outcomeNotes;

      const { error } = await supabase.from('signals').update(updatePayload).eq('id', id);
      if (!error) return true;
    } catch (e) {
      console.warn('[Supabase] Update error, applying in-memory:', e);
    }
  }

  const found = inMemorySignals.find((s) => s.id === id);
  if (found) {
    found.status = status;
    if (outcomeNotes !== undefined) found.outcomeNotes = outcomeNotes;
    return true;
  }

  return false;
}
