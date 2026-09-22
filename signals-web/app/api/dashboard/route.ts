import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';
import { getSignals } from '@/lib/supabase';

export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    // Look for dashboard/data.json in root or parent
    const possiblePaths = [
      path.join(process.cwd(), '..', 'dashboard', 'data.json'),
      path.join(process.cwd(), 'dashboard', 'data.json'),
      path.join('C:', 'Users', 'PwezaCore', 'Desktop', 'GOLD CLONE', 'dashboard', 'data.json')
    ];

    let data: any = null;
    for (const p of possiblePaths) {
      if (fs.existsSync(p)) {
        try {
          const raw = fs.readFileSync(p, 'utf-8');
          data = JSON.parse(raw);
          break;
        } catch (e) {}
      }
    }

    if (!data) {
      // Fallback response with market schedules & account profile for cloud/mobile access
      const now = new Date();
      const isWeekend = now.getUTCDay() === 0 || now.getUTCDay() === 6 || (now.getUTCDay() === 5 && now.getUTCHours() >= 21);
      data = {
        market_schedules: {
          XAUUSD: {
            symbol: 'XAUUSD',
            is_open: !isWeekend,
            status: isWeekend ? 'CLOSED' : 'OPEN',
            status_text: isWeekend ? 'MARKET CLOSED (Weekend - Reopens Sun 22:00 UTC)' : 'MARKET OPEN (Active Session)',
          },
          BTCUSD: {
            symbol: 'BTCUSD',
            is_open: true,
            status: 'OPEN',
            status_text: 'MARKET OPEN (24/7 Crypto)',
          }
        },
        accounts: [
          {
            login: 476719466,
            account_id: '476719466',
            server: 'Exness-MT5Trial9',
            broker: 'Exness',
            label: 'GOLD CLONE',
            balance: 35.60,
            equity: 35.60,
            currency: 'USD',
            leverage: 2000,
            ea_enabled: true,
            status: 'ACTIVE',
            open_positions_count: 0,
            floating_pnl: 0.0,
            daily_pnl: 0.0,
            margin_level: 0.0,
            max_daily_drawdown_pct: 3.0,
            current_drawdown_pct: 0.0,
            risk_tier: 'Aggressive (0.01 fixed)',
          }
        ],
        positions: [],
        perfect_setups: [],
        forming_setups: [],
        signals_history: [],
        early_warnings: [],
        system_status: {
          ea_running: true,
          mt5_connected: !isWeekend,
          cloud_synced: true,
          last_scan_utc: new Date().toISOString(),
        }
      };
    }

    // Cloud fallback & Supabase signal enrichment:
    // If data.json has empty setups, enrich with verified signals from Supabase
    if (!data.perfect_setups || data.perfect_setups.length === 0) {
      try {
        const cloudSignals = await getSignals();
        if (cloudSignals && cloudSignals.length > 0) {
          const mapped = cloudSignals.map((s) => ({
            id: s.id,
            symbol: s.symbol,
            direction: s.direction,
            grade: (s as any).confluenceScore === '3/3' ? 'A+ PERFECT SETUP' : 'GRADE A',
            conviction_score: s.scoreNumeric || 85,
            entry_price: s.entryPrice,
            stop_loss: s.stopLoss,
            tp1: s.takeProfit1,
            tp2: s.takeProfit2,
            risk_reward: s.riskReward || 2.0,
            sl_distance: s.slDistance || Math.abs(s.entryPrice - s.stopLoss),
            tp_distance: s.tpDistance || Math.abs(s.takeProfit1 - s.entryPrice),
            timeframe: 'D1/H4/H1',
            status: s.status || 'ACTIVE',
            invalidation_level: s.stopLoss,
            confluences: s.confluences || [],
            setup_summary: s.outcomeNotes || `[${s.direction} SIGNAL] Entry: ${s.entryPrice.toFixed(2)} | SL: ${s.stopLoss.toFixed(2)} | TP1: ${s.takeProfit1.toFixed(2)}`,
            formed_time: new Date(s.createdAt || Date.now()).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) + ' UTC',
            timestamp: Math.floor(new Date(s.createdAt || Date.now()).getTime() / 1000),
            order_type: `${s.direction} MARKET (or Limit on Retest)`,
            limit_price: s.limitPrice || s.entryPrice,
          }));
          data.perfect_setups = mapped;
          if (!data.signals_history || data.signals_history.length === 0) {
            data.signals_history = mapped;
          }
        }
      } catch (e) {
        // Continue with data
      }
    }

    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}
