import { NextRequest, NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

export const dynamic = 'force-dynamic';

export async function GET() {
  const possiblePaths = [
    path.join(process.cwd(), '..', 'dashboard', 'data.json'),
    path.join(process.cwd(), 'dashboard', 'data.json'),
    path.join('C:', 'Users', 'PwezaCore', 'Desktop', 'GOLD CLONE', 'dashboard', 'data.json'),
  ];

  let algoTradingActive = false;
  for (const p of possiblePaths) {
    if (fs.existsSync(p)) {
      try {
        const raw = fs.readFileSync(p, 'utf-8');
        const parsed = JSON.parse(raw);
        if (parsed.master_switch) {
          algoTradingActive = !!parsed.master_switch.algo_trading_active;
        }
        break;
      } catch (e) {}
    }
  }

  return NextResponse.json({
    success: true,
    algo_trading_active: algoTradingActive,
    status: algoTradingActive ? 'RUNNING' : 'STOPPED'
  });
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json().catch(() => ({}));
    const requestedState = body.active !== undefined ? body.active : (body.enabled !== undefined ? body.enabled : undefined);

    const possiblePaths = [
      path.join(process.cwd(), '..', 'dashboard', 'data.json'),
      path.join(process.cwd(), 'dashboard', 'data.json'),
      path.join('C:', 'Users', 'PwezaCore', 'Desktop', 'GOLD CLONE', 'dashboard', 'data.json'),
    ];

    let newState = true;

    for (const p of possiblePaths) {
      if (fs.existsSync(p)) {
        try {
          const raw = fs.readFileSync(p, 'utf-8');
          const parsed = JSON.parse(raw);
          const currentState = parsed.master_switch ? !!parsed.master_switch.algo_trading_active : false;
          newState = requestedState !== undefined ? !!requestedState : !currentState;

          parsed.master_switch = {
            primary_switch: 'MT5_NATIVE_ALGO_TRADING',
            algo_trading_active: newState,
          };

          fs.writeFileSync(p, JSON.stringify(parsed, null, 2), 'utf-8');
          break;
        } catch (e) {
          console.warn('[EA Toggle API] Failed updating data.json:', e);
        }
      }
    }

    // Also notify python backend daemon if running on port 8080
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 1500);
      await fetch('http://127.0.0.1:8080/api/ea/toggle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: controller.signal,
        body: JSON.stringify({ active: newState }),
      });
      clearTimeout(timeoutId);
    } catch (e) {}

    return NextResponse.json({
      success: true,
      algo_trading_active: newState,
      status: newState ? 'RUNNING' : 'STOPPED',
      message: newState ? 'EA started successfully (Auto-Trading ON)' : 'EA stopped successfully (Auto-Trading OFF)'
    });
  } catch (err: any) {
    return NextResponse.json({ success: false, error: err.message }, { status: 500 });
  }
}
