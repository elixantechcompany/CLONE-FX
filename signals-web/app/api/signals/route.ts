import { NextRequest, NextResponse } from 'next/server';
import { getSignals, updateSignalStatus } from '@/lib/supabase';

export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    const signals = await getSignals();
    return NextResponse.json({ signals });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}

export async function PATCH(req: NextRequest) {
  try {
    const body = await req.json();
    const { id, status, outcomeNotes } = body;

    if (!id || !status) {
      return NextResponse.json({ error: 'Missing id or status' }, { status: 400 });
    }

    const updated = await updateSignalStatus(id, status, outcomeNotes);
    return NextResponse.json({ success: updated });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}
