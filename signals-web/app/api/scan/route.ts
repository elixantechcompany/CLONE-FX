import { NextRequest, NextResponse } from 'next/server';
import { fetchMarketDataBundle } from '@/lib/marketData';
import { runConfluenceScan } from '@/lib/confluenceEngine';
import { saveSignal } from '@/lib/supabase';
import { sendTelegramSignalAlert } from '@/lib/telegram';
import { ConfluenceSignal } from '@/lib/types';

export const dynamic = 'force-dynamic';

export async function POST(req: NextRequest) {
  const CRON_SECRET = process.env.CRON_SECRET;

  // Validate Authorization header if CRON_SECRET is set
  if (CRON_SECRET) {
    const authHeader = req.headers.get('authorization');
    if (!authHeader || authHeader !== `Bearer ${CRON_SECRET}`) {
      return NextResponse.json({ error: 'Unauthorized scan invocation' }, { status: 401 });
    }
  }

  const symbols: ('XAUUSD' | 'BTCUSD')[] = ['XAUUSD', 'BTCUSD'];
  const scanResults: {
    symbol: string;
    signalFound: boolean;
    signal?: ConfluenceSignal;
  }[] = [];

  for (const sym of symbols) {
    try {
      const bundle = await fetchMarketDataBundle(sym);
      const signal = runConfluenceScan(bundle);

      if (signal) {
        // Save to Supabase
        const saved = await saveSignal(signal);

        // Dispatch alert to Telegram
        await sendTelegramSignalAlert(saved);

        scanResults.push({
          symbol: sym,
          signalFound: true,
          signal: saved,
        });
      } else {
        scanResults.push({
          symbol: sym,
          signalFound: false,
        });
      }
    } catch (err: any) {
      console.error(`[ScanAPI] Error scanning ${sym}:`, err);
      scanResults.push({
        symbol: sym,
        signalFound: false,
      });
    }
  }

  return NextResponse.json({
    success: true,
    timestamp: new Date().toISOString(),
    results: scanResults,
  });
}

// Allow GET for easy manual trigger or status check
export async function GET(req: NextRequest) {
  return POST(req);
}
