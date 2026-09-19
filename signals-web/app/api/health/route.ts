import { NextResponse } from 'next/server';

export const runtime = 'edge';

export async function GET() {
  return NextResponse.json({
    status: 'ok',
    service: 'GOLD CLONE FX — Institutional Trading Terminal',
    version: '1.0.0',
    timestamp: new Date().toISOString(),
    uptime_ms: Date.now(),
  });
}
