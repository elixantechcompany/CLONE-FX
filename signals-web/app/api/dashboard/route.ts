import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    // Look for dashboard/data.json in root or parent
    const possiblePaths = [
      path.join(process.cwd(), '..', 'dashboard', 'data.json'),
      path.join(process.cwd(), 'dashboard', 'data.json'),
      path.join('C:', 'Users', 'PwezaCore', 'Desktop', 'GOLD CLONE', 'dashboard', 'data.json')
    ];

    let data = null;
    for (const p of possiblePaths) {
      if (fs.existsSync(p)) {
        const raw = fs.readFileSync(p, 'utf-8');
        data = JSON.parse(raw);
        break;
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
            server: 'Exness-Real10',
            broker: 'Exness',
            label: 'GOLD CLONE',
            balance: 36.58,
            equity: 36.65,
            currency: 'USD',
            leverage: 200,
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
        early_warnings: [],
        system_status: {
          ea_running: true,
          mt5_connected: !isWeekend,
          cloud_synced: true,
          last_scan_utc: new Date().toISOString(),
        }
      };
    }

    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}
