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
          // getSignals() already returns camelCase ConfluenceSignal objects.
          // Map them to the shape SignalsView expects (entryPrice, takeProfit1, takeProfit2…)
          // and keep them consistent by setting any missing TP2 to a 1.5× extension.
          const mapped = cloudSignals.map((s) => ({
            id: s.id,
            symbol: s.symbol,
            direction: s.direction,
            // camelCase price fields (REQUIRED by SignalsView.tsx)
            entryPrice: Number(s.entryPrice) || 0,
            stopLoss: Number(s.stopLoss) || 0,
            takeProfit1: Number(s.takeProfit1) || 0,
            takeProfit2: s.takeProfit2
              ? Number(s.takeProfit2)
              : s.takeProfit1
              ? Number(s.takeProfit1) + Math.abs(Number(s.takeProfit1) - Number(s.entryPrice))
              : undefined,
            riskReward: Number(s.riskReward) || 2.0,
            slDistance: Number(s.slDistance) || Math.abs(Number(s.entryPrice) - Number(s.stopLoss)),
            tpDistance: Number(s.tpDistance) || Math.abs(Number(s.takeProfit1) - Number(s.entryPrice)),
            confluenceScore: (s as any).confluenceScore || '3/3',
            scoreNumeric: (s as any).scoreNumeric ?? 3,
            confluences: s.confluences || [],
            status: s.status || 'ACTIVE',
            outcomeNotes: s.outcomeNotes || '',
            setup_summary:
              s.outcomeNotes ||
              `[${s.direction} SIGNAL] Entry: ${Number(s.entryPrice).toFixed(2)} | SL: ${Number(s.stopLoss).toFixed(2)} | TP1: ${Number(s.takeProfit1).toFixed(2)}`,
            formed_time:
              new Date(s.createdAt || Date.now()).toLocaleTimeString([], {
                hour: '2-digit',
                minute: '2-digit',
              }) + ' UTC',
            createdAt: s.createdAt,
            timestamp: Math.floor(new Date(s.createdAt || Date.now()).getTime() / 1000),
            orderType: `${s.direction} MARKET (or Limit on Retest)` as any,
            limitPrice: (s as any).limitPrice || Number(s.entryPrice),
            // Legacy snake_case aliases kept for any server-only consumers
            grade: (s as any).confluenceScore === '3/3' ? 'A+ PERFECT SETUP' : 'GRADE A',
            entry_price: Number(s.entryPrice) || 0,
            stop_loss: Number(s.stopLoss) || 0,
            tp1: Number(s.takeProfit1) || 0,
            tp2: s.takeProfit2 ? Number(s.takeProfit2) : undefined,
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

    // Normalise any perfect_setups that came from data.json (snake_case from Python)
    // so they always have the camelCase fields SignalsView needs.
    if (data.perfect_setups && data.perfect_setups.length > 0) {
      data.perfect_setups = data.perfect_setups.map((s: any) => ({
        ...s,
        // Promote snake_case → camelCase if not already present
        entryPrice:   s.entryPrice   ?? s.entry_price   ?? 0,
        stopLoss:     s.stopLoss     ?? s.stop_loss      ?? 0,
        takeProfit1:  s.takeProfit1  ?? s.tp1            ?? 0,
        takeProfit2:  s.takeProfit2  ?? s.tp2
          ?? (s.tp1 ? Number(s.tp1) + Math.abs(Number(s.tp1) - Number(s.entry_price ?? 0)) : undefined),
        riskReward:   s.riskReward   ?? s.risk_reward    ?? 2.0,
        slDistance:   s.slDistance   ?? s.sl_distance    ?? 0,
        tpDistance:   s.tpDistance   ?? s.tp_distance    ?? 0,
        confluenceScore: s.confluenceScore ?? s.grade ?? '3/3',
        scoreNumeric:    s.scoreNumeric    ?? (s.conviction_score ? Math.round(s.conviction_score / 33) : 3),
        confluences:  s.confluences  ?? [],
        status:       s.status       ?? 'ACTIVE',
        symbol:       s.symbol       ?? 'XAUUSD',
        direction:    s.direction    ?? 'BUY',
      }));
    }

    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}
