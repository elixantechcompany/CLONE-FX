import { NextRequest, NextResponse } from 'next/server';
import { fetchMarketDataBundle } from '@/lib/marketData';
import { runConfluenceScan } from '@/lib/confluenceEngine';
import { saveSignal } from '@/lib/supabase';
import { sendTelegramSignalAlert } from '@/lib/telegram';
import { ConfluenceSignal } from '@/lib/types';

export const dynamic = 'force-dynamic';

export async function POST(req: NextRequest) {
  const CRON_SECRET = process.env.CRON_SECRET;
  const authHeader = req.headers.get('authorization');

  // If called externally with an Authorization header, validate against CRON_SECRET
  if (authHeader && CRON_SECRET) {
    if (authHeader !== `Bearer ${CRON_SECRET}`) {
      return NextResponse.json({ error: 'Unauthorized scan invocation' }, { status: 401 });
    }
  }

  // Market hours check
  const now = new Date();
  const day = now.getUTCDay(); // 0 is Sun, 6 is Sat, 5 is Fri
  const hour = now.getUTCHours();
  const isXauClosed = day === 6 || (day === 5 && hour >= 21) || (day === 0 && hour < 22);

  const scanResults: any[] = [];

  // Report XAUUSD status
  if (isXauClosed) {
    scanResults.push({
      symbol: 'XAUUSD',
      signalFound: false,
      marketStatus: 'CLOSED_WEEKEND',
      message: 'Gold market closed over weekend. Polling safely paused until Sun 22:00 UTC.',
    });
  }

  // Symbols active for scanning
  const activeSymbols: ('XAUUSD' | 'BTCUSD')[] = isXauClosed ? ['BTCUSD'] : ['XAUUSD', 'BTCUSD'];

  for (const sym of activeSymbols) {
    try {
      const bundle = await fetchMarketDataBundle(sym);
      const signal = runConfluenceScan(bundle);

      if (signal) {
        // Map to strict BUY or SELL
        const isLong = signal.direction === 'BUY' || signal.direction === 'LONG';
        signal.direction = isLong ? 'BUY' : 'SELL';

        // Save to Supabase
        const saved = await saveSignal(signal);

        // Dispatch alert to Telegram if configured
        await sendTelegramSignalAlert(saved);

        scanResults.push({
          symbol: sym,
          signalFound: true,
          marketStatus: 'OPEN',
          signal: saved,
        });
      } else {
        scanResults.push({
          symbol: sym,
          signalFound: false,
          marketStatus: 'OPEN',
          message: 'TradingView & MT5 engine analyzed D1/4H/1H holding structure. No 3/3 swing setup triggered.',
        });
      }
    } catch (err: any) {
      console.error(`[ScanAPI] Error scanning ${sym}:`, err);
      scanResults.push({
        symbol: sym,
        signalFound: false,
        error: err.message || 'Data feed timeout',
      });
    }
  }

  return NextResponse.json({
    success: true,
    timestamp: new Date().toISOString(),
    market_schedules: {
      XAUUSD: isXauClosed ? 'CLOSED (Weekend)' : 'OPEN',
      BTCUSD: 'OPEN (24/7)',
    },
    results: scanResults,
  });
}

// Allow GET for easy manual trigger or health check
export async function GET(req: NextRequest) {
  return POST(req);
}
