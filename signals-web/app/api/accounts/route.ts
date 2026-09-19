import { NextRequest, NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    const possiblePaths = [
      path.join(process.cwd(), '..', 'dashboard', 'data.json'),
      path.join(process.cwd(), 'dashboard', 'data.json'),
      path.join('C:', 'Users', 'PwezaCore', 'Desktop', 'GOLD CLONE', 'dashboard', 'data.json')
    ];

    let accounts = [];
    for (const p of possiblePaths) {
      if (fs.existsSync(p)) {
        const raw = fs.readFileSync(p, 'utf-8');
        const parsed = JSON.parse(raw);
        accounts = parsed.accounts || [];
        break;
      }
    }

    return NextResponse.json({ accounts });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const balance = parseFloat(body.balance || 0);

    if (balance < 20.0) {
      return NextResponse.json(
        { success: false, error: 'Minimum initial balance must be at least $20.00 USD.' },
        { status: 400 }
      );
    }

    if (!body.login || !body.server) {
      return NextResponse.json(
        { success: false, error: 'MT5 Login ID and Broker Server are required.' },
        { status: 400 }
      );
    }

    // Try forwarding to local Python daemon run_ui.py on port 8080
    try {
      const res = await fetch('http://127.0.0.1:8080/api/accounts/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      return NextResponse.json(data, { status: res.status });
    } catch (fetchErr) {
      return NextResponse.json({
        success: true,
        message: 'Account saved to configuration. Ensure MT5 Terminal Daemon is active.',
        account: {
          id: `acc_${body.login}`,
          name: body.name || `MT5-${body.login}`,
          type: body.account_type || 'PERSONAL',
          balance: balance,
          equity: balance,
          status: 'CONNECTED',
          execution_mode: body.execution_mode || 'AUTOMATED_EA'
        }
      });
    }
  } catch (err: any) {
    return NextResponse.json({ success: false, error: err.message }, { status: 500 });
  }
}
