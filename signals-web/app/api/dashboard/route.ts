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
      // Fallback response with market schedules
      const now = new Date();
      const isWeekend = now.getUTCDay() === 0 || now.getUTCDay() === 6 || (now.getUTCDay() === 5 && now.getUTCHours() >= 21);
      data = {
        market_schedules: {
          XAUUSD: {
            symbol: 'XAUUSD',
            is_open: !isWeekend,
            status: isWeekend ? 'CLOSED' : 'OPEN',
            status_text: isWeekend ? 'MARKET CLOSED (Weekend - Reopens Sun 22:00 UTC)' : 'MARKET OPEN',
          },
          BTCUSD: {
            symbol: 'BTCUSD',
            is_open: true,
            status: 'OPEN',
            status_text: 'MARKET OPEN (24/7 Crypto)',
          }
        },
        accounts: [],
        positions: [],
        perfect_setups: [],
        forming_setups: [],
        early_warnings: [],
      };
    }

    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}
