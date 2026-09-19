import { createClient, SupabaseClient } from '@supabase/supabase-js';
import { ConfluenceSignal, JournalEntry } from './types';

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

// In-Memory store for signals (zero dummy data, only live generated)
let inMemorySignals: ConfluenceSignal[] = [];

// In-Memory store for journal entries
let inMemoryJournal: JournalEntry[] = [];

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
          direction: newSignal.direction === 'BUY' || newSignal.direction === 'LONG' ? 'LONG' : 'SHORT',
          entry_price: newSignal.entryPrice,
          stop_loss: newSignal.stopLoss,
          take_profit_1: newSignal.takeProfit1,
          take_profit_2: newSignal.takeProfit2,
          risk_reward: newSignal.riskReward,
          sl_distance: newSignal.slDistance,
          tp_distance: newSignal.tpDistance,
          confluence_score: newSignal.confluenceScore,
          score_numeric: newSignal.scoreNumeric || 100,
          timeframe_stack: newSignal.timeframeStack || {},
          confluences: newSignal.confluences || [],
          status: newSignal.status,
          outcome_notes: newSignal.outcomeNotes,
        })
        .select()
        .single();

      if (!error && data) {
        return {
          id: data.id,
          symbol: data.symbol,
          direction: data.direction === 'LONG' ? 'BUY' : 'SELL',
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
      console.warn('[Supabase] Insert error, saving in-memory:', e);
    }
  }

  inMemorySignals.unshift(newSignal);
  return newSignal;
}

/**
 * Gets all signals (newest first, 0 dummy data)
 */
export async function getSignals(): Promise<ConfluenceSignal[]> {
  const supabase = getSupabase();
  if (supabase) {
    try {
      const { data, error } = await supabase
        .from('signals')
        .select('*')
        .order('created_at', { ascending: false });

      if (!error && data) {
        return data.map((d: any) => ({
          id: d.id,
          symbol: d.symbol,
          direction: d.direction === 'LONG' ? 'BUY' : d.direction === 'SHORT' ? 'SELL' : d.direction,
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
          confluences: d.confluences || [],
          status: d.status,
          outcomeNotes: d.outcome_notes,
          createdAt: d.created_at,
        }));
      }
    } catch (e) {
      console.warn('[Supabase] Fetch error:', e);
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

/**
 * TRADING JOURNAL: Fetch all journal entries
 */
export async function getJournalEntries(userEmail?: string): Promise<JournalEntry[]> {
  const supabase = getSupabase();
  if (supabase) {
    try {
      let query = supabase.from('trading_journal').select('*').order('created_at', { ascending: false });
      if (userEmail) {
        query = query.eq('user_email', userEmail);
      }
      const { data, error } = await query;
      if (!error && data) {
        return data.map((d: any) => ({
          id: d.id,
          user_email: d.user_email,
          symbol: d.symbol,
          order_action: d.order_action || 'BUY',
          order_type: d.order_type || 'BUY MARKET',
          entry_price: parseFloat(d.entry_price || 0),
          exit_price: d.exit_price ? parseFloat(d.exit_price) : undefined,
          stop_loss: parseFloat(d.stop_loss || 0),
          take_profit: parseFloat(d.take_profit || 0),
          lot_size: parseFloat(d.lot_size || 0.01),
          profit_usd: parseFloat(d.profit_usd || 0),
          rr_ratio: parseFloat(d.rr_ratio || 2.0),
          outcome: d.outcome || 'OPEN',
          session: d.session || 'London',
          setup_type: d.setup_type || 'Manual Structure',
          emotions: d.emotions || 'Disciplined',
          notes: d.notes || '',
          created_at: d.created_at,
          closed_at: d.closed_at,
        }));
      }
    } catch (e) {
      // If table doesn't exist yet or offline, use memory
    }
  }

  if (userEmail) {
    return inMemoryJournal.filter((j) => !j.user_email || j.user_email === userEmail);
  }
  return inMemoryJournal;
}

/**
 * TRADING JOURNAL: Save new entry
 */
export async function saveJournalEntry(entry: JournalEntry): Promise<JournalEntry> {
  const newEntry: JournalEntry = {
    ...entry,
    id: entry.id || `jrnl_${Date.now()}_${Math.random().toString(36).substr(2, 5)}`,
    created_at: entry.created_at || new Date().toISOString(),
  };

  const supabase = getSupabase();
  if (supabase) {
    try {
      const { data, error } = await supabase.from('trading_journal').insert({
        id: newEntry.id,
        user_email: newEntry.user_email,
        symbol: newEntry.symbol,
        order_action: newEntry.order_action,
        order_type: newEntry.order_type,
        entry_price: newEntry.entry_price,
        exit_price: newEntry.exit_price,
        stop_loss: newEntry.stop_loss,
        take_profit: newEntry.take_profit,
        lot_size: newEntry.lot_size,
        profit_usd: newEntry.profit_usd,
        rr_ratio: newEntry.rr_ratio,
        outcome: newEntry.outcome,
        session: newEntry.session,
        setup_type: newEntry.setup_type,
        emotions: newEntry.emotions,
        notes: newEntry.notes,
        created_at: newEntry.created_at,
        closed_at: newEntry.closed_at,
      }).select().single();

      if (!error && data) {
        return newEntry;
      }
    } catch (e) {
      // Fallback in-memory
    }
  }

  inMemoryJournal.unshift(newEntry);
  return newEntry;
}

/**
 * TRADING JOURNAL: Delete entry
 */
export async function deleteJournalEntry(id: string): Promise<boolean> {
  const supabase = getSupabase();
  if (supabase) {
    try {
      await supabase.from('trading_journal').delete().eq('id', id);
    } catch (e) {
      // continue to memory
    }
  }
  inMemoryJournal = inMemoryJournal.filter((j) => j.id !== id);
  return true;
}
