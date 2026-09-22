import { NextRequest, NextResponse } from 'next/server';
import { supabase } from '@/lib/supabase';

// GET latest signals
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const limit = parseInt(searchParams.get('limit') || '10');

    const { data, error } = await supabase
      .from('trading_signals')
      .select('*')
      .eq('is_valid', true)
      .order('created_at', { ascending: false })
      .limit(limit);

    if (error) throw error;

    // Add freshness information to each signal
    const signalsWithFreshness = data?.map(signal => {
      const now = new Date();
      const expiresAt = new Date(signal.expires_at);
      const createdAt = new Date(signal.created_at);
      
      const ageSeconds = (now.getTime() - createdAt.getTime()) / 1000;
      const timeUntilExpiry = (expiresAt.getTime() - now.getTime()) / 1000;
      const isFresh = timeUntilExpiry > 0;
      
      // Calculate opacity based on freshness
      const totalLifetime = 5 * 60; // 5 minutes in seconds
      const remainingRatio = Math.max(0, timeUntilExpiry / totalLifetime);
      const opacity = 0.3 + (0.7 * remainingRatio);
      
      // Format age text
      let ageText;
      if (ageSeconds < 60) {
        ageText = `${Math.floor(ageSeconds)}s ago`;
      } else if (ageSeconds < 3600) {
        ageText = `${Math.floor(ageSeconds / 60)}m ago`;
      } else {
        ageText = `${Math.floor(ageSeconds / 3600)}h ago`;
      }

      return {
        ...signal,
        freshness: {
          is_fresh: isFresh,
          age_seconds: ageSeconds,
          age_text: ageText,
          opacity: opacity,
          time_until_expiry: timeUntilExpiry
        }
      };
    }) || [];

    return NextResponse.json({ signals: signalsWithFreshness });
  } catch (error) {
    console.error('Error fetching signals:', error);
    return NextResponse.json({ error: 'Failed to fetch signals' }, { status: 500 });
  }
}

// POST generate new signal (would be called by Python engine)
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { 
      symbol, 
      direction, 
      entry_price, 
      stop_loss, 
      take_profit, 
      risk_reward_ratio,
      h4_ema50,
      h1_ema50,
      h4_price_above_ema,
      h1_price_above_ema,
      atr_value
    } = body;

    // Validate required fields
    if (!symbol || !direction || !entry_price || !stop_loss || !take_profit) {
      return NextResponse.json({ error: 'Missing required fields' }, { status: 400 });
    }

    const signal_time = new Date().toISOString();
    const expires_at = new Date(Date.now() + 5 * 60 * 1000).toISOString(); // 5 minutes from now

    const { data, error } = await supabase
      .from('trading_signals')
      .insert({
        symbol,
        direction,
        entry_price,
        stop_loss,
        take_profit,
        risk_reward_ratio,
        signal_time,
        expires_at,
        h4_ema50,
        h1_ema50,
        h4_price_above_ema,
        h1_price_above_ema,
        atr_value,
        is_valid: true
      })
      .select()
      .single();

    if (error) throw error;

    return NextResponse.json({ signal: data }, { status: 201 });
  } catch (error) {
    console.error('Error creating signal:', error);
    return NextResponse.json({ error: 'Failed to create signal' }, { status: 500 });
  }
}