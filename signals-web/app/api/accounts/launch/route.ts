import { NextRequest, NextResponse } from 'next/server';
import { spawn } from 'child_process';
import fs from 'fs';
import path from 'path';

export const dynamic = 'force-dynamic';

function findMT5Executable(): string | null {
  const candidates = [
    'C:\\Program Files\\MetaTrader 5\\terminal64.exe',
    'C:\\Program Files\\Exness MT5\\terminal64.exe',
    'C:\\Program Files\\Exness MetaTrader 5\\terminal64.exe',
    'C:\\Program Files\\FTMO MetaTrader 5\\terminal64.exe',
    'C:\\Program Files\\BrightFunded MT5\\terminal64.exe',
    'C:\\Program Files\\MetaTrader 5 Terminal\\terminal64.exe',
    path.join(process.env.LOCALAPPDATA || '', 'Programs', 'MetaTrader 5', 'terminal64.exe'),
  ];

  for (const c of candidates) {
    if (fs.existsSync(c)) {
      return c;
    }
  }
  return null;
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json().catch(() => ({}));
    const accountId = body.accountId || 'account_d';

    // 1. First try python daemon IPC
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 1500);
      const res = await fetch('http://127.0.0.1:8080/api/terminals/launch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ account_id: accountId }),
        signal: controller.signal,
      });
      clearTimeout(timeoutId);

      if (res.ok) {
        const data = await res.json();
        if (data.success) {
          return NextResponse.json({
            success: true,
            message: `MT5 Terminal launched via daemon for ${accountId}`,
            source: 'PYTHON_DAEMON',
          });
        }
      }
    } catch (e) {
      // Fallback to direct spawn
    }

    // 2. Direct local system spawn
    const exePath = findMT5Executable();
    if (!exePath) {
      return NextResponse.json(
        {
          success: false,
          error: 'MetaTrader 5 (terminal64.exe) not found in standard installation directories.',
        },
        { status: 404 }
      );
    }

    const workingDir = path.dirname(exePath);
    const proc = spawn(exePath, [], {
      cwd: workingDir,
      detached: true,
      stdio: 'ignore',
    });
    proc.unref();

    return NextResponse.json({
      success: true,
      message: `MetaTrader 5 terminal launched directly from ${exePath}`,
      path: exePath,
      source: 'DIRECT_SPAWN',
    });
  } catch (err: any) {
    return NextResponse.json(
      { success: false, error: err.message || 'Failed to launch MT5 terminal' },
      { status: 500 }
    );
  }
}
