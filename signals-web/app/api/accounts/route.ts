import { NextRequest, NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';
import { createClient } from '@supabase/supabase-js';

export const dynamic = 'force-dynamic';

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL || 'https://xeckbeavsvyoporldjzm.supabase.co';
const SUPABASE_SERVICE_ROLE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY || '';

// Blacklisted fake accounts that user never added
const FAKE_ACCOUNT_IDS = new Set(['account_a', 'account_b', 'account_c']);

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
        try {
          const raw = fs.readFileSync(p, 'utf-8');
          const parsed = JSON.parse(raw);
          accounts = parsed.accounts || [];
          break;
        } catch (e) {}
      }
    }

    // Filter out fake demo accounts user never added
    accounts = accounts.filter((a: any) => !FAKE_ACCOUNT_IDS.has(String(a.id || a.account_id || '').toLowerCase()));

    // If local json is empty, try reading from Supabase accounts_overview
    if (accounts.length === 0 && SUPABASE_SERVICE_ROLE_KEY) {
      try {
        const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, {
          auth: { persistSession: false },
        });
        const { data } = await supabase.from('accounts_overview').select('*');
        if (data && data.length > 0) {
          accounts = data
            .filter((a: any) => !FAKE_ACCOUNT_IDS.has(String(a.account_id || '').toLowerCase()))
            .map((a) => ({
              id: a.account_id,
              name: a.name,
              type: a.account_type === 'DEMO' ? 'DEMO' : 'REAL',
              balance: parseFloat(a.balance || 0),
              equity: parseFloat(a.equity || a.balance || 0),
              margin: 0,
              free_margin: parseFloat(a.balance || 0),
              profit: parseFloat(a.daily_pnl || 0),
              drawdown_pct: parseFloat(a.daily_dd_pct || 0),
              status: a.status || 'CONNECTED',
              execution_mode: a.execution_mode || 'AUTOMATED_EA',
            }));
        }
      } catch (e) {}
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

    const accId = `acc_${String(body.login).trim()}`;
    const accName = body.name || `MT5-${body.login}`;
    // Standard normal MT5 account types: REAL or DEMO
    const accType = body.account_type === 'DEMO' ? 'DEMO' : 'REAL';
    const execMode = body.execution_mode || 'AUTOMATED_EA';

    const newAccountObj = {
      id: accId,
      account_id: accId,
      name: accName,
      type: accType,
      account_type: accType,
      balance: balance,
      equity: balance,
      margin: 0,
      free_margin: balance,
      profit: 0.0,
      daily_pnl: 0.0,
      daily_dd_pct: 0.0,
      drawdown_pct: 0.0,
      status: 'CONNECTED',
      execution_mode: execMode,
      login: String(body.login).trim(),
      server: String(body.server).trim(),
      last_updated: new Date().toISOString()
    };

    // 1. Update dashboard/data.json directly for instant UI reflection
    const possiblePaths = [
      path.join(process.cwd(), '..', 'dashboard', 'data.json'),
      path.join(process.cwd(), 'dashboard', 'data.json'),
      path.join('C:', 'Users', 'PwezaCore', 'Desktop', 'GOLD CLONE', 'dashboard', 'data.json')
    ];

    for (const p of possiblePaths) {
      if (fs.existsSync(p)) {
        try {
          const raw = fs.readFileSync(p, 'utf-8');
          const parsed = JSON.parse(raw);
          const currentAccounts = (parsed.accounts || []).filter((a: any) => !FAKE_ACCOUNT_IDS.has(String(a.id || a.account_id || '').toLowerCase()));
          // Replace or add
          const updated = [
            ...currentAccounts.filter((a: any) => a.id !== accId && a.account_id !== accId),
            newAccountObj
          ];
          parsed.accounts = updated;
          fs.writeFileSync(p, JSON.stringify(parsed, null, 2), 'utf-8');
        } catch (e) {
          console.warn('[AccountsAPI] Failed updating data.json:', e);
        }
      }
    }

    // 2. Sync to Supabase accounts_overview table
    if (SUPABASE_SERVICE_ROLE_KEY) {
      try {
        const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, {
          auth: { persistSession: false },
        });
        await supabase.from('accounts_overview').upsert({
          account_id: accId,
          name: accName,
          account_type: accType,
          balance: balance,
          equity: balance,
          daily_pnl: 0.0,
          daily_dd_pct: 0.0,
          max_dd_limit: balance * 0.10,
          status: 'CONNECTED',
          last_updated: new Date().toISOString()
        });
      } catch (e) {
        console.warn('[AccountsAPI] Supabase sync notice:', e);
      }
    }

    // 3. Forward to Python background daemon if listening on port 8080 (non-blocking with timeout)
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 2000);
      await fetch('http://127.0.0.1:8080/api/accounts/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: controller.signal,
        body: JSON.stringify({
          name: accName,
          account_type: accType,
          balance: balance,
          login: String(body.login).trim(),
          password: String(body.password || '').trim(),
          server: String(body.server).trim(),
          execution_mode: execMode,
          mode: 'INDEPENDENT'
        }),
      });
      clearTimeout(timeoutId);
    } catch (e) {}

    return NextResponse.json({
      success: true,
      message: `Account ${accName} ($${balance.toFixed(2)}) connected successfully!`,
      account: newAccountObj
    });
  } catch (err: any) {
    return NextResponse.json({ success: false, error: err.message || 'Failed to add account' }, { status: 500 });
  }
}

export async function DELETE(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const id = searchParams.get('id');

    if (!id) {
      return NextResponse.json({ success: false, error: 'Account ID is required' }, { status: 400 });
    }

    const possiblePaths = [
      path.join(process.cwd(), '..', 'dashboard', 'data.json'),
      path.join(process.cwd(), 'dashboard', 'data.json'),
      path.join('C:', 'Users', 'PwezaCore', 'Desktop', 'GOLD CLONE', 'dashboard', 'data.json')
    ];

    for (const p of possiblePaths) {
      if (fs.existsSync(p)) {
        try {
          const raw = fs.readFileSync(p, 'utf-8');
          const parsed = JSON.parse(raw);
          const filtered = (parsed.accounts || []).filter((a: any) => a.id !== id && a.account_id !== id);
          parsed.accounts = filtered;
          fs.writeFileSync(p, JSON.stringify(parsed, null, 2), 'utf-8');
        } catch (e) {}
      }
    }

    // Forward to Python daemon
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 1500);
      await fetch('http://127.0.0.1:8080/api/accounts/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: controller.signal,
        body: JSON.stringify({ account_id: id }),
      });
      clearTimeout(timeoutId);
    } catch (e) {}

    // Delete from Supabase if configured
    if (SUPABASE_SERVICE_ROLE_KEY) {
      try {
        const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, {
          auth: { persistSession: false },
        });
        await supabase.from('accounts_overview').delete().eq('account_id', id);
      } catch (e) {}
    }

    return NextResponse.json({ success: true, message: `Account ${id} removed.` });
  } catch (err: any) {
    return NextResponse.json({ success: false, error: err.message }, { status: 500 });
  }
}
